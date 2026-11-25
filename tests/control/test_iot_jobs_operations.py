"""IoT Jobs on the wire: 16 control-plane and 4 device-plane operations.

The control plane signs with the `iot` scope and the device plane with
`iot-jobs-data`; both share the `iot` module's job store. A job targets a thing,
which is created first. Names carry a per-run token so a re-sweep creates fresh
jobs and templates, and each delete action owns the resource it removes.
"""

from __future__ import annotations

import json
import secrets

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
RUN = secrets.token_hex(4)
THING = "ops-jobs-thing"
JOB = f"ops-job-{RUN}"
TEMPLATE = f"ops-template-{RUN}"
DOCUMENT = json.dumps({"action": "reboot", "version": 1})


def call(endpoint, service: str, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, service, ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, service: str, method: str, path: str, payload: dict | None = None, status: int = 200) -> dict:
    code, text = call(endpoint, service, method, path, payload)
    assert code == status, f"{method} {path} answered {code}: {text[:400]}"
    return json.loads(text or "{}")


def ensure_thing(endpoint) -> str:
    answer = ok(endpoint, "iot", "POST", f"/things/{THING}", {})
    return answer["thingArn"]


def create_job(endpoint, job_id: str, **extra) -> dict:
    return ok(
        endpoint,
        "iot",
        "PUT",
        f"/jobs/{job_id}",
        {
            "targets": [ensure_thing(endpoint)],
            "document": DOCUMENT,
            "description": "ops job",
            **extra,
        },
    )


def ensure_job(endpoint, job_id: str = JOB) -> None:
    code, _text = call(endpoint, "iot", "GET", f"/jobs/{job_id}")
    if code != 200:
        create_job(endpoint, job_id)


def ensure_template(endpoint, template_id: str = TEMPLATE) -> None:
    code, _text = call(endpoint, "iot", "GET", f"/job-templates/{template_id}")
    if code != 200:
        ok(
            endpoint,
            "iot",
            "PUT",
            f"/job-templates/{template_id}",
            {"description": "ops template", "document": DOCUMENT},
        )


def test_create_job_answers_the_job(endpoint):
    created = create_job(endpoint, JOB)
    assert created["jobId"] == JOB
    assert created["jobArn"].endswith(f"job/{JOB}")


