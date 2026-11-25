"""AutoScaling on the wire: all 23 advertised operations, Query/XML.

Signed with the `autoscaling` credential scope and sent as form-encoded
`Action=...` requests. Groups, launch configurations, policies, hooks and
scheduled actions are keyed by name; a stable group carries most tests while a
create or delete test makes its own. No instances actually run.
"""

from __future__ import annotations

import time
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2011-01-01"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
ASG = "ops-asg"
LC = "ops-lc"


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "autoscaling", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return text


def refused(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:400]}"
    return text


def ensure_lc(endpoint, name: str = LC) -> str:
    status, text = call(endpoint, "CreateLaunchConfiguration", LaunchConfigurationName=name, ImageId="ami-12345678", InstanceType="t3.micro")
    assert status == 200 or "AlreadyExists" in text, text[:300]
    return name


def ensure_asg(endpoint, name: str = ASG) -> str:
    ensure_lc(endpoint)
    status, text = call(
        endpoint,
        "CreateAutoScalingGroup",
        AutoScalingGroupName=name,
        LaunchConfigurationName=LC,
        MinSize="0",
        MaxSize="2",
        DesiredCapacity="0",
        **{"AvailabilityZones.member.1": f"{REGION}a"},
    )
    assert status == 200 or "AlreadyExists" in text, text[:300]
    return name


def asg_xml(endpoint, name: str = ASG) -> str:
    return ok(endpoint, "DescribeAutoScalingGroups", **{"AutoScalingGroupNames.member.1": name})


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_create_auto_scaling_group_is_read_back(endpoint):
    name = f"ops-asg-created-{time.time_ns()}"
    ensure_lc(endpoint)
    ok(
        endpoint,
        "CreateAutoScalingGroup",
        AutoScalingGroupName=name,
        LaunchConfigurationName=LC,
        MinSize="0",
        MaxSize="1",
        **{"AvailabilityZones.member.1": f"{REGION}a"},
    )
    assert name in asg_xml(endpoint, name)


def test_describe_auto_scaling_groups_reads_the_group(endpoint):
    ensure_asg(endpoint)
    assert f"<AutoScalingGroupName>{ASG}</AutoScalingGroupName>" in asg_xml(endpoint)


def test_update_auto_scaling_group_changes_the_max_size(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "UpdateAutoScalingGroup", AutoScalingGroupName=ASG, MaxSize="3")
    assert "<MaxSize>3</MaxSize>" in asg_xml(endpoint)


def test_delete_auto_scaling_group_removes_the_group_it_created(endpoint):
    name = f"ops-asg-deleted-{time.time_ns()}"
    ensure_lc(endpoint)
    ok(endpoint, "CreateAutoScalingGroup", AutoScalingGroupName=name, LaunchConfigurationName=LC, MinSize="0", MaxSize="1")
    ok(endpoint, "DeleteAutoScalingGroup", AutoScalingGroupName=name)
    assert f"<AutoScalingGroupName>{name}</AutoScalingGroupName>" not in ok(
        endpoint, "DescribeAutoScalingGroups"
    )


def test_set_desired_capacity_changes_the_group(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "SetDesiredCapacity", AutoScalingGroupName=ASG, DesiredCapacity="1")
    assert "<DesiredCapacity>1</DesiredCapacity>" in asg_xml(endpoint)
    ok(endpoint, "SetDesiredCapacity", AutoScalingGroupName=ASG, DesiredCapacity="0")


def test_describe_auto_scaling_instances_answers_instances(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "SetDesiredCapacity", AutoScalingGroupName=ASG, DesiredCapacity="1")
    text = ok(endpoint, "DescribeAutoScalingInstances")
    assert "<AutoScalingInstances>" in text
    ok(endpoint, "SetDesiredCapacity", AutoScalingGroupName=ASG, DesiredCapacity="0")


# ---------------------------------------------------------------------------
# Launch configurations
# ---------------------------------------------------------------------------


