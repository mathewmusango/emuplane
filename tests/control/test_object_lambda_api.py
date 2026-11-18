"""The Object Lambda console API: create, replace the configuration, delete, and every refusal."""

from __future__ import annotations

from urllib.parse import quote

from conftest import ACCOUNT, api, s3

CONTROL_NS = "https://awss3control.amazonaws.com/doc/2018-08-20/"
BUCKET = "api-olap-api-bucket"
SUPPORT_AP = "api-olap-api-support"
SUPPORT_ARN = f"arn:aws:s3:us-east-1:{ACCOUNT}:accesspoint/{SUPPORT_AP}"
FUNCTION = f"arn:aws:lambda:us-east-1:{ACCOUNT}:function:api-olap-api"


def _bucket(console, name: str = BUCKET) -> None:
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
    assert status in (200, 400), body


def _supporting(gateway) -> None:
    """The general purpose access point an Object Lambda access point has to read through."""
    body = (
        f'<CreateAccessPointRequest xmlns="{CONTROL_NS}">'
        f"<Bucket>{BUCKET}</Bucket></CreateAccessPointRequest>"
    )
    status, _headers, text = s3(
        gateway,
        "PUT",
        f"/v20180820/accesspoint/{SUPPORT_AP}",
        body=body.encode(),
        headers={"x-amz-account-id": ACCOUNT},
    )
    assert status in (200, 409), text


def _payload(name: str, **overrides) -> dict:
    payload = {
        "account": ACCOUNT,
        "region": "us-east-1",
        "name": name,
        "supporting_access_point": SUPPORT_ARN,
        "function_arn": FUNCTION,
        "actions": ["GetObject", "HeadObject"],
        "cloudwatch_metrics": True,
    }
    payload.update(overrides)
    return payload


def _create(console, name: str, **overrides):
    return api(console, "POST", "/api/s3/object-lambda", _payload(name, **overrides))


def _detail(console, name: str):
    return api(
        console,
        "GET",
        f"/api/s3/access-point-detail?account={ACCOUNT}&region=us-east-1"
        f"&section=object-lambda&name={quote(name, safe='')}",
    )


def _configuration(name: str, function: str = FUNCTION) -> str:
    return (
        "<Configuration>"
        f"<SupportingAccessPoint>{SUPPORT_ARN}</SupportingAccessPoint>"
        "<CloudWatchMetricsEnabled>false</CloudWatchMetricsEnabled>"
        "<TransformationConfigurations><TransformationConfiguration>"
        "<Actions><Action>GetObject</Action></Actions>"
        "<ContentTransformation><AwsLambda>"
        f"<FunctionArn>{function}</FunctionArn>"
        "</AwsLambda></ContentTransformation>"
        "</TransformationConfiguration></TransformationConfigurations>"
        "</Configuration>"
    )


def test_a_created_object_lambda_access_point_reads_back(console, gateway):
    _bucket(console)
    _supporting(gateway)

    status, body = _create(console, "api-olap-created")
    assert status == 200, body
    assert body["name"] == "api-olap-created"
    assert body["created"] is True

    status, detail = _detail(console, "api-olap-created")
    assert status == 200, detail
    assert detail["state"] == "READY"
    assert detail["alias"]
    assert SUPPORT_ARN in detail["configuration"]
    assert FUNCTION in detail["configuration"]
    assert "GetObject" in detail["configuration"]
    assert "HeadObject" in detail["configuration"]
    assert detail["policy"] is None
    assert detail["errors"] == {}


def test_a_duplicate_name_is_refused_with_the_reason(console, gateway):
    _bucket(console)
    _supporting(gateway)
    assert _create(console, "api-olap-twice")[0] == 200

    status, body = _create(console, "api-olap-twice")
    assert status == 400
    assert "AccessPointAlreadyOwnedByYou" in body["error"]


def test_the_form_refuses_a_bad_name(console, gateway):
    _bucket(console)
    _supporting(gateway)

    status, body = _create(console, "Bad_Name")
    assert status == 400
    assert "lowercase" in body["error"]


def test_the_form_refuses_a_missing_supporting_access_point(console, gateway):
    _bucket(console)
    _supporting(gateway)

    status, body = _create(console, "api-olap-no-support", supporting_access_point="")
    assert status == 400
    assert "supporting" in body["error"].lower() or "Choose" in body["error"]


