"""STS on the wire: each operation the emulator advertises, plus the two it implements off its list."""

from __future__ import annotations

import base64
import http.client
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2011-06-15"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/sts-test-role"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def call(endpoint, action: str, key: str = ACCOUNT, **params):
    """One STS query-protocol call, signed with a credential name the emulator resolves."""
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "sts", key, REGION, "POST", "/", body, FORM)


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]+)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:300]}"
    return match.group(1)


def expires_in(text: str) -> float:
    stamp = datetime.strptime(field(text, "Expiration"), "%Y-%m-%dT%H:%M:%SZ")
    return (stamp.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()


def test_get_caller_identity_names_the_credential(endpoint):
    """The account is the key's, not the region's: this is how a tool checks where it landed."""
    status, text = call(endpoint, "GetCallerIdentity")

    assert status == 200, text
    assert field(text, "Account") == ACCOUNT
    assert field(text, "Arn") == f"arn:aws:iam::{ACCOUNT}:root"
    assert field(text, "UserId") == ACCOUNT


def test_assume_role_issues_a_session_that_resolves_as_the_role(endpoint):
    """The response is half the contract; the key it hands back must resolve to the role it named."""
    status, text = call(
        endpoint,
        "AssumeRole",
        RoleArn=ROLE_ARN,
        RoleSessionName="session-one",
        DurationSeconds=900,
    )

    assert status == 200, text
    key = field(text, "AccessKeyId")
    assert key.startswith("ASIA")
    assert field(text, "SessionToken")
    assert field(text, "Arn") == (
        f"arn:aws:sts::{ACCOUNT}:assumed-role/sts-test-role/session-one"
    )
    assert field(text, "AssumedRoleId").endswith(":session-one")
    assert 800 < expires_in(text) <= 900

    status, who = call(endpoint, "GetCallerIdentity", key=key)
    assert status == 200, who
    assert field(who, "Arn") == (
        f"arn:aws:sts::{ACCOUNT}:assumed-role/sts-test-role/session-one"
    )


def test_assume_role_refuses_a_role_arn_it_cannot_parse(endpoint):
    """AWS validates the ARN shape before the role exists, so a typo is a 400, not a 403."""
    status, text = call(
        endpoint,
        "AssumeRole",
        RoleArn="arn:aws:s3:::not-a-role",
        RoleSessionName="session-one",
    )

    assert status == 400, text
    assert "Invalid RoleArn" in text


def test_get_session_token_issues_temporary_credentials_for_the_caller(endpoint):
    """No role is assumed: the session inherits the key it was minted from."""
    status, text = call(endpoint, "GetSessionToken", DurationSeconds=900)

    assert status == 200, text
    key = field(text, "AccessKeyId")
    assert key.startswith("ASIA")
    assert 800 < expires_in(text) <= 900

    status, who = call(endpoint, "GetCallerIdentity", key=key)
    assert status == 200, who
    assert field(who, "Arn") == f"arn:aws:iam::{ACCOUNT}:root"


def test_get_federation_token_names_a_federated_user(endpoint):
    """A federated user is its own principal: the name is in the ARN, and the key resolves to it."""
    status, text = call(
        endpoint, "GetFederationToken", Name="sts-federated", DurationSeconds=900
    )

    assert status == 200, text
    assert field(text, "Arn") == (
        f"arn:aws:sts::{ACCOUNT}:federated-user/sts-federated"
    )
    assert field(text, "FederatedUserId") == f"{ACCOUNT}:sts-federated"
    assert field(text, "AccessKeyId").startswith("ASIA")

    status, who = call(endpoint, "GetCallerIdentity", key=field(text, "AccessKeyId"))
    assert status == 200, who
    assert field(who, "Arn") == (
        f"arn:aws:sts::{ACCOUNT}:federated-user/sts-federated"
    )


def test_get_federation_token_refuses_an_invalid_name(endpoint):
    """The name is the identity, so AWS's length bounds are the only thing standing between two callers."""
    status, text = call(endpoint, "GetFederationToken")
    assert status == 400, text
    assert "Member must not be null" in text

    status, text = call(endpoint, "GetFederationToken", Name="x")
    assert status == 400, text
    assert "greater than or equal to 2" in text


def test_assume_role_with_web_identity_issues_a_session(endpoint):
    """The token's trust policy is decided with AUTH on (the lab matrix carries that); here the session shape is pinned."""
    status, text = call(
        endpoint,
        "AssumeRoleWithWebIdentity",
        RoleArn=ROLE_ARN,
        RoleSessionName="web-session",
        WebIdentityToken="header.payload.signature",
    )

    assert status == 200, text
    assert field(text, "Arn") == (
        f"arn:aws:sts::{ACCOUNT}:assumed-role/sts-test-role/web-session"
    )
    assert field(text, "SubjectFromWebIdentityToken") == "test-subject"
    assert field(text, "Audience") == "sts.amazonaws.com"
    assert field(text, "AccessKeyId").startswith("ASIA")


def test_the_gateway_forwards_sts_for_the_signed_key(gateway):
    """Emuplane's own door: a CLI pointed at the gateway gets the account its key belongs to."""
    body = urlencode({"Action": "GetCallerIdentity", "Version": VERSION}).encode()
    headers = {
        "Host": gateway,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={ACCOUNT}/20261121/{REGION}/sts"
            "/aws4_request, SignedHeaders=host, Signature=test"
        ),
        "x-amz-date": "20261121T120000Z",
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
    }
    host, port = gateway.split(":")
    connection = http.client.HTTPConnection(host, int(port), timeout=15)
    try:
        connection.request("POST", "/", body=body, headers=headers)
        response = connection.getresponse()
        status, text = response.status, response.read().decode(errors="replace")
    finally:
        connection.close()

    assert status == 200, text
    assert f"<Account>{ACCOUNT}</Account>" in text


def test_get_access_key_info_validates_the_key_id(endpoint):
    """Off the advertised list, but it is in the module: a short key is a 400 with AWS's constraint text."""
    status, text = call(endpoint, "GetAccessKeyInfo", AccessKeyId="ABC")

    assert status == 400, text
    assert "greater than or equal to 16" in text


def test_get_web_identity_token_signs_a_token_for_the_audience(endpoint):
    """Also off the advertised list: the token it mints is a JWT whose claims name the request."""
    status, text = call(
        endpoint,
        "GetWebIdentityToken",
        SigningAlgorithm="RS256",
        **{"Audience.member.1": "https://example.test"},
    )

    assert status == 200, text
    token = field(text, "WebIdentityToken")
    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert claims["aud"] == "https://example.test"
    assert claims["iss"] == "https://sts.amazonaws.com"

    status, text = call(
        endpoint,
        "GetWebIdentityToken",
        **{"Audience.member.1": "https://example.test"},
    )
    assert status == 400, text
    assert "MissingParameter" in text
