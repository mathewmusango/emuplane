"""Every S3 operation the console does not drive, exercised on the wire.

The console covers part of S3; this module is the other part's proof. It exists
because the rule is that every operation the emulator advertises has a test that
runs on every run — not "the emulator's own suite covers it". A future operation
cannot slip in without one: `tests/s3/test_ledger.py` fails when a row names no
test.

Nothing here is cleaned up — buckets, objects and access points stay — except
where the operation itself is the delete.

Grouped as S3 groups them: bucket configuration, multipart, object tagging,
annotations, Object Lock, Multi-Region access points, Object Lambda.
"""

from __future__ import annotations

import base64
import json
import re
from urllib.parse import quote

import buckets
import signed

ACCOUNT = "344381301567"
location_constraint = buckets.location_constraint
S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"
CONTROL_NS = "https://awss3control.amazonaws.com/doc/2018-08-20/"


def call(endpoint, method, path, body="", headers=None, region="us-east-1"):
    """One signed request, answered `(status, text)`."""
    return signed.request(endpoint, "s3", ACCOUNT, region, method, path, body, headers)


def raw(endpoint, method, path, body="", headers=None, region="us-east-1"):
    """The same, answering `(status, headers, body)` — for an ETag or a version id."""
    return signed.request_bytes(
        endpoint, "s3", ACCOUNT, region, method, path, body, headers
    )


def bucket(endpoint, name, region="us-east-1", **headers):
    status, body = call(
        endpoint, "PUT", f"/{name}", location_constraint(region), headers or None, region
    )
    # 409 is a bucket an earlier case already made: these tests leave them behind.
    assert status in (200, 409), (status, body)
    return name


def put(endpoint, bucket_name, key, body="x", region="us-east-1"):
    status, text = call(endpoint, "PUT", f"/{bucket_name}/{key}", body, None, region)
    assert 200 <= status < 300, (status, text)


# ---------------------------------------------------------------------------
# Bucket configuration the console does not write
# ---------------------------------------------------------------------------


def test_put_bucket_logging_then_it_is_reported(s3_endpoint):
    bucket(s3_endpoint, "ops-logging-bucket")
    body = (
        f'<BucketLoggingStatus xmlns="{S3_NS}"><LoggingEnabled>'
        "<TargetBucket>ops-logging-bucket</TargetBucket><TargetPrefix>logs/</TargetPrefix>"
        "</LoggingEnabled></BucketLoggingStatus>"
    )
    status, text = call(s3_endpoint, "PUT", "/ops-logging-bucket?logging", body)
    assert 200 <= status < 300, (status, text)

    status, text = call(s3_endpoint, "GET", "/ops-logging-bucket?logging")
    assert status == 200
    assert "TargetBucket" in text


def test_put_bucket_notification_configuration_takes_an_eventbridge_rule(s3_endpoint):
    """EventBridge is a notification target S3 accepts without a queue to create."""
    bucket(s3_endpoint, "ops-notification-bucket")
    body = (
        f'<NotificationConfiguration xmlns="{S3_NS}">'
        "<EventBridgeConfiguration/></NotificationConfiguration>"
    )
    status, text = call(s3_endpoint, "PUT", "/ops-notification-bucket?notification", body)
    assert 200 <= status < 300, (status, text)

    status, text = call(s3_endpoint, "GET", "/ops-notification-bucket?notification")
    assert status == 200
    assert "EventBridgeConfiguration" in text


