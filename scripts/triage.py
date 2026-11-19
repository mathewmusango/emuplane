#!/usr/bin/env python3
"""The two triage gates: a pull request closes exactly one issue, an issue names a changelog label.

Run by CI with the event payload GitHub writes; the same file is what the tests
exercise, so the rule is one implementation and not a copy of a regex in YAML.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".github" / "changelog.json"

CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*#(\d+)", re.IGNORECASE)


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def changelog_labels(config: dict) -> set[str]:
    """Every label that places an issue in the changelog, including the ones that exclude it."""
    names = {label for section in config.get("sections", []) for label in section.get("labels", [])}
    names |= set(config.get("exclude_labels", []))
    return {str(name).strip().lower() for name in names}


def closed_issues(*texts: str) -> list[int]:
    """Every issue number these say they close, in order, each once."""
    found: list[int] = []
    for text in texts:
        for match in CLOSING.finditer(text or ""):
            number = int(match.group(1))
            if number not in found:
                found.append(number)
    return found


def closes_an_issue(*texts: str) -> bool:
    """Whether any of these says `Closes #12`, `Fixes #7`, `Resolved: #3`, …"""
    return bool(closed_issues(*texts))


def labelled(names, config: dict) -> bool:
    """Whether this issue carries a label the changelog can act on."""
    held = {str(name).strip().lower() for name in names or []}
    return bool(held & changelog_labels(config))


def check_pull_request(payload: dict, config: dict) -> int:
    pull = payload.get("pull_request") or {}
    issues = closed_issues(pull.get("title") or "", pull.get("body") or "")
    if len(issues) == 1:
        print(f"the pull request closes one issue: #{issues[0]}")
        return 0
    if issues:
        named = ", ".join(f"#{number}" for number in issues)
        print(
            f"::error::This pull request closes {len(issues)} issues ({named}). One issue per pull request: "
            "keep the one this change is for and land the rest on their own branches.",
            file=sys.stderr,
        )
        return 1
    print(
        "::error::This pull request does not name the issue it closes. Add a line such as "
        "'Closes #12' to the body, so the change reaches the changelog.",
        file=sys.stderr,
    )
    return 1


def check_issue(payload: dict, config: dict) -> int:
    issue = payload.get("issue") or {}
    names = [label.get("name") for label in issue.get("labels") or [] if isinstance(label, dict)]
    if labelled(names, config):
        print(f"the issue carries a changelog label: {', '.join(sorted(names))}")
        return 0
    print(
        "::error::This issue carries no changelog label. Add one of "
        f"{', '.join(sorted(changelog_labels(config)))}.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--pr", action="store_true", help="the event is a pull request")
    which.add_argument("--issue", action="store_true", help="the event is an issue")
    parser.add_argument(
        "--event",
        default=os.environ.get("GITHUB_EVENT_PATH", ""),
        help="the payload path; defaults to GITHUB_EVENT_PATH",
    )
    args = parser.parse_args()

    if not args.event:
        raise SystemExit("no event payload: pass --event or set GITHUB_EVENT_PATH")
    payload = json.loads(Path(args.event).read_text(encoding="utf-8"))
    config = load_config()
    return check_pull_request(payload, config) if args.pr else check_issue(payload, config)


if __name__ == "__main__":
    raise SystemExit(main())
