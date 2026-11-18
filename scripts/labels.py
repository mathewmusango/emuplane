#!/usr/bin/env python3
"""Create or update the repository's labels from `.github/*.json`.

Two sources, both already in the repository: `changelog.json` decides which labels
release notes use (and their colours), `modules.json` adds the `module:*` axis so an
issue can say *what* it changes as well as *how* the release notes should read.

    python3 scripts/labels.py            # print the gh commands
    python3 scripts/labels.py --apply    # run them (needs an authenticated gh)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB = ROOT / ".github"


def changelog_labels() -> list[tuple[str, str, str]]:
    """`(name, colour, description)` for every label the changelog config knows."""
    data = json.loads((GITHUB / "changelog.json").read_text(encoding="utf-8"))
    found = []
    for section in data["sections"]:
        for label in section["labels"]:
            found.append(
                (label, section["color"], f"{section['title']} — release notes")
            )
    for label in data.get("exclude_labels") or []:
        found.append((label, data.get("exclude_color") or "ededed", "no release note"))
    return found


def module_labels() -> list[tuple[str, str, str]]:
    data = json.loads((GITHUB / "modules.json").read_text(encoding="utf-8"))
    prefix = data["prefix"]
    return [
        (
            f"{prefix}{module['name']}",
            module["color"],
            module.get("description", ""),
        )
        for module in data["modules"]
    ]


def main(argv: list[str]) -> int:
    wanted = changelog_labels() + module_labels()
    commands = [
        [
            "gh",
            "label",
            "create",
            name,
            "--color",
            colour,
            "--description",
            description,
            "--force",
        ]
        for name, colour, description in wanted
    ]
    if "--apply" not in argv:
        for command in commands:
            print(" ".join(command))
        print(f"\n{len(commands)} labels; re-run with --apply to create them")
        return 0
    if shutil.which("gh") is None:
        print("gh is not installed", file=sys.stderr)
        return 1
    for command in commands:
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode != 0:
            print(f"failed: {command[3]}", file=sys.stderr)
            return 1
    print(f"synced {len(commands)} labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
