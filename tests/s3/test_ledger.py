"""`S3.md` is the generated record of what is covered; every operation must name a test, and the counts ratchet upwards."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER = ROOT / "site" / "docs" / "reference" / "s3-coverage.md"
README = ROOT.parent / "ministack-src" / "README.md"

# Today's numbers, pinned. Raising them is the point of closing an operation.
FLOOR_SHOWN = 83
FLOOR_READS_SHOWN = 35

ROW = re.compile(r"\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|")
TEST_FILE = re.compile(r"tests/[\w./-]+\.(?:py|jsx)")
READ_PREFIXES = ("Get", "List", "Head", "Describe")
# S3 Files has its own generated page, so its rows are not S3's.
DASH = "\u2014"
NOT_CONSOLE = "not a console action"
SKIP_SECTIONS = {"Console actions"}


def rows() -> list[tuple[str, str, str, str]]:
    """`(operation, console action, shown in the console, emuplane test)`."""
    found = []
    section = ""
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        match = ROW.match(line)
        if match and section not in SKIP_SECTIONS:
            found.append(tuple(part.strip() for part in match.groups()))
    return found


def test_every_published_page_names_its_service_and_lists_its_operations():
    """One data file per service, and a page that carries what it advertises."""
    plans = sorted((ROOT / "coverage").glob("*.json"))
    assert plans, "no coverage data files"
    for path in plans:
        spec = json.loads(path.read_text(encoding="utf-8"))
        page = (ROOT / spec["page"]).read_text(encoding="utf-8")
        assert "Operations upstream advertises: **" in page, spec["page"]
        assert [line for line in page.splitlines() if ROW.match(line)], spec["page"]


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
        "add them to the groups in coverage/s3.json"
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
    shown = [
        row
        for row in listed
        if row[2] != DASH and not row[2].startswith(NOT_CONSOLE)
    ]
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


def test_the_only_non_console_operation_is_the_runtime_callback():
    """No em dash is left; the one exception is named, so a new gap cannot hide behind it."""
    named = [op for op, _action, shown, _test in rows() if shown.startswith(NOT_CONSOLE)]
    assert named == ["WriteGetObjectResponse"]

    gaps = [op for op, _action, shown, _test in rows() if shown == DASH]
    assert gaps == [], f"operations reachable only over the wire: {gaps}"
