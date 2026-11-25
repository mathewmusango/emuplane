"""Signer on the wire: all 9 advertised operations, driven through REST/JSON.

Jobs read their source out of the local S3 store and write the signed object to
the destination bucket synchronously, so a job is already ``Succeeded`` when
``StartSigningJob`` returns. Without ACM-held signing material (the profile here
carries none) the written object is a JSON receipt: the source reference and the
SHA-256 of the bytes, not a signature.

A job is started with a stable ``clientRequestToken`` so a second sweep replays
the first job instead of minting another. Profiles and their permissions are
left in place; a cancel and a permission removal build their own profile and
remove only that.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}

PROFILE = "ops_signer_profile"
PROFILE_READ_BACK = "ops_signer_created"
CANCELLED_PROFILE = "ops_signer_cancelled"
PERMISSION_PROFILE = "ops_signer_perms"
STATEMENT = "ops_statement"

# Both platforms take no signingMaterial when Signer holds the key, so the profile
# is accepted under AUTH=false here and AUTH=true on the lab; the IoT platform
# refuses a material-less profile there.
PLATFORM = "AWSLambda-SHA384-ECDSA"
TOKEN = "ops-signer-token"

BUCKET = "ops-signer-source"
KEY = "payload.txt"
DATA = b"Emuplane signs this payload.\n"
DEST = "signed/"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, method: str, path: str, body=""):
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return signed.request(
        endpoint, "signer", ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = call(endpoint, method, path, body)
    assert status in (200, 201, 204), (
        f"{method} {path} answered {status}: {text[:400]}"
    )
    return json.loads(text) if text.strip() else {}


def rejected(endpoint, method: str, path: str, body="", status: int = 400) -> str:
    got, text = call(endpoint, method, path, body)
    assert got == status, f"{method} {path} answered {got}: {text[:400]}"
    return text


def s3_call(endpoint, method: str, path: str, body=b""):
    return signed.request(endpoint, "s3", ACCOUNT, REGION, method, path, body)


# ---------------------------------------------------------------------------
# Fixtures on the emulator itself
# ---------------------------------------------------------------------------


def prepare_source(endpoint) -> None:
    """The source bucket and object a job reads; a re-run overwrites in place."""
    status, text = s3_call(endpoint, "PUT", f"/{BUCKET}")
    assert status in (200, 409), f"CreateBucket answered {status}: {text[:400]}"
    status, text = s3_call(endpoint, "PUT", f"/{BUCKET}/{KEY}", DATA)
    assert status in (200, 204), f"PutObject answered {status}: {text[:400]}"


def ensure_profile(endpoint, name: str = PROFILE) -> None:
    status, text = call(endpoint, "PUT", f"/signing-profiles/{name}", {"platformId": PLATFORM})
    assert status in (200, 400), f"PutSigningProfile answered {status}: {text[:400]}"
    if status == 400:
        assert "ProfileAlreadyExists" in text


def ensure_job(endpoint) -> str:
    """The shared job, replayed by clientRequestToken on every call."""
    prepare_source(endpoint)
    ensure_profile(endpoint)
    status, text = call(
        endpoint,
        "POST",
        "/signing-jobs",
        {
            "profileName": PROFILE,
            "clientRequestToken": TOKEN,
            "source": {"s3": {"bucketName": BUCKET, "key": KEY, "version": "null"}},
            "destination": {"s3": {"bucketName": BUCKET, "prefix": DEST}},
        },
    )
    assert status == 200, f"StartSigningJob answered {status}: {text[:400]}"
    return json.loads(text)["jobId"]


def ensure_permission(endpoint) -> None:
    ensure_profile(endpoint, PERMISSION_PROFILE)
    status, text = call(
        endpoint,
        "POST",
        f"/signing-profiles/{PERMISSION_PROFILE}/permissions",
        {"statementId": STATEMENT, "principal": ACCOUNT, "action": "signer:StartSigningJob"},
    )
    assert status in (200, 400), f"AddProfilePermission answered {status}: {text[:400]}"
    if status == 400:
        assert "already in the policy" in text


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def test_put_signing_profile_is_read_back_by_get(endpoint):
    ensure_profile(endpoint, PROFILE_READ_BACK)
    profile = ok(endpoint, "GET", f"/signing-profiles/{PROFILE_READ_BACK}")
    assert profile["profileName"] == PROFILE_READ_BACK
    assert profile["platformId"] == PLATFORM
    assert profile["status"] == "Active"
    assert profile["arn"].endswith(f"/signing-profiles/{PROFILE_READ_BACK}")


def test_get_signing_profile_reports_the_default_validity_period(endpoint):
    ensure_profile(endpoint)
    profile = ok(endpoint, "GET", f"/signing-profiles/{PROFILE}")
    assert profile["signatureValidityPeriod"] == {"type": "MONTHS", "value": 135}
    assert profile["profileVersionArn"].endswith(profile["profileVersion"])


def test_cancel_signing_profile_marks_the_profile_cancelled(endpoint):
    ensure_profile(endpoint, CANCELLED_PROFILE)
    ok(endpoint, "DELETE", f"/signing-profiles/{CANCELLED_PROFILE}")
    profile = ok(endpoint, "GET", f"/signing-profiles/{CANCELLED_PROFILE}")
    assert profile["status"] == "Canceled"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def test_start_signing_job_answers_an_id_and_writes_the_signed_object(endpoint):
    job_id = ensure_job(endpoint)
    job = ok(endpoint, "GET", f"/signing-jobs/{job_id}")
    assert job["status"] == "Succeeded"
    assert job["signedObject"]["s3"]["key"] == f"{DEST}{job_id}"

    status, body = s3_call(
        endpoint, "GET", f"/{BUCKET}/{DEST}{job_id}"
    )
    assert status == 200, f"GET the signed object answered {status}: {body[:400]}"
    receipt = json.loads(body)
    assert receipt["jobId"] == job_id
    assert receipt["source"]["key"] == KEY
    assert len(receipt["sourceSha256"]) == 64


def test_describe_signing_job_reads_back_the_job_it_started(endpoint):
    job_id = ensure_job(endpoint)
    job = ok(endpoint, "GET", f"/signing-jobs/{job_id}")
    assert job["jobId"] == job_id
    assert job["profileName"] == PROFILE
    assert job["platformId"] == PLATFORM
    assert job["source"]["s3"]["bucketName"] == BUCKET
    assert job["source"]["s3"]["key"] == KEY
    assert job["statusReason"] == "Signing Succeeded"


def test_list_signing_jobs_returns_the_job_it_holds(endpoint):
    job_id = ensure_job(endpoint)
    answer = ok(endpoint, "GET", "/signing-jobs?maxResults=25")
    assert job_id in [job["jobId"] for job in answer["jobs"]]


def test_list_signing_jobs_filters_by_status(endpoint):
    job_id = ensure_job(endpoint)
    answer = ok(endpoint, "GET", "/signing-jobs?status=Succeeded&maxResults=25")
    assert job_id in [job["jobId"] for job in answer["jobs"]]


# ---------------------------------------------------------------------------
# Profile permissions
# ---------------------------------------------------------------------------


def test_add_profile_permission_answers_a_revision_id(endpoint):
    ensure_permission(endpoint)
    answer = ok(endpoint, "GET", f"/signing-profiles/{PERMISSION_PROFILE}/permissions")
    assert answer["revisionId"]
    assert [p["statementId"] for p in answer["permissions"]] == [STATEMENT]


def test_list_profile_permissions_shows_the_principal_and_action(endpoint):
    ensure_permission(endpoint)
    answer = ok(endpoint, "GET", f"/signing-profiles/{PERMISSION_PROFILE}/permissions")
    permission = answer["permissions"][0]
    assert permission["principal"] == ACCOUNT
    assert permission["action"] == "signer:StartSigningJob"
    assert answer["policySizeBytes"] > 0


def test_remove_profile_permission_takes_the_last_statement_with_it(endpoint):
    ensure_permission(endpoint)
    listed = ok(endpoint, "GET", f"/signing-profiles/{PERMISSION_PROFILE}/permissions")
    ok(
        endpoint,
        "DELETE",
        f"/signing-profiles/{PERMISSION_PROFILE}/permissions/{STATEMENT}"
        f"?revisionId={listed['revisionId']}",
    )
    # The last statement removes the policy, so a listing is PolicyNotFound again.
    rejected(
        endpoint,
        "GET",
        f"/signing-profiles/{PERMISSION_PROFILE}/permissions",
        status=404,
    )
