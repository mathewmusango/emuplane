"""CloudFormation exports on the wire: the one advertised operation, ListExports.

A stack publishes an `Outputs` export through `Export.Name`; `ListExports` reads
every export in the account and Region. The stack is created once and left in
place, so a lab re-run finds it rather than colliding.

In the in-process stand-in the deploy is cancelled before the stack reaches
`CREATE_COMPLETE`, and exports are published only on success; the live sweep
proves the export. The test states that instead of pretending a container with no
export is the right answer.
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

STACK = "ops-cfn-exports"
EXPORT_NAME = "ops-cfn-export"

TEMPLATE = {
    "Resources": {
        "Topic": {
            "Type": "AWS::SNS::Topic",
            "Properties": {"TopicName": "ops-cfn-export-topic"},
        }
    },
    "Outputs": {
        "TopicArn": {
            "Description": "The topic the export names.",
            "Value": {"Ref": "Topic"},
            "Export": {"Name": EXPORT_NAME},
        }
    },
}

LIFECYCLE_RUNS = bool(os.environ.get("EP_LAB_EMULATOR"))
needs_lifecycle = pytest.mark.skipif(
    not LIFECYCLE_RUNS,
    reason="exports are published when the deploy succeeds; the in-process stand-in "
    "cancels the deploy, so the live sweep proves the export",
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


# ------------------------------------------------------------------ operation


@needs_lifecycle
def test_list_exports_lists_the_stack_export(endpoint):
    ensure_stack(endpoint)
    text = ok(endpoint, "ListExports")
    exports = re.findall(
        r"<member><ExportingStackId>(.*?)</ExportingStackId>"
        r"<Name>(.*?)</Name><Value>(.*?)</Value></member>",
        text,
        re.S,
    )
    assert exports, text[:600]
    found = next(
        (stack_id, value) for stack_id, name, value in exports if html.unescape(name) == EXPORT_NAME
    )
    assert found[0].startswith(f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/")
    assert found[1].startswith(f"arn:aws:sns:{REGION}:{ACCOUNT}:")
