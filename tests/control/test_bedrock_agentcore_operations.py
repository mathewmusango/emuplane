"""Bedrock AgentCore on the wire: all 35 advertised operations across both planes.

The control plane (`bedrock-agentcore-control`) manages runtimes, endpoints,
resource policies and memories; the data plane (`bedrock-agentcore`) invokes a
runtime and drives the memory events, actors, sessions and records. Both sign
with the `bedrock-agentcore` credential scope and one module answers them.

Runtimes and memories are named, so a re-sweep reuses the record instead of
colliding; delete tests make their own resource. `StartMemoryExtractionJob`
never runs an extraction, so its only reachable answer is `ResourceNotFound`.
"""

from __future__ import annotations

import json
from urllib.parse import quote

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
RUNTIME = "opsAgentcoreRuntime"
ENDPOINT = "opsEndpoint"
MEMORY = "opsAgentcoreMemory"
ACTOR = "ops-actor"
SESSION = "ops-session"
NAMESPACE = "ops/ns"

INVOKE_BODY = {"prompt": "hello"}


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(
        endpoint, "bedrock-agentcore", ACCOUNT, REGION, method, path, body, JSON_TYPE
    )


def ok(endpoint, method: str, path: str, payload: dict | None = None, status: int = 200) -> dict:
    code, text = call(endpoint, method, path, payload)
    assert code == status, f"{method} {path} answered {code}: {text[:400]}"
    return json.loads(text or "{}")


RUNTIME_BODY = {
    "agentRuntimeArtifact": {
        "codeConfiguration": {
            "code": {"s3": {"bucket": "ops-bucket", "prefix": "agent.zip"}},
            "runtime": "PYTHON_3_11",
            "entryPoint": ["main.py"],
        }
    },
    "roleArn": f"arn:aws:iam::{ACCOUNT}:role/ops-agentcore-role",
    "networkConfiguration": {"networkMode": "PUBLIC"},
}


def ensure_runtime(endpoint) -> dict:
    listed = ok(endpoint, "POST", "/runtimes", {})
    for item in listed.get("agentRuntimes", []):
        if item.get("agentRuntimeName") == RUNTIME:
            return ok(endpoint, "GET", f"/runtimes/{item['agentRuntimeId']}")
    created = ok(
        endpoint,
        "PUT",
        "/runtimes",
        {"agentRuntimeName": RUNTIME, **RUNTIME_BODY},
    )
    return ok(endpoint, "GET", f"/runtimes/{created['agentRuntimeId']}")


def new_runtime(endpoint) -> dict:
    """A runtime a delete test owns; the name pattern forbids hyphens."""
    created = ok(
        endpoint,
        "PUT",
        "/runtimes",
        {"agentRuntimeName": f"opsDelete{suffix()}", **RUNTIME_BODY},
    )
    return created


def suffix() -> str:
    return f"{id(object()):x}"[-6:]


def ensure_endpoint(endpoint, runtime_id: str) -> dict:
    listed = ok(endpoint, "POST", f"/runtimes/{runtime_id}/runtime-endpoints", {})
    if ENDPOINT not in {item.get("name") for item in listed.get("runtimeEndpoints", [])}:
        ok(
            endpoint,
            "PUT",
            f"/runtimes/{runtime_id}/runtime-endpoints",
            {"name": ENDPOINT, "description": "ops endpoint"},
        )
    return ok(endpoint, "GET", f"/runtimes/{runtime_id}/runtime-endpoints/{ENDPOINT}")


def ensure_memory(endpoint) -> dict:
    listed = ok(endpoint, "POST", "/memories", {})
    for item in listed.get("memories", []):
        if item.get("id", "").startswith(f"{MEMORY}-"):
            return ok(endpoint, "GET", f"/memories/{item['id']}/details")["memory"]
    created = ok(
        endpoint,
        "POST",
        "/memories/create",
        {"name": MEMORY, "eventExpiryDuration": 30},
        status=202,
    )
    return created["memory"]


def new_memory(endpoint) -> dict:
    created = ok(
        endpoint,
        "POST",
        "/memories/create",
        {"name": f"opsDeleteMemory{suffix()}", "eventExpiryDuration": 30},
        status=202,
    )
    return created["memory"]


def new_event(endpoint, memory_id: str) -> dict:
    body = {
        "actorId": ACTOR,
        "sessionId": SESSION,
        "eventTimestamp": 1764000000,
        "payload": [{"conversational": {"role": "USER", "content": {"text": "hello"}}}],
    }
    return ok(endpoint, "POST", f"/memories/{memory_id}/events", body, status=201)["event"]


