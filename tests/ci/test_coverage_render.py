"""A coverage row that can never be a console action must not read as pending work."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import coverage_engine as engine  # noqa: E402

STS_PAGE = ROOT / "site" / "docs" / "reference" / "sts-coverage.md"


def test_the_single_table_honours_not_console(monkeypatch):
    """A service with no hand-written groups renders one table, which used to ignore the map."""
    monkeypatch.setattr(
        engine, "upstream_operations", lambda service: ["GetCallerIdentity"]
    )
    spec = {
        "service": "STS",
        "title": "STS coverage",
        "page": "site/docs/reference/sts-coverage.md",
        "group": "Core",
        "not_console": {"GetCallerIdentity": "not a console action (test)"},
    }
    table = engine.published(engine.render(spec))
    assert "not a console action (test)" in table
    assert "not yet" not in table


def test_the_published_sts_page_reads_as_out_of_scope():
    page = STS_PAGE.read_text(encoding="utf-8")
    assert "not yet" not in page
    assert page.count("not a console action (") == 5
    assert "Operations that are not console actions: **5**" in page
