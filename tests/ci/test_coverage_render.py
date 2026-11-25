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


def test_the_map_counts_every_group_it_lists():
    """One row per group on the map, and the totals above it agree with the service pages."""
    rows = engine.index_rows()
    text = engine.render_index()
    assert f"**{len(rows)} services**" in text
    for group in {row["group"] for row in rows}:
        members = engine.group_rows(group)
        assert f"| [{group}]({engine.GROUP_SLUGS[group]}/index.md) | {len(members)} " in text
    # The map links a group, never a service, so a new ledger cannot make it grow by a line.
    assert text.count("| [") == len({row["group"] for row in rows})


def test_every_group_has_a_page_that_matches_its_services():
    """A group page exists even when empty, and its table is the group's services."""
    for group, path, expected in engine.group_pages():
        assert path.is_file(), path
        assert engine.index_block(path) == expected
        if expected.startswith("|"):
            assert expected.count("| [") == len(engine.group_rows(group)), group


def test_every_page_points_back_at_the_map():
    """The map is the navigation; a growing sidebar per service is what this replaced."""
    assert not (ROOT / "site" / "sidebars.coverage.json").exists()
    for row in engine.index_rows():
        page = ROOT / "site" / "docs" / "reference" / row["page"]
        block = engine.block(page.read_text(encoding="utf-8"))
        assert block.startswith(engine.INDEX_LINK.strip()), row["page"]
