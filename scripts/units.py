#!/usr/bin/env python3
"""The units one release must keep in step: the tag, the changelog, and the docs.

A release is one event that touches several artefacts. This script names them and
refuses a release where one has been forgotten, which is how the docs site, the
image and the tag stop drifting apart.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every artefact a release names; `local` units are checked here, the rest are remote.
UNITS = (
    ("git tag", "vX.Y.Z"),
    ("CHANGELOG.md", "## [vX.Y.Z]"),
    ("site/versions.json", "X.Y.Z"),
    ("site/versioned_docs/version-X.Y.Z", "the frozen pages"),
    ("image tag", "X.Y.Z in GHCR"),
    ("release assets", "SBOM, SHA256SUMS, IMAGE-DIGEST"),
)


def changelog_has(root: Path, version: str) -> bool:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    return bool(re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE))


def docs_versions(root: Path) -> list[str]:
    path = root / "site" / "versions.json"
    if not path.is_file():
        return []
    try:
        return [str(entry) for entry in json.loads(path.read_text(encoding="utf-8"))]
    except ValueError:
        return []


def pages(directory: Path) -> set[str]:
    """Every file under a docs directory, named relative to it."""
    if not directory.is_dir():
        return set()
    return {
        str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()
    }


def docs_mirrored(root: Path, bare: str) -> bool:
    """The frozen version is the working docs copied out, not merely a directory."""
    working = pages(root / "site" / "docs")
    frozen = pages(root / "site" / "versioned_docs" / f"version-{bare}")
    return bool(working) and frozen == working


def tag_exists(root: Path, version: str) -> bool:
    found = subprocess.run(
        ["git", "tag", "--list", version], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    return bool(found)


COMPOSE_FILES = ("docker-compose.yml", "docker-compose.all.yml")


def compose_tags(root: Path) -> dict[str, str]:
    """Each compose file's pinned image version, so both stacks move with the release."""
    tags = {}
    for name in COMPOSE_FILES:
        path = root / name
        if not path.is_file():
            continue
        found = re.search(
            r"ghcr\.io/[^:\s]+/emuplane:(\d+\.\d+\.\d+)", path.read_text(encoding="utf-8")
        )
        tags[name] = found.group(1) if found else ""
    return tags


def report(root: Path, version: str, number: str = "") -> list[dict]:
    """Each unit with whether it is present; `version` is the tag, `number` its bare form."""
    bare = number or version.lstrip("v")
    docs = docs_versions(root)
    tags = compose_tags(root)
    return [
        {"unit": "git tag", "expected": version, "present": tag_exists(root, version)},
        {"unit": "CHANGELOG.md", "expected": f"## [{version}]", "present": changelog_has(root, version)},
        {"unit": "site/versions.json", "expected": bare, "present": bare in docs},
        {
            "unit": "versioned docs",
            "expected": f"site/versioned_docs/version-{bare} mirrors site/docs",
            "present": docs_mirrored(root, bare),
        },
        {
            "unit": "compose image tags",
            "expected": f"every compose file at {bare}",
            "present": bool(tags) and set(tags.values()) == {bare},
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the tag the release is, e.g. v0.2.0")
    parser.add_argument("--root", default=str(ROOT), help="the repository to read")
    parser.add_argument("--check", action="store_true", help="exit non-zero when a unit is missing")
    parser.add_argument("--skip-tag", action="store_true", help="do not require the tag yet")
    args = parser.parse_args()

    rows = report(Path(args.root), args.version)
    if args.skip_tag:
        rows = [row for row in rows if row["unit"] != "git tag"]
    for row in rows:
        print(f"{'ok  ' if row['present'] else 'MISS'} {row['unit']}: {row['expected']}")
    if args.check:
        missing = [row["unit"] for row in rows if not row["present"]]
        if missing:
            print(f"missing for {args.version}: {', '.join(missing)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
