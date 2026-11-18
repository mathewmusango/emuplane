#!/usr/bin/env python3
"""Plan one module's issues and its pull request from `.github/issues/<name>.json`.

The plan is data, in the same shape as `coverage/*.json`: one file per release
unit, each issue naming its module and its changelog label, so the two triage
gates and the release notes all read from one place.

    python3 scripts/issues.py                 # every plan, dry run
    python3 scripts/issues.py s3 --check      # validate the labels and bodies
    python3 scripts/issues.py s3 --apply      # create them (needs an authenticated gh)
    python3 scripts/issues.py s3 --project 11 # add them to a board, Module set
    python3 scripts/issues.py s3 --pr         # the pull request body that closes them
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB = ROOT / ".github"
PLANS = GITHUB / "issues"
CACHE = ROOT / "my-docs" / "issues.json"
MODULE_FIELD = "Module"


def plan_names() -> list[str]:
    return sorted(path.stem for path in PLANS.glob("*.json"))


def load(name: str) -> dict:
    path = PLANS / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"issues: {path} is missing")
    return json.loads(path.read_text(encoding="utf-8"))


def label_rules() -> tuple[set[str], set[str]]:
    """Every changelog label (sections and exclusions), and every module label."""
    changelog = json.loads((GITHUB / "changelog.json").read_text(encoding="utf-8"))
    modules = json.loads((GITHUB / "modules.json").read_text(encoding="utf-8"))
    changes = {label for section in changelog["sections"] for label in section["labels"]}
    changes |= set(changelog.get("exclude_labels") or [])
    prefix = modules["prefix"]
    return changes, {f"{prefix}{module['name']}" for module in modules["modules"]}


def labels_for(issue: dict) -> list[str]:
    """The two axes every issue carries: which module, and which release note."""
    return [f"module:{issue['module']}", issue["changelog"]]


def problems(spec: dict) -> list[str]:
    """What would make an issue fail triage or sit outside every module."""
    changes, modules = label_rules()
    found: list[str] = []
    seen: set[str] = set()
    for issue in spec.get("issues", []):
        key = str(issue.get("key") or "")
        if not key or key in seen:
            found.append(f"a key is missing or repeated: {key!r}")
        seen.add(key)
        if not str(issue.get("title") or "").strip():
            found.append(f"{key}: no title")
        if not str(issue.get("body") or "").strip():
            found.append(f"{key}: no body")
        if issue.get("changelog") not in changes:
            found.append(f"{key}: {issue.get('changelog')!r} is not a changelog label")
        if f"module:{issue.get('module')}" not in modules:
            found.append(f"{key}: module:{issue.get('module')} is not a module label")
    if not spec.get("issues"):
        found.append("the plan has no issues")
    return found


def render(name: str, spec: dict) -> str:
    lines = [f"# {name}: {spec.get('release', '')}", ""]
    for issue in spec["issues"]:
        labels = ", ".join(labels_for(issue))
        lines += [f"- [{issue['key']}] {issue['title']}", f"  labels: {labels}", ""]
    lines.append(f"{len(spec['issues'])} issues in {name}")
    return "\n".join(lines)


def read_cache(cache: Path = CACHE) -> dict[str, int]:
    return json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else {}


def write_cache(found: dict[str, int], cache: Path = CACHE) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(found, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create(issue: dict) -> str:
    command = [
        "gh",
        "issue",
        "create",
        "--title",
        issue["title"],
        "--body",
        issue["body"],
        "--label",
        ",".join(labels_for(issue)),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"issues: {issue['key']} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def apply(name: str, spec: dict, cache: Path = CACHE) -> int:
    if shutil.which("gh") is None:
        print("gh is not installed", file=sys.stderr)
        return 1
    found = read_cache(cache)
    for issue in spec["issues"]:
        slot = f"{name}:{issue['key']}"
        if slot in found:
            print(f"{slot} already exists as #{found[slot]}")
            continue
        number = int(create(issue).rstrip("/").rsplit("/", 1)[-1])
        found[slot] = number
        write_cache(found, cache)
        print(f"#{number} {issue['title']}")
    return 0


def parse(argv: list[str]) -> tuple[list[str], set[str], dict[str, str]]:
    """Plan names, flags, and the one flag that takes a value."""
    names: list[str] = []
    flags: set[str] = set()
    values: dict[str, str] = {}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--project":
            values["project"] = argv[index + 1] if index + 1 < len(argv) else ""
            index += 2
            continue
        if arg.startswith("-"):
            flags.add(arg)
        else:
            names.append(arg)
        index += 1
    return names, flags, values


def gh(*args: str) -> str:
    """One `gh` call, with its refusal surfaced instead of being swallowed."""
    result = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"issues: gh {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def repository() -> str:
    """`owner/name`, so nothing hard-codes an owner."""
    return json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]


def module_names() -> list[str]:
    modules = json.loads((GITHUB / "modules.json").read_text(encoding="utf-8"))
    return [module["name"] for module in modules["modules"]]


def board(number: str, owner: str) -> tuple[str, str, dict[str, str]]:
    """The project id, the Module field id, and its option ids by module name.

    The field is created from `modules.json` when the board has none, so the board
    and the labels cannot disagree about which modules exist.
    """
    project = json.loads(gh("project", "view", number, "--owner", owner, "--format", "json"))

    def fields() -> list[dict]:
        listed = gh("project", "field-list", number, "--owner", owner, "--format", "json")
        return json.loads(listed)["fields"]

    field = next((row for row in fields() if row["name"] == MODULE_FIELD), None)
    if field is None:
        gh(
            "project",
            "field-create",
            number,
            "--owner",
            owner,
            "--name",
            MODULE_FIELD,
            "--data-type",
            "SINGLE_SELECT",
            "--single-select-options",
            ",".join(module_names()),
        )
        field = next((row for row in fields() if row["name"] == MODULE_FIELD), None)
    options = {option["name"]: option["id"] for option in field.get("options") or []}
    return project["id"], field["id"], options


def add_to_board(name: str, spec: dict, number: str, cache: Path = CACHE) -> int:
    """Add every issue to the board and set its Module, which is the board's own axis."""
    found = read_cache(cache)
    missing = [
        f"{name}:{issue['key']}"
        for issue in spec["issues"]
        if f"{name}:{issue['key']}" not in found
    ]
    if missing:
        print(
            "issues: run --apply first, these have no number: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    repo = repository()
    owner = repo.split("/")[0]
    project_id, field_id, options = board(number, owner)
    for issue in spec["issues"]:
        url = f"https://github.com/{repo}/issues/{found[f'{name}:{issue['key']}']}"
        item = json.loads(
            gh("project", "item-add", number, "--owner", owner, "--url", url, "--format", "json")
        )
        option = options.get(issue["module"])
        if option:
            gh(
                "project",
                "item-edit",
                "--project-id",
                project_id,
                "--id",
                item["id"],
                "--field-id",
                field_id,
                "--single-select-option-id",
                option,
            )
        print(f"{url} -> {issue['module']}")
    return 0


def pull_request(name: str, spec: dict, cache: Path = CACHE) -> int:
    found = read_cache(cache)
    slots = [f"{name}:{issue['key']}" for issue in spec["issues"]]
    missing = [slot for slot in slots if slot not in found]
    if missing:
        print(
            "issues: run --apply first, these have no number: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    closes = ", ".join(f"#{found[slot]}" for slot in slots)
    lines = [
        spec["pr"]["title"],
        "",
        f"Branch: `{spec['pr']['branch']}`",
        "",
        f"Closes {closes}",
        "",
        "## What changed",
        "",
        "| Module | Issue |",
        "| --- | --- |",
    ]
    lines += [
        f"| `module:{issue['module']}` | {issue['title']} |" for issue in spec["issues"]
    ]
    lines += [
        "",
        "## Checks",
        "",
        "```bash",
        "python3 -m pytest tests -q",
        "cd web && npx tsc --noEmit && npm test",
        "npm --prefix site run build",
        "python3 scripts/coverage.py --check",
        "python3 scripts/qa_check.py",
        "```",
        "",
        "## Documentation",
        "",
        "The docs issue above is part of this pull request: `reference/limits.md`,",
        "`concepts/extensions.md`, `guides/s3.md`, and the generated",
        "`reference/s3-coverage.md` / `reference/control-api.md`.",
    ]
    print("\n".join(lines))
    return 0


def main(argv: list[str]) -> int:
    names, flags, values = parse(argv)
    targets = names or plan_names()
    failed = 0
    for name in targets:
        spec = load(name)
        found = problems(spec)
        for problem in found:
            print(f"{name}: {problem}", file=sys.stderr)
        if "--apply" in flags:
            if found:
                return 1
            failed |= apply(name, spec)
        elif "project" in values:
            if found:
                return 1
            failed |= add_to_board(name, spec, values["project"])
        elif "--pr" in flags:
            if found:
                return 1
            failed |= pull_request(name, spec)
        else:
            if "--check" in flags and found:
                failed = 1
            print(render(name, spec))
    return failed


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