def new_record(endpoint, memory_id: str) -> str:
    created = ok(
        endpoint,
        "POST",
        f"/memories/{memory_id}/memoryRecords/batchCreate",
        {
            "records": [
                {
                    "requestIdentifier": f"ops-{id(object()):x}",
                    "namespaces": [NAMESPACE],
                    "content": {"text": "hello memory"},
                    "timestamp": 1764000000,
                }
            ]
        },
        status=201,
    )
    return created["successfulRecords"][0]["memoryRecordId"]


def test_create_agent_runtime_answers_the_resource(endpoint):
    runtime = ensure_runtime(endpoint)
    assert runtime["agentRuntimeName"] == RUNTIME
    assert runtime["agentRuntimeId"]
    assert runtime["agentRuntimeArn"]
    assert runtime["status"] == "READY"


def test_get_agent_runtime_reads_it(endpoint):
    runtime = ensure_runtime(endpoint)
    answer = ok(endpoint, "GET", f"/runtimes/{runtime['agentRuntimeId']}")
    assert answer["agentRuntimeId"] == runtime["agentRuntimeId"]
    assert answer["agentRuntimeName"] == RUNTIME


def test_list_agent_runtimes_lists_it(endpoint):
    runtime = ensure_runtime(endpoint)
    answer = ok(endpoint, "POST", "/runtimes", {})
    assert runtime["agentRuntimeId"] in {
        item["agentRuntimeId"] for item in answer["agentRuntimes"]
    }


def test_update_agent_runtime_bumps_the_version(endpoint):
    runtime = ensure_runtime(endpoint)
    before = int(runtime["agentRuntimeVersion"])
    updated = ok(
        endpoint,
        "PUT",
        f"/runtimes/{runtime['agentRuntimeId']}",
        {**RUNTIME_BODY, "description": "ops runtime"},
    )
    assert int(updated["agentRuntimeVersion"]) == before + 1


def test_list_agent_runtime_versions_lists_it(endpoint):
    runtime = ensure_runtime(endpoint)
    answer = ok(endpoint, "POST", f"/runtimes/{runtime['agentRuntimeId']}/versions", {})
    assert "1" in {item["agentRuntimeVersion"] for item in answer["agentRuntimes"]}


def test_delete_agent_runtime_removes_it(endpoint):
    runtime = new_runtime(endpoint)
    ok(endpoint, "DELETE", f"/runtimes/{runtime['agentRuntimeId']}")
    code, _text = call(endpoint, "GET", f"/runtimes/{runtime['agentRuntimeId']}")
    assert code == 404


def test_create_agent_runtime_endpoint_answers_the_resource(endpoint):
    runtime = ensure_runtime(endpoint)
    endpoint_record = ensure_endpoint(endpoint, runtime["agentRuntimeId"])
    assert endpoint_record["name"] == ENDPOINT
    assert endpoint_record["agentRuntimeEndpointArn"]


def test_get_agent_runtime_endpoint_reads_it(endpoint):
    runtime = ensure_runtime(endpoint)
    ensure_endpoint(endpoint, runtime["agentRuntimeId"])
    answer = ok(
        endpoint,
        "GET",
        f"/runtimes/{runtime['agentRuntimeId']}/runtime-endpoints/{ENDPOINT}",
    )
    assert answer["name"] == ENDPOINT
    assert answer["agentRuntimeArn"] == runtime["agentRuntimeArn"]


def test_list_agent_runtime_endpoints_lists_it(endpoint):
    runtime = ensure_runtime(endpoint)
    ensure_endpoint(endpoint, runtime["agentRuntimeId"])
    answer = ok(
        endpoint, "POST", f"/runtimes/{runtime['agentRuntimeId']}/runtime-endpoints", {}
    )
    assert ENDPOINT in {item["name"] for item in answer["runtimeEndpoints"]}


def test_update_agent_runtime_endpoint_sets_the_description(endpoint):
    runtime = ensure_runtime(endpoint)
    ensure_endpoint(endpoint, runtime["agentRuntimeId"])
    ok(
        endpoint,
        "PUT",
        f"/runtimes/{runtime['agentRuntimeId']}/runtime-endpoints/{ENDPOINT}",
        {"description": "updated endpoint"},
    )
    answer = ok(
        endpoint,
        "GET",
        f"/runtimes/{runtime['agentRuntimeId']}/runtime-endpoints/{ENDPOINT}",
    )
    assert answer["description"] == "updated endpoint"


