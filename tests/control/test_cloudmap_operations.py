"""AWS Cloud Map on the wire: all 29 advertised operations, JSON 1.1.

The target prefix is `Route53AutoNaming_v20170314`. Namespaces are keyed by name
and services by name within a namespace, so a stable HTTP namespace and service
carry most tests; DNS types and delete tests make their own. Instances are keyed
by `ServiceId`/`InstanceId` and re-registering is idempotent.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "Route53AutoNaming_v20170314"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
NS = "ops-ns-http"
SVC = "ops-svc"
INST = "ops-inst"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "servicediscovery", ACCOUNT, REGION, "POST", "/", body, headers)


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


def ensure_namespace(endpoint, name: str = NS) -> dict:
    status, text = call(endpoint, "CreateHttpNamespace", {"Name": name})
    assert status == 200 or "NamespaceAlreadyExists" in text, text[:300]
    namespaces = ok(endpoint, "ListNamespaces")["Namespaces"]
    return {item["Name"]: item for item in namespaces}[name]


def ensure_service(endpoint, namespace_id: str, name: str = SVC) -> dict:
    summaries = ok(endpoint, "ListServices")["Services"]
    match = next((item for item in summaries if item["Name"] == name), None)
    if match:
        return ok(endpoint, "GetService", {"Id": match["Id"]})["Service"]
    return ok(endpoint, "CreateService", {"NamespaceId": namespace_id, "Name": name, "Type": "HTTP"})["Service"]


def ensure_instance(endpoint, service_id: str, instance_id: str = INST) -> str:
    ok(
        endpoint,
        "RegisterInstance",
        {"ServiceId": service_id, "InstanceId": instance_id, "Attributes": {"AWS_INSTANCE_IPV4": "10.0.0.1"}},
    )
    return instance_id


def context(endpoint):
    namespace = ensure_namespace(endpoint)
    service = ensure_service(endpoint, namespace["Id"])
    return namespace, service


# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------


def test_create_http_namespace_is_read_back(endpoint):
    name = f"ops-http-{time.time_ns()}"
    ok(endpoint, "CreateHttpNamespace", {"Name": name})
    assert name in {item["Name"] for item in ok(endpoint, "ListNamespaces")["Namespaces"]}


def test_create_private_dns_namespace_answers_an_operation(endpoint):
    name = f"ops-priv-{time.time_ns()}"
    assert ok(endpoint, "CreatePrivateDnsNamespace", {"Name": name, "Vpc": "vpc-ops"})["OperationId"]


def test_create_public_dns_namespace_answers_an_operation(endpoint):
    name = f"ops-pub-{time.time_ns()}"
    assert ok(endpoint, "CreatePublicDnsNamespace", {"Name": name})["OperationId"]


def test_get_namespace_reads_the_namespace(endpoint):
    namespace = ensure_namespace(endpoint)
    assert ok(endpoint, "GetNamespace", {"Id": namespace["Id"]})["Namespace"]["Name"] == NS


def test_list_namespaces_lists_the_namespace(endpoint):
    ensure_namespace(endpoint)
    assert NS in {item["Name"] for item in ok(endpoint, "ListNamespaces")["Namespaces"]}


def test_delete_namespace_removes_the_namespace_it_created(endpoint):
    name = f"ops-del-{time.time_ns()}"
    ok(endpoint, "CreateHttpNamespace", {"Name": name})
    namespace = {item["Name"]: item for item in ok(endpoint, "ListNamespaces")["Namespaces"]}[name]
    ok(endpoint, "DeleteNamespace", {"Id": namespace["Id"]})
    refused(endpoint, "GetNamespace", {"Id": namespace["Id"]}, "NamespaceNotFound")


def test_update_http_namespace_changes_the_description(endpoint):
    namespace = ensure_namespace(endpoint)
    ok(endpoint, "UpdateHttpNamespace", {"Id": namespace["Id"], "Namespace": {"Description": "updated"}})
    assert ok(endpoint, "GetNamespace", {"Id": namespace["Id"]})["Namespace"]["Description"] == "updated"


def test_update_private_dns_namespace_answers_an_operation(endpoint):
    name = f"ops-priv-u-{time.time_ns()}"
    ok(endpoint, "CreatePrivateDnsNamespace", {"Name": name, "Vpc": "vpc-ops"})
    namespace = {item["Name"]: item for item in ok(endpoint, "ListNamespaces")["Namespaces"]}[name]
    assert ok(
        endpoint,
        "UpdatePrivateDnsNamespace",
        {"Id": namespace["Id"], "Namespace": {"Description": "updated"}},
    )["OperationId"]


def test_update_public_dns_namespace_answers_an_operation(endpoint):
    name = f"ops-pub-u-{time.time_ns()}"
    ok(endpoint, "CreatePublicDnsNamespace", {"Name": name})
    namespace = {item["Name"]: item for item in ok(endpoint, "ListNamespaces")["Namespaces"]}[name]
    assert ok(
        endpoint,
        "UpdatePublicDnsNamespace",
        {"Id": namespace["Id"], "Namespace": {"Description": "updated"}},
    )["OperationId"]


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def test_create_service_is_read_back(endpoint):
    namespace = ensure_namespace(endpoint)
    name = f"ops-svc-{time.time_ns()}"
    created = ok(endpoint, "CreateService", {"NamespaceId": namespace["Id"], "Name": name, "Type": "HTTP"})["Service"]
    assert created["Name"] == name
    assert ok(endpoint, "GetService", {"Id": created["Id"]})["Service"]["Name"] == name


def test_get_service_reads_the_service(endpoint):
    _namespace, service = context(endpoint)
    assert ok(endpoint, "GetService", {"Id": service["Id"]})["Service"]["Name"] == SVC


def test_list_services_lists_the_service(endpoint):
    _namespace, service = context(endpoint)
    assert service["Id"] in {item["Id"] for item in ok(endpoint, "ListServices")["Services"]}


def test_delete_service_removes_the_service_it_created(endpoint):
    namespace = ensure_namespace(endpoint)
    name = f"ops-svc-del-{time.time_ns()}"
    created = ok(endpoint, "CreateService", {"NamespaceId": namespace["Id"], "Name": name, "Type": "HTTP"})["Service"]
    ok(endpoint, "DeleteService", {"Id": created["Id"]})
    refused(endpoint, "GetService", {"Id": created["Id"]}, "ServiceNotFound")


def test_update_service_changes_the_description(endpoint):
    _namespace, service = context(endpoint)
    ok(endpoint, "UpdateService", {"Id": service["Id"], "Service": {"Description": "updated"}})
    assert ok(endpoint, "GetService", {"Id": service["Id"]})["Service"]["Description"] == "updated"


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------


def test_register_instance_is_read_back(endpoint):
    _namespace, service = context(endpoint)
    instance = f"ops-reg-{time.time_ns()}"
    ensure_instance(endpoint, service["Id"], instance)
    assert ok(endpoint, "GetInstance", {"ServiceId": service["Id"], "InstanceId": instance})["Instance"]["Id"] == instance


def test_deregister_instance_removes_the_instance_it_created(endpoint):
    _namespace, service = context(endpoint)
    instance = f"ops-dereg-{time.time_ns()}"
    ensure_instance(endpoint, service["Id"], instance)
    ok(endpoint, "DeregisterInstance", {"ServiceId": service["Id"], "InstanceId": instance})
    refused(endpoint, "GetInstance", {"ServiceId": service["Id"], "InstanceId": instance}, "InstanceNotFound")


def test_discover_instances_answers_the_instance(endpoint):
    namespace, service = context(endpoint)
    ensure_instance(endpoint, service["Id"])
    answer = ok(
        endpoint,
        "DiscoverInstances",
        {"NamespaceName": namespace["Name"], "ServiceName": service["Name"]},
    )
    assert INST in {item["InstanceId"] for item in answer["Instances"]}


def test_discover_instances_revision_answers_a_number(endpoint):
    namespace, service = context(endpoint)
    ensure_instance(endpoint, service["Id"])
    answer = ok(
        endpoint,
        "DiscoverInstancesRevision",
        {"NamespaceName": namespace["Name"], "ServiceName": service["Name"]},
    )
    assert isinstance(answer["InstancesRevision"], int)


def test_list_instances_lists_the_instance(endpoint):
    _namespace, service = context(endpoint)
    ensure_instance(endpoint, service["Id"])
    assert INST in {item["Id"] for item in ok(endpoint, "ListInstances", {"ServiceId": service["Id"]})["Instances"]}


def test_get_instances_health_status_reports_healthy(endpoint):
    _namespace, service = context(endpoint)
    ensure_instance(endpoint, service["Id"])
    assert ok(endpoint, "GetInstancesHealthStatus", {"ServiceId": service["Id"]})["Status"][INST] == "HEALTHY"


def test_update_instance_custom_health_status_sets_it(endpoint):
    _namespace, service = context(endpoint)
    ensure_instance(endpoint, service["Id"])
    ok(
        endpoint,
        "UpdateInstanceCustomHealthStatus",
        {"ServiceId": service["Id"], "InstanceId": INST, "Status": "UNHEALTHY"},
    )
    assert ok(endpoint, "GetInstancesHealthStatus", {"ServiceId": service["Id"]})["Status"][INST] == "UNHEALTHY"
    ok(
        endpoint,
        "UpdateInstanceCustomHealthStatus",
        {"ServiceId": service["Id"], "InstanceId": INST, "Status": "HEALTHY"},
    )


# ---------------------------------------------------------------------------
# Service attributes
# ---------------------------------------------------------------------------


def test_get_service_attributes_reads_them(endpoint):
    _namespace, service = context(endpoint)
    assert "ServiceAttributes" in ok(endpoint, "GetServiceAttributes", {"ServiceId": service["Id"]})


def test_update_service_attributes_is_read_back(endpoint):
    _namespace, service = context(endpoint)
    ok(endpoint, "UpdateServiceAttributes", {"ServiceId": service["Id"], "Attributes": {"env": "ops"}})
    attributes = ok(endpoint, "GetServiceAttributes", {"ServiceId": service["Id"]})["ServiceAttributes"]["Attributes"]
    assert attributes.get("env") == "ops"


def test_delete_service_attributes_removes_the_key(endpoint):
    _namespace, service = context(endpoint)
    ok(endpoint, "UpdateServiceAttributes", {"ServiceId": service["Id"], "Attributes": {"doomed": "yes"}})
    ok(endpoint, "DeleteServiceAttributes", {"ServiceId": service["Id"], "Attributes": ["doomed"]})
    attributes = ok(endpoint, "GetServiceAttributes", {"ServiceId": service["Id"]})["ServiceAttributes"]["Attributes"]
    assert "doomed" not in attributes


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def test_get_operation_reads_the_operation(endpoint):
    name = f"ops-op-{time.time_ns()}"
    operation_id = ok(endpoint, "CreateHttpNamespace", {"Name": name})["OperationId"]
    assert ok(endpoint, "GetOperation", {"OperationId": operation_id})["Operation"]["Id"] == operation_id


def test_list_operations_lists_the_operations(endpoint):
    ok(endpoint, "CreateHttpNamespace", {"Name": f"ops-op-list-{time.time_ns()}"})
    assert ok(endpoint, "ListOperations")["Operations"]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    arn = ensure_namespace(endpoint)["Arn"]
    ok(endpoint, "TagResource", {"ResourceARN": arn, "Tags": [{"Key": "env", "Value": "ops"}]})
    assert {"Key": "env", "Value": "ops"} in ok(endpoint, "ListTagsForResource", {"ResourceARN": arn})["Tags"]


def test_untag_resource_removes_the_key_it_names(endpoint):
    arn = ensure_namespace(endpoint)["Arn"]
    ok(endpoint, "TagResource", {"ResourceARN": arn, "Tags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "UntagResource", {"ResourceARN": arn, "TagKeys": ["doomed"]})
    assert "doomed" not in {tag["Key"] for tag in ok(endpoint, "ListTagsForResource", {"ResourceARN": arn})["Tags"]}


def test_list_tags_for_resource_lists_the_tags(endpoint):
    arn = ensure_namespace(endpoint)["Arn"]
    ok(endpoint, "TagResource", {"ResourceARN": arn, "Tags": [{"Key": "team", "Value": "platform"}]})
    assert {"Key": "team", "Value": "platform"} in ok(endpoint, "ListTagsForResource", {"ResourceARN": arn})["Tags"]
