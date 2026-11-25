"""Amazon EMR on the wire: all 22 advertised operations, JSON 1.1.

The target prefix is `ElasticMapReduce`. A cluster is created by `RunJobFlow` and
found again by name through `ListClusters`; steps, fleets and groups are child
records. No Spark/Hadoop execution happens, so a step lands `COMPLETED` and a
cluster is `WAITING` when kept alive or `TERMINATED` when not.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "ElasticMapReduce"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
CLUSTER = "ops-emr"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "elasticmapreduce", ACCOUNT, REGION, "POST", "/", body, headers)


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


def run_cluster(endpoint, name: str, **extra) -> str:
    body = {
        "Name": name,
        "Instances": {"KeepJobFlowAliveWhenNoSteps": True, "MasterInstanceType": "m5.xlarge"},
        **extra,
    }
    return ok(endpoint, "RunJobFlow", body)["JobFlowId"]


def ensure_cluster(endpoint, name: str = CLUSTER) -> str:
    clusters = ok(endpoint, "ListClusters")["Clusters"]
    match = next((item for item in clusters if item["Name"] == name), None)
    return match["Id"] if match else run_cluster(endpoint, name)


def add_step(endpoint, cluster_id: str) -> str:
    step = {
        "Name": f"ops-step-{time.time_ns()}",
        "HadoopJarStep": {"Jar": "command-runner.jar", "Args": ["echo", "ops"]},
        "ActionOnFailure": "CONTINUE",
    }
    return ok(endpoint, "AddJobFlowSteps", {"JobFlowId": cluster_id, "Steps": [step]})["StepIds"][0]


def add_fleet(endpoint, cluster_id: str) -> str:
    fleet = {
        "Name": "ops-fleet",
        "InstanceFleetType": "TASK",
        "TargetOnDemandCapacity": 1,
        "InstanceTypeConfigs": [{"InstanceType": "m5.xlarge"}],
    }
    return ok(endpoint, "AddInstanceFleet", {"ClusterId": cluster_id, "InstanceFleet": fleet})["InstanceFleetId"]


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------


def test_run_job_flow_answers_a_cluster(endpoint):
    cluster_id = run_cluster(endpoint, f"ops-emr-created-{time.time_ns()}")
    cluster = ok(endpoint, "DescribeCluster", {"ClusterId": cluster_id})["Cluster"]
    assert cluster["Id"] == cluster_id
    assert cluster["Status"]["State"] == "WAITING"


def test_describe_cluster_reads_the_cluster(endpoint):
    cluster_id = ensure_cluster(endpoint)
    assert ok(endpoint, "DescribeCluster", {"ClusterId": cluster_id})["Cluster"]["Name"] == CLUSTER


def test_list_clusters_lists_the_cluster(endpoint):
    ensure_cluster(endpoint)
    assert CLUSTER in {item["Name"] for item in ok(endpoint, "ListClusters")["Clusters"]}


def test_terminate_job_flows_terminates_the_cluster_it_created(endpoint):
    cluster_id = run_cluster(endpoint, f"ops-emr-terminated-{time.time_ns()}")
    ok(endpoint, "TerminateJobFlows", {"JobFlowIds": [cluster_id]})
    assert ok(endpoint, "DescribeCluster", {"ClusterId": cluster_id})["Cluster"]["Status"]["State"] == "TERMINATED"


def test_modify_cluster_changes_the_step_concurrency(endpoint):
    cluster_id = ensure_cluster(endpoint)
    answer = ok(endpoint, "ModifyCluster", {"ClusterId": cluster_id, "StepConcurrencyLevel": 2})
    assert answer["StepConcurrencyLevel"] == 2


def test_set_termination_protection_protects_the_cluster(endpoint):
    cluster_id = run_cluster(endpoint, f"ops-emr-protected-{time.time_ns()}")
    ok(endpoint, "SetTerminationProtection", {"JobFlowIds": [cluster_id], "TerminationProtected": True})
    assert ok(endpoint, "DescribeCluster", {"ClusterId": cluster_id})["Cluster"]["TerminationProtected"] is True


def test_set_visible_to_all_users_sets_the_flag(endpoint):
    cluster_id = ensure_cluster(endpoint)
    ok(endpoint, "SetVisibleToAllUsers", {"JobFlowIds": [cluster_id], "VisibleToAllUsers": False})
    assert ok(endpoint, "DescribeCluster", {"ClusterId": cluster_id})["Cluster"]["VisibleToAllUsers"] is False
    ok(endpoint, "SetVisibleToAllUsers", {"JobFlowIds": [cluster_id], "VisibleToAllUsers": True})


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def test_add_job_flow_steps_answers_step_ids(endpoint):
    cluster_id = ensure_cluster(endpoint)
    step_id = add_step(endpoint, cluster_id)
    step = ok(endpoint, "DescribeStep", {"ClusterId": cluster_id, "StepId": step_id})["Step"]
    assert step["Status"]["State"] == "COMPLETED"


def test_describe_step_reads_the_step(endpoint):
    cluster_id = ensure_cluster(endpoint)
    step_id = add_step(endpoint, cluster_id)
    assert ok(endpoint, "DescribeStep", {"ClusterId": cluster_id, "StepId": step_id})["Step"]["Id"] == step_id


def test_list_steps_lists_the_step(endpoint):
    cluster_id = ensure_cluster(endpoint)
    step_id = add_step(endpoint, cluster_id)
    assert step_id in {item["Id"] for item in ok(endpoint, "ListSteps", {"ClusterId": cluster_id})["Steps"]}


def test_cancel_steps_reports_a_completed_step(endpoint):
    cluster_id = ensure_cluster(endpoint)
    step_id = add_step(endpoint, cluster_id)
    results = ok(endpoint, "CancelSteps", {"ClusterId": cluster_id, "StepIds": [step_id]})["CancelStepsInfoList"]
    assert results[0]["StepId"] == step_id


# ---------------------------------------------------------------------------
# Instance fleets and groups
# ---------------------------------------------------------------------------


def test_add_instance_fleet_answers_a_fleet(endpoint):
    cluster_id = ensure_cluster(endpoint)
    fleet_id = add_fleet(endpoint, cluster_id)
    assert fleet_id in {item["Id"] for item in ok(endpoint, "ListInstanceFleets", {"ClusterId": cluster_id})["InstanceFleets"]}


def test_list_instance_fleets_lists_the_fleet(endpoint):
    cluster_id = ensure_cluster(endpoint)
    fleet_id = add_fleet(endpoint, cluster_id)
    assert fleet_id in {item["Id"] for item in ok(endpoint, "ListInstanceFleets", {"ClusterId": cluster_id})["InstanceFleets"]}


def test_modify_instance_fleet_changes_the_capacity(endpoint):
    cluster_id = ensure_cluster(endpoint)
    fleet_id = add_fleet(endpoint, cluster_id)
    ok(endpoint, "ModifyInstanceFleet", {"ClusterId": cluster_id, "InstanceFleet": {"InstanceFleetId": fleet_id, "TargetOnDemandCapacity": 2}})
    fleets = {item["Id"]: item for item in ok(endpoint, "ListInstanceFleets", {"ClusterId": cluster_id})["InstanceFleets"]}
    assert fleets[fleet_id]["TargetOnDemandCapacity"] == 2


def test_add_instance_groups_answers_group_ids(endpoint):
    cluster_id = ensure_cluster(endpoint)
    body = {
        "JobFlowId": cluster_id,
        "InstanceGroups": [{"Name": "ops-group", "InstanceRole": "TASK", "InstanceType": "m5.xlarge", "InstanceCount": 1}],
    }
    group_id = ok(endpoint, "AddInstanceGroups", body)["InstanceGroupIds"][0]
    assert group_id in {item["Id"] for item in ok(endpoint, "ListInstanceGroups", {"ClusterId": cluster_id})["InstanceGroups"]}


def test_list_instance_groups_lists_the_groups(endpoint):
    cluster_id = ensure_cluster(endpoint)
    assert ok(endpoint, "ListInstanceGroups", {"ClusterId": cluster_id})["InstanceGroups"]


def test_modify_instance_groups_changes_the_count(endpoint):
    cluster_id = ensure_cluster(endpoint)
    group_id = ok(endpoint, "ListInstanceGroups", {"ClusterId": cluster_id})["InstanceGroups"][0]["Id"]
    body = {"ClusterId": cluster_id, "InstanceGroups": [{"InstanceGroupId": group_id, "InstanceCount": 3}]}
    ok(endpoint, "ModifyInstanceGroups", body)
    groups = {item["Id"]: item for item in ok(endpoint, "ListInstanceGroups", {"ClusterId": cluster_id})["InstanceGroups"]}
    assert groups[group_id]["RequestedInstanceCount"] == 3


# ---------------------------------------------------------------------------
# Bootstrap actions
# ---------------------------------------------------------------------------


def test_list_bootstrap_actions_lists_the_action(endpoint):
    name = f"ops-emr-bootstrap-{time.time_ns()}"
    cluster_id = run_cluster(
        endpoint,
        name,
        BootstrapActions=[{"Name": "ops-bootstrap", "ScriptBootstrapAction": {"Path": "s3://ops/bootstrap.sh"}}],
    )
    actions = ok(endpoint, "ListBootstrapActions", {"ClusterId": cluster_id})["BootstrapActions"]
    assert actions[0]["Name"] == "ops-bootstrap"


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_add_tags_is_read_back_by_describe(endpoint):
    cluster_id = ensure_cluster(endpoint)
    ok(endpoint, "AddTags", {"ResourceId": cluster_id, "Tags": [{"Key": "env", "Value": "ops"}]})
    tags = ok(endpoint, "DescribeCluster", {"ClusterId": cluster_id})["Cluster"]["Tags"]
    assert {"Key": "env", "Value": "ops"} in tags


def test_remove_tags_removes_the_key_it_names(endpoint):
    cluster_id = ensure_cluster(endpoint)
    ok(endpoint, "AddTags", {"ResourceId": cluster_id, "Tags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "RemoveTags", {"ResourceId": cluster_id, "TagKeys": ["doomed"]})
    tags = ok(endpoint, "DescribeCluster", {"ClusterId": cluster_id})["Cluster"]["Tags"]
    assert "doomed" not in {tag["Key"] for tag in tags}


# ---------------------------------------------------------------------------
# Block public access
# ---------------------------------------------------------------------------


def test_get_block_public_access_configuration_reads_it(endpoint):
    answer = ok(endpoint, "GetBlockPublicAccessConfiguration")
    assert "BlockPublicSecurityGroupRules" in answer["BlockPublicAccessConfiguration"]


def test_put_block_public_access_configuration_sets_it(endpoint):
    ok(
        endpoint,
        "PutBlockPublicAccessConfiguration",
        {"BlockPublicAccessConfiguration": {"BlockPublicSecurityGroupRules": True}},
    )
    answer = ok(endpoint, "GetBlockPublicAccessConfiguration")
    assert answer["BlockPublicAccessConfiguration"]["BlockPublicSecurityGroupRules"] is True
    # Restore the default for the next sweep.
    ok(
        endpoint,
        "PutBlockPublicAccessConfiguration",
        {"BlockPublicAccessConfiguration": {"BlockPublicSecurityGroupRules": False}},
    )
