#!/usr/bin/env python3
"""Check the compatibility chain, print the CI matrix, or inspect two emulator checkouts.

    python3 scripts/compatibility.py --check
    python3 scripts/compatibility.py --matrix
    python3 scripts/compatibility.py --diff ../.scratch/ministack-src-1543 ../.scratch/ministack-src-1544

`--diff` is the source check, not the data source: it hashes every service and core
module at the two checkouts, then lists the operation names a changed service gained
or lost. `compatibility.json` is still curated — a generic extractor cannot tell an
operation from a response element or a field name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "control"))

from compatibility import Compatibility, load, split, version_tuple  # noqa: E402

NAME = re.compile(r"^[A-Z][A-Za-z0-9]+$")
# A response wrapper or an exception class is named like an operation and is not one.
NOT_OPERATION = re.compile(r"(Response|Result|Exception)$")


def check(compat: Compatibility) -> list[str]:
    """Everything the data must satisfy before the gate, matrix or pages may trust it."""
    problems: list[str] = []
    if not compat.versions:
        return ["no versions are declared"]
    if len(compat.versions) != compat.window:
        problems.append(
            f"window is {compat.window}, but {len(compat.versions)} versions are declared"
        )
    parsed = [version_tuple(version) for version in compat.versions]
    if any(item is None for item in parsed):
        problems.append("a version is not MAJOR.MINOR.PATCH")
    elif parsed != sorted(parsed) or len(set(parsed)) != len(parsed):
        problems.append("versions are not sorted and unique")
    if compat.ceiling != compat.versions[-1]:
        problems.append(f"ceiling is {compat.ceiling}, but the newest version is {compat.versions[-1]}")
    if not compat.services:
        problems.append("no services are declared")

    added: set[tuple[str, str]] = set()
    removed: set[tuple[str, str]] = set()
    for version in compat.versions[1:]:
        delta = compat.deltas.get(version)
        if delta is None:
            continue
        for field in ("added", "advertised", "removed"):
            entries = delta.get(field) or []
            if not isinstance(entries, list):
                problems.append(f"{version}: {field} is not a list")
                continue
            for entry in entries:
                if not isinstance(entry, str) or ":" not in entry:
                    problems.append(f"{version}: {entry!r} is not service:Operation")
                    continue
                service, operation = split(entry)
                if service not in compat.services:
                    problems.append(f"{version}: {service} is not a declared service")
                if not NAME.match(operation):
                    problems.append(f"{version}: {entry!r} is not an operation name")
                elif NOT_OPERATION.search(operation):
                    problems.append(f"{version}: {entry!r} names a response or an exception")
                if field == "added":
                    if (service, operation) in added:
                        problems.append(f"{version}: {entry!r} is already declared added")
                    added.add((service, operation))
                if field == "removed":
                    if (service, operation) in removed:
                        problems.append(f"{version}: {entry!r} is already declared removed")
                    removed.add((service, operation))
    for entry in sorted(added & removed):
        problems.append(f"{entry[0]}:{entry[1]} is declared added and removed in one window")
    return problems


def matrix(compat: Compatibility) -> list[str]:
    """The GitHub Actions matrix: every supported tag."""
    return [f"v{version}" for version in compat.versions]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path, prefix: str) -> dict[str, str]:
    base = root / prefix
    if not base.is_dir():
        return {}
    found = {}
    for path in sorted(base.rglob("*.py")):
        found[path.relative_to(root).as_posix()] = digest(path)
    return found


def routes(source: str) -> set[str]:
    """Path literals: a REST service (Lambda's EventInvokeConfig) names no operation string."""
    return {path for path in re.findall(r'"(/[^"\s]*)"', source) if len(path) > 1}


def operations(source: str) -> set[str]:
    """Operation-looking literals; a report for a human, never the data source."""
    verbs = re.compile(
        r"^(Create|Delete|Describe|Get|List|Put|Update|Start|Stop|Associate|"
        r"Disassociate|Enable|Disable|Modify|Register|Deregister|Search|Add|Remove|"
        r"Set|Revoke|Authorize|Attach|Detach|Import|Replace|Reset|Allocate|Release|"
        r"Cancel|Complete|Abort|Upload|Restore|Copy|Publish|Subscribe|Unsubscribe|"
        r"Tag|Untag|Purchase|Accept|Reject|Failover|Reboot|Terminate|Run|Send|"
        r"Receive|Change|Purge|Execute|Invoke|Validate|Test|Rotate|Signal)[A-Za-z0-9]+$"
    )
    return {
        name
        for name in re.findall(r'"([A-Z][A-Za-z0-9]+)"', source)
        if verbs.match(name) and not NOT_OPERATION.search(name)
    }


def diff(old: Path, new: Path) -> int:
    """Changed service and core modules between two checkouts, and the names that moved."""
    for prefix in ("ministack/services", "ministack/core"):
        before, after = tree(old, prefix), tree(new, prefix)
        changed = sorted(path for path in set(before) & set(after) if before[path] != after[path])
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        print(f"== {prefix}: {len(changed)} changed, {len(added)} added, {len(removed)} removed")
        for path in changed:
            source_old = (old / path).read_text(encoding="utf-8")
            source_new = (new / path).read_text(encoding="utf-8")
            gained = sorted(operations(source_new) - operations(source_old))
            lost = sorted(operations(source_old) - operations(source_new))
            paths = sorted(routes(source_new) - routes(source_old))
            gone = sorted(routes(source_old) - routes(source_new))
            label = "direct" if prefix.endswith("services") else "indirect"
            note = ""
            if gained:
                note += f" +{gained}"
            if lost:
                note += f" -{lost}"
            if paths:
                note += f" routes+{paths}"
            if gone:
                note += f" routes-{gone}"
            print(f"  [{label}] {path}:{note or ' no operation name moved'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate compatibility.json")
    parser.add_argument("--matrix", action="store_true", help="print the tag matrix as JSON")
    parser.add_argument("--diff", nargs=2, metavar=("OLD", "NEW"), help="inspect two checkouts")
    args = parser.parse_args()

    if args.diff:
        return diff(Path(args.diff[0]).resolve(), Path(args.diff[1]).resolve())

    compat = load()
    if args.matrix:
        print(json.dumps(matrix(compat)))
        return 0

    problems = check(compat)
    if problems:
        for problem in problems:
            print(f"compatibility: {problem}", file=sys.stderr)
        return 1
    added = sum(len(compat.added(version)) for version in compat.versions)
    print(
        f"compatibility: {compat.ceiling} ceiling, {len(compat.versions)} versions, "
        f"{added} operation(s) added across the window"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
