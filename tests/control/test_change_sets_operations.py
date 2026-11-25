"""CloudFormation change sets on the wire: all 5 advertised operations.

The emulator answers the Query protocol (`Action=…&Version=2010-05-15`). A change
set is created against a stack of its own (`ops-cfn-cs-base`), which this module
creates and leaves in place; every set it reads is deleted and re-created first,
so a lab re-run meets a clean name instead of `AlreadyExistsException`.

`ExecuteChangeSet` needs a settled stack: the in-process stand-in cancels the
deploy and never leaves `CREATE_IN_PROGRESS`, so that one call is proven on the
lab and skipped here with the reason stated.
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

BASE = "ops-cfn-cs-base"
READ = "ops-cfn-cs-read"
LISTED = "ops-cfn-cs-listed"
DELETED = "ops-cfn-cs-deleted"

BASE_TEMPLATE = {
    "Resources": {
        "Topic": {
            "Type": "AWS::SNS::Topic",
            "Properties": {"TopicName": "ops-cfn-cs-base-topic"},
        }
    }
}
CHANGED_TEMPLATE = {
    "Resources": {
        "Topic": {
            "Type": "AWS::SNS::Topic",
            "Properties": {"TopicName": "ops-cfn-cs-changed-topic"},
        }
    }
}

LIFECYCLE_RUNS = bool(os.environ.get("EP_LAB_EMULATOR"))
needs_lifecycle = pytest.mark.skipif(
    not LIFECYCLE_RUNS,
    reason="ExecuteChangeSet needs a stack settled in CREATE_COMPLETE; the in-process "
    "stand-in cancels the deploy, so the live sweep proves it",
)


# ------------------------------------------------------------------ helpers


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "cloudformation", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:600]}"
    return text


def refused(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:600]}"
    return html.unescape(text)


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:600]}"
    return html.unescape(match.group(1))


def members(text: str, container: str) -> list[str]:
    block = re.search(rf"<{container}>(.*?)</{container}>", text, re.S)
    assert block, f"no <{container}> in {text[:600]}"
    return re.findall(r"<member>(.*?)</member>", block.group(1), re.S)


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
    if exists(endpoint, BASE):
        return
    ok(endpoint, "CreateStack", StackName=BASE, TemplateBody=json.dumps(BASE_TEMPLATE))
    if LIFECYCLE_RUNS:
        settle(endpoint, BASE, "CREATE_COMPLETE")


def make_set(endpoint, name: str, template: dict) -> str:
    """Delete the name, then create it, so a re-run starts from the same place."""
    ok(endpoint, "DeleteChangeSet", StackName=BASE, ChangeSetName=name)
    text = ok(
        endpoint,
        "CreateChangeSet",
        StackName=BASE,
        ChangeSetName=name,
        ChangeSetType="UPDATE",
        TemplateBody=json.dumps(template),
    )
    return field(text, "Id")


# ------------------------------------------------------------------ operations


def test_create_change_set_answers_an_id_and_the_stack_id(endpoint):
    ensure_stack(endpoint)
    # A rejected re-create is an AlreadyExists; clearing the name first keeps the
    # test about the create rather than about the sweep that ran before it.
    ok(endpoint, "DeleteChangeSet", StackName=BASE, ChangeSetName=READ)
    text = ok(
        endpoint,
        "CreateChangeSet",
        StackName=BASE,
        ChangeSetName=READ,
        ChangeSetType="UPDATE",
        TemplateBody=json.dumps(CHANGED_TEMPLATE),
    )
    assert "changeSet/" + READ in field(text, "Id")
    assert f":stack/{BASE}/" in field(text, "StackId")


def test_describe_change_set_reports_the_status_and_the_changes(endpoint):
    ensure_stack(endpoint)
    make_set(endpoint, READ, CHANGED_TEMPLATE)
    text = ok(endpoint, "DescribeChangeSet", StackName=BASE, ChangeSetName=READ)
    assert field(text, "ChangeSetName") == READ
    assert field(text, "StackName") == BASE
    assert field(text, "Status") == "CREATE_COMPLETE"
    changes = members(text, "Changes")
    assert changes
    assert field(changes[0], "Action") in ("Add", "Modify", "Remove")


def test_list_change_sets_includes_the_set(endpoint):
    ensure_stack(endpoint)
    make_set(endpoint, LISTED, CHANGED_TEMPLATE)
    text = ok(endpoint, "ListChangeSets", StackName=BASE)
    summaries = members(text, "Summaries")
    assert LISTED in [field(summary, "ChangeSetName") for summary in summaries]


@needs_lifecycle
def test_execute_change_set_updates_the_stack(endpoint):
    ensure_stack(endpoint)
    topic = f"ops-cfn-cs-run-{time.time_ns()}"
    template = {
        "Resources": {
            "Topic": {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": topic}}
        }
    }
    make_set(endpoint, READ, template)
    ok(endpoint, "ExecuteChangeSet", StackName=BASE, ChangeSetName=READ)
    settle(endpoint, BASE, "UPDATE_COMPLETE")
    # The change set records the execution it was asked for.
    text = ok(endpoint, "DescribeChangeSet", StackName=BASE, ChangeSetName=READ)
    assert field(text, "ExecutionStatus") == "EXECUTE_COMPLETE"


def test_delete_change_set_removes_the_set_it_created(endpoint):
    ensure_stack(endpoint)
    make_set(endpoint, DELETED, CHANGED_TEMPLATE)
    ok(endpoint, "DeleteChangeSet", StackName=BASE, ChangeSetName=DELETED)
    text = refused(endpoint, "DescribeChangeSet", StackName=BASE, ChangeSetName=DELETED)
    assert "ChangeSetNotFound" in text
