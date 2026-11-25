"""CloudFormation on the wire: the fourteen stack and stack-set operations the emulator advertises.

The emulator answers the Query protocol (`Action=…&Version=2010-05-15`, form-encoded), so every call
here is signed with `signed.request` and read as CloudFormation's XML. A stack deploys in the
background: `CreateStack` answers with a stack id and a stack in `CREATE_IN_PROGRESS`, and
`DescribeStacks` carries it to `CREATE_COMPLETE`. The in-process stand-in serves each request in its
own event loop and cancels the deploy after its first step, so a small stack's resources are
provisioned and every read that does not need a settled stack answers, while the status never leaves
`CREATE_IN_PROGRESS`: an update, which needs `CREATE_COMPLETE`, is proven on the lab and marked
`needs_lifecycle` here. A completion assertion that cannot run in the stand-in is skipped with the
reason stated, never faked.

The stacks and their resources are left in place, so a lab sweep meets them again by name, and only
`DeleteStack` creates a stack of its own to remove. StackSets have no standalone `CreateStackSet` in
this emulator: the set under test is the one an `AWS::CloudFormation::StackSet` resource deploys.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import uuid
from urllib.parse import urlencode

import pytest
import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2010-05-15"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

# Stable names, so a second sweep finds what the first left behind instead of colliding with it.
SHARED = "ops-cfn-shared"
UPDATED = "ops-cfn-updated"
FAILED = "ops-cfn-failed"
ROLLED_BACK = "ops-cfn-rolled-back"
DELETED = "ops-cfn-deleted"
STACK_SET = "ops-cfn-stack-set"
STACK_SET_STACK = "ops-cfn-stack-set-stack"

# The deploy runs in a background task; the stand-in cancels it after one step, the lab keeps its loop.
LIFECYCLE_RUNS = bool(os.environ.get("EP_LAB_EMULATOR"))
needs_lifecycle = pytest.mark.skipif(
    not LIFECYCLE_RUNS,
    reason="the in-process stand-in cancels the deploy before the stack leaves CREATE_IN_PROGRESS; "
    "the live sweep proves completion",
)

# One topic and one queue: two resources make DescribeStackResources a list, and neither needs a
# dependant (a role, a runtime) that a bare emulator does not have.
SHARED_TEMPLATE = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Description": "Emuplane CloudFormation operation sweep",
    "Parameters": {
        "TopicName": {
            "Type": "String",
            "Default": "ops-cfn-shared-topic",
            "Description": "The name of the topic the stack creates.",
        },
        "Owner": {"Type": "String", "Default": "platform", "NoEcho": True},
    },
    "Resources": {
        "Topic": {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": {"Ref": "TopicName"}}},
        "Queue": {"Type": "AWS::SQS::Queue", "Properties": {"QueueName": "ops-cfn-shared-queue"}},
    },
    "Outputs": {
        "TopicArn": {"Description": "The ARN of the topic.", "Value": {"Ref": "Topic"}},
    },
}
# The stack-level tags the shared stack is created with; they are read back from DescribeStacks.
STACK_TAGS = {"Tags.member.1.Key": "owner", "Tags.member.1.Value": "platform"}

# A template that cannot deploy: the property enum the engine validates before provisioning, so the
# stack is deterministic and fails at the same point in the stand-in and on the lab.
FAILING_TEMPLATE = {
    "Resources": {
        "Profile": {
            "Type": "AWS::Signer::SigningProfile",
            "Properties": {"PlatformId": "NOT_A_PLATFORM"},
        }
    }
}

# The stack UpdateStack owns: one parameter whose default is the whole difference between the two
# templates it is moved between, so each update changes something and a second sweep can repeat it.
UPDATE_TEMPLATE = {
    "Parameters": {
        "TopicName": {"Type": "String", "Default": "ops-cfn-updated-a"},
    },
    "Resources": {
        "Topic": {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": {"Ref": "TopicName"}}}
    },
}
UPDATE_TEMPLATE_CHANGED = {
    "Parameters": {
        "TopicName": {"Type": "String", "Default": "ops-cfn-updated-b"},
    },
    "Resources": {
        "Topic": {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": {"Ref": "TopicName"}}}
    },
}

# DeleteStack creates its own stack and removes only that one; the sweep's other stacks stay.
DELETE_TEMPLATE = {
    "Resources": {
        "Topic": {
            "Type": "AWS::SNS::Topic",
            "Properties": {"TopicName": "ops-cfn-deleted-topic"},
        }
    }
}

# The template an `AWS::CloudFormation::StackSet` resource deploys: one self-managed instance in the
# stack's own account and Region is the only shape the emulator accepts.
STACK_SET_TEMPLATE = {
    "Resources": {
        "Set": {
            "Type": "AWS::CloudFormation::StackSet",
            "Properties": {
                "StackSetName": STACK_SET,
                "Description": "Emuplane CloudFormation stack-set sweep",
                "PermissionModel": "SELF_MANAGED",
                "StackInstancesGroup": [
                    {"DeploymentTargets": {"Accounts": [ACCOUNT]}, "Regions": [REGION]}
                ],
                "TemplateBody": json.dumps(
                    {
                        "Resources": {
                            "Topic": {
                                "Type": "AWS::SNS::Topic",
                                "Properties": {"TopicName": "ops-cfn-stack-set-topic"},
                            }
                        }
                    }
                ),
                "Tags": [{"Key": "owner", "Value": "platform"}],
            },
        }
    }
}


# ------------------------------------------------------------------ helpers


def call(endpoint, action: str, **params):
    """One CloudFormation query-protocol call, form-encoded the way a client sends it."""
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "cloudformation", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:600]}"
    return text


def refused(endpoint, action: str, **params) -> str:
    """The service's own refusal, unescaped for reading: an error envelope, never a stack it quietly made."""
    status, text = call(endpoint, action, **params)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:600]}"
    return html.unescape(text)


