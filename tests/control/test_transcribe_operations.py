"""Amazon Transcribe on the wire: every advertised operation, driven through the JSON protocol.

MiniStack reads the media object back rather than transcribing it, so a bucket and an object
come first; any readable object is accepted and the transcript is derived from its URI. The
bucket, object and jobs are left in place, and DeleteTranscriptionJob starts a job of its own
and removes only that.

The in-process stand-in serves each request in its own event loop, so a job's background
worker is cancelled the moment StartTranscriptionJob returns. The lab server keeps its loop,
so completion (and a failure that only a worker can report) is proven there and skipped here.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

import pytest
import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "Transcribe."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

# Stable names, so a lab sweep that re-runs finds the jobs an earlier sweep left behind.
SHARED = "ops-transcribe-shared"
IDENTIFIED = "ops-transcribe-identify"
MISSING = "ops-transcribe-missing-media"
DELETED = "ops-transcribe-deleted"
PAGE_PREFIX = "ops-transcribe-page-"
PAGE_A = f"{PAGE_PREFIX}a"
PAGE_B = f"{PAGE_PREFIX}b"

BUCKET = "ops-transcribe-media"
MEDIA_KEY = "media/ops-transcribe.mp3"
MEDIA = b"ID3\x04\x00\x00\x00\x00\x00\x00ministack transcribe fixture"
MEDIA_URI = f"s3://{BUCKET}/{MEDIA_KEY}"
# The same object addressed the way an SDK emits it: virtual-hosted HTTPS is as valid as s3://.
VIRTUAL_HOSTED = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{MEDIA_KEY}"
OUTPUT_KEY = "transcripts/ops-transcribe.json"
IDENTIFIED_KEY = "transcripts/ops-transcribe-identified.json"

TERMINAL = ("COMPLETED", "FAILED")

# asyncio.run cancels the job worker in the stand-in; the lab's single long-lived loop does not.
WORKER_RUNS = bool(os.environ.get("EP_LAB_EMULATOR"))
needs_worker = pytest.mark.skipif(
    not WORKER_RUNS,
    reason="the in-process stand-in cancels a job's background worker; the live sweep proves it",
)


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "transcribe", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def start(endpoint, name: str, media_uri: str = MEDIA_URI, **params):
    return call(
        endpoint,
        "StartTranscriptionJob",
        TranscriptionJobName=name,
        Media={"MediaFileUri": media_uri},
        **params,
    )


def ensure_job(endpoint, name: str, media_uri: str = MEDIA_URI, **params) -> dict:
    """Find-or-create: a job is name-addressed, so a re-run meets the one already left there."""
    status, text = start(endpoint, name, media_uri, **params)
    if status == 200:
        return json.loads(text)["TranscriptionJob"]
    assert "ConflictException" in text, f"StartTranscriptionJob answered {status}: {text[:400]}"
    return ok(endpoint, "GetTranscriptionJob", TranscriptionJobName=name)["TranscriptionJob"]


def media(endpoint) -> None:
    """The bucket and the object a job transcribes; a re-run overwrites both."""
    status, text = signed.request(endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{BUCKET}")
    assert status in (200, 409), f"CreateBucket answered {status}: {text[:400]}"
    status, text = signed.request(
        endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{BUCKET}/{MEDIA_KEY}", MEDIA
    )
    assert status in (200, 204), f"PutObject answered {status}: {text[:400]}"


def object_body(endpoint, key: str) -> str:
    status, text = signed.request(endpoint, "s3", ACCOUNT, REGION, "GET", f"/{BUCKET}/{key}")
    assert status == 200, f"GET /{BUCKET}/{key} answered {status}: {text[:400]}"
    return text


def settled(endpoint, name: str, timeout: float = 20.0) -> dict:
    """GetTranscriptionJob until the job leaves IN_PROGRESS; the worker walks it in ~2s."""
    deadline = time.monotonic() + timeout
    while True:
        described = ok(
            endpoint, "GetTranscriptionJob", TranscriptionJobName=name
        )["TranscriptionJob"]
        if described["TranscriptionJobStatus"] in TERMINAL:
            return described
        assert time.monotonic() < deadline, (
            f"{name} was still {described['TranscriptionJobStatus']} after {timeout}s"
        )
        time.sleep(0.1)


def current_job(endpoint, name: str) -> dict:
    """The settled job where a worker runs, the stored one where the harness cannot run it."""
    if WORKER_RUNS:
        return settled(endpoint, name)
    return ok(endpoint, "GetTranscriptionJob", TranscriptionJobName=name)["TranscriptionJob"]


def summary_names(endpoint, **params) -> list[str]:
    answer = ok(endpoint, "ListTranscriptionJobs", **params)
    return [row["TranscriptionJobName"] for row in answer["TranscriptionJobSummaries"]]


def test_start_transcription_job_reports_the_job_in_progress(s3_endpoint):
    media(s3_endpoint)
    status, text = start(
        s3_endpoint,
        SHARED,
        LanguageCode="en-US",
        MediaFormat="mp3",
        MediaSampleRateHertz=16000,
        OutputBucketName=BUCKET,
        OutputKey=OUTPUT_KEY,
    )
    if status == 200:
        started = json.loads(text)["TranscriptionJob"]
        # The documented AWS response: IN_PROGRESS with StartTime set, never a queued phase.
        assert started["TranscriptionJobStatus"] == "IN_PROGRESS"
        assert started["StartTime"] == started["CreationTime"]
        assert "CompletionTime" not in started
    else:
        # A re-run meets the job an earlier sweep left, addressed by its name.
        assert status == 400 and "ConflictException" in text, text[:400]
        started = ok(
            s3_endpoint, "GetTranscriptionJob", TranscriptionJobName=SHARED
        )["TranscriptionJob"]
    assert started["TranscriptionJobName"] == SHARED
    assert started["LanguageCode"] == "en-US"
    assert started["MediaFormat"] == "mp3"
    assert started["MediaSampleRateHertz"] == 16000
    assert started["Media"] == {"MediaFileUri": MEDIA_URI}


def test_start_transcription_job_validates_its_required_fields(s3_endpoint):
    status, text = call(
        s3_endpoint, "StartTranscriptionJob", Media={"MediaFileUri": MEDIA_URI}, LanguageCode="en-US"
    )
    assert status == 400 and "transcriptionJobName" in text

    status, text = call(
        s3_endpoint,
        "StartTranscriptionJob",
        TranscriptionJobName="ops-transcribe-no-media",
        LanguageCode="en-US",
    )
    assert status == 400 and "'media'" in text

    status, text = call(
        s3_endpoint,
        "StartTranscriptionJob",
        TranscriptionJobName="ops-transcribe-invalid-uri",
        Media={"MediaFileUri": "ftp://example.com/audio.mp3"},
        LanguageCode="en-US",
    )
    assert status == 400
    assert "media.mediaFileUri" in text and "(s3://|http(s*)://).+" in text

    # An HTTPS S3 URL is accepted, but only with something after the bucket.
    status, text = call(
        s3_endpoint,
        "StartTranscriptionJob",
        TranscriptionJobName="ops-transcribe-no-key",
        Media={"MediaFileUri": f"https://{BUCKET}.s3.{REGION}.amazonaws.com"},
        LanguageCode="en-US",
    )
    assert status == 400 and "media.mediaFileUri" in text

    status, text = call(
        s3_endpoint,
        "StartTranscriptionJob",
        TranscriptionJobName="ops-transcribe-no-language",
        Media={"MediaFileUri": MEDIA_URI},
    )
    assert status == 400 and "LanguageCode or IdentifyLanguage" in text


def test_get_transcription_job_reads_back_the_job_it_started(s3_endpoint):
    media(s3_endpoint)
    ensure_job(
        s3_endpoint,
        SHARED,
        LanguageCode="en-US",
        MediaFormat="mp3",
        MediaSampleRateHertz=16000,
        OutputBucketName=BUCKET,
        OutputKey=OUTPUT_KEY,
    )
    job = ok(s3_endpoint, "GetTranscriptionJob", TranscriptionJobName=SHARED)["TranscriptionJob"]
    assert job["TranscriptionJobName"] == SHARED
    assert job["LanguageCode"] == "en-US"
    assert job["Media"] == {"MediaFileUri": MEDIA_URI}
    # One timestamp for both members: a job that starts immediately was created with it.
    assert job["CreationTime"] == job["StartTime"]
    assert job["TranscriptionJobStatus"] in ("IN_PROGRESS", "COMPLETED", "FAILED")


def test_get_transcription_job_names_a_job_that_is_not_there(s3_endpoint):
    status, text = call(
        s3_endpoint, "GetTranscriptionJob", TranscriptionJobName="ops-transcribe-nowhere"
    )
    assert status == 400 and "NotFoundException" in text
    assert "couldn't be found" in text


def test_get_transcription_job_validates_the_name(s3_endpoint):
    status, text = call(s3_endpoint, "GetTranscriptionJob")
    assert status == 400 and "transcriptionJobName" in text


@needs_worker
def test_get_transcription_job_reports_the_completed_transcript(s3_endpoint):
    media(s3_endpoint)
    ensure_job(
        s3_endpoint,
        SHARED,
        LanguageCode="en-US",
        MediaFormat="mp3",
        OutputBucketName=BUCKET,
        OutputKey=OUTPUT_KEY,
    )
    finished = settled(s3_endpoint, SHARED)
    assert finished["TranscriptionJobStatus"] == "COMPLETED", finished.get("FailureReason")
    assert finished["CompletionTime"] >= finished["StartTime"]
    assert finished["Transcript"]["TranscriptFileUri"].endswith(f"/{BUCKET}/{OUTPUT_KEY}")

    document = json.loads(object_body(s3_endpoint, OUTPUT_KEY))
    assert document["jobName"] == SHARED
    assert document["accountId"] == ACCOUNT
    assert document["status"] == "COMPLETED"
    text = document["results"]["transcripts"][0]["transcript"]
    assert text.startswith("[ministack mock transcript]")
    # The canned text is derived from the media URI, so identical input is identifiable.
    digest = hashlib.sha256(MEDIA_URI.encode()).hexdigest()[:8]
    assert f"media#{digest}" in text
    assert document["results"]["audio_segments"]


@needs_worker
def test_a_job_whose_media_is_unreadable_fails_with_the_reason(s3_endpoint):
    media(s3_endpoint)
    ensure_job(
        s3_endpoint,
        MISSING,
        media_uri=f"s3://{BUCKET}/media/absent.mp3",
        LanguageCode="en-US",
    )
    failed = settled(s3_endpoint, MISSING)
    assert failed["TranscriptionJobStatus"] == "FAILED", failed.get("Transcript")
    assert "can't be accessed" in failed["FailureReason"]
    assert "Transcript" not in failed


@needs_worker
def test_identify_language_fills_the_code_it_resolved(s3_endpoint):
    media(s3_endpoint)
    ensure_job(
        s3_endpoint,
        IDENTIFIED,
        media_uri=VIRTUAL_HOSTED,
        IdentifyLanguage=True,
        LanguageOptions=["sw-KE", "en-US"],
        OutputBucketName=BUCKET,
        OutputKey=IDENTIFIED_KEY,
    )
    finished = settled(s3_endpoint, IDENTIFIED)
    assert finished["TranscriptionJobStatus"] == "COMPLETED", finished.get("FailureReason")
    assert finished["IdentifyLanguage"] is True
    # The first option is the deterministic pick; two codes would report LanguageCodes instead.
    assert finished["LanguageCode"] == "sw-KE"
    assert finished["IdentifiedLanguageScore"] == 1.0
    assert "LanguageCodes" not in finished


def test_list_transcription_jobs_summarises_the_job_it_holds(s3_endpoint):
    media(s3_endpoint)
    ensure_job(
        s3_endpoint,
        SHARED,
        LanguageCode="en-US",
        OutputBucketName=BUCKET,
        OutputKey=OUTPUT_KEY,
    )
    job = current_job(s3_endpoint, SHARED)
    answer = ok(s3_endpoint, "ListTranscriptionJobs", JobNameContains=SHARED)
    rows = [
        row
        for row in answer["TranscriptionJobSummaries"]
        if row["TranscriptionJobName"] == SHARED
    ]
    assert len(rows) == 1
    assert rows[0]["TranscriptionJobStatus"] == job["TranscriptionJobStatus"]
    assert rows[0]["CreationTime"] == job["CreationTime"]
    assert rows[0]["LanguageCode"] == "en-US"
    # The caller named a bucket, so the transcript lands there, not in the service bucket.
    assert rows[0]["OutputLocationType"] == "CUSTOMER_BUCKET"
    # A summary is not the job: the media and the transcript answer on Get only.
    assert "Media" not in rows[0]
    assert "Transcript" not in rows[0]


def test_list_transcription_jobs_matches_a_name_case_insensitively(s3_endpoint):
    media(s3_endpoint)
    ensure_job(
        s3_endpoint, SHARED, LanguageCode="en-US", OutputBucketName=BUCKET, OutputKey=OUTPUT_KEY
    )
    assert SHARED in summary_names(s3_endpoint, JobNameContains=SHARED.upper())


def test_list_transcription_jobs_filters_by_status(s3_endpoint):
    media(s3_endpoint)
    ensure_job(
        s3_endpoint, SHARED, LanguageCode="en-US", OutputBucketName=BUCKET, OutputKey=OUTPUT_KEY
    )
    job = current_job(s3_endpoint, SHARED)
    status = job["TranscriptionJobStatus"]
    answer = ok(s3_endpoint, "ListTranscriptionJobs", Status=status, JobNameContains=SHARED)
    assert answer["Status"] == status
    rows = answer["TranscriptionJobSummaries"]
    assert SHARED in [row["TranscriptionJobName"] for row in rows]
    assert all(row["TranscriptionJobStatus"] == status for row in rows)


def test_list_transcription_jobs_refuses_an_unknown_status(s3_endpoint):
    status, text = call(s3_endpoint, "ListTranscriptionJobs", Status="RUNNING")
    assert status == 400
    assert (
        "Member must satisfy enum value set: [COMPLETED, IN_PROGRESS, QUEUED, FAILED]" in text
    )


def test_list_transcription_jobs_pages_with_the_token_it_returns(s3_endpoint):
    media(s3_endpoint)
    for name in (PAGE_A, PAGE_B):
        ensure_job(s3_endpoint, name, LanguageCode="en-US")
    page = {"JobNameContains": PAGE_PREFIX, "MaxResults": 1}
    first = ok(s3_endpoint, "ListTranscriptionJobs", **page)
    assert len(first["TranscriptionJobSummaries"]) == 1
    assert first["NextToken"]
    second = ok(
        s3_endpoint, "ListTranscriptionJobs", **page, NextToken=first["NextToken"]
    )
    assert len(second["TranscriptionJobSummaries"]) == 1
    assert {
        first["TranscriptionJobSummaries"][0]["TranscriptionJobName"],
        second["TranscriptionJobSummaries"][0]["TranscriptionJobName"],
    } == {PAGE_A, PAGE_B}
    # No bucket was named, so MiniStack's own output bucket takes the transcript.
    assert first["TranscriptionJobSummaries"][0]["OutputLocationType"] == "SERVICE_BUCKET"
    # The token is the last row's sort position, so the final page carries none.
    assert "NextToken" not in second


def test_list_transcription_jobs_refuses_a_page_over_the_cap(s3_endpoint):
    status, text = call(s3_endpoint, "ListTranscriptionJobs", MaxResults=101)
    assert status == 400
    assert "Member must have value less than or equal to 100" in text

    status, text = call(s3_endpoint, "ListTranscriptionJobs", NextToken="not-a-token")
    assert status == 400
    assert "NextToken that you provided is invalid" in text


def test_delete_transcription_job_removes_the_job_it_created(s3_endpoint):
    media(s3_endpoint)
    ensure_job(s3_endpoint, DELETED, LanguageCode="en-US")
    assert ok(
        s3_endpoint, "DeleteTranscriptionJob", TranscriptionJobName=DELETED
    ) == {}
    status, text = call(
        s3_endpoint, "GetTranscriptionJob", TranscriptionJobName=DELETED
    )
    assert status == 400 and "NotFoundException" in text
    assert DELETED not in summary_names(s3_endpoint, JobNameContains=DELETED)

    # botocore models no NotFoundException here: deleting a name that is gone succeeds.
    assert ok(
        s3_endpoint, "DeleteTranscriptionJob", TranscriptionJobName=DELETED
    ) == {}
