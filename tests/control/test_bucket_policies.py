"""Bucket policies against identity policies, across two lab accounts.

Same rule as the IAM matrix: the in-process emulator runs with `AUTH` off, so this
needs a live lab and skips without one. Account two is created through the console's
own `/signup` (alias `matrix-two`); the test needs its id:

    EP_LAB_EMULATOR=http://127.0.0.1:4566 EP_LAB_GATEWAY=127.0.0.1:4571 \
    EP_LAB_ACCOUNT=<owner> EP_LAB_ACCOUNT2=<second> \
    python3 -m pytest tests/control/test_bucket_policies.py -q -s

The bucket's policy is set by each test and removed afterwards, so the lab is left
as it was found; the recorded cells stay in `qa/bucket-policy-matrix.md`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sigv4 import call, iam_call, tag  # noqa: E402

EMULATOR = os.environ.get("EP_LAB_EMULATOR", "")
GATEWAY = os.environ.get("EP_LAB_GATEWAY", "")
ACCOUNT = os.environ.get("EP_LAB_ACCOUNT", "")
OTHER = os.environ.get("EP_LAB_ACCOUNT2", "")
REGION = "us-east-1"
BUCKET = "iam-matrix-lab"
CROSS_USER = "xreader"
SAME_USER = "matrix-none"
RESULTS = Path(__file__).resolve().parents[2] / "qa" / "bucket-policy-matrix.md"
KEYS = Path(__file__).resolve().parents[2] / "qa" / "iam-keys.json"

pytestmark = pytest.mark.skipif(
    not (EMULATOR and GATEWAY and ACCOUNT and OTHER),
    reason=(
        "set EP_LAB_EMULATOR, EP_LAB_GATEWAY, EP_LAB_ACCOUNT and EP_LAB_ACCOUNT2 to "
        "run the bucket-policy matrix against a lab"
    ),
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control"))
import signed  # noqa: E402

OBSERVED: list[tuple[str, str, int]] = []


def root(method: str, path: str, body: bytes | str = b"") -> int:
    status, _body = signed.request(EMULATOR, "s3", ACCOUNT, REGION, method, path, body)
    return status


def iam(account: str, action: str, **params) -> tuple[int, str]:
    status, body = iam_call(EMULATOR, account, action, REGION, **params)
    return status, body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)


def cached() -> dict:
    if not KEYS.is_file():
        return {}
    try:
        return json.loads(KEYS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save(keys: dict) -> None:
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(keys, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def key_for(account: str, name: str) -> tuple[str, str]:
    """A user in that account with its key cached; the secret is answered once."""
    iam(account, "CreateUser", UserName=name)
    held = cached()
    if held.get(name, {}).get("key"):
        status, body = iam(account, "ListAccessKeys", UserName=name)
        if status == 200 and held[name]["key"] in body:
            return held[name]["key"], held[name]["secret"]

    status, body = iam(account, "ListAccessKeys", UserName=name)
    for old in re.findall(r"<AccessKeyId>([^<]+)</AccessKeyId>", body):
        iam(account, "DeleteAccessKey", UserName=name, AccessKeyId=old)
    status, body = iam(account, "CreateAccessKey", UserName=name)
    assert status == 200, f"CreateAccessKey {name}: {status} {body[:120]}"
    key, secret = tag(body, "AccessKeyId"), tag(body, "SecretAccessKey")
    held[name] = {"key": key, "secret": secret}
    save(held)
    return key, secret


def set_policy(principal: str | None, actions="s3:GetObject", effect="Allow") -> None:
    """Install (or clear) the bucket policy naming one account root."""
    if principal is None:
        root("DELETE", f"/{BUCKET}?policy")
        return
    document = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": effect,
                    "Principal": {"AWS": principal},
                    "Action": actions,
                    "Resource": [
                        f"arn:aws:s3:::{BUCKET}",
                        f"arn:aws:s3:::{BUCKET}/*",
                    ],
                }
            ],
        }
    )
    assert root("PUT", f"/{BUCKET}?policy", document) in (200, 204)


@pytest.fixture(scope="module")
def lab():
    assert root("PUT", f"/{BUCKET}") in (200, 409)
    assert root("PUT", f"/{BUCKET}/hello.txt", b"matrix") in (200, 204)

    cross_policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{BUCKET}/*"],
                }
            ],
        }
    )
    iam(OTHER, "PutUserPolicy", UserName=CROSS_USER, PolicyName="read", PolicyDocument=cross_policy)
    cross = key_for(OTHER, CROSS_USER)

    # A same-account user with no identity policy at all.
    same = key_for(ACCOUNT, SAME_USER)

    yield {"cross": cross, "same": same}

    set_policy(None)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Bucket policy × identity policy — two accounts",
        "",
        f"Recorded {len(OBSERVED)} cells against `{GATEWAY}` (bucket `{BUCKET}`, "
        f"owner `{ACCOUNT}`, other account `{OTHER}`).",
        "",
        "| Case | Request | Status | Verdict |",
        "| --- | --- | ---: | --- |",
    ]
    for case, request, status in OBSERVED:
        lines.append(f"| {case} | {request} | {status} | {'allowed' if status < 300 else 'refused'} |")
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nBucket-policy matrix: {len(OBSERVED)} cells -> {RESULTS}")


def record(case: str, request: str, status: int) -> int:
    OBSERVED.append((case, request, status))
    return status


def test_cross_account_without_a_bucket_policy_is_refused(lab):
    set_policy(None)
    key, secret = lab["cross"]
    status = record("cross-account, no bucket policy", "GET hello.txt", call(
        GATEWAY, key, secret, "GET", f"/{BUCKET}/hello.txt"
    )[0])
    assert status == 403


def test_a_bucket_policy_naming_the_user_arn_is_not_matched(lab):
    """MiniStack compares the caller's account root ARN, so a user ARN in another account does nothing."""
    set_policy(f"arn:aws:iam::{OTHER}:user/{CROSS_USER}")
    key, secret = lab["cross"]
    status = record("cross-account, policy names the user ARN", "GET hello.txt", call(
        GATEWAY, key, secret, "GET", f"/{BUCKET}/hello.txt"
    )[0])
    assert status == 403


