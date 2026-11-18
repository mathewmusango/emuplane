"""The same operation from both ends — MiniStack directly and through the console — one bucket per case because the emulator is session-wide."""

from __future__ import annotations

import console
import signed
from conftest import ACCOUNT, api

BUCKET = "parity-ministack-bucket"


def ensure_bucket(raw, name: str) -> str:
    """A bucket this case can call its own; 409 means an earlier case made it."""
    status, _ = raw("PUT", f"/{name}")
    assert 200 <= status < 300 or status == 409, status
    return name


def ministack(endpoint: str, region: str = "us-east-1"):
    """A client that talks to MiniStack directly, as a foreign caller does."""

    def call(method: str, path: str, body: str = "", headers: dict | None = None):
        return signed.request(endpoint, "s3", ACCOUNT, region, method, path, body, headers)

    return call


def action(console, operation: str, params: dict, region: str = "us-east-1"):
    """One console action, through `/api/exec` — the catalogue's own path."""
    return api(
        console,
        "POST",
        "/api/exec",
        {
            "account": ACCOUNT,
            "region": region,
            "service": "s3",
            "operation": operation,
            "params": params,
        },
    )


def buckets(console, region: str = "all") -> dict:
    status, body = api(
        console, "GET", f"/api/browse?account={ACCOUNT}&region={region}&service=s3"
    )
    assert status == 200, body
    return {row["name"]: row for row in body["resources"]}


def objects(console, bucket: str, prefix: str = "") -> list[dict]:
    query = f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={bucket}"
    if prefix:
        query += f"&prefix={prefix}"
    status, body = api(console, "GET", query)
    assert status == 200, body
    return body["objects"]


def create_bucket(console, name: str) -> None:
    """The console's create page, as one request."""
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "namespace": "global",
            "ownership": "BucketOwnerEnforced",
            "block_public_access": None,
            "versioning": False,
            "tags": [],
            "encryption": "AES256",
            "bucket_key": True,
            "object_lock": False,
            "bucket": name,
        },
    )
    assert status == 200, body


# --- create-bucket ---------------------------------------------------------


def test_a_bucket_created_on_ministack_is_drawn_by_emuplane(s3_endpoint, console):
    """A bucket made straight on the emulator is listed by name, with the region it lives in."""
    raw = ministack(s3_endpoint)
    status, _ = raw("PUT", f"/{BUCKET}")
    assert 200 <= status < 300

    listed = buckets(console)
    assert BUCKET in listed
    assert listed[BUCKET]["region"] == "us-east-1"

    status, settings = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket={BUCKET}",
    )
    assert status == 200, settings
    assert settings["settings"]["versioning"] is False


def test_a_bucket_created_by_emuplane_is_a_bucket_on_ministack(s3_endpoint, console):
    raw = ministack(s3_endpoint)
    name = "parity-emuplane-bucket"
    create_bucket(console, name)

    status, body = raw("GET", f"/{name}?location")
    assert status == 200
    # us-east-1 answers with an empty constraint, as AWS does.
    assert "<LocationConstraint" in body and "us-west-2" not in body
    assert name in raw("GET", "/")[1]


# --- delete-bucket ---------------------------------------------------------


def test_a_bucket_deleted_by_emuplane_leaves_ministack(s3_endpoint, console):
    raw = ministack(s3_endpoint)
    name = "parity-delete-by-emuplane"
    assert 200 <= raw("PUT", f"/{name}")[0] < 300

    status, body = action(console, "delete-bucket", {"Bucket": name})
    assert status == 200, body

    assert raw("GET", f"/{name}?location")[0] == 404
    assert name not in buckets(console)


def test_a_bucket_deleted_on_ministack_leaves_emuplane(s3_endpoint, console):
    raw = ministack(s3_endpoint)
    name = "parity-delete-on-ministack"
    create_bucket(console, name)

    status, _ = raw("DELETE", f"/{name}")
    assert 200 <= status < 300

    assert name not in buckets(console)


# --- put-object / list-objects ---------------------------------------------


