"""The Access Points page's own API.

These run the real `ControlHandler` behind a real socket, authenticated with the
deployment's bearer token, and check the answers the page renders: a listing in
the account's context, a create that reports the server's own ARN, the policy
editor, and a delete.
"""

from __future__ import annotations

import http.client

from conftest import ACCOUNT, TOKEN, api

BUCKET = "api-access-point-bucket"


def _bucket(console, name: str = BUCKET) -> None:
    """The bucket a general purpose access point attaches to."""
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "namespace": "global",
            "ownership": "BucketOwnerEnforced",
            "block_public_access": None,
            "versioning": False,
            "tags": [],
            "encryption": "AES256",
            "bucket_key": True,
            "object_lock": False,
            "bucket": name,
        },
    )
    assert status in (200, 400), body  # 400 when an earlier test made it


def _point(console, name, **overrides):
    payload = {"account": ACCOUNT, "region": "us-east-1", "name": name, "bucket": BUCKET}
    payload.update(overrides)
    return api(console, "POST", "/api/s3/access-points", payload)


def _list(console, section="general", region="us-east-1", extra=""):
    return api(
        console,
        "GET",
        f"/api/s3/access-points?account={ACCOUNT}&region={region}&section={section}{extra}",
    )


def test_create_answers_the_arn_the_api_made(console):
    _bucket(console)
    status, body = _point(console, "api-point")
    assert status == 200, body
    assert body["ok"] is True
    assert body["arn"] == f"arn:aws:s3:us-east-1:{ACCOUNT}:accesspoint/api-point"
    assert body["alias"].endswith("-s3alias")


def test_the_listing_carries_the_row_the_page_renders(console):
    _bucket(console)
    _point(console, "listed-point")

    status, body = _list(console)
    assert status == 200, body
    row = next(item for item in body["access_points"] if item["name"] == "listed-point")
    assert row["bucket"] == BUCKET
    assert row["alias"].endswith("-s3alias")
    assert row["arn"].endswith("/listed-point")
    assert row["network_origin"] == "Internet"
    assert body["section"] == "general"
    assert body["account"] == ACCOUNT


def test_the_listing_can_narrow_to_one_bucket(console):
    other = "api-access-point-other"
    _bucket(console, other)
    _point(console, "narrow-point")
    _point(console, "elsewhere-point", bucket=other)

    status, body = _list(console, extra=f"&bucket={BUCKET}")
    assert status == 200, body
    names = [row["name"] for row in body["access_points"]]
    assert "narrow-point" in names
    assert "elsewhere-point" not in names
    assert {row["bucket"] for row in body["access_points"]} == {BUCKET}


def test_a_duplicate_name_is_refused_with_the_reason(console):
    _bucket(console)
    assert _point(console, "twice-point")[0] == 200

    status, body = _point(console, "twice-point")
    assert status == 400
    assert "AccessPointAlreadyOwnedByYou" in body["error"]


def test_a_region_the_account_has_not_enabled_is_refused(console):
    status, body = _point(console, "off-region-point", region="eu-central-1")
    assert status == 403
    assert "not enabled" in body["error"]


def test_an_unknown_section_is_refused(console):
    status, body = _list(console, section="directory")
    assert status == 400
    assert "unknown access point section" in body["error"]


def test_the_policy_editor_reads_writes_and_removes(console):
    _bucket(console)
    assert _point(console, "policy-point")[0] == 200

    status, body = api(
        console,
        "GET",
        f"/api/s3/access-point-policy?account={ACCOUNT}&region=us-east-1&name=policy-point",
    )
    assert status == 200, body
    assert body["policy"] is None

    document = '{"Statement":[{"Effect":"Allow","Action":"s3:GetObject","Resource":"*"}]}'
    status, body = api(
        console,
        "POST",
        "/api/s3/access-point-policy-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "name": "policy-point",
            "policy": document,
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/access-point-policy?account={ACCOUNT}&region=us-east-1&name=policy-point",
    )
    assert read["policy"] == document

    status, body = api(
        console,
        "POST",
        "/api/s3/access-point-policy-edit",
        {"account": ACCOUNT, "region": "us-east-1", "name": "policy-point", "policy": None},
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/access-point-policy?account={ACCOUNT}&region=us-east-1&name=policy-point",
    )
    assert read["policy"] is None