def test_put_bucket_replication_needs_versioning_and_names_a_destination(s3_endpoint):
    bucket(s3_endpoint, "ops-replication-bucket")
    versioning = (
        f'<VersioningConfiguration xmlns="{S3_NS}"><Status>Enabled</Status>'
        "</VersioningConfiguration>"
    )
    assert call(s3_endpoint, "PUT", "/ops-replication-bucket?versioning", versioning)[0] == 200

    body = (
        f'<ReplicationConfiguration xmlns="{S3_NS}">'
        f"<Role>arn:aws:iam::{ACCOUNT}:role/replication</Role>"
        "<Rule><Status>Enabled</Status><Priority>1</Priority><Filter><Prefix>data/</Prefix></Filter>"
        "<Destination><Bucket>arn:aws:s3:::ops-replication-target</Bucket></Destination>"
        "</Rule></ReplicationConfiguration>"
    )
    status, text = call(s3_endpoint, "PUT", "/ops-replication-bucket?replication", body)
    assert 200 <= status < 300, (status, text)

    status, text = call(s3_endpoint, "GET", "/ops-replication-bucket?replication")
    assert status == 200
    assert "role/replication" in text


def test_delete_bucket_replication_removes_it(s3_endpoint):
    status, _ = call(s3_endpoint, "DELETE", "/ops-replication-bucket?replication")
    assert 200 <= status < 300
    status, _ = call(s3_endpoint, "GET", "/ops-replication-bucket?replication")
    assert status == 404


def test_delete_public_access_block_removes_the_configuration(s3_endpoint):
    bucket(s3_endpoint, "ops-pab-bucket")
    body = (
        f'<PublicAccessBlockConfiguration xmlns="{S3_NS}">'
        "<BlockPublicAcls>false</BlockPublicAcls>"
        "<IgnorePublicAcls>false</IgnorePublicAcls>"
        "<BlockPublicPolicy>false</BlockPublicPolicy>"
        "<RestrictPublicBuckets>false</RestrictPublicBuckets>"
        "</PublicAccessBlockConfiguration>"
    )
    assert 200 <= call(s3_endpoint, "PUT", "/ops-pab-bucket?publicAccessBlock", body)[0] < 300

    status, _ = call(s3_endpoint, "DELETE", "/ops-pab-bucket?publicAccessBlock")
    assert 200 <= status < 300
    assert call(s3_endpoint, "GET", "/ops-pab-bucket?publicAccessBlock")[0] == 404


# ---------------------------------------------------------------------------
# Multipart upload
# ---------------------------------------------------------------------------


def _initiate(endpoint, bucket_name, key):
    status, text = call(
        endpoint, "POST", f"/{bucket_name}/{key}?uploads", "", {"Content-Type": "application/xml"}
    )
    assert status == 200, (status, text)
    found = re.search(r"<UploadId>(.*?)</UploadId>", text, re.S)
    assert found, text
    return found.group(1)


def test_multipart_upload_create_part_complete_and_read(s3_endpoint):
    bucket(s3_endpoint, "ops-multipart-bucket")
    key = "large/blob.bin"
    upload_id = _initiate(s3_endpoint, "ops-multipart-bucket", key)

    status, headers, _ = raw(
        s3_endpoint, "PUT", f"/ops-multipart-bucket/{key}?partNumber=1&uploadId={upload_id}", "part-one"
    )
    assert status == 200, status
    etag = headers.get("etag", "")
    assert etag

    complete = (
        f'<CompleteMultipartUpload xmlns="{S3_NS}"><Part>'
        f"<PartNumber>1</PartNumber><ETag>{etag}</ETag>"
        "</Part></CompleteMultipartUpload>"
    )
    status, text = call(
        s3_endpoint, "POST", f"/ops-multipart-bucket/{key}?uploadId={upload_id}", complete
    )
    assert status == 200, (status, text)

    status, text = call(s3_endpoint, "GET", f"/ops-multipart-bucket/{key}")
    assert status == 200
    assert text == "part-one"


def test_abort_multipart_upload_discards_the_parts(s3_endpoint):
    key = "large/aborted.bin"
    upload_id = _initiate(s3_endpoint, "ops-multipart-bucket", key)
    assert raw(
        s3_endpoint, "PUT", f"/ops-multipart-bucket/{key}?partNumber=1&uploadId={upload_id}", "x"
    )[0] == 200

    status, _ = call(
        s3_endpoint, "DELETE", f"/ops-multipart-bucket/{key}?uploadId={upload_id}"
    )
    assert 200 <= status < 300
    assert call(s3_endpoint, "GET", f"/ops-multipart-bucket/{key}")[0] == 404