def test_objects_written_on_ministack_are_listed_and_read_by_emuplane(
    s3_endpoint, console
):
    raw = ministack(s3_endpoint)
    bucket = ensure_bucket(raw, "parity-list-bucket")
    for key, body in (
        ("parity/one.txt", "one"),
        ("parity/two.txt", "two"),
        ("loose.txt", "loose"),
    ):
        assert 200 <= raw("PUT", f"/{bucket}/{key}", body)[0] < 300

    listed = objects(console, bucket)
    keys = sorted(row["key"] for row in listed)
    assert keys == ["loose.txt", "parity/"]

    narrowed = objects(console, bucket, prefix="parity/")
    assert sorted(row["key"] for row in narrowed) == ["parity/one.txt", "parity/two.txt"]

    status, read = api(
        console,
        "GET",
        f"/api/s3/object?account={ACCOUNT}&region=us-east-1&bucket={bucket}&key=parity/one.txt",
    )
    assert status == 200, read
    assert read["body"] == "one"


def test_an_object_put_by_emuplane_is_an_object_on_ministack(s3_endpoint, console):
    raw = ministack(s3_endpoint)
    bucket = ensure_bucket(raw, "parity-put-bucket")
    status, body = api(
        console,
        "POST",
        "/api/s3/object",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": bucket,
            "key": "parity/from-the-console.txt",
            "body": "written by the console",
        },
    )
    assert status == 200, body

    status, read = raw("GET", f"/{bucket}/parity/from-the-console.txt")
    assert status == 200
    assert read == "written by the console"
    assert "parity/from-the-console.txt" in raw("GET", f"/{bucket}?list-type=2")[1]


# --- delete-object ---------------------------------------------------------


def test_an_object_deleted_by_emuplane_is_gone_from_ministack(s3_endpoint, console):
    raw = ministack(s3_endpoint)
    bucket = ensure_bucket(raw, "parity-delete-object-bucket")
    key = "parity/delete-by-emuplane.txt"
    assert 200 <= raw("PUT", f"/{bucket}/{key}", "temporary")[0] < 300

    status, body = action(console, "delete-object", {"Bucket": bucket, "Key": key})
    assert status == 200, body

    assert raw("GET", f"/{bucket}/{key}")[0] == 404
    assert key not in [row["key"] for row in objects(console, bucket)]


def test_an_object_deleted_on_ministack_is_gone_from_emuplane(s3_endpoint, console):
    raw = ministack(s3_endpoint)
    bucket = ensure_bucket(raw, "parity-delete-object-2-bucket")
    key = "parity/delete-on-ministack.txt"
    status, body = api(
        console,
        "POST",
        "/api/s3/object",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": bucket,
            "key": key,
            "body": "temporary",
        },
    )
    assert status == 200, body

    assert 200 <= raw("DELETE", f"/{bucket}/{key}")[0] < 300

    assert key not in [row["key"] for row in objects(console, bucket)]


# --- the catalogue this slice covers ---------------------------------------


# --- MFA delete ------------------------------------------------------------


def test_ministack_takes_mfa_delete_and_never_answers_it(s3_endpoint):
    """The premise Emuplane's own flag rests on: the endpoint accepts MfaDelete and drops it."""
    raw = ministack(s3_endpoint)
    name = ensure_bucket(raw, "parity-ministack-mfa")
    status, body = raw(
        "PUT",
        f"/{name}?versioning",
        '<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<Status>Enabled</Status><MfaDelete>Enabled</MfaDelete></VersioningConfiguration>",
    )
    assert 200 <= status < 300, body

    status, body = raw("GET", f"/{name}?versioning")
    assert 200 <= status < 300, body
    assert "<Status>Enabled</Status>" in body
    # If this ever comes back, the control's flag is redundant: drop the shim rather than keep two answers.
    assert "MfaDelete" not in body


def test_the_five_core_operations_are_console_actions():
    """The slice this suite starts with, and the ids the console runs them by."""
    ids = {item["id"] for item in console.CATALOGUE["s3"]["operations"]}
    assert {
        "create-bucket",
        "delete-bucket",
        "list-objects",
        "put-object",
        "delete-object",
    } <= ids
