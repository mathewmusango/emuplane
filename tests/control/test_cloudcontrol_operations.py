"""Cloud Control API on the wire: all 8 advertised operations, JSON 1.1.

The target prefix is `CloudApiService`. A resource is keyed by `(TypeName,
Identifier)` and the identifier is extracted from the desired state, so an
`AWS::S3::Bucket` with a `BucketName` is the simplest type to drive. Mutations
complete synchronously, so `CancelResourceRequest` is exercised as the
documented conflict for a terminal request.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "CloudApiService"
TYPE = "AWS::S3::Bucket"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "cloudcontrol", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, action: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, action, payload)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def create(endpoint, name: str, **props) -> str:
    body = {"TypeName": TYPE, "DesiredState": json.dumps({"BucketName": name, **props})}
    return ok(endpoint, "CreateResource", body)["ProgressEvent"]["RequestToken"]


def ensure_bucket(endpoint, name: str = "ops-cc-bucket") -> str:
    status, text = call(endpoint, "CreateResource", {"TypeName": TYPE, "DesiredState": json.dumps({"BucketName": name})})
    assert status == 200 or "AlreadyExistsException" in text, text[:300]
    ok(endpoint, "GetResource", {"TypeName": TYPE, "Identifier": name})
    return name


def properties(endpoint, name: str) -> dict:
    described = ok(endpoint, "GetResource", {"TypeName": TYPE, "Identifier": name})
    return json.loads(described["ResourceDescription"]["Properties"])


def any_request_token(endpoint) -> str:
    summaries = ok(endpoint, "ListResourceRequests", {"MaxResults": 1})["ResourceRequestStatusSummaries"]
    if summaries:
        return summaries[0]["RequestToken"]
    return create(endpoint, f"ops-cc-token-{time.time_ns()}")


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def test_create_resource_answers_a_success_event(endpoint):
    name = f"ops-cc-created-{time.time_ns()}"
    token = create(endpoint, name)
    assert token
    event = ok(endpoint, "GetResourceRequestStatus", {"RequestToken": token})["ProgressEvent"]
    assert event["Operation"] == "CREATE"
    assert event["OperationStatus"] == "SUCCESS"
    assert event["Identifier"] == name
    assert properties(endpoint, name)["BucketName"] == name


def test_get_resource_reads_the_desired_state(endpoint):
    name = ensure_bucket(endpoint)
    assert properties(endpoint, name)["BucketName"] == name


def test_update_resource_applies_a_patch(endpoint):
    name = ensure_bucket(endpoint)
    patch = json.dumps([{"op": "add", "path": "/Versioning", "value": "Enabled"}])
    event = ok(
        endpoint,
        "UpdateResource",
        {"TypeName": TYPE, "Identifier": name, "PatchDocument": patch},
    )["ProgressEvent"]
    assert event["OperationStatus"] == "SUCCESS"
    assert properties(endpoint, name)["Versioning"] == "Enabled"


def test_delete_resource_removes_the_resource_it_created(endpoint):
    name = f"ops-cc-deleted-{time.time_ns()}"
    create(endpoint, name)
    event = ok(endpoint, "DeleteResource", {"TypeName": TYPE, "Identifier": name})["ProgressEvent"]
    assert event["OperationStatus"] == "SUCCESS"
    refused(endpoint, "GetResource", {"TypeName": TYPE, "Identifier": name}, "ResourceNotFoundException")


def test_list_resources_lists_the_type(endpoint):
    name = ensure_bucket(endpoint)
    described = ok(endpoint, "ListResources", {"TypeName": TYPE})["ResourceDescriptions"]
    assert name in {item["Identifier"] for item in described}


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def test_list_resource_requests_lists_the_operations(endpoint):
    any_request_token(endpoint)
    summaries = ok(endpoint, "ListResourceRequests")["ResourceRequestStatusSummaries"]
    assert summaries
    assert {"Operation", "OperationStatus", "RequestToken"} <= set(summaries[0])


def test_get_resource_request_status_reads_the_event(endpoint):
    token = any_request_token(endpoint)
    event = ok(endpoint, "GetResourceRequestStatus", {"RequestToken": token})["ProgressEvent"]
    assert event["RequestToken"] == token
    assert event["OperationStatus"] in ("SUCCESS", "FAILED")


def test_cancel_resource_request_refuses_a_terminal_request(endpoint):
    token = any_request_token(endpoint)
    text = refused(endpoint, "CancelResourceRequest", {"RequestToken": token}, "ConflictException")
    assert "Only IN_PROGRESS requests can be cancelled" in text
