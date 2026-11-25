"""CloudTrail on the wire: all 15 advertised operations, JSON 1.1.

The target prefix is `com.amazonaws.cloudtrail.v20131101.CloudTrail_20131101`. A
trail is keyed by name, so a stable trail carries the read/logging/selector/tag
tests while a create or delete test makes its own. Recording is off by default,
so `LookupEvents` answers the empty audit log it documents.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "com.amazonaws.cloudtrail.v20131101.CloudTrail_20131101"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
TRAIL = "ops-trail"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "cloudtrail", ACCOUNT, REGION, "POST", "/", body, headers)


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


def ensure_trail(endpoint, name: str = TRAIL) -> dict:
    status, text = call(endpoint, "CreateTrail", {"Name": name, "S3BucketName": "ops-cloudtrail-bucket"})
    assert status == 200 or "TrailAlreadyExistsException" in text, text[:300]
    return ok(endpoint, "GetTrail", {"Name": name})["Trail"]


def trail_arn(endpoint, name: str = TRAIL) -> str:
    return ensure_trail(endpoint, name)["TrailARN"]


# ---------------------------------------------------------------------------
# Trails
# ---------------------------------------------------------------------------


def test_create_trail_is_read_back(endpoint):
    name = f"ops-trail-created-{time.time_ns()}"
    created = ok(endpoint, "CreateTrail", {"Name": name, "S3BucketName": "ops-cloudtrail-bucket"})
    assert created["Name"] == name
    trail = ok(endpoint, "GetTrail", {"Name": name})["Trail"]
    assert trail["S3BucketName"] == "ops-cloudtrail-bucket"


def test_delete_trail_removes_the_trail_it_created(endpoint):
    name = f"ops-trail-deleted-{time.time_ns()}"
    ok(endpoint, "CreateTrail", {"Name": name})
    ok(endpoint, "DeleteTrail", {"Name": name})
    refused(endpoint, "GetTrail", {"Name": name}, "TrailNotFoundException")


def test_get_trail_reads_the_trail(endpoint):
    trail = ensure_trail(endpoint)
    assert trail["Name"] == TRAIL
    assert trail["HomeRegion"] == REGION


def test_describe_trails_lists_the_trail(endpoint):
    ensure_trail(endpoint)
    names = [item["Name"] for item in ok(endpoint, "DescribeTrails")["trailList"]]
    assert TRAIL in names


def test_list_trails_lists_the_trail(endpoint):
    ensure_trail(endpoint)
    names = [item["Name"] for item in ok(endpoint, "ListTrails")["Trails"]]
    assert TRAIL in names


def test_update_trail_changes_the_prefix(endpoint):
    ensure_trail(endpoint)
    ok(endpoint, "UpdateTrail", {"Name": TRAIL, "S3KeyPrefix": "ops/"})
    assert ok(endpoint, "GetTrail", {"Name": TRAIL})["Trail"]["S3KeyPrefix"] == "ops/"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_get_trail_status_reads_the_logging_state(endpoint):
    ensure_trail(endpoint)
    status = ok(endpoint, "GetTrailStatus", {"Name": TRAIL})
    assert isinstance(status["IsLogging"], bool)


def test_start_logging_turns_logging_on(endpoint):
    ensure_trail(endpoint)
    ok(endpoint, "StartLogging", {"Name": TRAIL})
    assert ok(endpoint, "GetTrailStatus", {"Name": TRAIL})["IsLogging"] is True


def test_stop_logging_turns_logging_off(endpoint):
    ensure_trail(endpoint)
    ok(endpoint, "StopLogging", {"Name": TRAIL})
    assert ok(endpoint, "GetTrailStatus", {"Name": TRAIL})["IsLogging"] is False


# ---------------------------------------------------------------------------
# Event selectors
# ---------------------------------------------------------------------------


def test_put_event_selectors_is_read_back(endpoint):
    ensure_trail(endpoint)
    selectors = [{"ReadWriteType": "All", "IncludeManagementEvents": True, "DataResources": []}]
    ok(endpoint, "PutEventSelectors", {"TrailName": TRAIL, "EventSelectors": selectors})
    read = ok(endpoint, "GetEventSelectors", {"TrailName": TRAIL})["EventSelectors"]
    assert read[0]["ReadWriteType"] == "All"


def test_get_event_selectors_reads_the_selectors(endpoint):
    ensure_trail(endpoint)
    answer = ok(endpoint, "GetEventSelectors", {"TrailName": TRAIL})
    assert "EventSelectors" in answer or "AdvancedEventSelectors" in answer


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_add_tags_is_read_back_by_list_tags(endpoint):
    arn = trail_arn(endpoint)
    ok(endpoint, "AddTags", {"ResourceId": arn, "TagsList": [{"Key": "env", "Value": "ops"}]})
    listed = ok(endpoint, "ListTags", {"ResourceIdList": [arn]})["ResourceTagList"]
    assert {"Key": "env", "Value": "ops"} in listed[0]["TagsList"]


def test_list_tags_lists_the_tags(endpoint):
    arn = trail_arn(endpoint)
    ok(endpoint, "AddTags", {"ResourceId": arn, "TagsList": [{"Key": "team", "Value": "platform"}]})
    listed = ok(endpoint, "ListTags", {"ResourceIdList": [arn]})["ResourceTagList"]
    assert {"Key": "team", "Value": "platform"} in listed[0]["TagsList"]


def test_remove_tags_removes_the_key_it_names(endpoint):
    arn = trail_arn(endpoint)
    ok(endpoint, "AddTags", {"ResourceId": arn, "TagsList": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "RemoveTags", {"ResourceId": arn, "TagsList": [{"Key": "doomed"}]})
    listed = ok(endpoint, "ListTags", {"ResourceIdList": [arn]})["ResourceTagList"]
    assert "doomed" not in {tag["Key"] for tag in listed[0]["TagsList"]}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def test_lookup_events_answers_the_audit_log(endpoint):
    answer = ok(endpoint, "LookupEvents", {})
    assert isinstance(answer["Events"], list)
