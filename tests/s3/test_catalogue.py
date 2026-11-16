"""The console's own S3 operations: what each one puts on the wire.

`console.py` is the catalogue the API explorer renders; its `run` functions are
the last hop before the signed client, so these tests pin the request itself —
method, path and body — rather than any state.
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest

import buckets
import console

ACCOUNT = "344381301567"


class Rest:
    """The signed client `console.run_action` hands each operation."""

    def __init__(self):
        self.calls = []

    def __call__(self, service, account, region, method, path, body=""):
        self.calls.append(
            {"service": service, "region": region, "method": method, "path": path, "body": body}
        )
        return 200, ""


def run(op_id: str, params: dict, region: str = "us-west-2"):
    operation = next(
        item for item in console.CATALOGUE["s3"]["operations"] if item["id"] == op_id
    )
    rest = Rest()
    ok, status, _body = operation["run"](params, ACCOUNT, region, None, rest)
    return ok, status, rest.calls


def test_create_bucket_names_the_region():
    ok, _status, calls = run("create-bucket", {"Bucket": "demo"}, region="eu-west-1")
    assert ok
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == "/demo"
    assert calls[0]["body"] == buckets.location_constraint("eu-west-1")


def test_create_bucket_sends_nothing_on_the_global_endpoint():
    _ok, _status, calls = run("create-bucket", {"Bucket": "demo"}, region="us-east-1")
    assert calls[0]["body"] == ""


def test_put_object_sends_the_body():
    ok, _status, calls = run(
        "put-object",
        {"Bucket": "demo", "Key": "notes/one.txt", "Body": "hello\nworld"},
    )
    assert ok
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == "/demo/notes/one.txt"
    assert calls[0]["body"] == "hello\nworld"


@pytest.mark.parametrize("op_id", ["put-object", "delete-object"])
def test_keys_are_percent_encoded_but_keep_their_separators(op_id):
    _ok, _status, calls = run(
        op_id, {"Bucket": "demo", "Key": "notes/2026 Q4+#%.csv", "Body": "x"}
    )
    path = calls[0]["path"]
    assert " " not in path and "+" not in path.split("/", 2)[2]
    assert path == "/demo/notes/2026%20Q4%2B%23%25.csv"
    # The bucket/key split survives: the emulator reads the decoded path.
    bucket, _, key = unquote(path).lstrip("/").partition("/")
    assert (bucket, key) == ("demo", "notes/2026 Q4+#%.csv")


def test_delete_object_sends_no_body():
    _ok, _status, calls = run("delete-object", {"Bucket": "demo", "Key": "plain.txt"})
    assert calls[0]["method"] == "DELETE"
    assert calls[0]["body"] == ""


def test_list_objects_asks_for_the_second_listing():
    _ok, _status, calls = run("list-objects", {"Bucket": "demo"})
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/demo?list-type=2"