def test_the_form_refuses_an_invalid_function_arn(console, gateway):
    _bucket(console)
    _supporting(gateway)

    status, body = _create(console, "api-olap-bad-function", function_arn="not-an-arn")
    assert status == 400
    assert "Lambda function ARN" in body["error"]


def test_the_form_refuses_an_unknown_action(console, gateway):
    _bucket(console)
    _supporting(gateway)

    status, body = _create(
        console, "api-olap-bad-action", actions=["GetObject", "DeleteObject"]
    )
    assert status == 400
    assert "GetObject and HeadObject" in body["error"]


def test_the_emulator_refuses_a_supporting_access_point_that_is_not_there(
    console, gateway
):
    _bucket(console)
    _supporting(gateway)

    status, body = _create(
        console,
        "api-olap-ghost-support",
        supporting_access_point=f"arn:aws:s3:us-east-1:{ACCOUNT}:accesspoint/not-there",
    )
    assert status == 400
    assert body["ok"] is False
    assert body["error"]


def test_the_configuration_is_replaced_from_the_details_view(console, gateway):
    _bucket(console)
    _supporting(gateway)
    assert _create(console, "api-olap-config")[0] == 200

    replacement = _configuration(
        "api-olap-config",
        f"arn:aws:lambda:us-east-1:{ACCOUNT}:function:api-olap-config-v2",
    )
    status, body = api(
        console,
        "POST",
        "/api/s3/object-lambda-configuration",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "name": "api-olap-config",
            "configuration": replacement,
        },
    )
    assert status == 200, body

    status, detail = _detail(console, "api-olap-config")
    assert status == 200, detail
    assert "api-olap-config-v2" in detail["configuration"]
    # The replacement dropped HeadObject, and the read shows exactly that.
    assert "HeadObject" not in detail["configuration"]


def test_a_configuration_that_is_not_xml_is_refused(console, gateway):
    _bucket(console)
    _supporting(gateway)
    assert _create(console, "api-olap-bad-config")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/object-lambda-configuration",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "name": "api-olap-bad-config",
            "configuration": "not xml",
        },
    )
    assert status == 400
    assert "not XML" in body["error"]


def test_a_configuration_without_the_supporting_access_point_is_refused(console, gateway):
    _bucket(console)
    _supporting(gateway)
    assert _create(console, "api-olap-no-support-config")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/object-lambda-configuration",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "name": "api-olap-no-support-config",
            "configuration": "<Configuration><CloudWatchMetricsEnabled>true"
            "</CloudWatchMetricsEnabled></Configuration>",
        },
    )
    assert status == 400
    assert "SupportingAccessPoint" in body["error"]


def test_a_configuration_needs_a_lambda_function(console, gateway):
    _bucket(console)
    _supporting(gateway)
    assert _create(console, "api-olap-no-function")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/object-lambda-configuration",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "name": "api-olap-no-function",
            "configuration": "<Configuration>"
            f"<SupportingAccessPoint>{SUPPORT_ARN}</SupportingAccessPoint>"
            "<TransformationConfigurations>"
            "<TransformationConfiguration><Actions><Action>GetObject</Action>"
            "</Actions></TransformationConfiguration>"
            "</TransformationConfigurations></Configuration>",
        },
    )
    assert status == 400
    assert "FunctionArn" in body["error"]


def test_the_access_point_can_be_deleted(console, gateway):
    _bucket(console)
    _supporting(gateway)
    assert _create(console, "api-olap-gone")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/object-lambda-delete",
        {"account": ACCOUNT, "region": "us-east-1", "name": "api-olap-gone"},
    )
    assert status == 200, body
    assert body["name"] == "api-olap-gone"

    status, _detail_body = _detail(console, "api-olap-gone")
    assert status == 404


def test_a_delete_needs_a_name(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/object-lambda-delete",
        {"account": ACCOUNT, "region": "us-east-1", "name": ""},
    )
    assert status == 400
    assert "name is required" in body["error"]


def test_a_delete_in_a_missing_region_is_refused(console, gateway):
    _bucket(console)
    _supporting(gateway)
    status, body = _create(console, "api-olap-off-region", region="eu-central-1")
    assert status == 403
    assert "not enabled" in body["error"]
