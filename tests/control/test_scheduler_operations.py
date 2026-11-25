"""EventBridge Scheduler on the wire: all 12 advertised operations, REST/JSON.

Schedules live at `/schedules/{name}` and groups at `/schedule-groups/{name}`;
tags are addressed by resource ARN under `/tags/{arn}`. A schedule is keyed by
`group/name`, a group by name, so a stable resource carries the read/update/tag
tests while a create or delete test makes its own.
"""

from __future__ import annotations

import json
import time
from urllib.parse import quote

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
SCHEDULE = "ops-schedule"
GROUP = "ops-schedule-group"


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "scheduler", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status == 200, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, method: str, path: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, method, path, payload)
    assert status >= 400, f"{method} {path} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def body(expression: str = "rate(1 day)") -> dict:
    return {
        "ScheduleExpression": expression,
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "Target": {
            "Arn": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:ops-target",
            "RoleArn": f"arn:aws:iam::{ACCOUNT}:role/ops-scheduler-role",
        },
    }


def ensure_schedule(endpoint, name: str = SCHEDULE) -> dict:
    status, text = call(endpoint, "POST", f"/schedules/{name}", body())
    assert status == 200 or "ConflictException" in text, text[:300]
    return ok(endpoint, "GET", f"/schedules/{name}")


def ensure_group(endpoint, name: str = GROUP) -> dict:
    status, text = call(endpoint, "POST", f"/schedule-groups/{name}", {})
    assert status == 200 or "ConflictException" in text, text[:300]
    return ok(endpoint, "GET", f"/schedule-groups/{name}")


def tags(endpoint, arn: str) -> list[dict]:
    return ok(endpoint, "GET", f"/tags/{quote(arn, safe='')}")["Tags"]


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


def test_create_schedule_is_read_back(endpoint):
    name = f"ops-sched-{time.time_ns()}"
    ok(endpoint, "POST", f"/schedules/{name}", body())
    created = ok(endpoint, "GET", f"/schedules/{name}")
    assert created["Name"] == name
    assert created["ScheduleExpression"] == "rate(1 day)"
    assert created["State"] == "ENABLED"


def test_get_schedule_reads_the_schedule(endpoint):
    created = ensure_schedule(endpoint)
    assert created["Name"] == SCHEDULE
    assert created["GroupName"] == "default"


def test_update_schedule_changes_the_expression(endpoint):
    ensure_schedule(endpoint)
    updated = body("rate(2 days)")
    ok(endpoint, "PUT", f"/schedules/{SCHEDULE}", updated)
    assert ok(endpoint, "GET", f"/schedules/{SCHEDULE}")["ScheduleExpression"] == "rate(2 days)"


def test_delete_schedule_removes_the_schedule_it_created(endpoint):
    name = f"ops-sched-del-{time.time_ns()}"
    ok(endpoint, "POST", f"/schedules/{name}", body())
    ok(endpoint, "DELETE", f"/schedules/{name}")
    refused(endpoint, "GET", f"/schedules/{name}", code="ResourceNotFoundException")


def test_list_schedules_lists_the_schedule(endpoint):
    ensure_schedule(endpoint)
    listed = ok(endpoint, "GET", "/schedules")["Schedules"]
    assert SCHEDULE in {item["Name"] for item in listed}


# ---------------------------------------------------------------------------
# Schedule groups
# ---------------------------------------------------------------------------


def test_create_schedule_group_is_read_back(endpoint):
    name = f"ops-group-{time.time_ns()}"
    ok(endpoint, "POST", f"/schedule-groups/{name}", {})
    created = ok(endpoint, "GET", f"/schedule-groups/{name}")
    assert created["Name"] == name
    assert created["State"] == "ACTIVE"


def test_get_schedule_group_reads_the_group(endpoint):
    created = ensure_group(endpoint)
    assert created["Name"] == GROUP


def test_delete_schedule_group_removes_the_group_it_created(endpoint):
    name = f"ops-group-del-{time.time_ns()}"
    ok(endpoint, "POST", f"/schedule-groups/{name}", {})
    ok(endpoint, "DELETE", f"/schedule-groups/{name}")
    refused(endpoint, "GET", f"/schedule-groups/{name}", code="ResourceNotFoundException")


def test_list_schedule_groups_lists_the_group(endpoint):
    ensure_group(endpoint)
    listed = ok(endpoint, "GET", "/schedule-groups")["ScheduleGroups"]
    assert GROUP in {item["Name"] for item in listed}


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    arn = ensure_schedule(endpoint)["Arn"]
    ok(endpoint, "POST", f"/tags/{quote(arn, safe='')}", {"Tags": [{"Key": "env", "Value": "ops"}]})
    assert {"Key": "env", "Value": "ops"} in tags(endpoint, arn)


def test_untag_resource_removes_the_key_it_names(endpoint):
    arn = ensure_schedule(endpoint)["Arn"]
    ok(endpoint, "POST", f"/tags/{quote(arn, safe='')}", {"Tags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "DELETE", f"/tags/{quote(arn, safe='')}?TagKeys=doomed")
    assert "doomed" not in {tag["Key"] for tag in tags(endpoint, arn)}


def test_list_tags_for_resource_lists_the_tags(endpoint):
    arn = ensure_schedule(endpoint)["Arn"]
    ok(endpoint, "POST", f"/tags/{quote(arn, safe='')}", {"Tags": [{"Key": "team", "Value": "platform"}]})
    assert {"Key": "team", "Value": "platform"} in tags(endpoint, arn)
