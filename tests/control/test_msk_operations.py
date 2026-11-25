"""Amazon MSK on the wire: all 17 advertised operations, REST/JSON.

Signing name `kafka`; clusters at `/v1/clusters`, configurations at
`/v1/configurations`, SCRAM secrets under a cluster, and tags under
`/v1/tags/{arn}`. A cluster is keyed by name, a configuration by name, so a
stable pair carries the read/tag tests while a delete test makes its own.
"""

from __future__ import annotations

import base64
import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
CLUSTER = "ops-msk"
CONFIG = "ops-msk-config"


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "kafka", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status in (200, 204), f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, method: str, path: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, method, path, payload)
    assert status >= 400, f"{method} {path} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def ensure_cluster(endpoint, name: str = CLUSTER) -> str:
    listed = ok(endpoint, "GET", "/v1/clusters")["clusterInfoList"]
    match = next((item for item in listed if item["clusterName"] == name), None)
    if match:
        return match["clusterArn"]
    return ok(
        endpoint,
        "POST",
        "/v1/clusters",
        {"clusterName": name, "brokerNodeGroupInfo": {"instanceType": "kafka.m5.large"}, "numberOfBrokerNodes": 3},
    )["clusterArn"]


def ensure_configuration(endpoint, name: str = CONFIG) -> str:
    listed = ok(endpoint, "GET", "/v1/configurations")["configurations"]
    match = next((item for item in listed if item["name"] == name), None)
    if match:
        return match["arn"]
    body = {
        "name": name,
        "serverProperties": base64.b64encode(b"auto.create.topics.enable=true").decode(),
    }
    return ok(endpoint, "POST", "/v1/configurations", body)["arn"]


def tags(endpoint, arn: str) -> dict:
    return ok(endpoint, "GET", f"/v1/tags/{arn}")["tags"]


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------


def test_create_cluster_is_read_back(endpoint):
    name = f"ops-msk-created-{time.time_ns()}"
    created = ok(endpoint, "POST", "/v1/clusters", {"clusterName": name, "numberOfBrokerNodes": 3})
    assert created["clusterName"] == name
    assert ok(endpoint, "GET", f"/v1/clusters/{created['clusterArn']}")["clusterInfo"]["clusterName"] == name


def test_list_clusters_lists_the_cluster(endpoint):
    ensure_cluster(endpoint)
    assert CLUSTER in {item["clusterName"] for item in ok(endpoint, "GET", "/v1/clusters")["clusterInfoList"]}


def test_describe_cluster_reads_the_cluster(endpoint):
    arn = ensure_cluster(endpoint)
    assert ok(endpoint, "GET", f"/v1/clusters/{arn}")["clusterInfo"]["state"] == "ACTIVE"


def test_delete_cluster_removes_the_cluster_it_created(endpoint):
    name = f"ops-msk-deleted-{time.time_ns()}"
    arn = ok(endpoint, "POST", "/v1/clusters", {"clusterName": name})["clusterArn"]
    ok(endpoint, "DELETE", f"/v1/clusters/{arn}")
    refused(endpoint, "GET", f"/v1/clusters/{arn}", code="NotFound")


def test_get_bootstrap_brokers_answers_brokers(endpoint):
    arn = ensure_cluster(endpoint)
    answer = ok(endpoint, "GET", f"/v1/clusters/{arn}/bootstrap-brokers")
    assert answer["bootstrapBrokerString"]


def test_list_nodes_lists_the_brokers(endpoint):
    arn = ensure_cluster(endpoint)
    nodes = ok(endpoint, "GET", f"/v1/clusters/{arn}/nodes")["nodeInfoList"]
    assert nodes


# ---------------------------------------------------------------------------
# Configurations
# ---------------------------------------------------------------------------


def test_create_configuration_is_read_back(endpoint):
    name = f"ops-config-{time.time_ns()}"
    body = {"name": name, "serverProperties": base64.b64encode(b"log.retention.hours=1").decode()}
    created = ok(endpoint, "POST", "/v1/configurations", body)
    assert ok(endpoint, "GET", f"/v1/configurations/{created['arn']}" )["name"] == name


def test_list_configurations_lists_the_configuration(endpoint):
    ensure_configuration(endpoint)
    assert CONFIG in {item["name"] for item in ok(endpoint, "GET", "/v1/configurations")["configurations"]}


def test_describe_configuration_reads_the_configuration(endpoint):
    arn = ensure_configuration(endpoint)
    assert ok(endpoint, "GET", f"/v1/configurations/{arn}" )["name"] == CONFIG


def test_list_configuration_revisions_lists_the_revision(endpoint):
    arn = ensure_configuration(endpoint)
    assert ok(endpoint, "GET", f"/v1/configurations/{arn}/revisions")["revisions"]


def test_describe_configuration_revision_reads_the_revision(endpoint):
    arn = ensure_configuration(endpoint)
    answer = ok(endpoint, "GET", f"/v1/configurations/{arn}/revisions/1")
    assert answer["revision"] == 1


# ---------------------------------------------------------------------------
# SCRAM secrets
# ---------------------------------------------------------------------------


def test_batch_associate_scram_secret_is_read_back(endpoint):
    arn = ensure_cluster(endpoint)
    secret = f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:ops-scram-{time.time_ns()}"
    ok(endpoint, "POST", f"/v1/clusters/{arn}/scram-secrets", {"secretArnList": [secret]})
    assert secret in ok(endpoint, "GET", f"/v1/clusters/{arn}/scram-secrets")["secretArnList"]


def test_batch_disassociate_scram_secret_removes_it(endpoint):
    arn = ensure_cluster(endpoint)
    secret = f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:ops-scram-del-{time.time_ns()}"
    ok(endpoint, "POST", f"/v1/clusters/{arn}/scram-secrets", {"secretArnList": [secret]})
    ok(endpoint, "PATCH", f"/v1/clusters/{arn}/scram-secrets", {"secretArnList": [secret]})
    assert secret not in ok(endpoint, "GET", f"/v1/clusters/{arn}/scram-secrets")["secretArnList"]


def test_list_scram_secrets_lists_the_secret(endpoint):
    arn = ensure_cluster(endpoint)
    secret = f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:ops-scram-list-{time.time_ns()}"
    ok(endpoint, "POST", f"/v1/clusters/{arn}/scram-secrets", {"secretArnList": [secret]})
    assert secret in ok(endpoint, "GET", f"/v1/clusters/{arn}/scram-secrets")["secretArnList"]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    arn = ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/v1/tags/{arn}", {"tags": {"env": "ops"}})
    assert tags(endpoint, arn)["env"] == "ops"


def test_untag_resource_removes_the_key_it_names(endpoint):
    arn = ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/v1/tags/{arn}", {"tags": {"doomed": "yes"}})
    ok(endpoint, "DELETE", f"/v1/tags/{arn}?tagKeys=doomed")
    assert "doomed" not in tags(endpoint, arn)


def test_list_tags_for_resource_lists_the_tags(endpoint):
    arn = ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/v1/tags/{arn}", {"tags": {"team": "platform"}})
    assert tags(endpoint, arn)["team"] == "platform"
