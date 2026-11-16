#!/usr/bin/env python3
"""Copy the S3 coverage ledger into docs/reference/s3-coverage.md.

Usage:
  npm run s3:coverage              # the repository this site lives in
  python3 scripts/s3_coverage.py <control checkout>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = ROOT.parent
PAGE = ROOT / "docs" / "reference" / "s3-coverage.md"
BEGIN = "<!-- coverage:begin -->"
END = "<!-- coverage:end -->"

SUMMARY = "- "
SKIP = {"Console actions"}
SEPARATOR = "| --- | --- | --- | --- |"


def control_dir() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    named = os.environ.get("CONTROL_SRC", "")
    if named:
        return Path(named).resolve()
    return REPOSITORY


def ledger(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    section = ""
    for line in lines:
        if line.startswith("## "):
            section = line[3:].strip()
            if section in SKIP:
                continue
            kept += ["", "##" + line[2:], ""]
        elif section in SKIP:
            continue
        elif line.startswith(SUMMARY) and "**" in line:
            kept.append(line)
        elif line.startswith("| `") or line.startswith("| Operation") or line == SEPARATOR:
            kept.append(line)
        elif line.startswith("- [x]") or line.startswith("- [ ]"):
            kept.append(line)
    return "\n".join(kept).strip()


def main() -> int:
    source = control_dir() / "S3.md"
    if not source.is_file():
        raise SystemExit(f"s3_coverage: {source} is not there")

    page = PAGE.read_text(encoding="utf-8")
    if BEGIN not in page or END not in page:
        raise SystemExit(f"s3_coverage: {PAGE} has no generated block markers")

    head, _, rest = page.partition(BEGIN)
    _, _, tail = rest.partition(END)
    PAGE.write_text(head + BEGIN + "\n\n" + ledger(source) + "\n\n" + END + tail)
    print(f"copied the ledger into {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
