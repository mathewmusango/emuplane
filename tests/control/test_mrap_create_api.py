"""A Multi-Region access point made from the console: the create route makes and describes the async operation at once."""

from __future__ import annotations

from conftest import ACCOUNT, api

NAME = "api-mrap-create"
EAST = "api-mrap-create-east"
WEST = "api-mrap-create-west"


def _bucket(console, name: str, region: str = "us-east-1") -> None:
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        {
            "account": ACCOUNT,
            "region": region,
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
    assert status in (200, 400), body


def _create(
    console,
    name: str = NAME,
    buckets: tuple[str, ...] = (EAST, WEST),
    region: str = "us-east-1",
    account: str = ACCOUNT,
):
    return api(
        console,
        "POST",
        "/api/s3/mrap",
        {
            "account": account,
            "region": region,
            "name": name,
            "buckets": list(buckets),
        },
    )


def test_a_create_is_described_by_the_token_it_answers_with(console):
    _bucket(console, EAST, "us-east-1")
    _bucket(console, WEST, "us-west-2")

    status, body = _create(console)
    assert status == 200, body
    # `ok` is the request; `created` is the operation's own verdict.
    assert body["ok"] is True
    assert body["created"] is True
    assert body["name"] == NAME

    operation = body["operation"]
    assert operation["operation"] == "CreateMultiRegionAccessPoint"
    assert operation["status"] == "SUCCEEDED"
    # The token names the operation: created in us-west-2, where S3 Control serves Multi-Region management.
    assert operation["token"].startswith(
        f"arn:aws:s3:us-west-2:{ACCOUNT}:async-request/mrap/create/"
    )
    assert operation["name"] == NAME
    assert operation["buckets"] == [EAST, WEST]
    assert sorted(row["region"] for row in operation["results"]) == [
        "us-east-1",
        "us-west-2",
    ]
    assert {row["status"] for row in operation["results"]} == {"SUCCEEDED"}
    assert operation["error"] is None
    assert "error" not in body

    # And the listing the page reads carries the access point over both members.
    status, listing = api(
        console,
        "GET",
        f"/api/s3/access-points?account={ACCOUNT}&region=us-east-1&section=multi-region",
    )
    assert status == 200, listing
    row = next(point for point in listing["access_points"] if point["name"] == NAME)
    assert {(member["bucket"], member["region"]) for member in row["buckets"]} == {
        (EAST, "us-east-1"),
        (WEST, "us-west-2"),
    }


def test_a_failed_operation_reports_its_status_instead_of_a_created_access_point(console):
    _bucket(console, "api-mrap-missing-east", "us-east-1")

    status, body = _create(
        console,
        name="api-mrap-missing",
        buckets=("api-mrap-missing-east", "api-mrap-missing-west"),
    )
    assert status == 200, body
    # The request itself was accepted, so `ok` holds: the failure is the operation's.
    assert body["ok"] is True
    assert body["created"] is False
    assert body["operation"]["status"] == "FAILED"
    assert body["operation"]["error"]["code"] == "NoSuchBucket"
    assert body["operation"]["error"]["message"] == "The specified bucket does not exist."
    assert body["operation"]["results"] == []
    assert "NoSuchBucket" in body["error"]


def test_two_members_in_one_region_are_refused_by_the_operation(console):
    _bucket(console, "api-mrap-same-region-a", "us-east-1")
    _bucket(console, "api-mrap-same-region-b", "us-east-1")

    status, body = _create(
        console,
        name="api-mrap-same-region",
        buckets=("api-mrap-same-region-a", "api-mrap-same-region-b"),
    )
    assert status == 200, body
    assert body["created"] is False
    assert body["operation"]["error"]["code"] == "MultiRegionAccessPointSameBucketRegion"


def test_a_create_needs_a_usable_name_and_two_members(console):
    for payload, expected in (
        ({"name": "Bad Name", "buckets": [EAST, WEST]}, "Access point names are 3 to 50"),
        ({"name": "api-mrap-one-member", "buckets": [EAST]}, "at least two Regions"),
        ({"name": "api-mrap-no-member", "buckets": []}, "at least two Regions"),
    ):
        status, body = api(
            console,
            "POST",
            "/api/s3/mrap",
            dict(payload, account=ACCOUNT, region="us-east-1"),
        )
        assert status == 400, body
        assert body["ok"] is False
        assert expected in body["error"]


def test_a_create_is_refused_for_an_unknown_account(console):
    status, body = _create(console, account="999999999999")
    assert status == 404
    assert "unknown account" in body["error"]


def test_a_create_is_refused_in_a_region_the_account_has_not_enabled(console):
    status, body = _create(console, region="eu-central-1")
    assert status == 403
    assert "eu-central-1" in body["error"]