# ---------------------------------------------------------------------------
# Object tagging
# ---------------------------------------------------------------------------


def test_object_tags_are_put_read_and_deleted(s3_endpoint):
    bucket(s3_endpoint, "ops-object-tags-bucket")
    put(s3_endpoint, "ops-object-tags-bucket", "tagged.txt")

    tagging = (
        f'<Tagging xmlns="{S3_NS}"><TagSet>'
        "<Tag><Key>stage</Key><Value>prod</Value></Tag>"
        "</TagSet></Tagging>"
    )
    status, text = call(
        s3_endpoint, "PUT", "/ops-object-tags-bucket/tagged.txt?tagging", tagging
    )
    assert 200 <= status < 300, (status, text)

    status, text = call(s3_endpoint, "GET", "/ops-object-tags-bucket/tagged.txt?tagging")
    assert status == 200
    assert "stage" in text and "prod" in text

    status, _ = call(s3_endpoint, "DELETE", "/ops-object-tags-bucket/tagged.txt?tagging")
    assert 200 <= status < 300
    status, text = call(s3_endpoint, "GET", "/ops-object-tags-bucket/tagged.txt?tagging")
    assert status == 200
    assert "<Tag>" not in text


# ---------------------------------------------------------------------------
# Object annotations
# ---------------------------------------------------------------------------


def test_object_annotations_are_put_listed_read_and_deleted(s3_endpoint):
    bucket(s3_endpoint, "ops-annotations-bucket")
    put(s3_endpoint, "ops-annotations-bucket", "annotated.txt")

    path = "/ops-annotations-bucket/annotated.txt?annotation&annotationName=note"
    status, text = call(s3_endpoint, "PUT", path, "hello annotation")
    assert 200 <= status < 300, (status, text)

    status, text = call(s3_endpoint, "GET", path)
    assert status == 200
    assert text == "hello annotation"

    status, text = call(
        s3_endpoint, "GET", "/ops-annotations-bucket/annotated.txt?annotation"
    )
    assert status == 200
    assert "note" in text

    status, _ = call(s3_endpoint, "DELETE", path)
    assert 200 <= status < 300
    assert call(s3_endpoint, "GET", path)[0] == 404


# ---------------------------------------------------------------------------
# Object Lock: retention and legal hold
# ---------------------------------------------------------------------------


def _locked_object(endpoint, bucket_name, key):
    """An object-lock bucket, a versioned object in it, and the version id."""
    status, text = call(
        endpoint,
        "PUT",
        f"/{bucket_name}",
        "",
        {"x-amz-bucket-object-lock-enabled": "true"},
    )
    assert 200 <= status < 300, (status, text)
    status, headers, _ = raw(endpoint, "PUT", f"/{bucket_name}/{key}", "locked")
    assert status == 200, status
    version = headers.get("x-amz-version-id", "")
    assert version, headers
    return version


def test_object_retention_is_put_and_read(s3_endpoint):
    version = _locked_object(s3_endpoint, "ops-retention-bucket", "held.txt")
    body = (
        f'<Retention xmlns="{S3_NS}"><Mode>GOVERNANCE</Mode>'
        "<RetainUntilDate>2030-01-01T00:00:00Z</RetainUntilDate></Retention>"
    )
    path = f"/ops-retention-bucket/held.txt?retention&versionId={version}"
    status, text = call(s3_endpoint, "PUT", path, body)
    assert 200 <= status < 300, (status, text)

    status, text = call(s3_endpoint, "GET", path)
    assert status == 200
    assert "GOVERNANCE" in text and "2030-01-01" in text


def test_object_legal_hold_is_put_and_read(s3_endpoint):
    version = _locked_object(s3_endpoint, "ops-legal-hold-bucket", "held.txt")
    body = f'<LegalHold xmlns="{S3_NS}"><Status>ON</Status></LegalHold>'
    path = f"/ops-legal-hold-bucket/held.txt?legal-hold&versionId={version}"
    status, text = call(s3_endpoint, "PUT", path, body)
    assert 200 <= status < 300, (status, text)

    status, text = call(s3_endpoint, "GET", path)
    assert status == 200
    assert "ON" in text


