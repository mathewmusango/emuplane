"""CloudFormation drift on the wire: all 4 advertised operations.

Detection runs synchronously and records `DriftInformation` on the stack and on
each resource it checked. The stack is created once and left in place.

The in-process stand-in cancels the deploy, so the stack never leaves
`CREATE_IN_PROGRESS` and every drift call is refused until it is settled: all
four are proven on the lab and skipped here with the reason stated.
"""

from __future__ import annotations

import html
import json
import os
import re
import time

import pytest
import signed
from conftest import ACCOUNT
from urllib.parse import urlencode

REGION = "us-east-1"
VERSION = "2010-05-15"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

STACK = "ops-cfn-drift"
RESOURCE = "Topic"

# A second stack carries a resource whose property is changed out-of-band, for the
# property-level drift the README lists; a second resource gives the listing a
# second row to page over.
PROPS_STACK = "ops-cfn-drift-props"
QUEUE_NAME = "ops-cfn-drift-queue"
PROPS_TEMPLATE = {
    "Resources": {
        "Queue": {
            "Type": "AWS::SQS::Queue",
            "Properties": {"QueueName": QUEUE_NAME, "VisibilityTimeout": 30},
        },
        "Topic": {
            "Type": "AWS::SNS::Topic",
            "Properties": {"TopicName": "ops-cfn-drift-topic-props"},
        },
    }
}
SQS_VERSION = "2012-11-05"

TEMPLATE = {
    "Resources": {
        RESOURCE: {
            "Type": "AWS::SNS::Topic",
            "Properties": {"TopicName": "ops-cfn-drift-topic"},
        }
    }
}

LIFECYCLE_RUNS = bool(os.environ.get("EP_LAB_EMULATOR"))
needs_lifecycle = pytest.mark.skipif(
    not LIFECYCLE_RUNS,
    reason="resource drift needs a settled stack with provisioned resources; the "
    "in-process stand-in cancels the deploy, so the live sweep proves it",
)


# ------------------------------------------------------------------ helpers


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "cloudformation", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:600]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:600]}"
    return html.unescape(match.group(1))


def exists(endpoint, name: str) -> bool:
    status, text = call(endpoint, "DescribeStacks", StackName=name)
    if status == 200:
        return True
    assert "does not exist" in text, text[:600]
    return False


