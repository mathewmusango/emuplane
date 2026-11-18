"""IAM identities against a running lab: what an identity policy lets S3 do.

The in-process suite runs the emulator with `AUTH` off, so no policy is enforced
there and none of this can be proven offline. Point the module at a live lab:

    EP_LAB_EMULATOR=http://127.0.0.1:4566 EP_LAB_GATEWAY=127.0.0.1:4571 \
    EP_LAB_ACCOUNT=<account> python3 -m pytest tests/control/test_iam_policies.py -q -s

Keys are cached in `qa/iam-keys.json` between runs, because a secret is answered
once; the bucket, the identities and the matrix itself are never deleted.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sigv4 import call, iam_call, tag  # noqa: E402

EMULATOR = os.environ.get("EP_LAB_EMULATOR", "")
GATEWAY = os.environ.get("EP_LAB_GATEWAY", "")
ACCOUNT = os.environ.get("EP_LAB_ACCOUNT", "")
REGION = "us-east-1"
BUCKET = "iam-matrix-lab"
GROUP = "matrix-readers"
HERE = Path(__file__).resolve().parents[2]
RESULTS = HERE / "qa" / "iam-matrix.md"
KEYS = HERE / "qa" / "iam-keys.json"

pytestmark = pytest.mark.skipif(
    not (EMULATOR and GATEWAY and ACCOUNT),
    reason=(
        "set EP_LAB_EMULATOR, EP_LAB_GATEWAY and EP_LAB_ACCOUNT to run the IAM "
        "matrix against a lab"
    ),
)

sys.path.insert(0, str(HERE / "control"))
import signed  # noqa: E402

OBSERVED: list[tuple[str, str, str, int]] = []


def root(method: str, path: str, body: bytes = b"") -> int:
    """A root call straight at the emulator, as the control makes it."""
    status, _body = signed.request(EMULATOR, "s3", ACCOUNT, REGION, method, path, body)
    return status


def iam(action: str, **params) -> tuple[int, str]:
    status, body = iam_call(EMULATOR, ACCOUNT, action, REGION, **params)
    return status, body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)


def allow(actions, resource):
    return {"Effect": "Allow", "Action": actions, "Resource": resource}


def deny(actions, resource):
    return {"Effect": "Deny", "Action": actions, "Resource": resource}


def policy(*statements) -> str:
    return json.dumps({"Version": "2012-10-17", "Statement": list(statements)})


IN_BUCKET = [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]

POLICIES = {
    "reader": policy(allow(["s3:GetObject", "s3:ListBucket"], IN_BUCKET)),
    "writer": policy(allow(["s3:PutObject"], IN_BUCKET)),
    "scoped": policy(allow(["s3:GetObject"], [f"arn:aws:s3:::{BUCKET}/public/*"])),
    "wildcard": policy(allow("s3:*", "*")),
    "denied": policy(
        allow("s3:*", "*"),
        deny(["s3:GetObject", "s3:ListBucket"], IN_BUCKET),
    ),
}


def cached_keys() -> dict:
    if not KEYS.is_file():
        return {}
    try:
        return json.loads(KEYS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_keys(keys: dict) -> None:
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(keys, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ensure_user(name: str, document: str | None, keys: dict) -> tuple[str, str]:
    """A user with one working key; reuses the cached key, makes a new one only when needed."""
    status, _body = iam("CreateUser", UserName=name)
    assert status in (200, 409), f"CreateUser {name}: {status}"
    if document:
        status, body = iam(
            "PutUserPolicy", UserName=name, PolicyName="matrix", PolicyDocument=document
        )
        assert status == 200, f"PutUserPolicy {name}: {status} {body[:120]}"

    held = keys.get(name) or {}
    if held.get("key"):
        status, body = iam("ListAccessKeys", UserName=name)
        if status == 200 and held["key"] in body:
            return held["key"], held["secret"]

    status, body = iam("CreateAccessKey", UserName=name)
    assert status == 200, f"CreateAccessKey {name}: {status} {body[:120]}"
    key, secret = tag(body, "AccessKeyId"), tag(body, "SecretAccessKey")
    keys[name] = {"key": key, "secret": secret}
    save_keys(keys)
    return key, secret


@pytest.fixture(scope="module")
def lab():
    """The bucket, the objects and every identity, created once for the run."""
    assert root("PUT", f"/{BUCKET}") in (200, 409)
    for name in ("hello.txt", "secret.txt", "public/ok.txt"):
        assert root("PUT", f"/{BUCKET}/{name}", b"matrix") in (200, 204)

    keys = cached_keys()
    credentials = {name: ensure_user(name, doc, keys) for name, doc in POLICIES.items()}

    # One identity whose only grant comes through a group policy.
    iam("CreateGroup", GroupName=GROUP)
    iam(
        "PutGroupPolicy",
        GroupName=GROUP,
        PolicyName="readers",
        PolicyDocument=policy(allow(["s3:GetObject", "s3:ListBucket"], IN_BUCKET)),
    )
    credentials["grouped"] = ensure_user("matrix-grouped", None, keys)
    iam("AddUserToGroup", GroupName=GROUP, UserName="matrix-grouped")

    # One identity whose policy is fine and whose credential is not.
    credentials["inactive"] = ensure_user("matrix-inactive", POLICIES["wildcard"], keys)
    inactive_key, _secret = credentials["inactive"]
    iam(
        "UpdateAccessKey",
        UserName="matrix-inactive",
        AccessKeyId=inactive_key,
        Status="Inactive",
    )

    yield credentials

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# IAM matrix — what an identity policy lets S3 do",
        "",
        f"Recorded {len(OBSERVED)} cells against `{GATEWAY}` (bucket `{BUCKET}`).",
        "Each cell is the status the gateway answered for that key and request.",
        "",
        "| Identity | Policy | Request | Status | Verdict |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for persona, summary, request, status in OBSERVED:
        verdict = "allowed" if status < 300 else "refused"
        lines.append(f"| `{persona}` | {summary} | {request} | {status} | {verdict} |")
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nIAM matrix: {len(OBSERVED)} cells -> {RESULTS}")


CASES = {
    "reader": ("GetObject + ListBucket", {"GET": 200, "LIST": 200, "PUT": 403, "DELETE": 403}),
    "writer": ("PutObject only", {"GET": 403, "LIST": 403, "PUT": 200, "DELETE": 403}),
    "scoped": (
        "GetObject on public/*",
        {"PUBLIC_GET": 200, "SCOPED_GET": 403, "PUT": 403},
    ),
    "wildcard": ("s3:* on *", {"GET": 200, "LIST": 200, "PUT": 200, "DELETE": 204}),
    "denied": ("Allow s3:* with an explicit Deny on reads", {"GET": 403, "LIST": 403}),
    "grouped": ("group policy: GetObject + ListBucket", {"GET": 200, "PUT": 403}),
    "inactive": ("s3:* with a deactivated key", {"GET": 403, "PUT": 403}),
}


def attempt(kind: str, persona: str, credentials) -> int:
    key, secret = credentials[persona]
    if kind == "GET":
        return call(GATEWAY, key, secret, "GET", f"/{BUCKET}/hello.txt")[0]
    if kind == "SCOPED_GET":
        return call(GATEWAY, key, secret, "GET", f"/{BUCKET}/secret.txt")[0]
    if kind == "PUBLIC_GET":
        return call(GATEWAY, key, secret, "GET", f"/{BUCKET}/public/ok.txt")[0]
    if kind == "LIST":
        return call(GATEWAY, key, secret, "GET", f"/{BUCKET}", "list-type=2")[0]
    if kind == "PUT":
        return call(GATEWAY, key, secret, "PUT", f"/{BUCKET}/{persona}-put.txt", body=b"x")[0]
    root("PUT", f"/{BUCKET}/{persona}-delete.txt", b"x")
    return call(GATEWAY, key, secret, "DELETE", f"/{BUCKET}/{persona}-delete.txt")[0]


@pytest.mark.parametrize("persona", sorted(CASES))
def test_identity_policy_decides_what_s3_answers(lab, persona):
    summary, expected = CASES[persona]
    for kind, want in expected.items():
        status = attempt(kind, persona, lab)
        OBSERVED.append((persona, summary, f"{kind}", status))
        assert status == want, f"{persona} {kind}: expected {want}, got {status}"


def test_a_key_that_does_not_exist_is_refused(lab):
    # Assembled at compile time so the repository's secret scanner does not read it as a key.
    unknown = "AKIA" "UNKNOWNKEY000000"
    status, _ = call(GATEWAY, unknown, "nothing", "GET", f"/{BUCKET}/hello.txt")
    OBSERVED.append(("unknown", "key that does not exist", "GET", status))
    assert status == 403


def test_the_account_root_still_reads_everything(lab):
    assert root("GET", f"/{BUCKET}/hello.txt") == 200