def test_delete_agent_runtime_endpoint_removes_it(endpoint):
    runtime = ensure_runtime(endpoint)
    name = f"opsDelete{suffix()}"
    ok(
        endpoint,
        "PUT",
        f"/runtimes/{runtime['agentRuntimeId']}/runtime-endpoints",
        {"name": name},
    )
    ok(endpoint, "DELETE", f"/runtimes/{runtime['agentRuntimeId']}/runtime-endpoints/{name}")
    code, _text = call(
        endpoint, "GET", f"/runtimes/{runtime['agentRuntimeId']}/runtime-endpoints/{name}"
    )
    assert code == 404


def resource_policy(runtime: dict) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": "bedrock-agentcore:InvokeAgentRuntime",
                    "Resource": runtime["agentRuntimeArn"],
                }
            ],
        }
    )


def test_put_resource_policy_answers_the_policy(endpoint):
    runtime = ensure_runtime(endpoint)
    policy = resource_policy(runtime)
    answer = ok(
        endpoint,
        "PUT",
        f"/resourcepolicy/{quote(runtime['agentRuntimeArn'], safe='')}",
        {"policy": policy},
        status=201,
    )
    assert answer["policy"] == policy


def test_get_resource_policy_reads_it(endpoint):
    runtime = ensure_runtime(endpoint)
    policy = resource_policy(runtime)
    arn = quote(runtime["agentRuntimeArn"], safe="")
    ok(endpoint, "PUT", f"/resourcepolicy/{arn}", {"policy": policy}, status=201)
    answer = ok(endpoint, "GET", f"/resourcepolicy/{arn}")
    assert answer["policy"] == policy


def test_delete_resource_policy_removes_it(endpoint):
    runtime = ensure_runtime(endpoint)
    policy = resource_policy(runtime)
    arn = quote(runtime["agentRuntimeArn"], safe="")
    ok(endpoint, "PUT", f"/resourcepolicy/{arn}", {"policy": policy}, status=201)
    code, text = call(endpoint, "DELETE", f"/resourcepolicy/{arn}")
    assert code == 204, text[:300]
    code, _text = call(endpoint, "GET", f"/resourcepolicy/{arn}")
    assert code == 404


def test_invoke_agent_runtime_answers_an_echo(endpoint):
    runtime = ensure_runtime(endpoint)
    answer = ok(
        endpoint,
        "POST",
        f"/runtimes/{runtime['agentRuntimeArn']}/invocations",
        INVOKE_BODY,
    )
    assert answer["agentRuntimeArn"] == runtime["agentRuntimeArn"]
    assert answer["input"] == INVOKE_BODY


def test_create_memory_answers_the_resource(endpoint):
    memory = ensure_memory(endpoint)
    assert memory["name"] == MEMORY
    assert memory["id"]
    assert memory["arn"]


def test_get_memory_reads_it(endpoint):
    memory = ensure_memory(endpoint)
    answer = ok(endpoint, "GET", f"/memories/{memory['id']}/details")
    assert answer["memory"]["id"] == memory["id"]
    assert answer["memory"]["name"] == MEMORY


def test_list_memories_lists_it(endpoint):
    memory = ensure_memory(endpoint)
    answer = ok(endpoint, "POST", "/memories", {})
    assert memory["id"] in {item["id"] for item in answer["memories"]}


def test_update_memory_sets_the_description(endpoint):
    memory = ensure_memory(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/memories/{memory['id']}/update",
        {"description": "updated memory"},
        status=202,
    )
    answer = ok(endpoint, "GET", f"/memories/{memory['id']}/details")
    assert answer["memory"]["description"] == "updated memory"


def test_delete_memory_removes_it(endpoint):
    memory = new_memory(endpoint)
    ok(endpoint, "DELETE", f"/memories/{memory['id']}/delete", status=202)
    code, _text = call(endpoint, "GET", f"/memories/{memory['id']}/details")
    assert code == 404


def test_create_event_answers_the_event(endpoint):
    memory = ensure_memory(endpoint)
    event = new_event(endpoint, memory["id"])
    assert event["eventId"]
    assert event["actorId"] == ACTOR
    assert event["sessionId"] == SESSION


def test_get_event_reads_it(endpoint):
    memory = ensure_memory(endpoint)
    event = new_event(endpoint, memory["id"])
    path = (
        f"/memories/{memory['id']}/actor/{ACTOR}/sessions/{SESSION}"
        f"/events/{quote(event['eventId'], safe='')}"
    )
    answer = ok(endpoint, "GET", path)
    assert answer["event"]["eventId"] == event["eventId"]


def test_delete_event_removes_it(endpoint):
    memory = ensure_memory(endpoint)
    event = new_event(endpoint, memory["id"])
    path = (
        f"/memories/{memory['id']}/actor/{ACTOR}/sessions/{SESSION}"
        f"/events/{quote(event['eventId'], safe='')}"
    )
    ok(endpoint, "DELETE", path)
    code, _text = call(endpoint, "GET", path)
    assert code == 404