def test_get_job_document_reads_the_document(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot", "GET", f"/jobs/{JOB}/job-document")
    assert json.loads(answer["document"]) == json.loads(DOCUMENT)


def test_describe_job_reads_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot", "GET", f"/jobs/{JOB}")
    job = answer["job"]
    assert job["jobId"] == JOB
    assert job["status"] == "IN_PROGRESS"
    assert "jobProcessDetails" in job


def test_update_job_sets_the_description(endpoint):
    ensure_job(endpoint)
    ok(endpoint, "iot", "PATCH", f"/jobs/{JOB}", {"description": "updated job"})
    answer = ok(endpoint, "iot", "GET", f"/jobs/{JOB}")
    assert answer["job"]["description"] == "updated job"


def test_list_jobs_lists_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot", "GET", "/jobs")
    assert JOB in {job["jobId"] for job in answer["jobs"]}


def test_list_job_executions_for_thing_lists_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot", "GET", f"/things/{THING}/jobs")
    assert JOB in {item["jobId"] for item in answer["executionSummaries"]}


def test_list_job_executions_for_job_lists_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot", "GET", f"/jobs/{JOB}/things")
    assert ensure_thing(endpoint) in {
        item["thingArn"] for item in answer["executionSummaries"]
    }


def test_describe_job_execution_reads_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot", "GET", f"/things/{THING}/jobs/{JOB}")
    execution = answer["execution"]
    assert execution["jobId"] == JOB
    assert execution["executionNumber"] == 1
    assert execution["versionNumber"] >= 1


def test_cancel_job_cancels_it(endpoint):
    job_id = f"ops-cancel-job-{RUN}"
    create_job(endpoint, job_id)
    ok(endpoint, "iot", "PUT", f"/jobs/{job_id}/cancel", {"reasonCode": "ops"})
    answer = ok(endpoint, "iot", "GET", f"/jobs/{job_id}")
    assert answer["job"]["status"] == "CANCELED"


def test_delete_job_removes_it(endpoint):
    job_id = f"ops-delete-job-{RUN}"
    create_job(endpoint, job_id)
    ok(endpoint, "iot", "DELETE", f"/jobs/{job_id}?force=true")
    code, _text = call(endpoint, "iot", "GET", f"/jobs/{job_id}")
    assert code == 404


def test_cancel_job_execution_cancels_it(endpoint):
    job_id = f"ops-cancel-execution-{RUN}"
    create_job(endpoint, job_id)
    ok(endpoint, "iot", "PUT", f"/things/{THING}/jobs/{job_id}/cancel", {})
    answer = ok(endpoint, "iot", "GET", f"/things/{THING}/jobs/{job_id}")
    assert answer["execution"]["status"] == "CANCELED"


def test_delete_job_execution_removes_it(endpoint):
    job_id = f"ops-delete-execution-{RUN}"
    create_job(endpoint, job_id)
    ok(endpoint, "iot", "DELETE", f"/things/{THING}/jobs/{job_id}/executionNumber/1")
    code, _text = call(endpoint, "iot", "GET", f"/things/{THING}/jobs/{job_id}")
    assert code == 404


def test_create_job_template_answers_the_template(endpoint):
    created = ok(
        endpoint,
        "iot",
        "PUT",
        f"/job-templates/{TEMPLATE}",
        {"description": "ops template", "document": DOCUMENT},
    )
    assert created["jobTemplateId"] == TEMPLATE
    assert created["jobTemplateArn"].endswith(f"jobtemplate/{TEMPLATE}")


def test_describe_job_template_reads_it(endpoint):
    ensure_template(endpoint)
    answer = ok(endpoint, "iot", "GET", f"/job-templates/{TEMPLATE}")
    assert answer["jobTemplateId"] == TEMPLATE
    assert json.loads(answer["document"]) == json.loads(DOCUMENT)


def test_list_job_templates_lists_it(endpoint):
    ensure_template(endpoint)
    answer = ok(endpoint, "iot", "GET", "/job-templates")
    assert TEMPLATE in {item["jobTemplateId"] for item in answer["jobTemplates"]}


def test_delete_job_template_removes_it(endpoint):
    template_id = f"ops-delete-template-{RUN}"
    ok(
        endpoint,
        "iot",
        "PUT",
        f"/job-templates/{template_id}",
        {"description": "ops template", "document": DOCUMENT},
    )
    ok(endpoint, "iot", "DELETE", f"/job-templates/{template_id}")
    code, _text = call(endpoint, "iot", "GET", f"/job-templates/{template_id}")
    assert code == 404


# --- Device data plane (`iot-jobs-data`) -----------------------------------


def test_get_pending_job_executions_lists_the_job(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot-jobs-data", "GET", f"/things/{THING}/jobs")
    pending = answer["queuedJobs"] + answer["inProgressJobs"]
    assert JOB in {item["jobId"] for item in pending}


def test_start_next_pending_job_execution_starts_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot-jobs-data", "PUT", f"/things/{THING}/jobs/$next", {})
    execution = answer["execution"]
    assert execution["status"] == "IN_PROGRESS"
    assert execution["jobId"]


def test_device_describe_job_execution_reads_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "iot-jobs-data", "GET", f"/things/{THING}/jobs/{JOB}")
    assert answer["execution"]["jobId"] == JOB
    # The `$next` sentinel is a read here: it peeks the queue without starting it.
    peek = ok(endpoint, "iot-jobs-data", "GET", f"/things/{THING}/jobs/$next")
    assert "execution" in peek or peek == {}


def test_update_job_execution_reports_progress(endpoint):
    job_id = f"ops-update-execution-{RUN}"
    create_job(endpoint, job_id)
    execution = ok(endpoint, "iot", "GET", f"/things/{THING}/jobs/{job_id}")["execution"]
    ok(
        endpoint,
        "iot-jobs-data",
        "POST",
        f"/things/{THING}/jobs/{job_id}",
        {"status": "IN_PROGRESS", "expectedVersion": execution["versionNumber"]},
    )
    answer = ok(endpoint, "iot", "GET", f"/things/{THING}/jobs/{job_id}")
    assert answer["execution"]["status"] == "IN_PROGRESS"
    assert answer["execution"]["versionNumber"] > execution["versionNumber"]
