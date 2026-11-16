"""The other Multi-Region writes: delete, policy, and the traffic dials.

DeleteMultiRegionAccessPoint and PutMultiRegionAccessPointPolicy answer with a
request token like the create does, so the control describes their operations the
same way. SubmitMultiRegionAccessPointRoutes is the exception: S3 answers it
synchronously, so its result is read back from the access point's own routes.
"""

from __future__ import annotations

import json

from conftest import ACCOUNT, api

EAST = "api-mrap-act-east"
WEST = "api-mrap-act-west"


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


def _create(console, name: str):
    _bucket(console, EAST, "us-east-1")
    _bucket(console, WEST, "us-west-2")
    status, body = api(
        console,
        "POST",
        "/api/s3/mrap",
        {"account": ACCOUNT, "region": "us-east-1", "name": name, "buckets": [EAST, WEST]},
    )
    assert status == 200, body
    assert body["created"] is True, body
    return body


def _delete(console, name: str):
    return api(
        console,
        "POST",
        "/api/s3/mrap-delete",
        {"account": ACCOUNT, "region": "us-east-1", "name": name},
    )


def _policy(console, name: str, policy):
    return api(
        console,
        "POST",
        "/api/s3/mrap-policy",
        {"account": ACCOUNT, "region": "us-east-1", "name": name, "policy": policy},
    )


def _routes(console, arn: str, routes: list[dict]):
    return api(
        console,
        "POST",
        "/api/s3/mrap-routes",
        {"account": ACCOUNT, "region": "us-east-1", "arn": arn, "routes": routes},
    )


def _detail(console, name: str):
    return api(
        console,
        "GET",
        f"/api/s3/access-point-detail?account={ACCOUNT}&region=us-east-1"
        f"&section=multi-region&name={name}",
    )


def _json_policy(name: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3::{ACCOUNT}:accesspoint/{name}.mrap/object/*",
                }
            ],
        }
    )


def test_a_delete_is_described_by_its_operation_and_the_access_point_goes(console):
    _create(console, "api-mrap-act-gone")

    status, body = _delete(console, "api-mrap-act-gone")
    assert status == 200, body
    assert body["ok"] is True
    assert body["created"] is True
    assert body["operation"]["operation"] == "DeleteMultiRegionAccessPoint"
    assert body["operation"]["status"] == "SUCCEEDED"
    assert body["operation"]["results"]

    status, gone = _detail(console, "api-mrap-act-gone")
    assert status == 404
    assert gone["ok"] is False

    _, listing = api(
        console,
        "GET",
        f"/api/s3/access-points?account={ACCOUNT}&region=us-east-1&section=multi-region",
    )
    assert "api-mrap-act-gone" not in [row["name"] for row in listing["access_points"]]


def test_deleting_one_that_is_not_there_is_a_failed_operation(console):
    status, body = _delete(console, "api-mrap-act-nowhere")
    assert status == 200, body
    assert body["ok"] is True
    assert body["created"] is False
    assert body["operation"]["status"] == "FAILED"
    assert body["operation"]["error"]["code"] == "NoSuchMultiRegionAccessPoint"
    assert "NoSuchMultiRegionAccessPoint" in body["error"]


def test_the_policy_is_written_by_an_operation_and_read_back(console):
    _create(console, "api-mrap-act-policy")
    document = _json_policy("api-mrap-act-policy")

    status, body = _policy(console, "api-mrap-act-policy", document)
    assert status == 200, body
    assert body["created"] is True
    assert body["operation"]["operation"] == "PutMultiRegionAccessPointPolicy"
    assert body["operation"]["status"] == "SUCCEEDED"

    status, read = api(
        console,
        "GET",
        f"/api/s3/access-point-policy?account={ACCOUNT}&region=us-east-1"
        "&section=multi-region&name=api-mrap-act-policy",
    )
    assert status == 200, read
    assert json.loads(read["policy"]) == json.loads(document)

    # The detail pane's own read agrees: one policy, two readers.
    status, detail = _detail(console, "api-mrap-act-policy")
    assert status == 200, detail
    assert json.loads(detail["policy"]) == json.loads(document)


def test_a_policy_that_is_not_a_document_is_refused_before_the_call(console):
    _create(console, "api-mrap-act-bad-policy")

    status, body = _policy(console, "api-mrap-act-bad-policy", "{not json")
    assert status == 400
    assert "not JSON" in body["error"]

    status, body = _policy(console, "api-mrap-act-bad-policy", '{"Version": "2012-10-17"}')
    assert status == 400
    assert "Statement" in body["error"]

    # S3 Control has no Delete for a Multi-Region policy, so an empty document is
    # refused rather than sent as a request that would keep the old policy.
    status, body = _policy(console, "api-mrap-act-bad-policy", None)
    assert status == 400
    assert "replaced, not removed" in body["error"]


def test_traffic_dials_are_submitted_and_read_back(console):
    made = _create(console, "api-mrap-act-routes")
    _, detail = _detail(console, "api-mrap-act-routes")
    arn = detail["arn"]
    assert {row["bucket"]: row["traffic"] for row in detail["routes"]} == {
        EAST: "100",
        WEST: "100",
    }

    status, body = _routes(
        console, arn, [{"bucket": EAST, "traffic": "0"}, {"bucket": WEST, "traffic": "100"}]
    )
    assert status == 200, body
    assert body["ok"] is True
    assert body["arn"] == arn

    _, detail = _detail(console, "api-mrap-act-routes")
    assert {row["bucket"]: row["traffic"] for row in detail["routes"]} == {
        EAST: "0",
        WEST: "100",
    }

    # Every member switched off is the update S3 refuses, with its own sentence.
    status, body = _routes(
        console, arn, [{"bucket": EAST, "traffic": "0"}, {"bucket": WEST, "traffic": "0"}]
    )
    assert status == 400
    assert "At least one Region or bucket" in body["error"]

    # And the dials stay as they were: a refused update changes nothing.
    _, detail = _detail(console, "api-mrap-act-routes")
    assert {row["bucket"]: row["traffic"] for row in detail["routes"]}[WEST] == "100"

    assert made["created"] is True


def test_a_dial_outside_the_two_states_is_refused(console):
    _create(console, "api-mrap-act-dial")
    _, detail = _detail(console, "api-mrap-act-dial")

    status, body = _routes(console, detail["arn"], [{"bucket": EAST, "traffic": "50"}])
    assert status == 400
    assert "0 (Inactive) or 100 (Active)" in body["error"]

    # The routes are addressed by the access point's ARN, not by its name.
    status, body = _routes(console, "api-mrap-act-dial", [{"bucket": EAST, "traffic": "100"}])
    assert status == 400
    assert "ARN" in body["error"]


def test_the_guards_are_the_access_point_pages_own(console):
    status, _body = api(
        console,
        "POST",
        "/api/s3/mrap-delete",
        {"account": "999999999999", "region": "us-east-1", "name": "api-mrap-act-gone"},
    )
    assert status == 404

    status, body = api(
        console,
        "POST",
        "/api/s3/mrap-policy",
        {
            "account": ACCOUNT,
            "region": "eu-central-1",
            "name": "api-mrap-act-gone",
            "policy": _json_policy("api-mrap-act-gone"),
        },
    )
    assert status == 403
    assert "eu-central-1" in body["error"]

    status, body = api(
        console,
        "POST",
        "/api/s3/mrap-routes",
        {"account": ACCOUNT, "region": "us-east-1", "arn": "", "routes": []},
    )
    assert status == 400
    assert "ARN" in body["error"]
