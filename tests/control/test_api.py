"""The control's own S3 API — what the console's pages call.

These run the real `ControlHandler` behind a real socket, authenticated with the
deployment's bearer token, and check the answers the pages rely on.
"""

from __future__ import annotations

from conftest import ACCOUNT, api, s3

PUBLIC_ACCESS = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}


def page(**overrides) -> dict:
    """Exactly what the create page posts, with one field varied."""
    payload = {
        "account": ACCOUNT,
        "region": "us-east-1",
        "namespace": "global",
        "ownership": "BucketOwnerEnforced",
        "block_public_access": PUBLIC_ACCESS,
        "versioning": False,
        "tags": [],
        "encryption": "AES256",
        "bucket_key": True,
        "object_lock": False,
    }
    payload.update(overrides)
    return payload


def test_create_needs_a_name(console):
    status, body = api(console, "POST", "/api/s3/buckets", page(bucket=""))
    assert status == 400
    assert "name is required" in body["error"]


def test_create_refuses_a_region_the_account_has_not_enabled(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="api-off-region-bucket", region="eu-central-1"),
    )
    assert status == 403
    assert "not enabled" in body["error"]


def test_create_answers_the_name_the_server_composed(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="api-regional-bucket", namespace="regional"),
    )
    assert status == 200, body
    assert body["bucket"] == f"api-regional-bucket.{ACCOUNT}-us-east-1-an"
    assert body["created"] is True


def test_a_name_held_in_another_region_is_refused(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="api-dup-bucket"))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="api-dup-bucket", region="us-west-2"),
    )
    assert status == 409
    assert "already exists" in body["error"]


def test_a_browse_row_carries_the_bucket_own_region(console):
    assert (
        api(
            console,
            "POST",
            "/api/s3/buckets",
            page(bucket="api-west-row-bucket", region="us-west-2"),
        )[0]
        == 200
    )

    status, body = api(
        console, "GET", f"/api/browse?account={ACCOUNT}&region=all&service=s3"
    )
    assert status == 200
    regions = {row["name"]: row.get("region") for row in body["resources"]}
    # The listing is account-wide, so the row must report the bucket's own region
    # rather than the one it was asked in.
    assert regions["api-west-row-bucket"] == "us-west-2"


def test_the_child_listings_answer(console):
    for section in ("table-buckets", "file-systems"):
        status, body = api(
            console, "GET", f"/api/s3/{section}?account={ACCOUNT}&region=us-east-1"
        )
        assert status == 200, body
        assert body["ok"] is True
        assert isinstance(body["items"], list)


def test_an_object_written_through_the_gateway_is_readable_in_the_console(
    console, gateway
):
    name = "api-object-bucket"
    assert s3(gateway, "PUT", f"/{name}")[0] == 200
    assert s3(gateway, "PUT", f"/{name}/notes/hello.txt", body=b"hi")[0] == 200

    status, body = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert status == 200, body
    assert [item["key"] for item in body["objects"]] == ["notes/hello.txt"]


def test_objects_are_read_in_the_bucket_own_region(console):
    """A bucket is signed for its own region; elsewhere is a 301 naming it."""
    name = "api-west-objects-bucket"
    assert (
        api(console, "POST", "/api/s3/buckets", page(bucket=name, region="us-west-2"))[0]
        == 200
    )

    status, body = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert status == 301
    assert "us-west-2" in body["error"]
    assert body["region"] == "us-west-2"

    # And the right region is served.
    status, body = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-west-2&bucket={name}",
    )
    assert status == 200, body