def settle(endpoint, name: str, wanted: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        status, text = call(endpoint, "DescribeStacks", StackName=name)
        assert status == 200, text[:600]
        current = field(text, "StackStatus")
        if current == wanted:
            return
        assert time.monotonic() < deadline, f"{name} was still {current} after {timeout}s"
        time.sleep(0.1)


def ensure_stack(endpoint) -> None:
    if exists(endpoint, STACK):
        if LIFECYCLE_RUNS:
            settle(endpoint, STACK, "CREATE_COMPLETE")
        return
    ok(endpoint, "CreateStack", StackName=STACK, TemplateBody=json.dumps(TEMPLATE))
    if LIFECYCLE_RUNS:
        settle(endpoint, STACK, "CREATE_COMPLETE")


def ensure_props_stack(endpoint) -> None:
    if exists(endpoint, PROPS_STACK):
        if LIFECYCLE_RUNS:
            settle(endpoint, PROPS_STACK, "CREATE_COMPLETE")
        return
    ok(endpoint, "CreateStack", StackName=PROPS_STACK, TemplateBody=json.dumps(PROPS_TEMPLATE))
    if LIFECYCLE_RUNS:
        settle(endpoint, PROPS_STACK, "CREATE_COMPLETE")


def members(text: str, container: str) -> list[str]:
    block = re.search(rf"<{container}>(.*?)</{container}>", text, re.S)
    assert block, f"no <{container}> in {text[:600]}"
    return re.findall(r"<member>(.*?)</member>", block.group(1), re.S)


def physical_id(endpoint, logical_id: str) -> str:
    text = ok(endpoint, "DescribeStackResource", StackName=PROPS_STACK, LogicalResourceId=logical_id)
    return field(text, "PhysicalResourceId")


def set_visibility_timeout(endpoint, queue_url: str, seconds: str) -> None:
    body = urlencode(
        {
            "Action": "SetQueueAttributes",
            "Version": SQS_VERSION,
            "QueueUrl": queue_url,
            "Attribute.1.Name": "VisibilityTimeout",
            "Attribute.1.Value": seconds,
        }
    )
    status, text = signed.request(
        endpoint, "sqs", ACCOUNT, REGION, "POST", "/", body, FORM
    )
    assert status == 200, f"SetQueueAttributes answered {status}: {text[:600]}"


def ensure_drifted(endpoint) -> None:
    """Settle the stack, change the queue behind its back, and detect both resources."""
    ensure_props_stack(endpoint)
    set_visibility_timeout(endpoint, physical_id(endpoint, "Queue"), "60")
    ok(endpoint, "DetectStackDrift", StackName=PROPS_STACK)


# ------------------------------------------------------------------ operations


@needs_lifecycle
def test_detect_stack_drift_answers_a_detection_id(endpoint):
    ensure_stack(endpoint)
    text = ok(endpoint, "DetectStackDrift", StackName=STACK)
    assert re.fullmatch(r"[0-9a-f-]{36}", field(text, "StackDriftDetectionId"))


@needs_lifecycle
def test_describe_stack_drift_detection_status_reports_the_detection(endpoint):
    ensure_stack(endpoint)
    detection_id = field(ok(endpoint, "DetectStackDrift", StackName=STACK), "StackDriftDetectionId")
    text = ok(endpoint, "DescribeStackDriftDetectionStatus", StackDriftDetectionId=detection_id)
    assert field(text, "StackDriftDetectionId") == detection_id
    assert field(text, "DetectionStatus") == "DETECTION_COMPLETE"
    assert field(text, "StackDriftStatus") in ("IN_SYNC", "DRIFTED", "UNKNOWN")


@needs_lifecycle
def test_detect_stack_resource_drift_checks_one_resource(endpoint):
    ensure_stack(endpoint)
    text = ok(
        endpoint,
        "DetectStackResourceDrift",
        StackName=STACK,
        LogicalResourceId=RESOURCE,
    )
    drift = re.search(r"<StackResourceDrift>(.*?)</StackResourceDrift>", text, re.S)
    assert drift, text[:600]
    assert field(drift.group(1), "LogicalResourceId") == RESOURCE
    assert field(drift.group(1), "ResourceType") == "AWS::SNS::Topic"
    assert field(drift.group(1), "StackResourceDriftStatus") in ("IN_SYNC", "MODIFIED", "DELETED")


@needs_lifecycle
def test_describe_stack_resource_drifts_lists_the_checked_resources(endpoint):
    ensure_stack(endpoint)
    ok(
        endpoint,
        "DetectStackResourceDrift",
        StackName=STACK,
        LogicalResourceId=RESOURCE,
    )
    text = ok(endpoint, "DescribeStackResourceDrifts", StackName=STACK)
    drifts = re.search(r"<StackResourceDrifts>(.*?)</StackResourceDrifts>", text, re.S)
    assert drifts, text[:600]
    assert f"<LogicalResourceId>{RESOURCE}</LogicalResourceId>" in drifts.group(1)


@needs_lifecycle
def test_a_changed_property_is_reported_as_modified(endpoint):
    ensure_drifted(endpoint)
    text = ok(
        endpoint,
        "DetectStackResourceDrift",
        StackName=PROPS_STACK,
        LogicalResourceId="Queue",
    )
    drift = re.search(r"<StackResourceDrift>(.*?)</StackResourceDrift>", text, re.S)
    assert drift, text[:600]
    body = drift.group(1)
    assert field(body, "StackResourceDriftStatus") == "MODIFIED"
    differences = members(body, "PropertyDifferences")
    assert any(
        field(item, "PropertyPath").lstrip("/") == "VisibilityTimeout" for item in differences
    )
    assert json.loads(field(body, "ExpectedProperties"))["VisibilityTimeout"] == 30
    assert json.loads(field(body, "ActualProperties"))["VisibilityTimeout"] == 60


@needs_lifecycle
def test_drift_information_appears_on_the_stack_and_resource_reads(endpoint):
    ensure_drifted(endpoint)
    stack = ok(endpoint, "DescribeStacks", StackName=PROPS_STACK)
    assert field(stack, "StackDriftStatus") == "DRIFTED"

    listing = ok(endpoint, "ListStacks")
    summary = next(
        item
        for item in members(listing, "StackSummaries")
        if field(item, "StackName") == PROPS_STACK
    )
    assert field(summary, "StackDriftStatus") == "DRIFTED"

    resource = ok(
        endpoint, "DescribeStackResource", StackName=PROPS_STACK, LogicalResourceId="Queue"
    )
    assert field(resource, "StackResourceDriftStatus") == "MODIFIED"
    resources = ok(endpoint, "DescribeStackResources", StackName=PROPS_STACK)
    by_id = {field(item, "LogicalResourceId"): item for item in members(resources, "StackResources")}
    assert field(by_id["Queue"], "StackResourceDriftStatus") == "MODIFIED"


@needs_lifecycle
def test_describe_stack_resource_drifts_filters_by_status_and_pages(endpoint):
    ensure_drifted(endpoint)
    modified = ok(
        endpoint,
        "DescribeStackResourceDrifts",
        StackName=PROPS_STACK,
        **{"StackResourceDriftStatusFilters.member.1": "MODIFIED"},
    )
    assert [field(item, "LogicalResourceId") for item in members(modified, "StackResourceDrifts")] == [
        "Queue"
    ]

    in_sync = ok(
        endpoint,
        "DescribeStackResourceDrifts",
        StackName=PROPS_STACK,
        **{"StackResourceDriftStatusFilters.member.1": "IN_SYNC"},
    )
    assert "Queue" not in [
        field(item, "LogicalResourceId") for item in members(in_sync, "StackResourceDrifts")
    ]

    first = ok(endpoint, "DescribeStackResourceDrifts", StackName=PROPS_STACK, MaxResults="1")
    assert len(members(first, "StackResourceDrifts")) == 1
    token = field(first, "NextToken")
    second = ok(
        endpoint,
        "DescribeStackResourceDrifts",
        StackName=PROPS_STACK,
        MaxResults="1",
        NextToken=token,
    )
    assert len(members(second, "StackResourceDrifts")) == 1
