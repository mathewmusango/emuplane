"""Step Functions on the wire: every console action, driven through the JSON protocol.

A state machine created here is left in place; the delete actions create one of their own.
The definition is a single Pass state, so nothing has to be invoked to prove the machine exists.
Executions and activities are left in place too: a sweep against the lab re-runs over them.
"""

from __future__ import annotations

import json
import time
import uuid
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "AWSStepFunctions."
HEADERS = {"Content-Type": "application/x-amz-json-1.0"}
ROLE_NAME = "ops-state-machine"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
TRUST = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "states.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)
DEFINITION = json.dumps(
    {"StartAt": "Done", "States": {"Done": {"Type": "Pass", "End": True}}}
)
UPDATED = json.dumps(
    {
        "StartAt": "Done",
        "States": {"Done": {"Type": "Pass", "Result": {"version": 2}, "End": True}},
    }
)
WAITING = json.dumps(
    {
        "StartAt": "Delay",
        "States": {"Delay": {"Type": "Wait", "Seconds": 3600, "End": True}},
    }
)


def ensure_role(endpoint) -> None:
    """A live emulator checks the role exists; in-process it is always admitted."""
    body = urlencode(
        {
            "Action": "CreateRole",
            "Version": "2010-05-08",
            "RoleName": ROLE_NAME,
            "AssumeRolePolicyDocument": TRUST,
        }
    )
    status, text = signed.request(endpoint, "iam", ACCOUNT, REGION, "POST", "/", body, FORM)
    assert status == 200 or "EntityAlreadyExists" in text, text[:300]


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "states", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    # A lab sweep re-runs against the machines an earlier sweep deliberately left behind.
    if status == 200:
        return json.loads(text or "{}")
    assert "AlreadyExists" in text, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def machine(endpoint, name: str, definition: str = DEFINITION, kind: str = "STANDARD") -> str:
    ensure_role(endpoint)
    status, text = call(
        endpoint,
        "CreateStateMachine",
        name=name,
        definition=definition,
        roleArn=ROLE,
        type=kind,
    )
    if status == 200:
        return json.loads(text)["stateMachineArn"]
    assert "AlreadyExists" in text, f"CreateStateMachine answered {status}: {text[:400]}"
    listed = ok(endpoint, "ListStateMachines")["stateMachines"]
    return next(item["stateMachineArn"] for item in listed if item["name"] == name)


def activity(endpoint, name: str) -> str:
    """Create the activity, or return the one an earlier sweep left behind."""
    status, text = call(endpoint, "CreateActivity", name=name)
    if status == 200:
        return json.loads(text)["activityArn"]
    assert "AlreadyExists" in text, f"CreateActivity answered {status}: {text[:400]}"
    listed = ok(endpoint, "ListActivities")["activities"]
    return next(item["activityArn"] for item in listed if item["name"] == name)


def start(endpoint, machine_arn: str, name: str, input_json: str = "{}") -> str:
    """Start one execution, tolerating the name an earlier sweep already used."""
    status, text = call(
        endpoint,
        "StartExecution",
        stateMachineArn=machine_arn,
        name=name,
        input=input_json,
    )
    if status == 200:
        return json.loads(text)["executionArn"]
    assert "ExecutionAlreadyExists" in text, f"StartExecution answered {status}: {text[:400]}"
    listed = ok(endpoint, "ListExecutions", stateMachineArn=machine_arn)["executions"]
    return next(item["executionArn"] for item in listed if item["name"] == name)