# ---------------------------------------------------------------------------
# Multi-Region access points
# ---------------------------------------------------------------------------


def _mrap(endpoint):
    """Two member buckets in different regions, and the MRAP management region."""
    bucket(endpoint, "ops-mrap-east", "us-east-1")
    bucket(endpoint, "ops-mrap-west", "us-west-2")
    return "us-west-2"


def _async(endpoint, operation, details, region):
    body = (
        f'<{operation}Request xmlns="{CONTROL_NS}"><Details>{details}</Details>'
        f"</{operation}Request>"
    )
    status, text = call(
        endpoint, "POST", f"/v20180820/async-requests/mrap/{operation_hint(operation)}", body,
        {"x-amz-account-id": ACCOUNT}, region,
    )
    return status, text


def operation_hint(operation):
    return {
        "CreateMultiRegionAccessPoint": "create",
        "DeleteMultiRegionAccessPoint": "delete",
        "PutMultiRegionAccessPointPolicy": "put-policy",
    }[operation]


def _token(text):
    found = re.search(r"<RequestTokenARN>(.*?)</RequestTokenARN>", text, re.S)
    assert found, text
    return found.group(1)


def _create_mrap(endpoint, name):
    region = _mrap(endpoint)
    details = (
        f"<Name>{name}</Name><Regions>"
        "<Region><Bucket>ops-mrap-east</Bucket></Region>"
        "<Region><Bucket>ops-mrap-west</Bucket></Region></Regions>"
    )
    status, text = _async(endpoint, "CreateMultiRegionAccessPoint", details, region)
    assert status == 200, (status, text)
    return region, _token(text)


def test_mrap_create_and_describe_the_operation(s3_endpoint):
    region, token = _create_mrap(s3_endpoint, "ops-mrap")

    path = "/v20180820/async-requests/mrap/" + quote(token, safe="")
    status, text = call(
        s3_endpoint, "GET", path, "", {"x-amz-account-id": ACCOUNT}, region
    )
    assert status == 200, (status, text)
    assert "<Name>ops-mrap</Name>" in text
    assert "SUCCEEDED" in text


