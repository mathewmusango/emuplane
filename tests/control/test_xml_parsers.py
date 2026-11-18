"""The other two XML parsers refuse a DTD too; the access point one is pinned in `tests/s3/test_access_points.py`."""

from __future__ import annotations

from pathlib import Path

import buckets

ROOT = Path(__file__).resolve().parent.parent.parent

ENTITY = '<!DOCTYPE x [<!ENTITY a "aaa">]><x>&a;</x>'


def test_the_bucket_parser_refuses_a_dtd():
    assert buckets._root(ENTITY) is None


def test_the_bootstrap_reads_a_bomb_as_unparseable(monkeypatch):
    import store

    # The suite doubles `store`; apply imports it for the tables it provisions.
    monkeypatch.setattr(store, "PREFIX", "emuplane", raising=False)
    monkeypatch.setattr(store, "TABLES", [], raising=False)
    monkeypatch.syspath_prepend(str(ROOT / "bootstrap"))
    import apply

    class Response:
        status = 200

        def read(self):
            return ENTITY.encode()

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(apply.http.client, "HTTPConnection", Connection)
    assert apply.call("DescribeStacks", {}).tag == "Unparseable"
