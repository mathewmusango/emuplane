"""The S3 children the bucket list cannot answer: S3 Tables and S3 Files.

Each case creates the resource through the emulator's own API, then lists it
through `control/s3extra.py` — so the parsing and the endpoint mapping are
exercised against real responses, over a socket.
"""

from __future__ import annotations

import json

import pytest

import s3extra
import signed

ACCOUNT = "344381301567"


def _call(endpoint, region="us-east-1"):
    def call(service, method, path, body=""):
        return signed.request(endpoint, service, ACCOUNT, region, method, path, body)

    return call


def _lister(call):
    return lambda service, method, path: call(service, method, path)


def test_table_buckets_are_listed(s3_endpoint):
    call = _call(s3_endpoint)
    status, body = call("s3tables", "PUT", "/buckets", json.dumps({"name": "console-tables"}))
    assert status == 200, body

    result = s3extra.list_items("table-buckets", _lister(call))
    assert result["ok"], result.get("error")
    names = [bucket.get("name") for bucket in result["items"]]
    assert "console-tables" in names


def test_file_systems_are_listed(s3_endpoint):
    call = _call(s3_endpoint)
    status, body = call(
        "s3files",
        "PUT",
        "/file-systems",
        json.dumps({"bucket": "logs-bucket", "roleArn": "arn:aws:iam::344381301567:role/s3files"}),
    )
    assert status in (200, 201), body

    result = s3extra.list_items("file-systems", _lister(call))
    assert result["ok"], result.get("error")
    assert any(system.get("bucket") == "logs-bucket" for system in result["items"])


def test_an_empty_listing_is_not_an_error():
    """Nothing to show is a list of nothing, not a failure."""

    def call(service, method, path):
        return 200, json.dumps({"tableBuckets": []})

    result = s3extra.list_items("table-buckets", call)
    assert result["ok"] is True
    assert result["items"] == []


def test_a_refusal_carries_what_the_backend_said():
    def call(service, method, path):
        return 404, "<Error><Code>NoSuchAPI</Code><Message>no such thing</Message></Error>"

    result = s3extra.list_items("file-systems", call)
    assert result["ok"] is False
    assert result["status"] == 404
    assert "no such thing" in result["error"]


def test_a_body_that_is_not_the_documented_json_is_a_failure():
    def call(service, method, path):
        return 200, "<ListFileSystems/>"

    result = s3extra.list_items("file-systems", call)
    assert result["ok"] is False
    assert "not JSON" in result["error"]

    def call_no_key(service, method, path):
        return 200, json.dumps({"something": []})

    result = s3extra.list_items("file-systems", call_no_key)
    assert result["ok"] is False
    assert "fileSystems" in result["error"]


@pytest.mark.parametrize("section", sorted(s3extra.SOURCES))
def test_every_section_names_a_service_and_a_path(section):
    service, path, key = s3extra.SOURCES[section]
    assert service.startswith("s3")
    assert path.startswith("/")
    assert key
