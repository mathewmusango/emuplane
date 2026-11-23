"""The console's user routes: creating a user materialises its IAM identity, deleting removes both sides."""

from __future__ import annotations

import json

from conftest import ACCOUNT, api

PASSWORD = "long-enough-password"


def create(console, name: str):
    return api(
        console,
        "POST",
        "/api/users",
        {"username": name, "password": PASSWORD, "account": ACCOUNT},
    )


def iam_users(console) -> list[str]:
    status, body = api(
        console,
        "GET",
        f"/api/browse?account={ACCOUNT}&region=us-east-1&service=iam",
    )
    assert status == 200, body
    return [row["name"] for row in body.get("resources", []) if row["kind"] == "user"]


def exec_iam(console, operation: str, params: dict):
    return api(
        console,
        "POST",
        "/api/exec",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "service": "iam",
            "operation": operation,
            "params": params,
        },
    )


def test_creating_a_user_creates_its_iam_identity(console):
    """The console page lists IAM users, so a console principal must exist in IAM as well."""
    status, body = create(console, "ui-created-user")
    assert status == 200, body
    assert "ui-created-user" in iam_users(console)

    status, body = create(console, "ui-created-user")
    assert status == 409, body


def test_deleting_a_user_clears_its_keys_and_policies(console):
    """DeleteUser is refused while a key or policy remains, so a 200 proves the purge ran."""
    assert create(console, "ui-deleted-user")[0] == 200

    policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}],
    }
    status, body = exec_iam(
        console,
        "create-policy",
        {"PolicyName": "ui-delete-policy", "PolicyDocument": json.dumps(policy)},
    )
    assert status == 200, body
    status, body = exec_iam(
        console,
        "attach-user-policy",
        {
            "UserName": "ui-deleted-user",
            "PolicyArn": f"arn:aws:iam::{ACCOUNT}:policy/ui-delete-policy",
        },
    )
    assert status == 200, body
    status, body = exec_iam(console, "create-access-key", {"UserName": "ui-deleted-user"})
    assert status == 200, body

    status, body = api(
        console, "DELETE", f"/api/users/ui-deleted-user?account={ACCOUNT}"
    )
    assert status == 200, body
    assert "ui-deleted-user" not in iam_users(console)

    status, body = api(console, "GET", "/api/users")
    assert status == 200, body
    names = {
        user["username"]
        for account in body
        if account["account_id"] == ACCOUNT
        for user in account["users"]
    }
    assert "ui-deleted-user" not in names


def test_the_root_and_unknown_users_cannot_be_deleted(console):
    """The account root is the tenancy itself, not an identity to remove."""
    status, body = api(console, "DELETE", f"/api/users/root?account={ACCOUNT}")
    assert status == 400, body
    assert "root cannot be deleted" in body["error"]

    status, body = api(
        console, "DELETE", f"/api/users/nobody-here?account={ACCOUNT}"
    )
    assert status == 404, body
