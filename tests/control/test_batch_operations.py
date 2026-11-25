"""AWS Batch on the wire: all 10 advertised operations, REST/JSON.

Paths are `/v1/<operation>`. Compute environments, job queues and job
definitions are records keyed by name; a submitted job is a stub that lands
`SUCCEEDED` immediately. A stable environment/queue/definition carries the read
tests; a create test makes its own.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
CE = "ops-batch-ce"
QUEUE = "ops-batch-queue"
JD = "ops-batch-jd"


def call(endpoint, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "batch", ACCOUNT, REGION, "POST", path, body, JSON_TYPE)


def ok(endpoint, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, path, payload)
    assert status == 200, f"{path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def ensure_ce(endpoint, name: str = CE) -> str:
    status, text = call(endpoint, "/v1/createcomputeenvironment", {"computeEnvironmentName": name, "type": "UNMANAGED"})
    assert status == 200 or "Object already exists" in text, text[:300]
    names = [item["computeEnvironmentName"] for item in ok(endpoint, "/v1/describecomputeenvironments")["computeEnvironments"]]
    assert name in names
    return name


def ensure_queue(endpoint, name: str = QUEUE, ce: str = CE) -> str:
    ensure_ce(endpoint, ce)
    body = {
        "jobQueueName": name,
        "priority": 1,
        "computeEnvironmentOrder": [{"order": 1, "computeEnvironment": ce}],
    }
    status, text = call(endpoint, "/v1/createjobqueue", body)
    assert status == 200 or "Object already exists" in text, text[:300]
    names = [item["jobQueueName"] for item in ok(endpoint, "/v1/describejobqueues")["jobQueues"]]
    assert name in names
    return name


def ensure_job_definition(endpoint, name: str = JD) -> str:
    existing = ok(endpoint, "/v1/describejobdefinitions", {"jobDefinitionName": name})["jobDefinitions"]
    if not existing:
        ok(endpoint, "/v1/registerjobdefinition", {"jobDefinitionName": name, "type": "container"})
    return name


def submit(endpoint, name: str = "ops-batch-job") -> str:
    queue = ensure_queue(endpoint)
    definition = ensure_job_definition(endpoint)
    return ok(
        endpoint,
        "/v1/submitjob",
        {"jobName": name, "jobQueue": queue, "jobDefinition": definition},
    )["jobId"]


# ---------------------------------------------------------------------------
# Compute environments
# ---------------------------------------------------------------------------


def test_create_compute_environment_is_read_back(endpoint):
    name = f"ops-batch-ce-{time.time_ns()}"
    ok(endpoint, "/v1/createcomputeenvironment", {"computeEnvironmentName": name, "type": "UNMANAGED"})
    names = [item["computeEnvironmentName"] for item in ok(endpoint, "/v1/describecomputeenvironments")["computeEnvironments"]]
    assert name in names


def test_update_compute_environment_changes_the_state(endpoint):
    ensure_ce(endpoint)
    ok(endpoint, "/v1/updatecomputeenvironment", {"computeEnvironment": CE, "state": "DISABLED"})
    described = {item["computeEnvironmentName"]: item for item in ok(endpoint, "/v1/describecomputeenvironments")["computeEnvironments"]}
    assert described[CE]["state"] == "DISABLED"


def test_describe_compute_environments_lists_the_environment(endpoint):
    ensure_ce(endpoint)
    names = [item["computeEnvironmentName"] for item in ok(endpoint, "/v1/describecomputeenvironments")["computeEnvironments"]]
    assert CE in names


# ---------------------------------------------------------------------------
# Job queues
# ---------------------------------------------------------------------------


def test_create_job_queue_is_read_back(endpoint):
    name = f"ops-batch-queue-{time.time_ns()}"
    ensure_ce(endpoint)
    ok(endpoint, "/v1/createjobqueue", {"jobQueueName": name, "priority": 1, "computeEnvironmentOrder": [{"order": 1, "computeEnvironment": CE}]})
    names = [item["jobQueueName"] for item in ok(endpoint, "/v1/describejobqueues")["jobQueues"]]
    assert name in names


def test_describe_job_queues_lists_the_queue(endpoint):
    ensure_queue(endpoint)
    names = [item["jobQueueName"] for item in ok(endpoint, "/v1/describejobqueues")["jobQueues"]]
    assert QUEUE in names


# ---------------------------------------------------------------------------
# Job definitions
# ---------------------------------------------------------------------------


def test_register_job_definition_is_read_back(endpoint):
    name = f"ops-batch-jd-{time.time_ns()}"
    registered = ok(endpoint, "/v1/registerjobdefinition", {"jobDefinitionName": name, "type": "container"})
    assert registered["revision"] == 1
    definitions = ok(endpoint, "/v1/describejobdefinitions", {"jobDefinitionName": name})["jobDefinitions"]
    assert definitions[0]["jobDefinitionName"] == name
    assert definitions[0]["status"] == "ACTIVE"


def test_describe_job_definitions_lists_the_definition(endpoint):
    ensure_job_definition(endpoint)
    names = [item["jobDefinitionName"] for item in ok(endpoint, "/v1/describejobdefinitions")["jobDefinitions"]]
    assert JD in names


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def test_submit_job_answers_a_job(endpoint):
    job_id = submit(endpoint)
    jobs = ok(endpoint, "/v1/describejobs", {"jobs": [job_id]})["jobs"]
    assert jobs[0]["jobId"] == job_id
    assert jobs[0]["status"] == "SUCCEEDED"


def test_describe_jobs_reads_the_job(endpoint):
    job_id = submit(endpoint)
    job = ok(endpoint, "/v1/describejobs", {"jobs": [job_id]})["jobs"][0]
    assert job["jobName"] == "ops-batch-job"
    assert job["container"]["exitCode"] == 0


def test_list_jobs_lists_the_job(endpoint):
    job_id = submit(endpoint)
    listed = ok(endpoint, "/v1/listjobs", {"jobQueue": QUEUE})["jobSummaryList"]
    assert job_id in {item["jobId"] for item in listed}
