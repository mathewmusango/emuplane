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
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".github" / "changelog.json"
FILE = ROOT / "CHANGELOG.md"
API = "https://api.github.com"


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


def since_default() -> str:
    """The commit date of the newest tag, so 'since the last release' is a fact."""
    tag = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not tag:
        raise SystemExit("no tag to measure from: pass --since (an ISO date)")
    stamp = subprocess.run(
        ["git", "log", "-1", "--format=%cI", tag], capture_output=True, text=True
    ).stdout.strip()
    if not stamp:
        raise SystemExit(f"cannot read the date of {tag}: pass --since")
    return stamp


def fetch_issues(repo: str, since: str, token: str) -> list[dict]:
    """Every closed issue in the window, from the search API, one page at a time."""
    query = quote(f"repo:{repo} is:issue state:closed closed:>={since}")
    issues: list[dict] = []
    page = 1
    while True:
        request = Request(
            f"{API}/search/issues?q={query}&per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "emuplane-changelog",
            },
        )
        with urlopen(request, timeout=30) as answer:
            payload = json.loads(answer.read())
        items = payload.get("items") or []
        issues.extend(items)
        if len(items) < 100:
            return issues
        page += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="the tag this release is, e.g. v0.2.0")
    parser.add_argument("--since", default="", help="ISO date to count from; defaults to the last tag")
    parser.add_argument("--repo", default="", help="owner/name; defaults to origin")
    parser.add_argument("--date", default=date.today().isoformat(), help="the release date in the heading")
    parser.add_argument("--write", action="store_true", help="insert the section into CHANGELOG.md")
    parser.add_argument("--check", action="store_true", help="fail when the section is missing")
    args = parser.parse_args()

    text = FILE.read_text(encoding="utf-8")
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
