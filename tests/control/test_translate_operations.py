"""Amazon Translate on the wire: every advertised operation, driven through the JSON protocol.

A batch job translates documents it reads out of S3, so an input bucket with a document comes
first; the bucket, its objects and every job are left in place. Jobs are ClientToken-idempotent,
so each test starts with a stable token and a second sweep meets the job the first one left.

The in-process stand-in serves each request in its own event loop, so a job's background worker
is cancelled the moment StartTextTranslationJob returns and the job stays SUBMITTED. The lab
server keeps its loop, so the SUBMITTED -> IN_PROGRESS -> COMPLETED walk, the translated objects
and a stop that reaches a running job are proven there and skipped here.
"""

from __future__ import annotations

import json
import os
import time

import pytest
import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "Translate."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

INPUT_BUCKET = "ops-translate-input"
OUTPUT_BUCKET = "ops-translate-output"
DOCUMENT_NAME = "hello.txt"
# Each job reads out of this one folder, so a job's document counts are always one.
INPUT_PREFIX = "shared/"
DOCUMENT_KEY = f"{INPUT_PREFIX}{DOCUMENT_NAME}"
DOCUMENT = b"Hello from Emuplane.\nSecond line.\n"
INPUT_URI = f"s3://{INPUT_BUCKET}/{INPUT_PREFIX}"
OUTPUT_PREFIX = "translated/"
OUTPUT_URI = f"s3://{OUTPUT_BUCKET}/{OUTPUT_PREFIX}"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/ops-translate"

# Stable names and tokens, so a lab sweep that re-runs meets the job it started before.
SHARED = "ops-translate-shared"
SHARED_TOKEN = "ops-translate-shared-token"
REPLAYED = "ops-translate-replayed"
REPLAYED_TOKEN = "ops-translate-replayed-token"
DESCRIBED = "ops-translate-described"
DESCRIBED_TOKEN = "ops-translate-described-token"
LISTED = "ops-translate-listed"
LISTED_TOKEN = "ops-translate-listed-token"
COMPLETED = "ops-translate-completed"
COMPLETED_TOKEN = "ops-translate-completed-token"
STOPPED = "ops-translate-stop"
STOPPED_TOKEN = "ops-translate-stop-token"
PAGE_PREFIX = "ops-translate-page-"
PAGE_A = f"{PAGE_PREFIX}a"
PAGE_B = f"{PAGE_PREFIX}b"

STATUSES = (
    "SUBMITTED",
    "IN_PROGRESS",
    "COMPLETED",
    "COMPLETED_WITH_ERROR",
    "FAILED",
    "STOP_REQUESTED",
    "STOPPED",
)
TERMINAL = ("COMPLETED", "COMPLETED_WITH_ERROR", "FAILED", "STOPPED")

# asyncio.run cancels the job worker in the stand-in; the lab's single long-lived loop does not.
WORKER_RUNS = bool(os.environ.get("EP_LAB_EMULATOR"))
needs_worker = pytest.mark.skipif(
    not WORKER_RUNS,
    reason="the in-process stand-in cancels a job's background worker; the live sweep proves it",
)


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "translate", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def valid_start(**overrides) -> dict:
    """A start request every field of which passes validation, minus the overrides."""
    body = {
        "JobName": SHARED,
        "ClientToken": SHARED_TOKEN,
        "DataAccessRoleArn": ROLE,
        "InputDataConfig": {"S3Uri": INPUT_URI, "ContentType": "text/plain"},
        "OutputDataConfig": {"S3Uri": OUTPUT_URI},
        "SourceLanguageCode": "en",
        "TargetLanguageCodes": ["fr"],
    }
    body.update(overrides)
    return body


def start(endpoint, **overrides):
    return call(endpoint, "StartTextTranslationJob", **valid_start(**overrides))


