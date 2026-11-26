"""The OpenAPI document is generated from the control's routes, so it cannot drift."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import control_routes  # noqa: E402
import openapi  # noqa: E402

APP = ROOT / "control" / "app.py"


def test_a_literal_route_is_its_own_path():
    assert control_routes.shape("/api/exec") == ("/api/exec", [])


def test_a_capture_becomes_a_named_path_parameter():
    path, parameters = control_routes.shape("/api/accounts/([0-9]{12})/disabled")
    assert path == "/api/accounts/{account_id}/disabled"
    assert parameters == [
        {
            "name": "account_id",
            "in": "path",
            "required": True,
            "schema": {"type": "string", "pattern": "^[0-9]{12}$"},
        }
    ]


def test_an_open_ended_capture_carries_no_pattern():
    path, parameters = control_routes.shape("/api/buckets/([^/]+)")
    assert path == "/api/buckets/{bucket}"
    assert parameters[0]["schema"] == {"type": "string"}


def test_an_unknown_collection_is_refused_rather_than_guessed():
    with pytest.raises(SystemExit, match="PARAMETERS"):
        control_routes.shape("/api/widgets/([^/]+)")


def test_the_regex_routes_the_old_matcher_missed_are_read():
    found = control_routes.routes(APP)
    assert ("DELETE", "/api/users/([^/]+)") in found
    assert ("POST", "/api/users/([^/]+)/password") in found
    assert ("POST", "/api/users/([^/]+)/reset-link") in found


def test_every_route_becomes_one_operation_with_a_unique_id():
    found = control_routes.routes(APP)
    document = openapi.document(found, "v1")
    operations = [
        operation
        for path in document["paths"].values()
        for operation in path.values()
    ]
    assert len(operations) == len(found)
    identifiers = [operation["operationId"] for operation in operations]
    assert len(set(identifiers)) == len(identifiers)


def test_the_checked_in_document_is_current():
    assert openapi.SPEC.read_text(encoding="utf-8") == openapi.render()


def test_the_document_states_the_api_it_describes():
    document = json.loads(openapi.render())
    assert document["openapi"] == "3.0.3"
    assert document["info"]["version"] == openapi.api_version(APP)
    assert "/api/accounts/{account_id}" in document["paths"]
