"""A coverage row that can never be a console action must not read as pending work."""

from __future__ import annotations

import re
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


def test_the_index_is_grouped_and_links_every_ledger():
    """One generated index row per ledger, under the emulator's own group headings."""
    rows = engine.index_rows()
    text = engine.render_index()
    assert f"**{len(rows)} services**" in text
    for group in {row["group"] for row in rows}:
        assert f"### {group} " in text
    for row in rows:
        label = row["page"].removesuffix(".md")
        assert f"[{label}]({row['page']})" in text
    # Every ledger is counted exactly once, so a duplicated service cannot hide a missing one.
    assert text.count("| [") == len(rows)


def test_the_index_headings_carry_anchors():
    """A group is linkable, so the index can be the only navigation entry."""
    text = engine.render_index()
    for group in {row["group"] for row in engine.index_rows()}:
        anchor = re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-")
        assert f"### {group} {{#{anchor}}}" in text


def test_every_page_points_back_at_the_index():
    """The index is the map; a growing sidebar per service is what this replaced."""
    assert not (ROOT / "site" / "sidebars.coverage.json").exists()
    for row in engine.index_rows():
        page = ROOT / "site" / "docs" / "reference" / row["page"]
        block = engine.block(page.read_text(encoding="utf-8"))
        assert block.startswith(engine.INDEX_LINK.strip()), row["page"]
