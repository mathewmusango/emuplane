#!/usr/bin/env python3
"""The control plane's documents, stored in the emulator's DynamoDB.

Every store in `app.py` keeps its working set in memory and writes each change
through to one table of key -> JSON document. That shape is what makes the swap
from the old SQLite file mechanical: the callers ask for "everything in this
table" at boot and put/delete individual keys after that.

Tables are created at Layer 0 by `ensure_tables()`, before the API serves, so a
cold start needs no migration step and no operator action. A failure to reach the
emulator is raised with the endpoint named — the control plane depends on the
service it fronts, and that dependency must fail loudly, not silently fall back
to a local file.
"""

from __future__ import annotations

import json

from dynamo import Dynamo, DynamoError  # noqa: F401  (DynamoError re-exported)

# One table per store keeps the access patterns obvious and the boot scan small.
# `cells`, `principals` and `audit` are the substrate records from
# ARCHITECTURE.md; the rest are the console's own state.
TABLES = (
    "accounts",
    "users",
    "sessions",
    "owners",
    "settings",
    "buckets",
    "bucket_nodes",
    "cells",
    "principals",
    "audit",
)

PREFIX = "ministack-control-"


def table_name(store: str) -> str:
    return f"{PREFIX}{store}"


class Store:
    def __init__(self, dynamo: Dynamo | None = None) -> None:
        self.dynamo = dynamo or Dynamo()
        self.ready = False

    # -- layer 0 -----------------------------------------------------------

    def ensure_tables(self) -> list[str]:
        """Create every table that is missing. Idempotent, and safe to race."""
        created = []
        for store in TABLES:
            name = table_name(store)
            if not self.dynamo.table_exists(name):
                self.dynamo.ensure_table(name)
                created.append(store)
        self.ready = True
        return created

    # -- reads -------------------------------------------------------------

    def items(self, store: str) -> list[tuple[str, str]]:
        return self.dynamo.scan(table_name(store))

    def payloads(self, store: str) -> dict[str, dict]:
        """The whole store, decoded. A bad document is skipped, not fatal."""
        found: dict[str, dict] = {}
        for key, payload in self.items(store):
            try:
                value = json.loads(payload)
            except ValueError:
                continue
            if isinstance(value, dict):
                found[key] = value
        return found

    # -- writes ------------------------------------------------------------

    def put(self, store: str, key: str, payload) -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        self.dynamo.put(table_name(store), key, body)

    def delete(self, store: str, key: str) -> None:
        self.dynamo.delete(table_name(store), key)

    def delete_prefix(self, store: str, prefix: str) -> None:
        for key, _ in self.items(store):
            if key.startswith(prefix):
                self.dynamo.delete(table_name(store), key)

    def replace_all(self, store: str, rows: dict[str, str]) -> None:
        """Make the table exactly `rows` — put what is there, drop what is not.

        The old `replace()`/`rewrite()` rewrote a whole table in one transaction.
        DynamoDB has no such transaction across a partition, but these tables hold
        tens of rows, so a scan-and-diff is honest and cheap. A concurrent writer
        would be a bug either way: each store holds a lock while it saves.
        """
        existing = {key for key, _ in self.items(store)}
        for key, payload in rows.items():
            self.put(store, key, payload)
        for key in existing - set(rows):
            self.delete(store, key)
