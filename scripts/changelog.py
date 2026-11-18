#!/usr/bin/env python3
"""Build a CHANGELOG section from the issues a release closed.

The unit is the issue: its label picks the section, and its title — or a
`Changelog:` line in its body — is the bullet. Nothing is read from commits, so
the format does not change when the code does.

  scripts/changelog.py --version v0.2.0 --write     # insert the section
  scripts/changelog.py --version v0.2.0 --check     # fail when it is missing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from http.client import HTTPSConnection
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".github" / "changelog.json"
FILE = ROOT / "CHANGELOG.md"
API_HOST = "api.github.com"


def load_config(path: Path = CONFIG) -> dict:
    """The label map, with its lists lower-cased so a label matches however it is typed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for section in data.get("sections", []):
        section["labels"] = [label.lower() for label in section.get("labels", [])]
    data["exclude_labels"] = [label.lower() for label in data.get("exclude_labels", [])]
    return data


def labels_of(issue: dict) -> set[str]:
    return {
        str(label.get("name", "")).strip().lower()
        for label in issue.get("labels") or []
        if isinstance(label, dict)
    }


def section_for(issue: dict, config: dict) -> str | None:
    """The section an issue belongs to; None means it is not changelog material."""
    held = labels_of(issue)
    if held & set(config["exclude_labels"]):
        return None
    for section in config.get("sections", []):
        if held & set(section["labels"]):
            return section["title"]
    return config.get("unlabelled")


def summary(issue: dict, config: dict) -> str:
    """The `Changelog:` line when the body carries one, else the issue title."""
    body = issue.get("body") or ""
    prefix = str(config.get("prefix") or "Changelog:")
    found = re.search(rf"^{re.escape(prefix)}[ \t]*(.+)$", body, re.MULTILINE | re.IGNORECASE)
    text = found.group(1) if found else str(issue.get("title") or "")
    return " ".join(text.split())


def render(version: str, when: str, issues: list[dict], config: dict) -> tuple[str, int]:
    """The Keep a Changelog section, and how many issues were left out."""
    groups: dict[str, list[dict]] = {s["title"]: [] for s in config.get("sections", [])}
    dropped = 0
    for issue in sorted(issues, key=lambda item: item.get("number", 0)):
        if issue.get("state_reason") == "not_planned":
            dropped += 1
            continue
        title = section_for(issue, config)
        if title is None:
            dropped += 1
            continue
        groups.setdefault(title, []).append(issue)

    lines = [f"## [{version}] - {when}"]
    for title, items in groups.items():
        if not items:
            continue
        lines += ["", f"### {title}", ""]
        for issue in items:
            lines.append(f"- {summary(issue, config)} ([#{issue['number']}]({issue['html_url']}))")
    if len(lines) == 1:
        lines += ["", "Nothing was closed for this release."]
    return "\n".join(lines) + "\n", dropped


def insert(text: str, section: str, version: str) -> str:
    """Put the new section between `Unreleased` and the newest released section."""
    if re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE):
        raise SystemExit(f"CHANGELOG.md already has a section for {version}")
    unreleased = re.search(r"^## \[Unreleased\].*?(?=^## \[|\Z)", text, re.MULTILINE | re.DOTALL)
    if unreleased is None:
        raise SystemExit("CHANGELOG.md has no ## [Unreleased] section to insert after")
    head, tail = text[: unreleased.end()].rstrip("\n"), text[unreleased.end() :]
    tail = tail.lstrip("\n")
    joined = f"{head}\n\n{section}"
    return f"{joined}\n{tail}" if tail else joined


def check(text: str, version: str) -> int:
    if re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE):
        print(f"CHANGELOG.md has a section for {version}")
        return 0
    print(
        f"CHANGELOG.md has no section for {version}: "
        f"run scripts/changelog.py --version {version} --write before tagging",
        file=sys.stderr,
    )
    return 1


def parse_version(text: str) -> tuple[int, int, int]:
    """`v0.2.1`, `0.2.1` and a bare tag all read as (0, 2, 1)."""
    found = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not found:
        raise SystemExit(f"not a semantic version: {text!r}")
    return tuple(int(part) for part in found.groups())  # type: ignore[return-value]


BUMP_RANK = {"patch": 1, "minor": 2, "major": 3}


def bump_level(issues: list[dict], config: dict) -> str | None:
    """The highest bump the issues imply, or None when none of them is changelog material."""
    level: str | None = None
    for issue in issues:
        if issue.get("state_reason") == "not_planned":
            continue
        title = section_for(issue, config)
        section = next((s for s in config.get("sections", []) if s["title"] == title), None)
        wanted = str((section or {}).get("bump") or "").lower()
        if wanted not in BUMP_RANK:
            continue
        if level is None or BUMP_RANK[wanted] > BUMP_RANK[level]:
            level = wanted
    return level


def next_version(current: str, issues: list[dict], config: dict) -> str:
    """The version the closed issues imply: the highest `bump` any of them carries.

    Below 1.0.0 a `major` bump moves the minor number: SemVer reserves the leading
    number for the first stable API, so a breaking change is a 0.y step.
    """
    level = bump_level(issues, config) or "patch"
    major, minor, patch = parse_version(current)
    if major == 0 and level == "major":
        level = "minor"
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def label_plan(config: dict) -> list[dict]:
    """Every label the two gates depend on, with the colour and description `gh` is given."""
    plan: list[dict] = []
    for section in config.get("sections", []):
        for name in section.get("labels", []):
            plan.append(
                {
                    "name": name,
                    "color": str(section.get("color") or "ededed").lstrip("#"),
                    "description": f"Changelog: {section['title']}",
                }
            )
    for name in config.get("exclude_labels", []):
        plan.append(
            {
                "name": name,
                "color": str(config.get("exclude_color") or "ededed").lstrip("#"),
                "description": "Not in the changelog",
            }
        )
    return plan