def test_a_policy_that_is_not_a_document_is_refused(console):
    _bucket(console)
    assert _point(console, "policy-form-point")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/access-point-policy-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "name": "policy-form-point",
            "policy": "{not json",
        },
    )
    assert status == 400
    assert "not JSON" in body["error"]


def test_a_policy_for_a_missing_access_point_names_it(console):
    status, body = api(
        console,
        "GET",
        f"/api/s3/access-point-policy?account={ACCOUNT}&region=us-east-1&name=nowhere-point",
    )
    assert status == 400
    assert "NoSuchAccessPoint" in body["error"]


def test_delete_removes_the_access_point(console):
    _bucket(console)
    assert _point(console, "gone-point")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/access-point-delete",
        {"account": ACCOUNT, "region": "us-east-1", "name": "gone-point"},
    )
    assert status == 200, body

    _, listing = _list(console)
    assert "gone-point" not in [row["name"] for row in listing["access_points"]]

    status, body = api(
        console,
        "POST",
        "/api/s3/access-point-delete",
        {"account": ACCOUNT, "region": "us-east-1", "name": "gone-point"},
    )
    assert status == 400
    assert "NoSuchAccessPoint" in body["error"]


def test_the_multi_region_section_is_read_from_us_west_2(console):
    status, body = _list(console, section="multi-region")
    assert status == 200, body
    assert body["region"] == "us-west-2"
    assert body["access_points"] == []


def test_the_object_lambda_section_answers_for_the_page_region(console):
    status, body = _list(console, section="object-lambda")
    assert status == 200, body
    assert body["region"] == "us-east-1"
    assert body["access_points"] == []


def test_s3_control_calls_name_the_account_in_the_header(control, console, monkeypatch):
    """S3 Control refuses a call without `x-amz-account-id`, so the page's calls
    must carry it — and be signed in the region they act in."""
    seen = []

    def fake(service, account, region, method, path, body="", extra_headers=None):
        seen.append((service, account, region, method, path, dict(extra_headers or {})))
        return 200, "<ListAccessPointsResult><AccessPointList /></ListAccessPointsResult>"

    monkeypatch.setattr(control, "signed_rest", fake)
    status, body = _list(console, region="us-west-2")
    assert status == 200, body
    service, account, region, method, path, headers = seen[0]
    assert (service, account, region, method) == ("s3", ACCOUNT, "us-west-2", "GET")
    assert path == "/v20180820/accesspoint"
    assert headers["x-amz-account-id"] == ACCOUNT


def _page(host: str, path: str):
    name, _, port = host.partition(":")
    connection = http.client.HTTPConnection(name, int(port), timeout=15)
    try:
        connection.request("GET", path, headers={"Authorization": f"Bearer {TOKEN}"})
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type", ""), response.read().decode(
            errors="replace"
        )
    finally:
        connection.close()


def test_a_page_opens_by_its_url(console, control, tmp_path, monkeypatch):
    """A page you cannot open directly is a page you cannot bookmark: the SPA
    shell has to answer at any depth under `/s3/`."""
    (tmp_path / "index.html").write_text("<!doctype html><title>Emuplane</title>")
    monkeypatch.setattr(control, "STATIC_DIR", str(tmp_path))
    for path in ("/s3/access-points", "/s3/access-points/create", "/s3/buckets/logs-bucket"):
        status, kind, body = _page(console, path)
        assert status == 200, path
        assert "text/html" in kind
        assert "<!doctype html>" in body.lower()