def test_create_launch_configuration_is_read_back(endpoint):
    name = f"ops-lc-created-{time.time_ns()}"
    ok(endpoint, "CreateLaunchConfiguration", LaunchConfigurationName=name, ImageId="ami-12345678", InstanceType="t3.micro")
    text = ok(endpoint, "DescribeLaunchConfigurations", **{"LaunchConfigurationNames.member.1": name})
    assert f"<LaunchConfigurationName>{name}</LaunchConfigurationName>" in text


def test_describe_launch_configurations_lists_the_configuration(endpoint):
    ensure_lc(endpoint)
    assert f"<LaunchConfigurationName>{LC}</LaunchConfigurationName>" in ok(endpoint, "DescribeLaunchConfigurations")


def test_delete_launch_configuration_removes_the_configuration_it_created(endpoint):
    name = f"ops-lc-deleted-{time.time_ns()}"
    ok(endpoint, "CreateLaunchConfiguration", LaunchConfigurationName=name, ImageId="ami-12345678")
    ok(endpoint, "DeleteLaunchConfiguration", LaunchConfigurationName=name)
    assert f"<LaunchConfigurationName>{name}</LaunchConfigurationName>" not in ok(endpoint, "DescribeLaunchConfigurations")


# ---------------------------------------------------------------------------
# Scaling policies
# ---------------------------------------------------------------------------


def test_put_scaling_policy_is_read_back(endpoint):
    ensure_asg(endpoint)
    ok(
        endpoint,
        "PutScalingPolicy",
        AutoScalingGroupName=ASG,
        PolicyName="ops-policy",
        PolicyType="SimpleScaling",
        AdjustmentType="ChangeInCapacity",
        ScalingAdjustment="1",
        Cooldown="60",
    )
    text = ok(endpoint, "DescribePolicies", AutoScalingGroupName=ASG)
    assert "<PolicyName>ops-policy</PolicyName>" in text


