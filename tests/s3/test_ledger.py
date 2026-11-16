"""`S3.md` is the record of what is covered; this keeps it honest.

The table is generated, so it cannot go stale — `scripts/qa_check.py` runs
`s3_coverage.py --check` and fails when the file drifts. Generation cannot catch
what actually went wrong in this repository: a row whose proof was deleted, and a
count that quietly walked backwards when a control was removed.

The rule this file enforces is simple and absolute: **every operation the
emulator advertises names a test, and those tests run on every run**. Not "the
emulator's own suite covers it" — an operation with no emuplane test is a row
with an em dash in the last column, and that fails. So does a test file that is
named but absent, an operation with no row at all, and a headline count that
falls below its pinned floor.

A floor is a ratchet, not a target: raise it when an operation is closed, and the
next person is told when one slips back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER = ROOT / "S3.md"
README = ROOT.parent / "ministack-src" / "README.md"

# Today's numbers, pinned. Raising them is the point of closing an operation.
FLOOR_SHOWN = 47
FLOOR_READS_SHOWN = 23

ROW = re.compile(r"\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|")
TEST_FILE = re.compile(r"tests/[\w./-]+\.(?:py|jsx)")
READ_PREFIXES = ("Get", "List", "Head", "Describe")
DASH = "\u2014"


def rows() -> list[tuple[str, str, str, str]]:
    """`(operation, console action, shown in the console, emuplane test)`."""
    found = []
    section = ""
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        match = ROW.match(line)
        if match and section != "Console actions":
            found.append(tuple(part.strip() for part in match.groups()))
    return found


def test_every_operation_upstream_advertises_has_a_row():
    if not README.is_file():
        pytest.skip("ministack-src is not checked out beside the control")
    line = next(
        (row for row in README.read_text(encoding="utf-8").splitlines()
         if row.startswith("| **S3** |")),
        "",
    )
    upstream = {
        part.strip() for part in line.split("|")[2].split(",") if part.strip()
    }
    assert upstream, "no `| **S3** |` row in the emulator README"

    listed = {op for op, _action, _shown, _test in rows()}
    missing = sorted(upstream - listed)
    assert missing == [], (
        f"operations upstream advertises with no row in S3.md: {missing} — "
        "add them to GROUPS in scripts/s3_coverage.py"
    )


def test_every_operation_names_a_test():
    """The rule. An em dash here means nobody in emuplane exercises it."""
    bare = [op for op, _action, _shown, test in rows() if test == DASH]
    assert bare == [], (
        "these operations have no emuplane test, so nothing would catch them "
        f"breaking: {bare}"
    )


def test_every_test_a_row_names_exists():
    missing = [
        (op, path)
        for op, _action, _shown, test in rows()
        for path in TEST_FILE.findall(test)
        if not (ROOT / path).is_file()
    ]
    assert missing == [], f"rows name test files that are not there: {missing}"


def test_the_counts_do_not_go_backwards():
    listed = rows()
    shown = [row for row in listed if row[2] != DASH]
    reads = [row for row in listed if row[0].startswith(READ_PREFIXES)]
    reads_shown = [row for row in reads if row[2] != DASH]

    assert len(shown) >= FLOOR_SHOWN, (
        f"{len(shown)} operations are shown in the console, down from "
        f"{FLOOR_SHOWN}: did a control disappear?"
    )
    assert len(reads_shown) >= FLOOR_READS_SHOWN, (
        f"{len(reads_shown)} read operations are shown in the console, down from "
        f"{FLOOR_READS_SHOWN}"
    )