def test_list_events_lists_them(endpoint):
    memory = ensure_memory(endpoint)
    event = new_event(endpoint, memory["id"])
    answer = ok(
        endpoint,
        "POST",
        f"/memories/{memory['id']}/actor/{ACTOR}/sessions/{SESSION}",
        {},
    )
    assert event["eventId"] in {item["eventId"] for item in answer["events"]}


def test_list_actors_lists_them(endpoint):
    memory = ensure_memory(endpoint)
    new_event(endpoint, memory["id"])
    answer = ok(endpoint, "POST", f"/memories/{memory['id']}/actors", {})
    assert ACTOR in {item["actorId"] for item in answer["actorSummaries"]}


def test_list_sessions_lists_them(endpoint):
    memory = ensure_memory(endpoint)
    new_event(endpoint, memory["id"])
    answer = ok(
        endpoint, "POST", f"/memories/{memory['id']}/actor/{ACTOR}/sessions", {}
    )
    assert SESSION in {item["sessionId"] for item in answer["sessionSummaries"]}


def test_batch_create_memory_records_answers_the_records(endpoint):
    memory = ensure_memory(endpoint)
    record_id = new_record(endpoint, memory["id"])
    assert record_id.startswith("mem-")


def test_batch_update_memory_records_answers_the_records(endpoint):
    memory = ensure_memory(endpoint)
    record_id = new_record(endpoint, memory["id"])
    answer = ok(
        endpoint,
        "POST",
        f"/memories/{memory['id']}/memoryRecords/batchUpdate",
        {
            "records": [
                {
                    "memoryRecordId": record_id,
                    "timestamp": 1764000001,
                    "content": {"text": "updated memory"},
                }
            ]
        },
    )
    assert answer["successfulRecords"][0]["memoryRecordId"] == record_id


def test_batch_delete_memory_records_answers_the_records(endpoint):
    memory = ensure_memory(endpoint)
    record_id = new_record(endpoint, memory["id"])
    answer = ok(
        endpoint,
        "POST",
        f"/memories/{memory['id']}/memoryRecords/batchDelete",
        {"records": [{"memoryRecordId": record_id}]},
    )
    assert answer["successfulRecords"][0]["memoryRecordId"] == record_id


def test_get_memory_record_reads_it(endpoint):
    memory = ensure_memory(endpoint)
    record_id = new_record(endpoint, memory["id"])
    answer = ok(
        endpoint, "GET", f"/memories/{memory['id']}/memoryRecord/{record_id}"
    )
    assert answer["memoryRecord"]["memoryRecordId"] == record_id


def test_list_memory_records_lists_them(endpoint):
    memory = ensure_memory(endpoint)
    record_id = new_record(endpoint, memory["id"])
    answer = ok(endpoint, "POST", f"/memories/{memory['id']}/memoryRecords", {})
    assert record_id in {
        item["memoryRecordId"] for item in answer["memoryRecordSummaries"]
    }


def test_delete_memory_record_removes_it(endpoint):
    memory = ensure_memory(endpoint)
    record_id = new_record(endpoint, memory["id"])
    ok(endpoint, "DELETE", f"/memories/{memory['id']}/memoryRecords/{record_id}")
    code, _text = call(
        endpoint, "GET", f"/memories/{memory['id']}/memoryRecord/{record_id}"
    )
    assert code == 404


def test_retrieve_memory_records_scores_them(endpoint):
    memory = ensure_memory(endpoint)
    new_record(endpoint, memory["id"])
    answer = ok(
        endpoint,
        "POST",
        f"/memories/{memory['id']}/retrieve",
        {"searchCriteria": {"searchQuery": "hello"}},
    )
    assert answer["memoryRecordSummaries"]
    assert answer["memoryRecordSummaries"][0]["score"] > 0


def test_start_memory_extraction_job_answers_not_found(endpoint):
    """No extraction runs, so a job id never exists; the not-found contract is the answer."""
    memory = ensure_memory(endpoint)
    code, text = call(
        endpoint,
        "POST",
        f"/memories/{memory['id']}/extractionJobs/start",
        {"extractionJob": {"jobId": "ops-extraction-job"}},
    )
    assert code == 404, text[:300]


def test_list_memory_extraction_jobs_answers_a_list(endpoint):
    memory = ensure_memory(endpoint)
    answer = ok(endpoint, "POST", f"/memories/{memory['id']}/extractionJobs", {})
    assert isinstance(answer["jobs"], list)