def field(text: str, tag: str) -> str:
    """The first `<tag>`'s value, unescaped: a template body comes back as escaped JSON."""
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:600]}"
    return html.unescape(match.group(1))


def members(text: str, container: str) -> list[str]:
    """The inner text of each flat `<member>` of one response container."""
    block = re.search(rf"<{container}>(.*?)</{container}>", text, re.S)
    assert block, f"no <{container}> in {text[:600]}"
    return re.findall(r"<member>(.*?)</member>", block.group(1), re.S)


def status_of(endpoint, name: str) -> str | None:
    """The stack's status, or None where the name answers no stack."""
    status, text = call(endpoint, "DescribeStacks", StackName=name)
    if status != 200:
        assert "does not exist" in text, text[:600]
        return None
    return field(text, "StackStatus")


def settle(
    endpoint, name: str, terminal: tuple[str, ...] = ("CREATE_COMPLETE",), timeout: float = 20.0
) -> str:
    """DescribeStacks until the stack reaches a terminal status; bounded, never an open loop."""
    deadline = time.monotonic() + timeout
    while True:
        answer = ok(endpoint, "DescribeStacks", StackName=name)
        status = field(answer, "StackStatus")
        if status in terminal:
            return status
        assert time.monotonic() < deadline, f"{name} was still {status} after {timeout}s"
        time.sleep(0.1)


def ensure_stack(endpoint, name: str, template: dict, **params) -> None:
    """Find-or-create by name: a lab re-run meets the stack an earlier sweep left behind."""
    if status_of(endpoint, name) is not None:
        return
    text = ok(endpoint, "CreateStack", StackName=name, TemplateBody=json.dumps(template), **params)
    assert f":stack/{name}/" in field(text, "StackId"), text[:600]


def failed_stack(endpoint, name: str) -> None:
    """A stack in CREATE_FAILED, the state RollbackStack is defined for; a re-run finds or re-makes it."""
    current = status_of(endpoint, name)
    if current == "CREATE_FAILED":
        return
    assert current in (None, "ROLLBACK_COMPLETE"), f"{name} is {current}"
    ok(
        endpoint,
        "CreateStack",
        StackName=name,
        TemplateBody=json.dumps(FAILING_TEMPLATE),
        DisableRollback="true",
    )
    assert settle(endpoint, name, ("CREATE_FAILED",)) == "CREATE_FAILED"


def settle_away(endpoint, name: str, timeout: float = 20.0) -> None:
    """DescribeStacks until the name answers no stack; bounded, like every other wait here."""
    deadline = time.monotonic() + timeout
    while status_of(endpoint, name) is not None:
        assert time.monotonic() < deadline, f"{name} was still a stack after {timeout}s"
        time.sleep(0.1)


# ------------------------------------------------------- ValidateTemplate, GetTemplateSummary