def ensure_job(endpoint, name: str, token: str, **params) -> str:
    """Find-or-create through ClientToken: a re-run gets the job id the first sweep created."""
    status, text = start(endpoint, JobName=name, ClientToken=token, **params)
    assert status == 200, f"StartTextTranslationJob answered {status}: {text[:400]}"
    return json.loads(text)["JobId"]


def describe(endpoint, job_id: str) -> dict:
    return ok(endpoint, "DescribeTextTranslationJob", JobId=job_id)[
        "TextTranslationJobProperties"
    ]


def documents(endpoint) -> None:
    """The input bucket, the output bucket and the document a job reads; a re-run overwrites."""
    for bucket in (INPUT_BUCKET, OUTPUT_BUCKET):
        status, text = signed.request(endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{bucket}")
        assert status in (200, 409), f"CreateBucket {bucket} answered {status}: {text[:400]}"
    status, text = signed.request(
        endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{INPUT_BUCKET}/{DOCUMENT_KEY}", DOCUMENT
    )
    assert status in (200, 204), f"PutObject answered {status}: {text[:400]}"


def object_body(endpoint, bucket: str, key: str) -> str:
    status, text = signed.request(endpoint, "s3", ACCOUNT, REGION, "GET", f"/{bucket}/{key}")
    assert status == 200, f"GET /{bucket}/{key} answered {status}: {text[:400]}"
    return text


def output_folder(job: dict) -> tuple[str, str]:
    """The (bucket, prefix) Describe reports, which it rewrote from the caller's location."""
    bucket, _, prefix = job["OutputDataConfig"]["S3Uri"][len("s3://") :].partition("/")
    return bucket, prefix


def all_jobs(endpoint, **filters) -> list[dict]:
    """Every page of one filter's result, following NextToken to the end."""
    rows: list[dict] = []
    token = None
    while True:
        params: dict = {"MaxResults": 500}
        if filters:
            params["Filter"] = filters
        if token:
            params["NextToken"] = token
        answer = ok(endpoint, "ListTextTranslationJobs", **params)
        rows.extend(answer["TextTranslationJobPropertiesList"])
        token = answer.get("NextToken")
        if not token:
            return rows


def settled(endpoint, job_id: str, timeout: float = 25.0) -> dict:
    """DescribeTextTranslationJob until the job leaves its walk; the worker takes ~2s."""
    deadline = time.monotonic() + timeout
    while True:
        job = describe(endpoint, job_id)
        if job["JobStatus"] in TERMINAL:
            return job
        assert time.monotonic() < deadline, (
            f"{job_id} was still {job['JobStatus']} after {timeout}s"
        )
        time.sleep(0.1)


def wait_for_status(endpoint, job_id: str, wanted: str, timeout: float = 15.0) -> dict:
    """Describe until the job reaches ``wanted`` or any terminal state, so a miss is reported."""
    deadline = time.monotonic() + timeout
    while True:
        job = describe(endpoint, job_id)
        if job["JobStatus"] == wanted or job["JobStatus"] in TERMINAL:
            return job
        assert time.monotonic() < deadline, (
            f"{job_id} was still {job['JobStatus']} after {timeout}s"
        )
        time.sleep(0.05)


def test_start_text_translation_job_queues_a_new_job(s3_endpoint):
    documents(s3_endpoint)
    # A name an earlier sweep left behind means the start below is a replay, not a fresh job.
    existing = [j for j in all_jobs(s3_endpoint, JobName=SHARED) if j["JobName"] == SHARED]
    status, text = start(s3_endpoint, JobName=SHARED, ClientToken=SHARED_TOKEN)
    assert status == 200, f"StartTextTranslationJob answered {status}: {text[:400]}"
    answer = json.loads(text)
    # StartTextTranslationJobOutput carries the id and the status, and nothing else.
    assert set(answer) == {"JobId", "JobStatus"}
    assert answer["JobStatus"] in STATUSES
    if not existing:
        # A job this call created is queued; only the worker moves it on.
        assert answer["JobStatus"] == "SUBMITTED"

    job = describe(s3_endpoint, answer["JobId"])
    assert job["JobId"] == answer["JobId"]
    assert job["JobName"] == SHARED
    assert job["SourceLanguageCode"] == "en"
    assert job["TargetLanguageCodes"] == ["fr"]
    assert job["InputDataConfig"] == {"S3Uri": INPUT_URI, "ContentType": "text/plain"}
    assert job["DataAccessRoleArn"] == ROLE
    # SubmittedTime is a whole epoch second, the shape the json protocol carries a timestamp in.
    assert isinstance(job["SubmittedTime"], int)
    if job["JobStatus"] in TERMINAL:
        assert job["EndTime"] >= job["SubmittedTime"]
    else:
        # A queued or running job has not counted anything yet and has no end.
        assert "JobDetails" not in job
        assert "EndTime" not in job


def test_start_text_translation_job_is_idempotent_on_its_client_token(s3_endpoint):
    documents(s3_endpoint)
    status, text = start(s3_endpoint, JobName=REPLAYED, ClientToken=REPLAYED_TOKEN)
    assert status == 200, f"StartTextTranslationJob answered {status}: {text[:400]}"
    first = json.loads(text)

    status, text = start(s3_endpoint, JobName=REPLAYED, ClientToken=REPLAYED_TOKEN)
    assert status == 200, f"StartTextTranslationJob answered {status}: {text[:400]}"
    second = json.loads(text)

    # A replayed token resolves to the job the first call created, as it stands now.
    assert second["JobId"] == first["JobId"]
    assert second["JobStatus"] == describe(s3_endpoint, first["JobId"])["JobStatus"]
    # And no second job of the same name was started behind it.
    assert [
        j["JobId"] for j in all_jobs(s3_endpoint, JobName=REPLAYED) if j["JobName"] == REPLAYED
    ] == [first["JobId"]]


def test_start_text_translation_job_validates_its_required_fields(s3_endpoint):
    body = valid_start()
    body.pop("ClientToken")
    status, text = call(s3_endpoint, "StartTextTranslationJob", **body)
    assert status == 400 and "clientToken" in text
    assert "^[a-zA-Z0-9-]+$" in text

    status, text = call(
        s3_endpoint, "StartTextTranslationJob", **valid_start(ClientToken="not a token")
    )
    assert status == 400 and "clientToken" in text

    body = valid_start()
    body.pop("DataAccessRoleArn")
    status, text = call(s3_endpoint, "StartTextTranslationJob", **body)
    assert status == 400 and "dataAccessRoleArn" in text

    status, text = call(
        s3_endpoint, "StartTextTranslationJob", **valid_start(JobName="ops-translate!")
    )
    assert status == 400 and "jobName" in text

    # Both S3 locations are folders addressed with s3:// — Translate takes no HTTPS form.
    status, text = call(
        s3_endpoint,
        "StartTextTranslationJob",
        **valid_start(
            InputDataConfig={
                "S3Uri": f"https://{INPUT_BUCKET}.s3.amazonaws.com/{INPUT_PREFIX}",
                "ContentType": "text/plain",
            }
        ),
    )
    assert status == 400 and "inputDataConfig.s3Uri" in text

    body = valid_start()
    body.pop("OutputDataConfig")
    status, text = call(s3_endpoint, "StartTextTranslationJob", **body)
    assert status == 400 and "outputDataConfig.s3Uri" in text

    status, text = call(
        s3_endpoint,
        "StartTextTranslationJob",
        **valid_start(InputDataConfig={"S3Uri": INPUT_URI, "ContentType": "application/pdf"}),
    )
    assert status == 400 and "InvalidRequestException" in text
    assert "Unsupported content type" in text

    status, text = call(
        s3_endpoint, "StartTextTranslationJob", **valid_start(TargetLanguageCodes=[])
    )
    assert status == 400 and "targetLanguageCodes" in text

    status, text = call(
        s3_endpoint,
        "StartTextTranslationJob",
        **valid_start(TargetLanguageCodes=[f"l{index}" for index in range(11)]),
    )
    assert status == 400 and "less than or equal to 10" in text

    status, text = call(
        s3_endpoint,
        "StartTextTranslationJob",
        **valid_start(SourceLanguageCode="en", TargetLanguageCodes=["en"]),
    )
    assert status == 400 and "UnsupportedLanguagePairException" in text
    assert "Unsupported language pair: en to en." in text


def test_describe_text_translation_job_reads_back_the_job_it_started(s3_endpoint):
    documents(s3_endpoint)
    job_id = ensure_job(
        s3_endpoint,
        DESCRIBED,
        DESCRIBED_TOKEN,
        TargetLanguageCodes=["fr", "es"],
        TerminologyNames=["ops-translate-terms"],
    )
    job = describe(s3_endpoint, job_id)
    assert job["JobId"] == job_id
    assert job["JobName"] == DESCRIBED
    assert job["SourceLanguageCode"] == "en"
    assert job["TargetLanguageCodes"] == ["fr", "es"]
    assert job["TerminologyNames"] == ["ops-translate-terms"]
    assert job["DataAccessRoleArn"] == ROLE
    # The input location is echoed; the output location is rewritten to the folder the service
    # actually writes into, which is where a consumer has to look.
    assert job["InputDataConfig"] == {"S3Uri": INPUT_URI, "ContentType": "text/plain"}
    assert job["OutputDataConfig"]["S3Uri"] == f"{OUTPUT_URI}{ACCOUNT}-TranslateText-{job_id}/"
    assert job["JobStatus"] in STATUSES
    assert isinstance(job["SubmittedTime"], int)
    assert set(job) <= {
        "JobId",
        "JobName",
        "JobStatus",
        "JobDetails",
        "SourceLanguageCode",
        "TargetLanguageCodes",
        "TerminologyNames",
        "ParallelDataNames",
        "Message",
        "SubmittedTime",
        "EndTime",
        "InputDataConfig",
        "OutputDataConfig",
        "DataAccessRoleArn",
        "Settings",
    }


def test_describe_text_translation_job_names_a_job_that_is_not_there(s3_endpoint):
    status, text = call(
        s3_endpoint, "DescribeTextTranslationJob", JobId="ops-translate-nowhere"
    )
    assert status == 400 and "ResourceNotFoundException" in text
    assert "could not be found" in text

    status, text = call(s3_endpoint, "DescribeTextTranslationJob")
    assert status == 400 and "InvalidParameterValueException" in text
    assert "jobId" in text


def test_list_text_translation_jobs_returns_the_job_it_holds(s3_endpoint):
    documents(s3_endpoint)
    job_id = ensure_job(s3_endpoint, LISTED, LISTED_TOKEN)
    job = describe(s3_endpoint, job_id)
    rows = [j for j in all_jobs(s3_endpoint, JobName=LISTED) if j["JobName"] == LISTED]
    assert len(rows) == 1
    row = rows[0]
    assert row["JobId"] == job_id
    assert row["JobStatus"] == job["JobStatus"]
    assert row["SubmittedTime"] == job["SubmittedTime"]
    assert row["TargetLanguageCodes"] == ["fr"]
    # Translate's list returns the job properties, not a cut-down summary.
    assert row["InputDataConfig"] == {"S3Uri": INPUT_URI, "ContentType": "text/plain"}
    assert row["OutputDataConfig"]["S3Uri"].endswith(f"-TranslateText-{job_id}/")


def test_list_text_translation_jobs_matches_a_name_prefix_case_insensitively(s3_endpoint):
    documents(s3_endpoint)
    ensure_job(s3_endpoint, LISTED, LISTED_TOKEN)
    rows = all_jobs(s3_endpoint, JobName=LISTED.upper())
    assert LISTED in [row["JobName"] for row in rows]
    assert all(row["JobName"].lower().startswith(LISTED) for row in rows)


def test_list_text_translation_jobs_filters_by_status(s3_endpoint):
    documents(s3_endpoint)
    job_id = ensure_job(s3_endpoint, LISTED, LISTED_TOKEN)
    job = describe(s3_endpoint, job_id)
    rows = all_jobs(s3_endpoint, JobStatus=job["JobStatus"])
    assert rows
    assert all(row["JobStatus"] == job["JobStatus"] for row in rows)
    assert job_id in [row["JobId"] for row in rows]


def test_list_text_translation_jobs_refuses_two_filters_at_once(s3_endpoint):
    status, text = call(
        s3_endpoint,
        "ListTextTranslationJobs",
        Filter={"JobName": "ops-translate", "JobStatus": "COMPLETED"},
    )
    assert status == 400 and "InvalidFilterException" in text
    assert "only one filter at a time" in text

    # The two submission-time bounds describe one window, so together they are one filter.
    window = {"SubmittedAfterTime": 0, "SubmittedBeforeTime": int(time.time()) + 60}
    answer = ok(s3_endpoint, "ListTextTranslationJobs", Filter=window)
    assert isinstance(answer["TextTranslationJobPropertiesList"], list)


def test_list_text_translation_jobs_refuses_an_unknown_status(s3_endpoint):
    status, text = call(
        s3_endpoint, "ListTextTranslationJobs", Filter={"JobStatus": "RUNNING"}
    )
    assert status == 400 and "InvalidParameterValueException" in text
    assert "Member must satisfy enum value set" in text
    assert "STOP_REQUESTED" in text


def test_list_text_translation_jobs_pages_with_the_token_it_returns(s3_endpoint):
    documents(s3_endpoint)
    for name in (PAGE_A, PAGE_B):
        ensure_job(s3_endpoint, name, f"{name}-token")
    page = {"Filter": {"JobName": PAGE_PREFIX}, "MaxResults": 1}
    first = ok(s3_endpoint, "ListTextTranslationJobs", **page)
    assert len(first["TextTranslationJobPropertiesList"]) == 1
    assert first["NextToken"]

    second = ok(
        s3_endpoint, "ListTextTranslationJobs", **page, NextToken=first["NextToken"]
    )
    assert len(second["TextTranslationJobPropertiesList"]) == 1
    assert {
        first["TextTranslationJobPropertiesList"][0]["JobName"],
        second["TextTranslationJobPropertiesList"][0]["JobName"],
    } == {PAGE_A, PAGE_B}
    # The token carries the last row's sort position, so the final page carries none.
    assert "NextToken" not in second


def test_list_text_translation_jobs_refuses_a_page_over_the_cap(s3_endpoint):
    status, text = call(s3_endpoint, "ListTextTranslationJobs", MaxResults=501)
    assert status == 400 and "less than or equal to 500" in text

    status, text = call(s3_endpoint, "ListTextTranslationJobs", MaxResults="ten")
    assert status == 400 and "MaxResults must be an integer" in text

    status, text = call(s3_endpoint, "ListTextTranslationJobs", NextToken="not-a-token")
    assert status == 400 and "NextToken that you provided is invalid" in text


def test_stop_text_translation_job_reaches_the_job_and_a_second_stop_is_accepted(s3_endpoint):
    documents(s3_endpoint)
    job_id = ensure_job(s3_endpoint, STOPPED, STOPPED_TOKEN)
    first = ok(s3_endpoint, "StopTextTranslationJob", JobId=job_id)
    assert first["JobId"] == job_id
    # A running job is flagged STOP_REQUESTED; one that already finished keeps its status.
    assert first["JobStatus"] in ("STOP_REQUESTED", "STOPPED", "COMPLETED", "COMPLETED_WITH_ERROR")

    again = ok(s3_endpoint, "StopTextTranslationJob", JobId=job_id)
    assert again["JobId"] == job_id
    assert again["JobStatus"] in (
        "STOP_REQUESTED",
        "STOPPED",
        "COMPLETED",
        "COMPLETED_WITH_ERROR",
    )
    # Repeating a stop is accepted, never an error: the job is still the one named.

    status, text = call(s3_endpoint, "StopTextTranslationJob", JobId="ops-translate-nowhere")
    assert status == 400 and "ResourceNotFoundException" in text

    status, text = call(s3_endpoint, "StopTextTranslationJob")
    assert status == 400 and "jobId" in text


@needs_worker
def test_stop_text_translation_job_stops_a_running_job(s3_endpoint):
    documents(s3_endpoint)
    # Its own job per sweep: a stop is one-shot, so a job stopped by an earlier sweep could only
    # ever answer STOPPED and the request would prove nothing about a running one.
    suffix = f"{int(time.time())}-{os.getpid()}"
    name = f"ops-translate-live-stop-{suffix}"
    job_id = ensure_job(s3_endpoint, name, f"{name}-token")

    running = wait_for_status(s3_endpoint, job_id, "IN_PROGRESS")
    assert running["JobStatus"] == "IN_PROGRESS", running.get("Message")
    assert "JobDetails" not in running

    stopped = ok(s3_endpoint, "StopTextTranslationJob", JobId=job_id)
    assert stopped["JobStatus"] == "STOP_REQUESTED"

    # The worker owns the terminal state, so it is the one that records the stop.
    final = settled(s3_endpoint, job_id)
    assert final["JobStatus"] == "STOPPED"
    assert final["EndTime"] >= final["SubmittedTime"]
    # A stopped job never counted, translated or wrote anything.
    assert "JobDetails" not in final


@needs_worker
def test_a_finished_job_reports_its_counts_and_writes_the_documents(s3_endpoint):
    documents(s3_endpoint)
    job_id = ensure_job(
        s3_endpoint, COMPLETED, COMPLETED_TOKEN, TargetLanguageCodes=["fr", "es"]
    )
    job = settled(s3_endpoint, job_id)
    assert job["JobStatus"] == "COMPLETED", job.get("Message")
    assert job["JobDetails"] == {
        "TranslatedDocumentsCount": 1,
        "DocumentsWithErrorsCount": 0,
        "InputDocumentsCount": 1,
    }
    assert job["Message"] == "Your job has completed successfully."
    assert job["EndTime"] >= job["SubmittedTime"]
    assert job["InputDataConfig"] == {"S3Uri": INPUT_URI, "ContentType": "text/plain"}

    bucket, prefix = output_folder(job)
    assert bucket == OUTPUT_BUCKET
    assert prefix == f"{OUTPUT_PREFIX}{ACCOUNT}-TranslateText-{job_id}/"

    for code in ("fr", "es"):
        body = object_body(s3_endpoint, bucket, f"{prefix}{code}.{DOCUMENT_NAME}")
        # One tagged line per line of the source, so the line count survives.
        assert body.startswith(f"[{code}] Hello from Emuplane.")
        assert f"\n[{code}] Second line." in body

        details = json.loads(
            object_body(
                s3_endpoint,
                bucket,
                f"{prefix}details/{code}.auxiliary-translation-details.json",
            )
        )
        assert details["sourceLanguageCode"] == "en"
        assert details["targetLanguageCode"] == code
        assert details["charactersTranslated"] == str(len(DOCUMENT))
        assert details["documentCountWithCustomerError"] == "0"
        assert details["details"] == [
            {
                "sourceFile": DOCUMENT_NAME,
                "targetFile": f"{code}.{DOCUMENT_NAME}",
                "auxiliaryData": {"appliedTerminologies": []},
            }
        ]