def settled(endpoint, execution_arn: str, timeout: float = 20.0) -> dict:
    """DescribeExecution until the run leaves RUNNING; a Pass run ends in about 0.2s."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, text = call(endpoint, "DescribeExecution", executionArn=execution_arn)
        assert status == 200, f"DescribeExecution answered {status}: {text[:400]}"
        described = json.loads(text)
        if described["status"] != "RUNNING":
            return described
        time.sleep(0.1)
    raise AssertionError(f"{execution_arn} was still RUNNING after {timeout}s")


def callback_definition(activity_arn: str) -> str:
    """A Task on an activity: the worker takes the token off GetActivityTask, then SendTask*."""
    return json.dumps(
        {
            "StartAt": "Work",
            "States": {
                "Work": {
                    "Type": "Task",
                    "Resource": activity_arn,
                    "TimeoutSeconds": 3600,
                    "End": True,
                }
            },
        }
    )


def queued_task(endpoint, activity_arn: str, marker: str, attempts: int = 5) -> dict:
    """The activity task GetActivityTask hands this run's execution.

    A lab sweep can leave an earlier run's task queued; the marker in the
    execution input tells ours apart, and abandoned ones are stepped over.
    """
    for _ in range(attempts):
        status, text = call(endpoint, "GetActivityTask", activityArn=activity_arn)
        assert status == 200, f"GetActivityTask answered {status}: {text[:400]}"
        task = json.loads(text or "{}")
        if not task.get("taskToken"):
            break  # the queue emptied without carrying our task
        if marker in (task.get("input") or ""):
            return task
    raise AssertionError(f"GetActivityTask never handed out the task carrying {marker!r}")


def callback_run(endpoint, machine_arn: str, activity_arn: str) -> tuple[str, str, dict]:
    """Start an execution that blocks on the activity, and take its task."""
    marker = uuid.uuid4().hex
    execution_arn = start(
        endpoint,
        machine_arn,
        f"callback-{marker[:8]}",
        json.dumps({"marker": marker}),
    )
    return execution_arn, marker, queued_task(endpoint, activity_arn, marker)


def test_create_state_machine_is_read_back_by_list_and_describe(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-created")
    listed = ok(s3_endpoint, "ListStateMachines")["stateMachines"]
    assert arn in [item["stateMachineArn"] for item in listed]
    described = ok(s3_endpoint, "DescribeStateMachine", stateMachineArn=arn)
    assert described["name"] == "ops-states-created"


def test_delete_state_machine_removes_the_machine_it_created(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-deleted")
    ok(s3_endpoint, "DeleteStateMachine", stateMachineArn=arn)
    listed = ok(s3_endpoint, "ListStateMachines")["stateMachines"]
    assert arn not in [item["stateMachineArn"] for item in listed]


def test_describe_state_machine_reports_definition_and_role(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-described")
    described = ok(s3_endpoint, "DescribeStateMachine", stateMachineArn=arn)
    assert described["stateMachineArn"] == arn
    assert described["name"] == "ops-states-described"
    assert described["roleArn"] == ROLE
    assert described["type"] == "STANDARD"
    assert described["status"] == "ACTIVE"
    assert json.loads(described["definition"]) == json.loads(DEFINITION)


def test_update_state_machine_replaces_the_definition(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-updated")
    updated = ok(
        s3_endpoint, "UpdateStateMachine", stateMachineArn=arn, definition=UPDATED, roleArn=ROLE
    )
    assert updated["updateDate"]
    described = ok(s3_endpoint, "DescribeStateMachine", stateMachineArn=arn)
    definition = json.loads(described["definition"])
    assert definition["States"]["Done"]["Result"] == {"version": 2}


def test_start_execution_runs_the_pass_definition(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-started")
    execution = start(s3_endpoint, arn, "started-run", json.dumps({"greeting": "hi"}))
    described = settled(s3_endpoint, execution)
    assert described["executionArn"] == execution
    assert described["stateMachineArn"] == arn
    assert described["status"] == "SUCCEEDED"
    assert json.loads(described["output"]) == {"greeting": "hi"}


def test_start_sync_execution_returns_the_output(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-sync", kind="EXPRESS")
    result = ok(
        s3_endpoint,
        "StartSyncExecution",
        stateMachineArn=arn,
        name="sync-run",
        input=json.dumps({"greeting": "hi"}),
    )
    assert result["status"] == "SUCCEEDED"
    assert result["stateMachineArn"] == arn
    assert result["stopDate"]
    assert json.loads(result["output"]) == {"greeting": "hi"}


def test_stop_execution_aborts_a_waiting_execution(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-stopped", WAITING)
    execution = start(s3_endpoint, arn, "stopped-run")
    stopped = ok(
        s3_endpoint,
        "StopExecution",
        executionArn=execution,
        error="OpsStopped",
        cause="the sweep stopped it",
    )
    assert stopped["stopDate"]
    assert settled(s3_endpoint, execution)["status"] == "ABORTED"


def test_describe_execution_reports_status_and_output(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-execution")
    execution = start(s3_endpoint, arn, "described-run", json.dumps({"step": 1}))
    described = settled(s3_endpoint, execution)
    assert described["name"] == "described-run"
    assert described["status"] == "SUCCEEDED"
    assert json.loads(described["input"]) == {"step": 1}
    assert json.loads(described["output"]) == {"step": 1}
    assert described["startDate"]
    assert described["stopDate"]


def test_describe_state_machine_for_execution_reports_the_definition(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-for-execution")
    execution = start(s3_endpoint, arn, "for-execution-run")
    settled(s3_endpoint, execution)
    described = ok(s3_endpoint, "DescribeStateMachineForExecution", executionArn=execution)
    assert described["stateMachineArn"] == arn
    assert described["name"] == "ops-states-for-execution"
    assert described["roleArn"] == ROLE
    assert json.loads(described["definition"]) == json.loads(DEFINITION)
    assert described["updateDate"]


def test_list_executions_filters_by_state_machine(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-listed")
    first = start(s3_endpoint, arn, "listed-run-a")
    second = start(s3_endpoint, arn, "listed-run-b")
    settled(s3_endpoint, first)
    settled(s3_endpoint, second)
    listed = ok(s3_endpoint, "ListExecutions", stateMachineArn=arn)["executions"]
    found = [item["executionArn"] for item in listed]
    assert first in found
    assert second in found
    assert {item["stateMachineArn"] for item in listed} == {arn}
    succeeded = ok(
        s3_endpoint, "ListExecutions", stateMachineArn=arn, statusFilter="SUCCEEDED"
    )["executions"]
    assert {item["status"] for item in succeeded} == {"SUCCEEDED"}


def test_get_execution_history_lists_execution_events(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-history")
    execution = start(s3_endpoint, arn, "history-run", json.dumps({"step": 1}))
    settled(s3_endpoint, execution)
    history = ok(s3_endpoint, "GetExecutionHistory", executionArn=execution)["events"]
    types = [event["type"] for event in history]
    assert types[0] == "ExecutionStarted"
    assert types[-1] == "ExecutionSucceeded"
    assert [event["id"] for event in history] == sorted(event["id"] for event in history)
    # The data is elided on request, as the console does for large payloads.
    elided = ok(
        s3_endpoint,
        "GetExecutionHistory",
        executionArn=execution,
        includeExecutionData=False,
    )["events"]
    started = next(event for event in elided if event["type"] == "ExecutionStarted")
    assert "input" not in started["executionStartedEventDetails"]


def test_get_activity_task_returns_a_token_and_input(s3_endpoint):
    activity_arn = activity(s3_endpoint, "ops-states-activity")
    machine_arn = machine(s3_endpoint, "ops-states-callback", callback_definition(activity_arn))
    execution, marker, task = callback_run(s3_endpoint, machine_arn, activity_arn)
    assert task["taskToken"]
    assert json.loads(task["input"])["marker"] == marker
    # Release the waiting execution so no worker thread stays blocked in the lab.
    ok(s3_endpoint, "SendTaskSuccess", taskToken=task["taskToken"], output="{}")
    assert settled(s3_endpoint, execution)["status"] == "SUCCEEDED"


def test_send_task_success_finishes_the_callback(s3_endpoint):
    activity_arn = activity(s3_endpoint, "ops-states-activity")
    machine_arn = machine(s3_endpoint, "ops-states-callback", callback_definition(activity_arn))
    execution, _marker, task = callback_run(s3_endpoint, machine_arn, activity_arn)
    ok(
        s3_endpoint,
        "SendTaskSuccess",
        taskToken=task["taskToken"],
        output=json.dumps({"approved": True}),
    )
    described = settled(s3_endpoint, execution)
    assert described["status"] == "SUCCEEDED"
    assert json.loads(described["output"]) == {"approved": True}
    # A token that was never issued is refused rather than silently accepted.
    status, text = call(s3_endpoint, "SendTaskSuccess", taskToken=uuid.uuid4().hex, output="{}")
    assert status == 400 and "TaskDoesNotExist" in text, f"answered {status}: {text[:300]}"


def test_send_task_failure_fails_the_callback(s3_endpoint):
    activity_arn = activity(s3_endpoint, "ops-states-activity")
    machine_arn = machine(s3_endpoint, "ops-states-callback", callback_definition(activity_arn))
    execution, _marker, task = callback_run(s3_endpoint, machine_arn, activity_arn)
    ok(
        s3_endpoint,
        "SendTaskFailure",
        taskToken=task["taskToken"],
        error="OpsTaskFailed",
        cause="the worker refused",
    )
    described = settled(s3_endpoint, execution)
    assert described["status"] == "FAILED"
    assert described["error"] == "OpsTaskFailed"
    assert described["cause"] == "the worker refused"


def test_send_task_heartbeat_keeps_the_task(s3_endpoint):
    activity_arn = activity(s3_endpoint, "ops-states-activity")
    machine_arn = machine(s3_endpoint, "ops-states-callback", callback_definition(activity_arn))
    execution, _marker, task = callback_run(s3_endpoint, machine_arn, activity_arn)
    ok(s3_endpoint, "SendTaskHeartbeat", taskToken=task["taskToken"])
    # A heartbeat neither ends the task nor the execution: the token still finishes it.
    status, text = call(s3_endpoint, "DescribeExecution", executionArn=execution)
    assert status == 200 and json.loads(text)["status"] == "RUNNING", text[:300]
    ok(s3_endpoint, "SendTaskSuccess", taskToken=task["taskToken"], output="{}")
    assert settled(s3_endpoint, execution)["status"] == "SUCCEEDED"


def test_create_activity_is_read_back_by_describe_and_list(s3_endpoint):
    arn = activity(s3_endpoint, "ops-states-activity")
    described = ok(s3_endpoint, "DescribeActivity", activityArn=arn)
    assert described["activityArn"] == arn
    assert described["name"] == "ops-states-activity"
    assert described["creationDate"]
    listed = ok(s3_endpoint, "ListActivities")["activities"]
    assert arn in [item["activityArn"] for item in listed]


def test_delete_activity_removes_the_activity_it_created(s3_endpoint):
    arn = activity(s3_endpoint, "ops-states-activity-deleted")
    ok(s3_endpoint, "DeleteActivity", activityArn=arn)
    status, text = call(s3_endpoint, "DescribeActivity", activityArn=arn)
    assert status == 400 and "ActivityDoesNotExist" in text, f"answered {status}: {text[:300]}"
    listed = ok(s3_endpoint, "ListActivities")["activities"]
    assert arn not in [item["activityArn"] for item in listed]


def test_describe_activity_reports_the_creation_date(s3_endpoint):
    arn = activity(s3_endpoint, "ops-states-activity")
    described = ok(s3_endpoint, "DescribeActivity", activityArn=arn)
    assert described["activityArn"] == arn
    assert described["name"] == "ops-states-activity"
    # Step Functions models timestamps as JSON numbers, not ISO strings.
    assert isinstance(described["creationDate"], (int, float))


def test_list_activities_includes_the_shared_activity(s3_endpoint):
    arn = activity(s3_endpoint, "ops-states-activity")
    listed = ok(s3_endpoint, "ListActivities")["activities"]
    assert arn in [item["activityArn"] for item in listed]
    assert all(item["name"] and item["creationDate"] for item in listed)


def test_test_state_runs_the_pass_state(s3_endpoint):
    result = ok(
        s3_endpoint,
        "TestState",
        definition=json.dumps(
            {
                "StartAt": "Done",
                "States": {
                    "Done": {"Type": "Pass", "Result": {"ok": True}, "End": True}
                },
            }
        ),
        input=json.dumps({"step": 1}),
        inspectionLevel="DEBUG",
    )
    assert result["status"] == "SUCCEEDED"
    assert json.loads(result["output"]) == {"ok": True}
    assert "nextState" not in result
    assert json.loads(result["inspectionData"]["input"]) == {"step": 1}


def test_tag_resource_adds_a_tag(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-tagged")
    ok(
        s3_endpoint,
        "TagResource",
        resourceArn=arn,
        tags=[{"key": "env", "value": "ops"}, {"key": "owner", "value": "platform"}],
    )
    tags = ok(s3_endpoint, "ListTagsForResource", resourceArn=arn)["tags"]
    assert {"key": "env", "value": "ops"} in tags
    assert {"key": "owner", "value": "platform"} in tags
    # Only a Step Functions resource of this account and region can be tagged.
    status, text = call(s3_endpoint, "TagResource", resourceArn="not-an-arn", tags=[])
    assert status == 400 and "InvalidArn" in text, f"answered {status}: {text[:300]}"


def test_untag_resource_removes_the_tag(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-tagged")
    ok(
        s3_endpoint,
        "TagResource",
        resourceArn=arn,
        tags=[{"key": "env", "value": "ops"}, {"key": "owner", "value": "platform"}],
    )
    ok(s3_endpoint, "UntagResource", resourceArn=arn, tagKeys=["owner"])
    tags = ok(s3_endpoint, "ListTagsForResource", resourceArn=arn)["tags"]
    keys = [tag["key"] for tag in tags]
    assert "owner" not in keys
    assert "env" in keys


def test_list_tags_for_resource_lists_the_tags(s3_endpoint):
    arn = machine(s3_endpoint, "ops-states-tags-listed")
    ok(s3_endpoint, "TagResource", resourceArn=arn, tags=[{"key": "team", "value": "ops"}])
    tags = ok(s3_endpoint, "ListTagsForResource", resourceArn=arn)["tags"]
    assert tags == [{"key": "team", "value": "ops"}]