def test_mrap_is_read_back_policy_put_and_read(s3_endpoint):
    region, _token_arn = _create_mrap(s3_endpoint, "ops-mrap-read")

    status, text = call(
        s3_endpoint, "GET", "/v20180820/mrap/instances/ops-mrap-read", "",
        {"x-amz-account-id": ACCOUNT}, region,
    )
    assert status == 200, (status, text)
    assert "READY" in text and ".mrap" in text

    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3::{ACCOUNT}:accesspoint/ops-mrap-read.mrap/object/*",
                }
            ],
        }
    )
    details = f"<Name>ops-mrap-read</Name><Policy>{policy}</Policy>"
    status, text = _async(s3_endpoint, "PutMultiRegionAccessPointPolicy", details, region)
    assert status == 200, (status, text)

    status, text = call(
        s3_endpoint, "GET", "/v20180820/mrap/instances/ops-mrap-read/policy", "",
        {"x-amz-account-id": ACCOUNT}, region,
    )
    assert status == 200, (status, text)
    assert "Established" in text


def test_mrap_routes_are_read_and_submitted(s3_endpoint):
    region, _token_arn = _create_mrap(s3_endpoint, "ops-mrap-routes")
    status, text = call(
        s3_endpoint, "GET", "/v20180820/mrap/instances/ops-mrap-routes", "",
        {"x-amz-account-id": ACCOUNT}, region,
    )
    alias = re.search(r"<Alias>(.*?)</Alias>", text, re.S).group(1)
    arn = f"arn:aws:s3::{ACCOUNT}:accesspoint/{alias}"

    status, text = call(
        s3_endpoint, "GET", f"/v20180820/mrap/instances/{arn}/routes".replace("arn:", "arn:"),
        "", {"x-amz-account-id": ACCOUNT}, region,
    )
    assert status == 200, (status, text)
    assert "TrafficDialPercentage" in text

    update = (
        f'<SubmitMultiRegionAccessPointRoutesRequest xmlns="{CONTROL_NS}"><Mrap>{arn}</Mrap>'
        "<RouteUpdates><Route><Bucket>ops-mrap-east</Bucket>"
        "<TrafficDialPercentage>0</TrafficDialPercentage></Route></RouteUpdates>"
        "</SubmitMultiRegionAccessPointRoutesRequest>"
    )
    status, text = call(
        s3_endpoint, "PATCH", f"/v20180820/mrap/instances/{arn}/routes", update,
        {"x-amz-account-id": ACCOUNT}, region,
    )
    assert 200 <= status < 300, (status, text)


def test_mrap_delete_removes_it(s3_endpoint):
    region, _token_arn = _create_mrap(s3_endpoint, "ops-mrap-delete")
    details = "<Name>ops-mrap-delete</Name>"
    status, text = _async(s3_endpoint, "DeleteMultiRegionAccessPoint", details, region)
    assert status == 200, (status, text)

    status, _ = call(
        s3_endpoint, "GET", "/v20180820/mrap/instances/ops-mrap-delete", "",
        {"x-amz-account-id": ACCOUNT}, region,
    )
    assert status == 404


# ---------------------------------------------------------------------------
# Object Lambda access points
# ---------------------------------------------------------------------------


def _object_lambda(endpoint, name):
    """A supporting access point (and its bucket) for the Object Lambda AP."""
    bucket(endpoint, "ops-olap-bucket")
    status, text = call(
        endpoint,
        "PUT",
        "/v20180820/accesspoint/ops-olap-support",
        f'<CreateAccessPointRequest xmlns="{CONTROL_NS}">'
        "<Bucket>ops-olap-bucket</Bucket></CreateAccessPointRequest>",
        {"x-amz-account-id": ACCOUNT},
    )
    assert status in (200, 409), (status, text)

    configuration = (
        f'<PutAccessPointConfigurationForObjectLambdaRequest xmlns="{CONTROL_NS}"><Configuration>'
        f"<SupportingAccessPoint>arn:aws:s3:us-east-1:{ACCOUNT}:accesspoint/ops-olap-support"
        "</SupportingAccessPoint><CloudWatchMetricsEnabled>false</CloudWatchMetricsEnabled>"
        "<TransformationConfigurations><TransformationConfiguration><Actions>"
        "<Action>GetObject</Action></Actions><ContentTransformation><AwsLambda>"
        f"<FunctionArn>arn:aws:lambda:us-east-1:{ACCOUNT}:function:ops-olap</FunctionArn>"
        "</AwsLambda></ContentTransformation></TransformationConfiguration>"
        "</TransformationConfigurations></Configuration>"
        "</PutAccessPointConfigurationForObjectLambdaRequest>"
    )
    status, text = call(
        endpoint,
        "PUT",
        f"/v20180820/accesspointforobjectlambda/{name}",
        configuration,
        {"x-amz-account-id": ACCOUNT},
    )
    assert status == 200, (status, text)
    return name


def test_object_lambda_access_point_is_created_and_read(s3_endpoint):
    _object_lambda(s3_endpoint, "ops-olap")

    status, text = call(
        s3_endpoint, "GET", "/v20180820/accesspointforobjectlambda/ops-olap", "",
        {"x-amz-account-id": ACCOUNT},
    )
    assert status == 200, (status, text)
    assert "ops-olap" in text

    status, text = call(
        s3_endpoint, "GET", "/v20180820/accesspointforobjectlambda/ops-olap/configuration",
        "", {"x-amz-account-id": ACCOUNT},
    )
    assert status == 200, (status, text)
    assert "SupportingAccessPoint" in text


def test_object_lambda_configuration_can_be_replaced(s3_endpoint):
    configuration = (
        f'<PutAccessPointConfigurationForObjectLambdaRequest xmlns="{CONTROL_NS}"><Configuration>'
        f"<SupportingAccessPoint>arn:aws:s3:us-east-1:{ACCOUNT}:accesspoint/ops-olap-support"
        "</SupportingAccessPoint><CloudWatchMetricsEnabled>true</CloudWatchMetricsEnabled>"
        "<AllowedFeatures><AllowedFeature>GetObject-Range</AllowedFeature></AllowedFeatures>"
        "<TransformationConfigurations><TransformationConfiguration><Actions>"
        "<Action>GetObject</Action><Action>HeadObject</Action></Actions>"
        "<ContentTransformation><AwsLambda>"
        f"<FunctionArn>arn:aws:lambda:us-east-1:{ACCOUNT}:function:ops-olap</FunctionArn>"
        "</AwsLambda></ContentTransformation></TransformationConfiguration>"
        "</TransformationConfigurations></Configuration>"
        "</PutAccessPointConfigurationForObjectLambdaRequest>"
    )
    status, text = call(
        s3_endpoint,
        "PUT",
        "/v20180820/accesspointforobjectlambda/ops-olap/configuration",
        configuration,
        {"x-amz-account-id": ACCOUNT},
    )
    assert status == 200, (status, text)

    status, text = call(
        s3_endpoint, "GET", "/v20180820/accesspointforobjectlambda/ops-olap/configuration",
        "", {"x-amz-account-id": ACCOUNT},
    )
    assert status == 200
    assert "true" in text and "GetObject-Range" in text


def test_object_lambda_policy_is_put_read_and_deleted(s3_endpoint):
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Principal": "*", "Action": "s3-object-lambda:GetObject", "Resource": "*"}
            ],
        }
    )
    put_path = (
        f'<PutAccessPointPolicyForObjectLambdaRequest xmlns="{CONTROL_NS}">'
        f"<Policy>{policy}</Policy></PutAccessPointPolicyForObjectLambdaRequest>"
    )
    path = "/v20180820/accesspointforobjectlambda/ops-olap/policy"
    status, text = call(s3_endpoint, "PUT", path, put_path, {"x-amz-account-id": ACCOUNT})
    assert status == 200, (status, text)

    status, text = call(s3_endpoint, "GET", path, "", {"x-amz-account-id": ACCOUNT})
    assert status == 200
    assert "s3-object-lambda:GetObject" in text

    status, _ = call(s3_endpoint, "DELETE", path, "", {"x-amz-account-id": ACCOUNT})
    assert 200 <= status < 300
    assert call(s3_endpoint, "GET", path, "", {"x-amz-account-id": ACCOUNT})[0] == 404


def test_object_lambda_access_point_is_deleted(s3_endpoint):
    _object_lambda(s3_endpoint, "ops-olap-gone")
    status, _ = call(
        s3_endpoint, "DELETE", "/v20180820/accesspointforobjectlambda/ops-olap-gone", "",
        {"x-amz-account-id": ACCOUNT},
    )
    assert 200 <= status < 300
    assert (
        call(
            s3_endpoint,
            "GET",
            "/v20180820/accesspointforobjectlambda/ops-olap-gone",
            "",
            {"x-amz-account-id": ACCOUNT},
        )[0]
        == 404
    )


def test_write_get_object_response_refuses_an_unknown_route(s3_endpoint):
    """The success path needs a Lambda mid-GET; its contract is the route header.

    An unknown (or spent) route is AWS's `400 InvalidHostHeader`, which is what a
    caller writing outside a request sees. The full path is the emulator's own
    Object Lambda suite's job.
    """
    status, text = call(
        s3_endpoint,
        "POST",
        "/WriteGetObjectResponse",
        "body",
        {
            "x-amz-request-route": "io-use1-unknownroute",
            "x-amz-request-token": "unknown",
        },
    )
    assert status == 400
    assert "InvalidHostHeader" in text