def test_validate_template_reports_what_the_template_declares(endpoint):
    """ValidateTemplate echoes the description and every parameter, and omits the capabilities it lacks."""
    text = ok(endpoint, "ValidateTemplate", TemplateBody=json.dumps(SHARED_TEMPLATE))
    assert field(text, "Description") == SHARED_TEMPLATE["Description"]
    parameters = members(text, "Parameters")
    assert [field(parameter, "ParameterKey") for parameter in parameters] == ["TopicName", "Owner"]
    assert field(parameters[0], "DefaultValue") == "ops-cfn-shared-topic"
    assert field(parameters[0], "Description") == "The name of the topic the stack creates."
    assert field(parameters[0], "NoEcho") == "false"
    assert field(parameters[1], "NoEcho") == "true"
    # SNS and SQS need no capability and the template declares no transform, so AWS omits both.
    assert "<Capabilities>" not in text
    assert "<DeclaredTransforms>" not in text

    # An IAM resource is what makes an account ask for a capability, and it is reported as one.
    role = {
        "Resources": {
            "Role": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "sns.amazonaws.com"},
                                "Action": "sts:AssumeRole",
                            }
                        ],
                    }
                },
            }
        }
    }
    text = ok(endpoint, "ValidateTemplate", TemplateBody=json.dumps(role))
    assert members(text, "Capabilities") == ["CAPABILITY_IAM"]


def test_validate_template_refuses_a_template_it_cannot_read(endpoint):
    """No body, unreadable JSON and no Resources are three refusal a client can meet."""
    assert "TemplateBody is required" in refused(endpoint, "ValidateTemplate")
    assert "Template format error" in refused(endpoint, "ValidateTemplate", TemplateBody="{not json")
    text = refused(
        endpoint, "ValidateTemplate", TemplateBody=json.dumps({"Description": "no resources"})
    )
    assert "At least one Resources member must be defined" in text


