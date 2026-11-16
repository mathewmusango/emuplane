"""One access point in full, from the section that owns it.

A listing is not a detail: a Multi-Region Access Point's listing carries neither
its policy nor its routing dials, and an Object Lambda access point's carries no
configuration. The page's row view reads the instance resources instead, and these
tests make those access points through the gateway — signed as a client signs —
and then check what the console reads back for them.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from conftest import ACCOUNT, api, s3

CONTROL_NS = "https://awss3control.amazonaws.com/doc/2018-08-20/"
MRAP = "api-mrap-detail"
LAMBDA = "api-olap-detail"
SUPPORT_BUCKET = "api-olap-detail-bucket"


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


def _detail(console, section: str, name: str, region: str = "us-east-1"):
    return api(
        console,
        "GET",
        f"/api/s3/access-point-detail?account={ACCOUNT}&region={region}"
        f"&section={section}&name={quote(name, safe='')}",
    )


def _mrap(gateway) -> None:
    """The Multi-Region access point over the two member buckets."""
    details = (
        f"<Name>{MRAP}</Name><Regions>"
        "<Region><Bucket>api-mrap-detail-east</Bucket></Region>"
        "<Region><Bucket>api-mrap-detail-west</Bucket></Region></Regions>"
    )
    body = (
        f'<CreateMultiRegionAccessPointRequest xmlns="{CONTROL_NS}">'
        f"<Details>{details}</Details></CreateMultiRegionAccessPointRequest>"
    )
    status, _headers, text = s3(
        gateway,
        "POST",
        "/v20180820/async-requests/mrap/create",
        body=body.encode(),
        headers={"x-amz-account-id": ACCOUNT},
        region="us-west-2",
    )
    assert status == 200, text


def _mrap_policy(gateway) -> str:
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3::{ACCOUNT}:accesspoint/{MRAP}.mrap/object/*",
                }
            ],
        }
    )
    body = (
        f'<PutMultiRegionAccessPointPolicyRequest xmlns="{CONTROL_NS}"><Details>'
        f"<Name>{MRAP}</Name><Policy>{policy}</Policy>"
        "</Details></PutMultiRegionAccessPointPolicyRequest>"
    )
    status, _headers, text = s3(
        gateway,
        "POST",
        "/v20180820/async-requests/mrap/put-policy",
        body=body.encode(),
        headers={"x-amz-account-id": ACCOUNT},
        region="us-west-2",
    )
    assert status == 200, text
    return policy


def _object_lambda(gateway) -> str:
    """A supporting access point, then the Object Lambda access point over it."""
    status, _headers, text = s3(
        gateway,
        "PUT",
        "/v20180820/accesspoint/api-olap-detail-support",
        body=(
            f'<CreateAccessPointRequest xmlns="{CONTROL_NS}">'
            f"<Bucket>{SUPPORT_BUCKET}</Bucket></CreateAccessPointRequest>"
        ).encode(),
        headers={"x-amz-account-id": ACCOUNT},
    )
    assert status in (200, 409), text

    configuration = (
        f'<PutAccessPointConfigurationForObjectLambdaRequest xmlns="{CONTROL_NS}">'
        "<Configuration>"
        f"<SupportingAccessPoint>arn:aws:s3:us-east-1:{ACCOUNT}:accesspoint/"
        "api-olap-detail-support</SupportingAccessPoint>"
        "<CloudWatchMetricsEnabled>false</CloudWatchMetricsEnabled>"
        "<TransformationConfigurations><TransformationConfiguration><Actions>"
        "<Action>GetObject</Action></Actions><ContentTransformation><AwsLambda>"
        f"<FunctionArn>arn:aws:lambda:us-east-1:{ACCOUNT}:function:api-olap-detail"
        "</FunctionArn></AwsLambda></ContentTransformation></TransformationConfiguration>"
        "</TransformationConfigurations></Configuration>"
        "</PutAccessPointConfigurationForObjectLambdaRequest>"
    )
    status, _headers, text = s3(
        gateway,
        "PUT",
        "/v20180820/accesspointforobjectlambda/" + LAMBDA,
        body=configuration.encode(),
        headers={"x-amz-account-id": ACCOUNT},
    )
    assert status == 200, text

    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3-object-lambda:GetObject",
                    "Resource": "*",
                }
            ],
        }
    )
    status, _headers, text = s3(
        gateway,
        "PUT",
        f"/v20180820/accesspointforobjectlambda/{LAMBDA}/policy",
        body=(
            f'<PutAccessPointPolicyForObjectLambdaRequest xmlns="{CONTROL_NS}">'
            f"<Policy>{policy}</Policy></PutAccessPointPolicyForObjectLambdaRequest>"
        ).encode(),
        headers={"x-amz-account-id": ACCOUNT},
    )
    assert status == 200, text
    return policy


def test_a_multi_region_access_point_reads_back_with_policy_and_routes(console, gateway):
    _bucket(console, "api-mrap-detail-east", "us-east-1")
    _bucket(console, "api-mrap-detail-west", "us-west-2")
    _mrap(gateway)
    policy = _mrap_policy(gateway)

    status, body = _detail(console, "multi-region", MRAP)
    assert status == 200, body
    assert body["name"] == MRAP
    # The alias is S3's own random name plus `.mrap`, and the ARN is built on it.
    assert body["alias"].endswith(".mrap")
    assert body["state"] == "READY"
    assert body["arn"] == f"arn:aws:s3::{ACCOUNT}:accesspoint/{body['alias']}"
    assert {(row["bucket"], row["region"]) for row in body["buckets"]} == {
        ("api-mrap-detail-east", "us-east-1"),
        ("api-mrap-detail-west", "us-west-2"),
    }

    assert json.loads(body["policy"]) == json.loads(policy)
    # The routing dials are their own read, addressed by the ARN the report implies.
    assert {row["bucket"] for row in body["routes"]} == {
        "api-mrap-detail-east",
        "api-mrap-detail-west",
    }
    assert all(row["traffic"] for row in body["routes"])
    assert body["errors"] == {}


def test_an_object_lambda_access_point_reads_back_with_configuration_and_policy(
    console, gateway
):
    _bucket(console, SUPPORT_BUCKET)
    policy = _object_lambda(gateway)

    status, body = _detail(console, "object-lambda", LAMBDA)
    assert status == 200, body
    assert body["name"] == LAMBDA
    assert body["state"] == "READY"
    assert body["alias"]
    # The configuration is the document S3 answers with, not a flattened form.
    assert "SupportingAccessPoint" in body["configuration"]
    assert "api-olap-detail-support" in body["configuration"]
    assert "GetObject" in body["configuration"]
    assert json.loads(body["policy"]) == json.loads(policy)
    assert body["errors"] == {}


def test_an_access_point_that_is_not_there_says_so(console):
    status, body = _detail(console, "multi-region", "no-such-mrap")
    assert status == 404
    assert body["ok"] is False
    assert body["error"]


def test_the_general_section_has_no_detail_here(console):
    status, body = _detail(console, "general", "api-point")
    assert status == 400
    assert "no detail view" in body["error"]


def test_a_detail_needs_a_name(console):
    status, body = api(
        console,
        "GET",
        f"/api/s3/access-point-detail?account={ACCOUNT}&region=us-east-1&section=multi-region",
    )
    assert status == 400
    assert "name is required" in body["error"]