def test_a_bucket_policy_naming_the_account_root_is_honoured(lab):
    set_policy(f"arn:aws:iam::{OTHER}:root")
    key, secret = lab["cross"]
    status = record("cross-account, policy names the account root", "GET hello.txt", call(
        GATEWAY, key, secret, "GET", f"/{BUCKET}/hello.txt"
    )[0])
    assert status == 200


def test_cross_account_also_needs_the_identity_policy_to_allow(lab):
    """The bucket grants GetObject; the user's own policy does not allow PutObject."""
    set_policy(f"arn:aws:iam::{OTHER}:root")
    key, secret = lab["cross"]
    status = record("cross-account, identity policy lacks the action", "PUT x.txt", call(
        GATEWAY, key, secret, "PUT", f"/{BUCKET}/x.txt", body=b"x"
    )[0])
    assert status == 403


def test_a_bucket_policy_deny_beats_a_same_account_identity_allow(lab):
    set_policy(f"arn:aws:iam::{ACCOUNT}:root", actions="s3:PutObject", effect="Deny")
    keys = cached()
    wildcard = keys.get("wildcard") or {}
    if not wildcard.get("key"):
        pytest.skip("the IAM matrix has not run yet, so there is no wildcard user")
    status = record("same account, explicit Deny in the bucket policy", "PUT denied-key.txt", call(
        GATEWAY, wildcard["key"], wildcard["secret"], "PUT", f"/{BUCKET}/denied-key.txt", body=b"x"
    )[0])
    assert status == 403


def test_a_same_account_bucket_policy_naming_the_user_carries_them(lab):
    """In-account, a resource statement naming the user allows on its own."""
    set_policy(f"arn:aws:iam::{ACCOUNT}:user/{SAME_USER}")
    key, secret = lab["same"]
    status = record(
        "same account, no identity policy, bucket policy names the user",
        "GET hello.txt",
        call(GATEWAY, key, secret, "GET", f"/{BUCKET}/hello.txt")[0],
    )
    assert status == 200


def test_a_same_account_policy_naming_only_the_account_delegates(lab):
    """A statement naming only the account root delegates to identity policies, which this user has none of."""
    set_policy(f"arn:aws:iam::{ACCOUNT}:root")
    key, secret = lab["same"]
    status = record(
        "same account, no identity policy, bucket policy names only the account",
        "GET hello.txt",
        call(GATEWAY, key, secret, "GET", f"/{BUCKET}/hello.txt")[0],
    )
    assert status == 403
