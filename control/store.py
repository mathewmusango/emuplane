#!/usr/bin/env python3
"""The control plane's documents, in emulator DynamoDB tables that `bootstrap/template.yml` provisions and this module only verifies."""

from __future__ import annotations

import json

from dynamo import Dynamo, DynamoError  # noqa: F401  (DynamoError re-exported)

# One table per store keeps the access patterns obvious and the boot scan small.
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
    "resets",
)

PREFIX = "emuplane-"
STACK_NAME = "emuplane"


def table_name(store: str) -> str:
    return f"{PREFIX}{store}"


class StoreNotProvisioned(RuntimeError):
    """The bootstrap stack has not created the tables this control needs."""


class Store:
    def __init__(self, dynamo: Dynamo | None = None) -> None:
        self.dynamo = dynamo or Dynamo()
        self.ready = False

    # -- layer 0 -----------------------------------------------------------

    def verify_tables(self) -> None:
        """Refuse to serve unless the bootstrap stack has provisioned every table."""
        missing = [
            table_name(store)
            for store in TABLES
            if not self.dynamo.table_exists(table_name(store))
        ]
        if missing:
            raise StoreNotProvisioned(
                "the control store is not provisioned: missing "
                + ", ".join(missing)
                + ". Run ./scripts/up.sh (it applies bootstrap/template.yml as the "
                f"{STACK_NAME} stack) or python bootstrap/apply.py."
            )
        self.ready = True

    # -- reads -------------------------------------------------------------

    def get(self, store: str, key: str) -> str | None:
        return self.dynamo.get(table_name(store), key)

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
        """Make the table exactly `rows`: a scan-and-diff, safe because each store holds a lock while it saves."""
        existing = {key for key, _ in self.items(store)}
        for key, payload in rows.items():
            self.put(store, key, payload)
        for key in existing - set(rows):
            self.delete(store, key)