def gh(arguments: list[str]) -> str:
    """One `gh` call, answered as stdout; a failure is reported rather than swallowed."""
    finished = subprocess.run(["gh", *arguments], capture_output=True, text=True)
    if finished.returncode != 0:
        raise SystemExit(f"gh {' '.join(arguments)} failed: {finished.stderr.strip()}")
    return finished.stdout


def sync_labels(repo: str, plan: list[dict], dry_run: bool = False, runner=gh) -> tuple[int, int]:
    """Create the labels the repository does not have yet, and leave the rest alone."""
    existing = json.loads(runner(["label", "list", "--repo", repo, "--limit", "400", "--json", "name"]))
    held = {str(label.get("name", "")).lower() for label in existing}
    created = 0
    for label in plan:
        if label["name"].lower() in held:
            continue
        if dry_run:
            print(f"would create {label['name']} ({label['color']}): {label['description']}")
            continue
        runner(
            [
                "label", "create", label["name"],
                "--repo", repo,
                "--color", label["color"],
                "--description", label["description"],
            ]
        )
        created += 1
    present = sum(1 for label in plan if label["name"].lower() in held)
    return created, present


def repo_slug(explicit: str = "") -> str:
    if explicit:
        return explicit
    found = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True
    ).stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", found)
    if not match:
        raise SystemExit("cannot tell the repository: pass --repo owner/name")
    return match.group(1)


def latest_tag() -> str:
    """The newest tag, or an empty string when nothing has been released."""
    return subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
    ).stdout.strip()


def tags() -> set[str]:
    """Every release tag this checkout knows."""
    found = subprocess.run(
        ["git", "tag", "--list", "v*"], capture_output=True, text=True
    ).stdout
    return {line.strip() for line in found.splitlines() if line.strip()}


def since_default() -> str:
    """The commit date of the newest tag, or of the first commit when the repo has no tag yet."""
    tag = latest_tag()
    if tag:
        stamp = subprocess.run(
            ["git", "log", "-1", "--format=%cI", tag], capture_output=True, text=True
        ).stdout.strip()
        if stamp:
            return stamp
    first = subprocess.run(
        ["git", "log", "--reverse", "--format=%cI"], capture_output=True, text=True
    ).stdout.strip().splitlines()
    if not first:
        raise SystemExit("no commit to measure from: pass --since (an ISO date)")
    return first[0]


def fetch_issues(repo: str, since: str, token: str) -> list[dict]:
    """Every closed issue in the window, from the search API, one page at a time."""
    query = quote(f"repo:{repo} is:issue state:closed closed:>={since}")
    issues: list[dict] = []
    page = 1
    while True:
        connection = HTTPSConnection(API_HOST, timeout=30)
        try:
            connection.request(
                "GET",
                f"/search/issues?q={query}&per_page=100&page={page}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "emuplane-changelog",
                },
            )
            answer = connection.getresponse()
            body = answer.read()
        finally:
            connection.close()
        if answer.status != 200:
            raise SystemExit(f"the search API answered {answer.status} for {repo}")
        payload = json.loads(body)
        items = payload.get("items") or []
        issues.extend(items)
        if len(items) < 100:
            return issues
        page += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default="", help="the tag this release is, e.g. v0.2.0")
    parser.add_argument("--since", default="", help="ISO date to count from; defaults to the last tag")
    parser.add_argument("--repo", default="", help="owner/name; defaults to origin")
    parser.add_argument("--date", default=date.today().isoformat(), help="the release date in the heading")
    parser.add_argument("--write", action="store_true", help="insert the section into CHANGELOG.md")
    parser.add_argument("--check", action="store_true", help="fail when the section is missing")
    parser.add_argument(
        "--create-labels",
        action="store_true",
        help="create the labels the gates need, from .github/changelog.json",
    )
    parser.add_argument(
        "--next-version",
        action="store_true",
        help="print the version the closed issues imply, and write nothing",
    )
    parser.add_argument("--dry-run", action="store_true", help="say what --create-labels would do")
    args = parser.parse_args()

    if args.create_labels:
        plan = label_plan(load_config())
        created, present = sync_labels(repo_slug(args.repo), plan, dry_run=args.dry_run)
        if args.dry_run:
            print(f"{len(plan) - present} label(s) missing, {present} already there")
        else:
            print(f"{created} label(s) created, {present} already there")
        return 0

    text = FILE.read_text(encoding="utf-8")
    if args.next_version:
        config = load_config()
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise SystemExit("set GITHUB_TOKEN to read the issues")
        issues = fetch_issues(
            repo_slug(args.repo), args.since or since_default(), token
        )
        print(next_version(args.version or latest_tag() or "v0.0.0", issues, config))
        return 0

    if not args.version:
        raise SystemExit("--version is required unless --create-labels is used")
    if args.check:
        return check(text, args.version)

    config = load_config()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("set GITHUB_TOKEN to read the issues")
    issues = fetch_issues(repo_slug(args.repo), args.since or since_default(), token)
    section, dropped = render(args.version, args.date, issues, config)
    print(f"{len(issues)} issue(s) closed, {dropped} left out of the changelog", file=sys.stderr)
    if args.write:
        FILE.write_text(insert(text, section, args.version), encoding="utf-8")
        print(f"CHANGELOG.md gained a section for {args.version}", file=sys.stderr)
    else:
        print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
