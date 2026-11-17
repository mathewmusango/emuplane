"""The bootstrap template and the store module agree on the tables a control needs."""

from __future__ import annotations

import re
from pathlib import Path

import store

TEMPLATE = Path(__file__).resolve().parent.parent.parent / "bootstrap" / "template.yml"


def _template_tables(text: str) -> list[str]:
    return re.findall(r'TableName: !Sub "\$\{TablePrefix\}([a-z_]+)"', text)


def test_every_table_the_store_needs_is_provisioned():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert sorted(_template_tables(text)) == sorted(store.TABLES)


def test_the_stack_reports_how_many_tables_it_owns():
    text = TEMPLATE.read_text(encoding="utf-8")
    found = re.search(r'TableCount:\s*\n\s*Description:.*\n\s*Value: "(\d+)"', text)
    assert found, "no TableCount output in the template"
    assert int(found.group(1)) == len(store.TABLES)
