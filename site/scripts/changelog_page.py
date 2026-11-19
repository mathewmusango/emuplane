#!/usr/bin/env python3
"""Write the repository's CHANGELOG.md into the site as the `/changelog` page."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = ROOT.parent
SOURCE = REPOSITORY / "CHANGELOG.md"
PAGE = ROOT / "src" / "pages" / "changelog.md"

FRONT_MATTER = """---
title: Changelog
description: Every release, and what it changed.
hide_table_of_contents: false
---
"""


def main() -> None:
    if not SOURCE.is_file():
        sys.exit(f"changelog_page: no {SOURCE}")
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    # The page starts at the newest release: the file's title, its policy paragraph and an
    # empty `Unreleased` section are the repository's business, not the reader's.
    start = next((n for n, line in enumerate(lines) if line.startswith("## [v")), 0)
    body = "\n".join(lines[start:]).strip() + "\n"
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(FRONT_MATTER + "\n" + body, encoding="utf-8")
    headings = sum(1 for line in body.splitlines() if line.startswith("## ["))
    print(f"wrote {headings} releases into {PAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
