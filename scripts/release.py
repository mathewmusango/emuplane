#!/usr/bin/env python3
"""Decide what the closed issues mean for a release: nothing, a patch, or a pull request.

The policy is the repository's, not this script's: `.github/changelog.json` names
which bump levels may publish themselves. Everything else waits for a human.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import changelog  # noqa: E402

NOTHING = "nothing"
RELEASE = "release"
PULL_REQUEST = "pull-request"


def decide(
    current: str,
    issues: list[dict],
    config: dict,
    released: set[str] | frozenset[str] = frozenset(),
) -> dict:
    """`{"action", "level", "version", "count"}` for this set of closed issues.

    A version whose tag is already in `released` decides nothing: a plan that
    runs again after its own release has nothing left to prepare.
    """
    level = changelog.bump_level(issues, config)
    if level is None:
        return {"action": NOTHING, "level": None, "version": current, "count": 0}
    version = changelog.next_version(current, issues, config)
    if f"v{version}" in released:
        return {"action": NOTHING, "level": None, "version": current, "count": 0}
    automatic = [str(step).lower() for step in (config.get("policy") or {}).get("auto", [])]
    return {
        "action": RELEASE if level in automatic else PULL_REQUEST,
        "level": level,
        "version": version,
        "count": len(issues),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default="", help="the version released last; defaults to the newest tag")
    parser.add_argument("--since", default="", help="ISO date to count from; defaults to the last tag")
    parser.add_argument("--repo", default="", help="owner/name; defaults to origin")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("set GITHUB_TOKEN to read the issues")
    config = changelog.load_config()
    current = args.version or changelog.latest_tag() or "v0.0.0"
    issues = changelog.fetch_issues(
        changelog.repo_slug(args.repo), args.since or changelog.since_default(), token
    )
    print(json.dumps(decide(current, issues, config, changelog.tags()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