def test_get_template_summary_reads_a_body_and_a_stack(endpoint):
    """GetTemplateSummary reads a body it is given and, with no body, the template a stack stores."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    text = ok(endpoint, "GetTemplateSummary", TemplateBody=json.dumps(SHARED_TEMPLATE))
    assert field(text, "Description") == SHARED_TEMPLATE["Description"]
    assert members(text, "ResourceTypes") == ["AWS::SNS::Topic", "AWS::SQS::Queue"]
    parameters = members(text, "Parameters")
    assert [field(parameter, "ParameterKey") for parameter in parameters] == ["TopicName", "Owner"]
    assert field(parameters[1], "NoEcho") == "true"
    assert "<Capabilities>" not in text

    from_stack = ok(endpoint, "GetTemplateSummary", StackName=SHARED)
    assert members(from_stack, "ResourceTypes") == ["AWS::SNS::Topic", "AWS::SQS::Queue"]
    assert field(from_stack, "Description") == SHARED_TEMPLATE["Description"]

    text = refused(endpoint, "GetTemplateSummary")
    assert "Either TemplateBody, TemplateURL, or StackName must be provided" in text


# ------------------------------------------------ CreateStack, DescribeStacks, ListStacks


def test_create_stack_mints_a_stack_id_and_refuses_a_second_create(endpoint):
    """A create answers its stack id; the name is then taken, and two malformed requests are refused."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    stack_id = field(ok(endpoint, "DescribeStacks", StackName=SHARED), "StackId")
    assert stack_id.startswith(f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{SHARED}/")
    # Nothing takes the name twice, so a replayed create meets the stack rather than replacing it.
    text = refused(
        endpoint, "CreateStack", StackName=SHARED, TemplateBody=json.dumps(SHARED_TEMPLATE)
    )
    assert "AlreadyExistsException" in text
    assert f"Stack [{SHARED}] already exists" in text

    # A create with no template never reaches a stack, and a name outside the documented pattern is a
    # request error rather than a stack nothing can address.
    text = refused(endpoint, "CreateStack", StackName="ops-cfn-no-template")
    assert "TemplateBody or TemplateURL is required" in text
    text = refused(
        endpoint,
        "CreateStack",
        StackName="ops_cfn_bad",
        TemplateBody=json.dumps(SHARED_TEMPLATE),
    )
    assert "Value 'ops_cfn_bad' at 'stackName' failed to satisfy constraint" in text
    assert "[a-zA-Z][-a-zA-Z0-9]*" in text


def test_describe_stacks_reads_the_shared_stack_back(endpoint):
    """DescribeStacks answers the stack's identity, parameters, tags and outputs, by name and by id."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    text = ok(endpoint, "DescribeStacks", StackName=SHARED)
    stack_id = field(text, "StackId")
    assert field(text, "StackName") == SHARED
    assert field(text, "Description") == SHARED_TEMPLATE["Description"]
    assert field(text, "DisableRollback") == "false"
    assert field(text, "EnableTerminationProtection") == "false"
    # The parameters the stack resolved, with the NoEcho value masked as the service masks it.
    parameters = re.search(r"<Parameters>(.*?)</Parameters>", text, re.S)
    assert parameters, text[:600]
    assert field(parameters.group(1), "ParameterValue") == "ops-cfn-shared-topic"
    assert "<ParameterValue>****</ParameterValue>" in parameters.group(1)
    assert "<Key>owner</Key>" in text and "<Value>platform</Value>" in text
    assert field(text, "StackStatus") in ("CREATE_IN_PROGRESS", "CREATE_COMPLETE")

    # A stack is addressable by name or by the unique id a client reads, and both answer one record.
    by_id = ok(endpoint, "DescribeStacks", StackName=stack_id)
    assert field(by_id, "StackName") == SHARED
    assert field(by_id, "StackId") == stack_id

    # Without a name, every stack that is not deleted is described.
    assert f"<StackName>{SHARED}</StackName>" in ok(endpoint, "DescribeStacks")

    text = refused(endpoint, "DescribeStacks", StackName="ops-cfn-nowhere")
    assert "Stack with id ops-cfn-nowhere does not exist" in text

    if LIFECYCLE_RUNS:
        # Completion is the lab's to prove: the output is resolved only once the deploy has finished.
        finished = ok(endpoint, "DescribeStacks", StackName=SHARED)
        assert field(finished, "StackStatus") == "CREATE_COMPLETE"
        assert field(finished, "OutputValue") == (
            f"arn:aws:sns:{REGION}:{ACCOUNT}:ops-cfn-shared-topic"
        )


def test_list_stacks_summarises_the_stacks_it_holds(endpoint):
    """ListStacks is a summary per stack, and its status filter selects on the status a client names."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    summaries = members(ok(endpoint, "ListStacks"), "StackSummaries")
    listed = {field(summary, "StackName"): summary for summary in summaries}
    assert SHARED in listed
    assert field(listed[SHARED], "StackStatus") == status_of(endpoint, SHARED)
    assert f":stack/{SHARED}/" in field(listed[SHARED], "StackId")
    # A summary is not the stack: the outputs and the resources answer on Describe only.
    assert "<Outputs>" not in listed[SHARED]

    status = status_of(endpoint, SHARED)
    filtered = members(
        ok(endpoint, "ListStacks", **{"StackStatusFilter.member.1": status}), "StackSummaries"
    )
    assert SHARED in {field(summary, "StackName") for summary in filtered}
    other = "CREATE_FAILED" if status != "CREATE_FAILED" else "CREATE_COMPLETE"
    excluded = members(
        ok(endpoint, "ListStacks", **{"StackStatusFilter.member.1": other}), "StackSummaries"
    )
    assert SHARED not in {field(summary, "StackName") for summary in excluded}


# ---------------------------------------------------------------- GetTemplate


def test_get_template_returns_the_body_the_stack_was_created_with(endpoint):
    """GetTemplate answers the template as sent, at both stages, and refuses what it cannot address."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    text = ok(endpoint, "GetTemplate", StackName=SHARED)
    assert json.loads(field(text, "TemplateBody")) == SHARED_TEMPLATE
    assert members(text, "StagesAvailable") == ["Original", "Processed"]

    # The template declares no transform, so what the account processed is what it was sent.
    original = ok(endpoint, "GetTemplate", StackName=SHARED, TemplateStage="Original")
    processed = ok(endpoint, "GetTemplate", StackName=SHARED, TemplateStage="Processed")
    assert field(processed, "TemplateBody") == field(original, "TemplateBody")
    assert json.loads(field(processed, "TemplateBody")) == SHARED_TEMPLATE

    text = refused(endpoint, "GetTemplate", StackName="ops-cfn-nowhere")
    assert "Stack [ops-cfn-nowhere] does not exist" in text
    text = refused(endpoint, "GetTemplate", StackName=SHARED, TemplateStage="Sideways")
    assert "Member must satisfy enum value set: [Original, Processed]" in text


# --------------------------------------------------------- DescribeStackEvents


def test_describe_stack_events_orders_the_deploy_newest_first(endpoint):
    """DescribeStackEvents reads newest first, from the user's create down to the resources it made."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    text = ok(endpoint, "DescribeStackEvents", StackName=SHARED)
    events = members(text, "StackEvents")
    assert events

    # The stack's own event is the operation a person started; the resources it makes follow it.
    stack_events = [event for event in events if field(event, "LogicalResourceId") == SHARED]
    assert stack_events
    assert field(stack_events[0], "ResourceType") == "AWS::CloudFormation::Stack"
    assert field(stack_events[0], "PhysicalResourceId").startswith(
        f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{SHARED}/"
    )
    assert "User Initiated" in text
    assert {"Topic", "Queue"} <= {field(event, "LogicalResourceId") for event in events}
    assert "<ResourceStatus>CREATE_COMPLETE</ResourceStatus>" in text

    # Every event carries an id and a timestamp, and the list is ordered newest first.
    timestamps = [field(event, "Timestamp") for event in events]
    assert timestamps == sorted(timestamps, reverse=True)
    for event in events:
        assert str(uuid.UUID(field(event, "EventId"))) == field(event, "EventId")

    assert "StackName is required" in refused(endpoint, "DescribeStackEvents")
    text = refused(endpoint, "DescribeStackEvents", StackName="ops-cfn-nowhere")
    assert "Stack [ops-cfn-nowhere] does not exist" in text


# ------------------------------------- DescribeStackResource, DescribeStackResources


def test_describe_stack_resource_reads_one_resource_of_the_stack(endpoint):
    """DescribeStackResource is the detail of one logical id: its type, its id and its status."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    text = ok(endpoint, "DescribeStackResource", StackName=SHARED, LogicalResourceId="Topic")
    assert field(text, "LogicalResourceId") == "Topic"
    assert field(text, "ResourceType") == "AWS::SNS::Topic"
    assert field(text, "PhysicalResourceId") == (
        f"arn:aws:sns:{REGION}:{ACCOUNT}:ops-cfn-shared-topic"
    )
    assert field(text, "ResourceStatus") == "CREATE_COMPLETE"
    assert field(text, "StackName") == SHARED
    assert field(text, "LastUpdatedTimestamp")

    text = refused(endpoint, "DescribeStackResource", StackName=SHARED, LogicalResourceId="Nope")
    assert f"Resource [Nope] does not exist in stack [{SHARED}]" in text


def test_describe_stack_resources_lists_every_resource(endpoint):
    """DescribeStackResources is every resource of the stack, or the one logical id a client names."""
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    resources = members(ok(endpoint, "DescribeStackResources", StackName=SHARED), "StackResources")
    by_id = {field(resource, "LogicalResourceId"): resource for resource in resources}
    assert set(by_id) == {"Topic", "Queue"}
    assert field(by_id["Topic"], "ResourceType") == "AWS::SNS::Topic"
    assert field(by_id["Topic"], "PhysicalResourceId") == (
        f"arn:aws:sns:{REGION}:{ACCOUNT}:ops-cfn-shared-topic"
    )
    assert field(by_id["Queue"], "ResourceType") == "AWS::SQS::Queue"
    assert field(by_id["Queue"], "PhysicalResourceId").endswith("/ops-cfn-shared-queue")
    assert {field(resource, "ResourceStatus") for resource in resources} == {"CREATE_COMPLETE"}
    assert {field(resource, "StackName") for resource in resources} == {SHARED}

    one = members(
        ok(endpoint, "DescribeStackResources", StackName=SHARED, LogicalResourceId="Queue"),
        "StackResources",
    )
    assert [field(resource, "LogicalResourceId") for resource in one] == ["Queue"]

    text = refused(endpoint, "DescribeStackResources", StackName=SHARED, LogicalResourceId="Nope")
    assert f"Resource [Nope] does not exist in stack [{SHARED}]" in text


# ------------------------------------------------ UpdateStack, RollbackStack, DeleteStack


def test_update_stack_refuses_a_stack_without_a_stable_state(endpoint):
    """UpdateStack takes a settled stack: a failed create and an unknown name are both refused."""
    failed_stack(endpoint, FAILED)
    text = refused(endpoint, "UpdateStack", StackName=FAILED, UsePreviousTemplate="true")
    assert f"Stack [{FAILED}] is in CREATE_FAILED state and cannot be updated" in text

    text = refused(endpoint, "UpdateStack", StackName="ops-cfn-nowhere", UsePreviousTemplate="true")
    assert "Stack [ops-cfn-nowhere] does not exist" in text


@needs_lifecycle
def test_update_stack_applies_the_template_it_is_given(endpoint):
    """UpdateStack replaces the template, settles UPDATE_COMPLETE and refuses an empty update."""
    ensure_stack(endpoint, UPDATED, UPDATE_TEMPLATE)
    settle(endpoint, UPDATED, ("CREATE_COMPLETE", "UPDATE_COMPLETE"))
    # What a previous sweep left is moved to the template this one starts from, so the first update
    # below always has something to change.
    running = json.loads(field(ok(endpoint, "GetTemplate", StackName=UPDATED), "TemplateBody"))
    if running != UPDATE_TEMPLATE:
        ok(endpoint, "UpdateStack", StackName=UPDATED, TemplateBody=json.dumps(UPDATE_TEMPLATE))
        assert settle(endpoint, UPDATED, ("UPDATE_COMPLETE",)) == "UPDATE_COMPLETE"

    text = ok(
        endpoint, "UpdateStack", StackName=UPDATED, TemplateBody=json.dumps(UPDATE_TEMPLATE_CHANGED)
    )
    assert f":stack/{UPDATED}/" in field(text, "StackId")
    assert settle(endpoint, UPDATED, ("UPDATE_COMPLETE",)) == "UPDATE_COMPLETE"

    after = ok(endpoint, "DescribeStacks", StackName=UPDATED)
    assert field(after, "ParameterValue") == "ops-cfn-updated-b"
    resource = ok(endpoint, "DescribeStackResource", StackName=UPDATED, LogicalResourceId="Topic")
    assert field(resource, "PhysicalResourceId") == (
        f"arn:aws:sns:{REGION}:{ACCOUNT}:ops-cfn-updated-b"
    )
    # The template a client reads back is the one the update applied.
    template = ok(endpoint, "GetTemplate", StackName=UPDATED)
    assert json.loads(field(template, "TemplateBody")) == UPDATE_TEMPLATE_CHANGED

    # Sending the template the stack already runs is not an update, and the account says so.
    text = refused(
        endpoint, "UpdateStack", StackName=UPDATED, TemplateBody=json.dumps(UPDATE_TEMPLATE_CHANGED)
    )
    assert "No updates are to be performed." in text

    # Back to the first template, so the state this sweep started from is the state it leaves and a
    # second sweep's first update still changes something.
    ok(endpoint, "UpdateStack", StackName=UPDATED, TemplateBody=json.dumps(UPDATE_TEMPLATE))
    assert settle(endpoint, UPDATED, ("UPDATE_COMPLETE",)) == "UPDATE_COMPLETE"
    template = ok(endpoint, "GetTemplate", StackName=UPDATED)
    assert json.loads(field(template, "TemplateBody")) == UPDATE_TEMPLATE


def test_rollback_stack_rolls_a_failed_create_back(endpoint):
    """RollbackStack returns a failed stack to a stable state, and refuses one that never failed."""
    failed_stack(endpoint, ROLLED_BACK)
    text = ok(endpoint, "RollbackStack", StackName=ROLLED_BACK)
    assert field(text, "StackId").startswith(
        f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{ROLLED_BACK}/"
    )
    assert settle(endpoint, ROLLED_BACK, ("ROLLBACK_COMPLETE",)) == "ROLLBACK_COMPLETE"
    events = ok(endpoint, "DescribeStackEvents", StackName=ROLLED_BACK)
    assert "Rollback complete" in events

    # CREATE_FAILED and UPDATE_FAILED are the only states with something to undo.
    ensure_stack(endpoint, SHARED, SHARED_TEMPLATE, **STACK_TAGS)
    text = refused(endpoint, "RollbackStack", StackName=SHARED)
    assert "RollbackStack cannot be called from current stack status" in text


def test_delete_stack_removes_the_stack_it_created(endpoint):
    """DeleteStack removes the stack it made, and a name with no stack behind it is answered as success."""
    # A stack of its own: only this one goes, the sweep's other stacks and their resources stay.
    ensure_stack(endpoint, DELETED, DELETE_TEMPLATE)
    ok(endpoint, "DeleteStack", StackName=DELETED)

    if LIFECYCLE_RUNS:
        # The lab runs the delete to the end: the name answers no stack and the summary keeps the
        # DELETE_COMPLETE record ListStacks reports.
        settle_away(endpoint, DELETED)
        summaries = members(ok(endpoint, "ListStacks"), "StackSummaries")
        listed = {field(summary, "StackName"): summary for summary in summaries}
        assert field(listed[DELETED], "StackStatus") == "DELETE_COMPLETE"
    else:
        # The stand-in stops after the delete starts, so the transition is what it can show.
        assert status_of(endpoint, DELETED) == "DELETE_IN_PROGRESS"

    # Deleting a stack that is not there is a success: the operation is addressed by name.
    ok(endpoint, "DeleteStack", StackName="ops-cfn-never-created")


# ------------------------------------------------ DescribeStackSet, ListStackInstances


def ensure_stack_set(endpoint) -> None:
    """The StackSet an `AWS::CloudFormation::StackSet` resource deploys; a re-run meets the one left."""
    status, text = call(endpoint, "DescribeStackSet", StackSetName=STACK_SET)
    if status == 200:
        return
    assert status == 404 and "StackSetNotFoundException" in text, text[:600]
    ensure_stack(endpoint, STACK_SET_STACK, STACK_SET_TEMPLATE)
    deadline = time.monotonic() + 20.0
    while call(endpoint, "DescribeStackSet", StackSetName=STACK_SET)[0] != 200:
        assert time.monotonic() < deadline, f"{STACK_SET} was never registered"
        time.sleep(0.1)


def test_describe_stack_set_reads_the_set_a_stack_made(endpoint):
    """DescribeStackSet reads the set an AWS::CloudFormation::StackSet resource deployed."""
    ensure_stack_set(endpoint)
    text = ok(endpoint, "DescribeStackSet", StackSetName=STACK_SET)
    assert field(text, "StackSetName") == STACK_SET
    set_id = field(text, "StackSetId")
    assert re.fullmatch(rf"{STACK_SET}:[0-9a-f-]{{36}}", set_id), set_id
    assert field(text, "Status") == "ACTIVE"
    assert field(text, "Description") == "Emuplane CloudFormation stack-set sweep"
    assert json.loads(field(text, "TemplateBody")) == {
        "Resources": {
            "Topic": {
                "Type": "AWS::SNS::Topic",
                "Properties": {"TopicName": "ops-cfn-stack-set-topic"},
            }
        }
    }
    assert "<Key>owner</Key>" in text and "<Value>platform</Value>" in text
    # The ARN is built from the id, and the roles are the defaults an unconfigured set reports.
    assert field(text, "StackSetARN") == (
        f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stackset/{set_id}"
    )
    assert field(text, "AdministrationRoleARN") == (
        f"arn:aws:iam::{ACCOUNT}:role/AWSCloudFormationStackSetAdministrationRole"
    )
    assert field(text, "ExecutionRoleName") == "AWSCloudFormationStackSetExecutionRole"
    # An active set names the one Region its instance is deployed to.
    assert members(text, "Regions") == [REGION]

    text = refused(endpoint, "DescribeStackSet", StackSetName="ops-cfn-nowhere")
    assert "StackSetNotFoundException" in text
    assert "StackSet ops-cfn-nowhere not found" in text


def test_list_stack_instances_reports_the_one_instance(endpoint):
    """ListStackInstances is the one instance the set deploys, filtered by account and Region."""
    ensure_stack_set(endpoint)
    text = ok(endpoint, "ListStackInstances", StackSetName=STACK_SET)
    summaries = members(text, "Summaries")
    assert len(summaries) == 1
    instance = summaries[0]
    assert field(instance, "Region") == REGION
    assert field(instance, "Account") == ACCOUNT
    assert field(instance, "Status") == "CURRENT"
    assert field(instance, "DetailedStatus") == "SUCCEEDED"
    assert field(instance, "DriftStatus") == "NOT_CHECKED"
    assert field(instance, "StackSetId") == field(
        ok(endpoint, "DescribeStackSet", StackSetName=STACK_SET), "StackSetId"
    )
    # The instance is a nested stack of the parent, named after the set.
    assert field(instance, "StackId").startswith(
        f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/StackSet-{STACK_SET}-"
    )

    # The instance answers only the account and Region it was deployed to.
    elsewhere = ok(endpoint, "ListStackInstances", StackSetName=STACK_SET, StackInstanceRegion="eu-west-1")
    assert members(elsewhere, "Summaries") == []
    text = refused(endpoint, "ListStackInstances", StackSetName="ops-cfn-nowhere")
    assert "StackSet ops-cfn-nowhere not found" in text


# ---------------------------------------------------------------- Rules


# The Rules section runs after the parameters resolve and before any resource is
# touched. The assertion compares a parameter with a literal, which is the plain
# `Fn::Equals` shape the Rules reference documents.
RULES_FAILING_TEMPLATE = {
    "Parameters": {"Env": {"Type": "String", "Default": "prod"}},
    "Rules": {
        "CheckEnv": {
            "Assertions": [
                {
                    "Assert": {"Fn::Equals": [{"Ref": "Env"}, "dev"]},
                    "AssertDescription": "Env must be dev",
                }
            ]
        }
    },
    "Resources": {
        "Topic": {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": "ops-cfn-rules-topic"}}
    },
}
RULES_PASSING_TEMPLATE = {
    **RULES_FAILING_TEMPLATE,
    "Parameters": {"Env": {"Type": "String", "Default": "dev"}},
}


def test_rules_assertions_refuse_a_stack_that_breaks_them(endpoint):
    text = refused(
        endpoint,
        "CreateStack",
        StackName="ops-cfn-rules-refused",
        TemplateBody=json.dumps(RULES_FAILING_TEMPLATE),
    )
    assert "rule CheckEnv failed" in text
    assert "Env must be dev" in text
    # The assertion runs before any resource exists, so no stack was left behind.
    assert status_of(endpoint, "ops-cfn-rules-refused") is None


def test_rules_let_a_satisfied_template_create_the_stack(endpoint):
    if status_of(endpoint, "ops-cfn-rules") is None:
        text = ok(
            endpoint,
            "CreateStack",
            StackName="ops-cfn-rules",
            TemplateBody=json.dumps(RULES_PASSING_TEMPLATE),
        )
        assert ":stack/ops-cfn-rules/" in field(text, "StackId")
    assert status_of(endpoint, "ops-cfn-rules") is not None


# ---------------------------------------------------- Client Request Tokens


def test_client_request_token_is_recorded_on_the_stack_events(endpoint):
    """Every event a stack operation records carries that operation's token."""
    stamp = time.time_ns()
    name = f"ops-cfn-token-{stamp}"
    token = f"ops-cfn-token-{stamp}"
    template = {
        "Resources": {
            "Topic": {
                "Type": "AWS::SNS::Topic",
                "Properties": {"TopicName": f"ops-cfn-token-topic-{stamp}"},
            }
        }
    }
    text = ok(
        endpoint,
        "CreateStack",
        StackName=name,
        TemplateBody=json.dumps(template),
        ClientRequestToken=token,
    )
    assert f":stack/{name}/" in field(text, "StackId")
    events = ok(endpoint, "DescribeStackEvents", StackName=name)
    assert f"<ClientRequestToken>{token}</ClientRequestToken>" in events


# ------------------------------------------------------------- Conditions


# One condition exercises each of the four functions the README names; the second
# is a plain false. Only the resource whose condition holds is created.
CONDITIONS_TEMPLATE = {
    "Conditions": {
        "Always": {
            "Fn::And": [
                {"Fn::Equals": ["a", "a"]},
                {"Fn::Or": [{"Fn::Equals": ["a", "b"]}, {"Fn::Equals": ["a", "a"]}]},
                {"Fn::Not": [{"Fn::Equals": ["a", "b"]}]},
            ]
        },
        "Never": {"Fn::Equals": ["a", "b"]},
    },
    "Resources": {
        "Kept": {
            "Type": "AWS::SNS::Topic",
            "Condition": "Always",
            "Properties": {"TopicName": "ops-cfn-cond-kept"},
        },
        "Skipped": {
            "Type": "AWS::SNS::Topic",
            "Condition": "Never",
            "Properties": {"TopicName": "ops-cfn-cond-skipped"},
        },
    },
}


def test_conditions_create_only_the_resources_whose_condition_holds(endpoint):
    name = "ops-cfn-conditions"
    if status_of(endpoint, name) is None:
        ok(endpoint, "CreateStack", StackName=name, TemplateBody=json.dumps(CONDITIONS_TEMPLATE))
    resources = members(ok(endpoint, "DescribeStackResources", StackName=name), "StackResources")
    assert {field(resource, "LogicalResourceId") for resource in resources} == {"Kept"}


# ------------------------------------------------------------------ Quotas


def test_quotas_are_enforced_before_a_stack_exists(endpoint):
    """The template and stack-name quotas are checked before anything is created."""
    too_many = {"Resources": {f"Topic{i}": {"Type": "AWS::SNS::Topic"} for i in range(501)}}
    text = refused(
        endpoint,
        "CreateStack",
        StackName="ops-cfn-quota",
        TemplateBody=json.dumps(too_many),
    )
    assert "Number of resources, 501" in text
    assert "maximum allowed, 500" in text

    long_name = "a" + "b" * 128
    text = refused(
        endpoint,
        "CreateStack",
        StackName=long_name,
        TemplateBody=json.dumps({"Resources": {}}),
    )
    assert "less than or equal to 128" in text
    # Neither refusal left a stack behind.
    assert status_of(endpoint, "ops-cfn-quota") is None
