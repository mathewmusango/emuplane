"""The request inspector: the gateway records the operation and status, never a credential value."""

from __future__ import annotations

import http.client
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "control"))

import traffic  # noqa: E402

from conftest import ACCOUNT, OTHER, api, s3  # noqa: E402

SECRET_SIGNATURE = "super-secret-signature"
SECRET_COOKIE = "super-secret-cookie"
SECRET_TOKEN = "super-secret-session-token"


def test_a_signed_request_is_recorded_and_its_credential_is_not(gateway, console):
    status, _, _ = s3(
        gateway,
        "GET",
        "/inspector-probe?list-type=2",
        headers={
            "Authorization": (
                f"AWS4-HMAC-SHA256 Credential={ACCOUNT}/20261116/us-east-1/s3"
                f"/aws4_request, SignedHeaders=host, Signature={SECRET_SIGNATURE}"
            ),
            "Cookie": f"emuplane_session={SECRET_COOKIE}",
            "X-Amz-Security-Token": SECRET_TOKEN,
        },
    )

    # The console's bearer token sees every account, which is where the probe landed.
    code, answer = api(console, "GET", "/api/traffic?limit=500")
    assert code == 200, answer
    assert answer["capacity"] == 500
    recorded = [row for row in answer["entries"] if row["path"] == "/inspector-probe"]
    assert recorded, "the gateway did not record its own request"
    row = recorded[0]
    assert row["method"] == "GET"
    assert row["operation"] == "ListObjectsV2"
    assert row["status"] == status
    assert row["service"] == "s3"
    assert row["account"] == ACCOUNT
    assert row["signed"] is True
    assert row["credentials"] == [
        "SigV4 (redacted)",
        "Cookie (redacted)",
        "X-Amz-Security-Token (redacted)",
    ]
    assert "authorization" in row["headers"]
    assert row["request_bytes"] == 0
    assert row["response_bytes"] > 0

    # The rule is about the whole answer, not only the fields this test names.
    text = json.dumps(answer)
    for secret in (SECRET_SIGNATURE, SECRET_COOKIE, SECRET_TOKEN):
        assert secret not in text


def test_the_query_is_kept_as_names_and_the_body_as_a_size(gateway, console):
    body = b"not-a-secret-but-not-kept-either"
    s3(gateway, "PUT", "/inspector-probe-body?acl", body=body)
    _, answer = api(console, "GET", "/api/traffic?limit=50")
    row = next(item for item in answer["entries"] if item["path"] == "/inspector-probe-body")
    assert row["operation"] == "PutBucketAcl"
    assert row["query"] == ["acl"]
    assert row["request_bytes"] == len(body)
    assert body.decode() not in json.dumps(answer)


def test_the_operation_is_read_the_way_the_router_reads_it():
    headers = {"X-Amz-Target": "DynamoDB_20120810.ListTables"}
    assert traffic.operation("POST", "/", headers, b"{}", "dynamodb") == "ListTables"
    assert (
        traffic.operation("POST", "/", {}, b"Action=ListUsers&Version=2010-05-08", "iam")
        == "ListUsers"
    )
    assert traffic.operation("GET", "/b?x-id=GetObject&versionId=1", {}, b"", "s3") == "GetObject"
    assert traffic.operation("PUT", "/b/k", {}, b"", "s3", bucket="b", key="k") == "PutObject"
    assert (
        traffic.operation("GET", "/b/k?tagging", {}, b"", "s3", bucket="b", key="k")
        == "GetObjectTagging"
    )
    assert (
        traffic.operation("GET", "/b?tagging", {}, b"", "s3", bucket="b") == "GetBucketTagging"
    )
    assert (
        traffic.operation("PUT", "/b/k?partNumber=2&uploadId=1", {}, b"", "s3", bucket="b", key="k")
        == "UploadPart"
    )
    assert (
        traffic.operation("POST", "/b/k?uploads", {}, b"", "s3", bucket="b", key="k")
        == "CreateMultipartUpload"
    )
    assert traffic.operation("GET", "/b", {}, b"", "s3", bucket="b") == "ListObjects"
    assert traffic.operation("PUT", "/b", {}, b"", "s3", bucket="b") == "CreateBucket"
    assert traffic.operation("DELETE", "/b/k", {}, b"", "s3", bucket="b", key="k") == "DeleteObject"
    assert traffic.operation("GET", "/", {}, b"", "s3") == "ListBuckets"


def test_the_ring_buffer_drops_the_oldest_entry():
    log = traffic.TrafficLog(3)
    for number in range(5):
        log.record(
            method="GET",
            path=f"/probe-{number}",
            headers={},
            body=b"",
            service="s3",
            account="",
            region="us-east-1",
            status=200,
            duration_ms=1,
            request_bytes=0,
            response_bytes=0,
        )
    entries, latest = log.page(limit=10)
    assert latest == 5
    assert [item["path"] for item in entries] == ["/probe-4", "/probe-3", "/probe-2"]
    since, _ = log.page(since=3)
    assert [item["path"] for item in since] == ["/probe-3", "/probe-4"]


def test_a_page_is_newest_first_and_a_since_poll_is_oldest_first():
    log = traffic.TrafficLog(10)
    for number in range(4):
        log.record(
            method="GET",
            path=f"/page-{number}",
            headers={},
            body=b"",
            service="s3",
            account=ACCOUNT if number < 2 else OTHER,
            region="us-east-1",
            status=200 if number < 3 else 500,
            duration_ms=1,
            request_bytes=0,
            response_bytes=0,
        )
    newest, _ = log.page(limit=2)
    assert [item["path"] for item in newest] == ["/page-3", "/page-2"]
    older, _ = log.page(before=3, limit=2)
    assert [item["path"] for item in older] == ["/page-1", "/page-0"]
    mine, _ = log.page(account=ACCOUNT)
    assert [item["path"] for item in mine] == ["/page-1", "/page-0"]
    errors, _ = log.page(status="5xx")
    assert [item["path"] for item in errors] == ["/page-3"]


def test_a_session_reads_only_its_own_accounts_traffic(console, control):
    # A console login carries one account; only the deployment token sees across tenants.
    token = control.new_session("other", OTHER, "root")
    connection = http.client.HTTPConnection(console, timeout=15)
    try:
        connection.request(
            "GET",
            "/api/traffic?limit=500",
            headers={"Cookie": f"emuplane_session={token}"},
        )
        response = connection.getresponse()
        answer = json.loads(response.read().decode() or "{}")
    finally:
        connection.close()
    assert response.status == 200
    # The probes above belong to ACCOUNT, so this session must not see any of them.
    assert all(row["account"] == OTHER for row in answer["entries"])
    assert not any(row["path"].startswith("/inspector-probe") for row in answer["entries"])
