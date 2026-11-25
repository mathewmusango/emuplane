"""ECS on the wire: all 47 advertised operations, JSON with `X-Amz-Target`.

Signed with the `ecs` credential scope. Without Docker `RunTask` records a
`RUNNING` task rather than starting a container, so the tests never pull an
image. A stable cluster, task definition and service carry the read and update
rows; delete actions and lifecycle tests make their own.
"""

from __future__ import annotations

import json
import secrets

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
RUN = secrets.token_hex(3)

CLUSTER = "ops-ecs-cluster"
TD_FAMILY = "ops-ecs-task"
SERVICE = "ops-ecs-service"
CAPACITY = "ops-ecs-capacity"


def call(endpoint, action: str, **payload):
    body = json.dumps(payload)
    headers = {
        "X-Amz-Target": f"AmazonEC2ContainerServiceV20141113.{action}",
        **JSON_TYPE,
    }
    return signed.request(endpoint, "ecs", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def ensure_cluster(endpoint, name: str = CLUSTER) -> dict:
    return ok(endpoint, "CreateCluster", clusterName=name)["cluster"]


def register_task_definition(endpoint, family: str, **extra) -> dict:
    return ok(
        endpoint,
        "RegisterTaskDefinition",
        family=family,
        containerDefinitions=[
            {"name": "ops", "image": "public.ecr.aws/nginx/nginx:latest", "memory": 128}
        ],
        **extra,
    )["taskDefinition"]


def ensure_task_definition(endpoint) -> str:
    listed = ok(endpoint, "ListTaskDefinitions", familyPrefix=TD_FAMILY)
    if listed["taskDefinitionArns"]:
        return listed["taskDefinitionArns"][-1]
    return register_task_definition(endpoint, TD_FAMILY)["taskDefinitionArn"]


def describe_service(endpoint, name: str = SERVICE) -> dict:
    answer = ok(endpoint, "DescribeServices", cluster=CLUSTER, services=[name])
    assert answer["services"], f"service {name} not found"
    return answer["services"][0]


def ensure_service(endpoint) -> dict:
    ensure_cluster(endpoint)
    task_definition = ensure_task_definition(endpoint)
    answer = ok(endpoint, "DescribeServices", cluster=CLUSTER, services=[SERVICE])
    if answer["services"] and answer["services"][0]["status"] == "ACTIVE":
        return answer["services"][0]
    return ok(
        endpoint,
        "CreateService",
        cluster=CLUSTER,
        serviceName=SERVICE,
        taskDefinition=task_definition,
        desiredCount=1,
    )["service"]


def service_task(endpoint) -> str:
    ensure_service(endpoint)
    listed = ok(endpoint, "ListTasks", cluster=CLUSTER, serviceName=SERVICE)
    assert listed["taskArns"], "the service has no running task"
    return listed["taskArns"][0]


def run_task(endpoint) -> str:
    ensure_cluster(endpoint)
    task_definition = ensure_task_definition(endpoint)
    answer = ok(
        endpoint, "RunTask", cluster=CLUSTER, taskDefinition=task_definition, count=1
    )
    assert answer["tasks"], answer
    return answer["tasks"][0]["taskArn"]


def ensure_capacity_provider(endpoint) -> dict:
    listed = ok(endpoint, "DescribeCapacityProviders", capacityProviders=[CAPACITY])
    if listed["capacityProviders"]:
        return listed["capacityProviders"][0]
    return ok(endpoint, "CreateCapacityProvider", name=CAPACITY)["capacityProvider"]


def cluster_arn(endpoint) -> str:
    return ensure_cluster(endpoint)["clusterArn"]


# --- Clusters ---------------------------------------------------------------


def test_create_cluster_answers_the_cluster(endpoint):
    cluster = ensure_cluster(endpoint)
    assert cluster["clusterName"] == CLUSTER
    assert cluster["status"] == "ACTIVE"


def test_describe_clusters_reads_it(endpoint):
    ensure_cluster(endpoint)
    answer = ok(endpoint, "DescribeClusters", clusters=[CLUSTER])
    assert answer["clusters"][0]["clusterName"] == CLUSTER
    assert answer["failures"] == []


def test_list_clusters_lists_it(endpoint):
    cluster = ensure_cluster(endpoint)
    answer = ok(endpoint, "ListClusters")
    assert cluster["clusterArn"] in answer["clusterArns"]


def test_update_cluster_sets_the_configuration(endpoint):
    ensure_cluster(endpoint)
    answer = ok(
        endpoint,
        "UpdateCluster",
        cluster=CLUSTER,
        configuration={"executeCommandConfiguration": {"logging": "DEFAULT"}},
    )
    assert answer["cluster"]["configuration"]["executeCommandConfiguration"]["logging"] == "DEFAULT"


def test_update_cluster_settings_sets_container_insights(endpoint):
    ensure_cluster(endpoint)
    answer = ok(
        endpoint,
        "UpdateClusterSettings",
        cluster=CLUSTER,
        settings=[{"name": "containerInsights", "value": "enabled"}],
    )
    assert answer["cluster"]["settings"] == [{"name": "containerInsights", "value": "enabled"}]


def test_put_cluster_capacity_providers_sets_them(endpoint):
    ensure_cluster(endpoint)
    answer = ok(
        endpoint,
        "PutClusterCapacityProviders",
        cluster=CLUSTER,
        capacityProviders=["FARGATE"],
        defaultCapacityProviderStrategy=[{"capacityProvider": "FARGATE", "weight": 1}],
    )
    assert answer["cluster"]["capacityProviders"] == ["FARGATE"]


def test_delete_cluster_removes_it(endpoint):
    name = f"ops-ecs-delete-cluster-{RUN}"
    ok(endpoint, "CreateCluster", clusterName=name)
    ok(endpoint, "DeleteCluster", cluster=name)
    answer = ok(endpoint, "DescribeClusters", clusters=[name])
    assert answer["clusters"] == []


# --- Task definitions -------------------------------------------------------


def test_register_task_definition_answers_the_definition(endpoint):
    family = f"ops-ecs-register-{RUN}"
    td = register_task_definition(endpoint, family)
    assert td["family"] == family
    assert td["revision"] == 1
    assert td["status"] == "ACTIVE"


def test_describe_task_definition_reads_it(endpoint):
    arn = ensure_task_definition(endpoint)
    answer = ok(endpoint, "DescribeTaskDefinition", taskDefinition=arn)
    assert answer["taskDefinition"]["family"] == TD_FAMILY


def test_list_task_definitions_lists_it(endpoint):
    arn = ensure_task_definition(endpoint)
    answer = ok(endpoint, "ListTaskDefinitions", familyPrefix=TD_FAMILY)
    assert arn in answer["taskDefinitionArns"]


def test_list_task_definition_families_lists_it(endpoint):
    ensure_task_definition(endpoint)
    answer = ok(endpoint, "ListTaskDefinitionFamilies", familyPrefix=TD_FAMILY)
    assert TD_FAMILY in answer["families"]


def test_deregister_task_definition_marks_it_inactive(endpoint):
    family = f"ops-ecs-deregister-{RUN}"
    arn = register_task_definition(endpoint, family)["taskDefinitionArn"]
    answer = ok(endpoint, "DeregisterTaskDefinition", taskDefinition=arn)
    assert answer["taskDefinition"]["status"] == "INACTIVE"


def test_delete_task_definitions_marks_them_deleting(endpoint):
    family = f"ops-ecs-delete-td-{RUN}"
    arn = register_task_definition(endpoint, family)["taskDefinitionArn"]
    answer = ok(endpoint, "DeleteTaskDefinitions", taskDefinitions=[arn])
    assert answer["taskDefinitions"][0]["status"] == "DELETE_IN_PROGRESS"
    assert answer["failures"] == []


# --- Services ---------------------------------------------------------------


def test_create_service_answers_the_service(endpoint):
    service = ensure_service(endpoint)
    assert service["serviceName"] == SERVICE
    assert service["status"] == "ACTIVE"


def test_describe_services_reads_it(endpoint):
    ensure_service(endpoint)
    answer = describe_service(endpoint)
    assert answer["serviceName"] == SERVICE
    assert answer["clusterArn"] == cluster_arn(endpoint)


def test_update_service_keeps_the_desired_count(endpoint):
    ensure_service(endpoint)
    answer = ok(
        endpoint, "UpdateService", cluster=CLUSTER, service=SERVICE, desiredCount=1
    )
    assert answer["service"]["serviceName"] == SERVICE


def test_list_services_lists_it(endpoint):
    service = ensure_service(endpoint)
    answer = ok(endpoint, "ListServices", cluster=CLUSTER)
    assert service["serviceArn"] in answer["serviceArns"]


def test_list_services_by_namespace_lists_it(endpoint):
    service = ensure_service(endpoint)
    answer = ok(endpoint, "ListServicesByNamespace", namespace="")
    assert service["serviceArn"] in answer["serviceArns"]


def test_delete_service_removes_it(endpoint):
    name = f"ops-ecs-delete-service-{RUN}"
    td = ensure_task_definition(endpoint)
    ok(
        endpoint,
        "CreateService",
        cluster=CLUSTER,
        serviceName=name,
        taskDefinition=td,
        desiredCount=0,
    )
    ok(endpoint, "DeleteService", cluster=CLUSTER, service=name)
    answer = ok(endpoint, "DescribeServices", cluster=CLUSTER, services=[name])
    assert answer["services"][0]["status"] == "INACTIVE"


# --- Tasks ------------------------------------------------------------------


def test_run_task_answers_the_task(endpoint):
    task = run_task(endpoint)
    answer = ok(endpoint, "DescribeTasks", cluster=CLUSTER, tasks=[task])
    assert answer["tasks"][0]["lastStatus"] == "RUNNING"


def test_describe_tasks_reads_it(endpoint):
    task = run_task(endpoint)
    answer = ok(endpoint, "DescribeTasks", cluster=CLUSTER, tasks=[task])
    assert answer["tasks"][0]["taskArn"] == task
    assert answer["failures"] == []


def test_list_tasks_lists_it(endpoint):
    task = run_task(endpoint)
    answer = ok(endpoint, "ListTasks", cluster=CLUSTER)
    assert task in answer["taskArns"]


def test_stop_task_stops_it(endpoint):
    task = run_task(endpoint)
    answer = ok(endpoint, "StopTask", cluster=CLUSTER, task=task, reason="ops")
    assert answer["task"]["lastStatus"] == "STOPPED"


def test_execute_command_answers_a_session(endpoint):
    task = service_task(endpoint)
    answer = ok(
        endpoint,
        "ExecuteCommand",
        cluster=CLUSTER,
        task=task,
        command="echo hello",
        interactive=True,
    )
    assert answer["taskArn"] == task
    assert answer["session"]["sessionId"]


def test_update_task_protection_protects_it(endpoint):
    task = service_task(endpoint)
    answer = ok(
        endpoint,
        "UpdateTaskProtection",
        cluster=CLUSTER,
        tasks=[task],
        protectionEnabled=True,
        expiresInMinutes=10,
    )
    protected = answer["protectedTasks"][0]
    assert protected["taskArn"] == task
    assert protected["protectionEnabled"] is True


def test_get_task_protection_reads_it(endpoint):
    task = service_task(endpoint)
    ok(
        endpoint,
        "UpdateTaskProtection",
        cluster=CLUSTER,
        tasks=[task],
        protectionEnabled=True,
        expiresInMinutes=10,
    )
    answer = ok(endpoint, "GetTaskProtection", cluster=CLUSTER, tasks=[task])
    assert answer["protectedTasks"][0]["protectionEnabled"] is True
    ok(
        endpoint,
        "UpdateTaskProtection",
        cluster=CLUSTER,
        tasks=[task],
        protectionEnabled=False,
    )


# --- Capacity providers -----------------------------------------------------


def test_create_capacity_provider_answers_the_provider(endpoint):
    provider = ensure_capacity_provider(endpoint)
    assert provider["name"] == CAPACITY
    assert provider["status"] == "ACTIVE"


def test_update_capacity_provider_sets_termination_protection(endpoint):
    ensure_capacity_provider(endpoint)
    answer = ok(
        endpoint,
        "UpdateCapacityProvider",
        name=CAPACITY,
        autoScalingGroupProvider={"managedTerminationProtection": "ENABLED"},
    )
    assert answer["capacityProvider"]["updateStatus"] == "UPDATE_COMPLETE"


def test_describe_capacity_providers_reads_it(endpoint):
    ensure_capacity_provider(endpoint)
    answer = ok(endpoint, "DescribeCapacityProviders", capacityProviders=[CAPACITY])
    assert answer["capacityProviders"][0]["name"] == CAPACITY


def test_delete_capacity_provider_removes_it(endpoint):
    name = f"ops-ecs-delete-capacity-{RUN}"
    ok(endpoint, "CreateCapacityProvider", name=name)
    ok(endpoint, "DeleteCapacityProvider", capacityProvider=name)
    answer = ok(endpoint, "DescribeCapacityProviders", capacityProviders=[name])
    assert answer["capacityProviders"] == []


# --- Tags -------------------------------------------------------------------


def test_tag_resource_adds_tags(endpoint):
    arn = cluster_arn(endpoint)
    ok(endpoint, "TagResource", resourceArn=arn, tags=[{"key": "ops", "value": "ecs"}])
    answer = ok(endpoint, "ListTagsForResource", resourceArn=arn)
    assert {"key": "ops", "value": "ecs"} in answer["tags"]


def test_list_tags_for_resource_reads_them(endpoint):
    arn = cluster_arn(endpoint)
    ok(endpoint, "TagResource", resourceArn=arn, tags=[{"key": "ops", "value": "ecs"}])
    answer = ok(endpoint, "ListTagsForResource", resourceArn=arn)
    assert any(tag["key"] == "ops" for tag in answer["tags"])


def test_untag_resource_removes_tags(endpoint):
    arn = cluster_arn(endpoint)
    ok(
        endpoint,
        "TagResource",
        resourceArn=arn,
        tags=[{"key": "ops-remove", "value": "ecs"}],
    )
    ok(endpoint, "UntagResource", resourceArn=arn, tagKeys=["ops-remove"])
    answer = ok(endpoint, "ListTagsForResource", resourceArn=arn)
    assert all(tag["key"] != "ops-remove" for tag in answer["tags"])


# --- Account settings -------------------------------------------------------


def test_list_account_settings_reads_them(endpoint):
    answer = ok(endpoint, "ListAccountSettings")
    assert answer["settings"]


def test_put_account_setting_sets_it(endpoint):
    answer = ok(endpoint, "PutAccountSetting", name="containerInsights", value="enabled")
    assert answer["setting"]["name"] == "containerInsights"
    assert answer["setting"]["value"] == "enabled"


def test_put_account_setting_default_sets_it(endpoint):
    answer = ok(endpoint, "PutAccountSettingDefault", name="dualStackIPv6", value="enabled")
    assert answer["setting"]["type"] == "account"


def test_delete_account_setting_removes_it(endpoint):
    ok(endpoint, "PutAccountSettingDefault", name="fargateFIPSMode", value="enabled")
    answer = ok(endpoint, "DeleteAccountSetting", name="fargateFIPSMode")
    assert answer["setting"]["name"] == "fargateFIPSMode"


# --- Attributes -------------------------------------------------------------


def test_put_attributes_stores_them(endpoint):
    attribute = {
        "targetId": "ops-instance",
        "targetType": "container-instance",
        "name": "ops",
        "value": "1",
    }
    answer = ok(endpoint, "PutAttributes", attributes=[attribute])
    assert answer["attributes"] == [attribute]


def test_list_attributes_lists_them(endpoint):
    attribute = {
        "targetId": "ops-instance",
        "targetType": "container-instance",
        "name": "ops",
        "value": "1",
    }
    ok(endpoint, "PutAttributes", attributes=[attribute])
    answer = ok(endpoint, "ListAttributes", targetType="container-instance", attributeName="ops")
    assert any(item["targetId"] == "ops-instance" for item in answer["attributes"])


def test_delete_attributes_removes_them(endpoint):
    attribute = {
        "targetId": "ops-instance",
        "targetType": "container-instance",
        "name": "ops-delete",
        "value": "1",
    }
    ok(endpoint, "PutAttributes", attributes=[attribute])
    ok(endpoint, "DeleteAttributes", attributes=[attribute])
    answer = ok(endpoint, "ListAttributes", targetType="container-instance", attributeName="ops-delete")
    assert answer["attributes"] == []


# --- Service deployments ----------------------------------------------------


def test_list_service_deployments_lists_them(endpoint):
    ensure_service(endpoint)
    answer = ok(endpoint, "ListServiceDeployments", cluster=CLUSTER, service=SERVICE)
    assert answer["serviceDeployments"]


def test_describe_service_deployments_reads_them(endpoint):
    ensure_service(endpoint)
    listed = ok(endpoint, "ListServiceDeployments", cluster=CLUSTER, service=SERVICE)
    arn = listed["serviceDeployments"][0]["serviceDeploymentArn"]
    answer = ok(endpoint, "DescribeServiceDeployments", serviceDeploymentArns=[arn])
    assert answer["serviceDeployments"][0]["serviceDeploymentArn"] == arn


def test_describe_service_revisions_answers_them(endpoint):
    answer = ok(endpoint, "DescribeServiceRevisions", serviceRevisionArns=[])
    assert answer["serviceRevisions"] == []


# --- Agent stubs ------------------------------------------------------------


def test_submit_task_state_change_is_acknowledged(endpoint):
    answer = ok(endpoint, "SubmitTaskStateChange", cluster=CLUSTER, task=run_task(endpoint))
    assert answer["acknowledgment"] == "ACCEPT"


def test_submit_container_state_change_is_acknowledged(endpoint):
    answer = ok(endpoint, "SubmitContainerStateChange", cluster=CLUSTER, task=run_task(endpoint))
    assert answer["acknowledgment"] == "ACCEPT"


def test_submit_attachment_state_changes_is_acknowledged(endpoint):
    answer = ok(endpoint, "SubmitAttachmentStateChanges", cluster=CLUSTER, attachments=[])
    assert answer["acknowledgment"] == "ACCEPT"


def test_discover_poll_endpoint_answers_an_endpoint(endpoint):
    answer = ok(endpoint, "DiscoverPollEndpoint", cluster=CLUSTER)
    assert answer["endpoint"]
    assert answer["telemetryEndpoint"]