def test_describe_policies_lists_the_policy(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutScalingPolicy", AutoScalingGroupName=ASG, PolicyName="ops-policy", PolicyType="SimpleScaling", AdjustmentType="ChangeInCapacity", ScalingAdjustment="1")
    assert "<PolicyName>ops-policy</PolicyName>" in ok(endpoint, "DescribePolicies", AutoScalingGroupName=ASG)


def test_delete_policy_removes_the_policy_it_created(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutScalingPolicy", AutoScalingGroupName=ASG, PolicyName="ops-policy-doomed", PolicyType="SimpleScaling", AdjustmentType="ChangeInCapacity", ScalingAdjustment="1")
    ok(endpoint, "DeletePolicy", AutoScalingGroupName=ASG, PolicyName="ops-policy-doomed")
    assert "<PolicyName>ops-policy-doomed</PolicyName>" not in ok(endpoint, "DescribePolicies", AutoScalingGroupName=ASG)


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


def test_put_lifecycle_hook_is_read_back(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutLifecycleHook", AutoScalingGroupName=ASG, LifecycleHookName="ops-hook", LifecycleTransition="autoscaling:EC2_INSTANCE_LAUNCHING")
    assert "<LifecycleHookName>ops-hook</LifecycleHookName>" in ok(endpoint, "DescribeLifecycleHooks", AutoScalingGroupName=ASG)


def test_describe_lifecycle_hooks_lists_the_hook(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutLifecycleHook", AutoScalingGroupName=ASG, LifecycleHookName="ops-hook", LifecycleTransition="autoscaling:EC2_INSTANCE_LAUNCHING")
    assert "<LifecycleHookName>ops-hook</LifecycleHookName>" in ok(endpoint, "DescribeLifecycleHooks", AutoScalingGroupName=ASG)


def test_delete_lifecycle_hook_removes_the_hook_it_created(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutLifecycleHook", AutoScalingGroupName=ASG, LifecycleHookName="ops-hook-doomed", LifecycleTransition="autoscaling:EC2_INSTANCE_LAUNCHING")
    ok(endpoint, "DeleteLifecycleHook", AutoScalingGroupName=ASG, LifecycleHookName="ops-hook-doomed")
    assert "<LifecycleHookName>ops-hook-doomed</LifecycleHookName>" not in ok(endpoint, "DescribeLifecycleHooks", AutoScalingGroupName=ASG)


def test_complete_lifecycle_action_is_accepted(endpoint):
    text = ok(
        endpoint,
        "CompleteLifecycleAction",
        AutoScalingGroupName=ASG,
        LifecycleHookName="ops-hook",
        LifecycleActionToken="ops-token",
        LifecycleActionResult="CONTINUE",
    )
    assert "CompleteLifecycleActionResponse" in text


def test_record_lifecycle_action_heartbeat_is_accepted(endpoint):
    text = ok(
        endpoint,
        "RecordLifecycleActionHeartbeat",
        AutoScalingGroupName=ASG,
        LifecycleHookName="ops-hook",
        LifecycleActionToken="ops-token",
    )
    assert "RecordLifecycleActionHeartbeatResponse" in text


# ---------------------------------------------------------------------------
# Scheduled actions
# ---------------------------------------------------------------------------


def test_put_scheduled_update_group_action_is_read_back(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutScheduledUpdateGroupAction", AutoScalingGroupName=ASG, ScheduledActionName="ops-schedule", Recurrence="0 5 * * *", DesiredCapacity="1")
    assert "<ScheduledActionName>ops-schedule</ScheduledActionName>" in ok(endpoint, "DescribeScheduledActions", AutoScalingGroupName=ASG)


def test_describe_scheduled_actions_lists_the_action(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutScheduledUpdateGroupAction", AutoScalingGroupName=ASG, ScheduledActionName="ops-schedule", Recurrence="0 5 * * *", DesiredCapacity="1")
    assert "<ScheduledActionName>ops-schedule</ScheduledActionName>" in ok(endpoint, "DescribeScheduledActions", AutoScalingGroupName=ASG)


def test_delete_scheduled_action_removes_the_action_it_created(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "PutScheduledUpdateGroupAction", AutoScalingGroupName=ASG, ScheduledActionName="ops-schedule-doomed", Recurrence="0 5 * * *", DesiredCapacity="1")
    ok(endpoint, "DeleteScheduledAction", AutoScalingGroupName=ASG, ScheduledActionName="ops-schedule-doomed")
    assert "<ScheduledActionName>ops-schedule-doomed</ScheduledActionName>" not in ok(endpoint, "DescribeScheduledActions", AutoScalingGroupName=ASG)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_create_or_update_tags_is_read_back(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "CreateOrUpdateTags", **{"Tags.member.1.ResourceId": ASG, "Tags.member.1.ResourceType": "auto-scaling-group", "Tags.member.1.Key": "ops-env", "Tags.member.1.Value": "ops", "Tags.member.1.PropagateAtLaunch": "true"})
    assert "<Key>ops-env</Key>" in asg_xml(endpoint)


def test_describe_tags_lists_the_tag(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "CreateOrUpdateTags", **{"Tags.member.1.ResourceId": ASG, "Tags.member.1.ResourceType": "auto-scaling-group", "Tags.member.1.Key": "ops-team", "Tags.member.1.Value": "platform"})
    assert "<Key>ops-team</Key>" in ok(endpoint, "DescribeTags")


def test_delete_tags_removes_the_key_it_names(endpoint):
    ensure_asg(endpoint)
    ok(endpoint, "CreateOrUpdateTags", **{"Tags.member.1.ResourceId": ASG, "Tags.member.1.ResourceType": "auto-scaling-group", "Tags.member.1.Key": "ops-doomed", "Tags.member.1.Value": "yes"})
    ok(endpoint, "DeleteTags", **{"Tags.member.1.ResourceId": ASG, "Tags.member.1.Key": "ops-doomed"})
    assert "<Key>ops-doomed</Key>" not in asg_xml(endpoint)
