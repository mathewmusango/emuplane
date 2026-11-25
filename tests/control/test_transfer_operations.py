"""AWS Transfer Family on the wire: every advertised operation, driven through the JSON protocol.

The control plane only. The emulator also binds an SFTP listener on :2222, and nothing here
reaches it, depends on it being reachable, or proves the data plane works.

Servers and users created here are left in place: a server is found again by a stable `Name`
tag (ListServers carries none, so each listed server is described), and a user by its
(server, user name) key. The two delete actions create what they remove and remove only that,
so a second sweep over the same lab passes over the first sweep's footprint.

ImportSshPublicKey is the one create with no create-or-find: the key is minted at runtime,
so a sweep cannot recognise an earlier sweep's body and imports one more key. The test asserts
the key it imported is read back, and nothing counts keys exactly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest
import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "Transfer."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

# Stable names, so a sweep that re-runs finds instead of conflicting.
TAG_KEY = "Name"
SHARED = "ops-transfer-shared"
CREATED = "ops-transfer-created"
DELETED = "ops-transfer-deleted"

SHARED_USER = "ops-transfer-shared-user"
CREATED_USER = "ops-transfer-created-user"
DELETED_USER = "ops-transfer-deleted-user"
CASCADED_USER = "ops-transfer-cascaded-user"
DOOMED_KEY_USER = "ops-transfer-key-user"

BUCKET = "ops-transfer-bucket"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/ops-transfer-role"


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "transfer", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def server_body(name: str) -> dict:
    """What CreateServer is given: the tag is the address a later sweep looks the server up by."""
    return {
        "Domain": "S3",
        "EndpointType": "PUBLIC",
        "IdentityProviderType": "SERVICE_MANAGED",
        "Protocols": ["SFTP"],
        "IpAddressType": "IPV4",
        "Tags": [{"Key": TAG_KEY, "Value": name}],
    }


def user_body() -> dict:
    """A logical home directory: a mapping plus a role, which is what the API requires of it."""
    return {
        "HomeDirectoryType": "LOGICAL",
        "HomeDirectoryMappings": [{"Entry": "/", "Target": f"/{BUCKET}"}],
        "Role": ROLE,
        "Tags": [{"Key": "owner", "Value": "emuplane"}],
    }


def servers(endpoint) -> list[dict]:
    """Every page of ListServers: a lab may hold more than one page of them."""
    found: list[dict] = []
    params = {"MaxResults": 1000}
    while True:
        answer = ok(endpoint, "ListServers", **params)
        found.extend(answer["Servers"])
        token = answer.get("NextToken")
        if not token:
            return found
        params = {"MaxResults": 1000, "NextToken": token}


def server_named(endpoint, name: str) -> str | None:
    """The server carrying the stable tag, or None: the summaries carry no tags, so each is described."""
    for row in servers(endpoint):
        status, text = call(endpoint, "DescribeServer", ServerId=row["ServerId"])
        if status != 200:  # a server another sweep removed between the list and the describe
            continue
        tags = json.loads(text)["Server"].get("Tags", [])
        if {"Key": TAG_KEY, "Value": name} in tags:
            return row["ServerId"]
    return None


def ensure_server(endpoint, name: str) -> str:
    """Find-or-create. The emulator has no server-name uniqueness, so two sweeps racing may
    each create one; the tag still finds a server either way."""
    found = server_named(endpoint, name)
    if found:
        return found
    return ok(endpoint, "CreateServer", **server_body(name))["ServerId"]


def described_server(endpoint, server_id: str) -> dict:
    return ok(endpoint, "DescribeServer", ServerId=server_id)["Server"]


def users(endpoint, server_id: str) -> list[dict]:
    return ok(endpoint, "ListUsers", ServerId=server_id)["Users"]


def ensure_user(endpoint, server_id: str, user_name: str) -> None:
    """Find-or-create on the (server, user name) key a re-run meets its own user by."""
    if user_name in [row["UserName"] for row in users(endpoint, server_id)]:
        return
    status, text = call(
        endpoint, "CreateUser", ServerId=server_id, UserName=user_name, **user_body()
    )
    assert status == 200 or "ResourceExistsException" in text, (
        f"CreateUser answered {status}: {text[:400]}"
    )


def described_user(endpoint, server_id: str, user_name: str) -> dict:
    return ok(endpoint, "DescribeUser", ServerId=server_id, UserName=user_name)["User"]


@lru_cache(maxsize=None)
def public_key(label: str) -> str:
    """A real ed25519 public line, minted by ssh-keygen in a throwaway directory.

    Only the public half leaves the directory and the key file goes with it: the API takes a
    public key and nothing else, so no private material is needed, kept, or written down here.
    """
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        pytest.skip("ssh-keygen is not installed to mint an SSH public key")
    with tempfile.TemporaryDirectory(prefix="ops-transfer-") as tmp:
        path = Path(tmp) / label
        subprocess.run(
            [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-C", label, "-f", str(path)],
            check=True,
            capture_output=True,
        )
        minted = subprocess.run(
            [ssh_keygen, "-y", "-f", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    return minted.stdout.strip()


# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------


def test_create_server_is_read_back_by_describe(s3_endpoint):
    # A re-run finds the server the first sweep created rather than creating a second one.
    server_id = server_named(s3_endpoint, CREATED)
    if server_id is None:
        answer = ok(s3_endpoint, "CreateServer", **server_body(CREATED))
        assert set(answer) == {"ServerId"}
        server_id = answer["ServerId"]
        assert server_id.startswith("s-")

    described = described_server(s3_endpoint, server_id)
    assert described["ServerId"] == server_id
    assert described["Arn"] == f"arn:aws:transfer:{REGION}:{ACCOUNT}:server/{server_id}"
    assert {"Key": TAG_KEY, "Value": CREATED} in described["Tags"]


def test_describe_server_reports_the_configuration_it_was_created_with(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    described = described_server(s3_endpoint, shared)
    assert described["Domain"] == "S3"
    assert described["EndpointType"] == "PUBLIC"
    assert described["IdentityProviderType"] == "SERVICE_MANAGED"
    assert described["Protocols"] == ["SFTP"]
    assert described["IpAddressType"] == "IPV4"
    assert described["State"] == "ONLINE"
    assert isinstance(described["UserCount"], int)
    assert {"Key": TAG_KEY, "Value": SHARED} in described["Tags"]


def test_describe_server_answers_not_found_for_an_unknown_server(s3_endpoint):
    status, text = call(s3_endpoint, "DescribeServer", ServerId="s-00000000000000000")
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_list_servers_summarises_the_shared_server(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, SHARED_USER)
    row = next(row for row in servers(s3_endpoint) if row["ServerId"] == shared)
    assert row["Arn"] == f"arn:aws:transfer:{REGION}:{ACCOUNT}:server/{shared}"
    assert row["Domain"] == "S3"
    assert row["EndpointType"] == "PUBLIC"
    assert row["IdentityProviderType"] == "SERVICE_MANAGED"
    assert row["State"] == "ONLINE"
    assert row["UserCount"] >= 1


def test_list_servers_bounds_a_page_and_offers_a_token(s3_endpoint):
    """The page contract only. v1.5.40 sets NextToken to the next page's first ServerId and
    resumes *after* that id, so the boundary row is never returned; following the token to the
    end would assert that off-by-one rather than the API, so this stops at the first page."""
    wanted = {ensure_server(s3_endpoint, SHARED), ensure_server(s3_endpoint, CREATED)}
    first = ok(s3_endpoint, "ListServers", MaxResults=1)
    assert len(first["Servers"]) == 1
    assert first["NextToken"]
    assert wanted <= {row["ServerId"] for row in servers(s3_endpoint)}


def test_stop_server_takes_the_shared_server_offline(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ok(s3_endpoint, "StartServer", ServerId=shared)
    assert described_server(s3_endpoint, shared)["State"] == "ONLINE"
    assert ok(s3_endpoint, "StopServer", ServerId=shared) == {}
    assert described_server(s3_endpoint, shared)["State"] == "OFFLINE"
    # Leave the shared server as the first sweep found it.
    ok(s3_endpoint, "StartServer", ServerId=shared)


def test_start_server_brings_the_shared_server_online(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ok(s3_endpoint, "StopServer", ServerId=shared)
    assert ok(s3_endpoint, "StartServer", ServerId=shared) == {}
    assert described_server(s3_endpoint, shared)["State"] == "ONLINE"


def test_start_and_stop_answer_not_found_for_an_unknown_server(s3_endpoint):
    for action in ("StartServer", "StopServer"):
        status, text = call(s3_endpoint, action, ServerId="s-00000000000000000")
        assert status == 400, text[:300]
        assert "ResourceNotFoundException" in text


def test_delete_server_removes_the_server_it_created(s3_endpoint):
    doomed = ensure_server(s3_endpoint, DELETED)
    ensure_user(s3_endpoint, doomed, CASCADED_USER)
    assert ok(s3_endpoint, "DeleteServer", ServerId=doomed) == {}
    assert doomed not in [row["ServerId"] for row in servers(s3_endpoint)]
    status, text = call(s3_endpoint, "DescribeServer", ServerId=doomed)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text
    # The server's users go with it.
    status, text = call(s3_endpoint, "DescribeUser", ServerId=doomed, UserName=CASCADED_USER)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_create_user_is_read_back_by_describe_user(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, CREATED_USER)
    user = described_user(s3_endpoint, shared, CREATED_USER)
    assert user["UserName"] == CREATED_USER
    assert user["Arn"] == (
        f"arn:aws:transfer:{REGION}:{ACCOUNT}:user/{shared}/{CREATED_USER}"
    )
    assert user["HomeDirectoryType"] == "LOGICAL"
    assert user["HomeDirectoryMappings"] == user_body()["HomeDirectoryMappings"]
    assert user["Role"] == ROLE
    assert {"Key": "owner", "Value": "emuplane"} in user["Tags"]
    assert user["SshPublicKeys"] == []


def test_create_user_refuses_a_duplicate_name(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, CREATED_USER)
    status, text = call(
        s3_endpoint, "CreateUser", ServerId=shared, UserName=CREATED_USER, **user_body()
    )
    assert status == 400, text[:300]
    assert "ResourceExistsException" in text


def test_create_user_rejects_an_invalid_ssh_public_key(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    status, text = call(
        s3_endpoint,
        "CreateUser",
        ServerId=shared,
        UserName="ops-transfer-bad-key",
        SshPublicKeyBody="not-a-public-key",
        **user_body(),
    )
    assert status == 400, text[:300]
    assert "InvalidRequestException" in text
    # The rejected create made no user.
    assert "ops-transfer-bad-key" not in [
        row["UserName"] for row in users(s3_endpoint, shared)
    ]


def test_create_user_answers_not_found_for_an_unknown_server(s3_endpoint):
    status, text = call(
        s3_endpoint,
        "CreateUser",
        ServerId="s-00000000000000000",
        UserName=CREATED_USER,
        **user_body(),
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_describe_user_reports_the_user_shape(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, SHARED_USER)
    answer = ok(s3_endpoint, "DescribeUser", ServerId=shared, UserName=SHARED_USER)
    assert answer["ServerId"] == shared
    user = answer["User"]
    assert user["UserName"] == SHARED_USER
    assert user["HomeDirectoryType"] == "LOGICAL"
    assert user["Role"] == ROLE
    assert "HomeDirectory" not in user  # a logical user addresses its home by mapping


def test_describe_user_answers_not_found_for_an_unknown_user(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    status, text = call(
        s3_endpoint, "DescribeUser", ServerId=shared, UserName="ops-transfer-absent"
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_list_users_lists_the_shared_server_users(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, SHARED_USER)
    ensure_user(s3_endpoint, shared, CREATED_USER)
    listed = users(s3_endpoint, shared)
    names = [row["UserName"] for row in listed]
    assert SHARED_USER in names
    assert CREATED_USER in names
    summary = next(row for row in listed if row["UserName"] == SHARED_USER)
    assert summary["Arn"] == f"arn:aws:transfer:{REGION}:{ACCOUNT}:user/{shared}/{SHARED_USER}"
    assert summary["HomeDirectoryType"] == "LOGICAL"
    assert summary["Role"] == ROLE
    assert isinstance(summary["SshPublicKeyCount"], int)


def test_list_users_bounds_a_page_and_offers_a_token(s3_endpoint):
    """The page contract only: the same NextToken off-by-one as ListServers is the emulator's,
    not the API's, so this does not walk past the first page (see the ListServers test)."""
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, SHARED_USER)
    ensure_user(s3_endpoint, shared, CREATED_USER)
    first = ok(s3_endpoint, "ListUsers", ServerId=shared, MaxResults=1)
    assert first["ServerId"] == shared
    assert len(first["Users"]) == 1
    assert first["NextToken"]


def test_list_users_answers_not_found_for_an_unknown_server(s3_endpoint):
    status, text = call(s3_endpoint, "ListUsers", ServerId="s-00000000000000000")
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_delete_user_removes_the_user_it_created(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, DELETED_USER)
    assert ok(s3_endpoint, "DeleteUser", ServerId=shared, UserName=DELETED_USER) == {}
    assert DELETED_USER not in [row["UserName"] for row in users(s3_endpoint, shared)]
    status, text = call(s3_endpoint, "DescribeUser", ServerId=shared, UserName=DELETED_USER)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


# ---------------------------------------------------------------------------
# SSH public keys
# ---------------------------------------------------------------------------


def test_import_ssh_public_key_is_read_back_by_describe_user(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, SHARED_USER)
    key = public_key("shared")
    assert key.startswith("ssh-ed25519 ")
    answer = ok(
        s3_endpoint,
        "ImportSshPublicKey",
        ServerId=shared,
        UserName=SHARED_USER,
        SshPublicKeyBody=key,
    )
    assert answer["ServerId"] == shared
    assert answer["UserName"] == SHARED_USER
    assert answer["SshPublicKeyId"].startswith("key-")
    keys = described_user(s3_endpoint, shared, SHARED_USER)["SshPublicKeys"]
    entry = next((row for row in keys if row["SshPublicKeyBody"] == key), None)
    assert entry is not None, "the imported key is not on the user"
    assert entry["SshPublicKeyId"] == answer["SshPublicKeyId"]
    assert entry["DateImported"]
    listed = next(row for row in users(s3_endpoint, shared) if row["UserName"] == SHARED_USER)
    assert listed["SshPublicKeyCount"] >= 1


def test_import_ssh_public_key_rejects_an_invalid_body(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, SHARED_USER)
    status, text = call(
        s3_endpoint,
        "ImportSshPublicKey",
        ServerId=shared,
        UserName=SHARED_USER,
        SshPublicKeyBody="not-a-public-key",
    )
    assert status == 400, text[:300]
    assert "InvalidRequestException" in text


def test_import_ssh_public_key_answers_not_found_for_an_unknown_user(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    status, text = call(
        s3_endpoint,
        "ImportSshPublicKey",
        ServerId=shared,
        UserName="ops-transfer-absent",
        SshPublicKeyBody=public_key("shared"),
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_delete_ssh_public_key_removes_the_key_it_imported(s3_endpoint):
    shared = ensure_server(s3_endpoint, SHARED)
    # Its own user, so the shared user's imported key is never a candidate for removal.
    ensure_user(s3_endpoint, shared, DOOMED_KEY_USER)
    key = public_key("doomed")
    imported = ok(
        s3_endpoint,
        "ImportSshPublicKey",
        ServerId=shared,
        UserName=DOOMED_KEY_USER,
        SshPublicKeyBody=key,
    )["SshPublicKeyId"]
    assert ok(
        s3_endpoint,
        "DeleteSshPublicKey",
        ServerId=shared,
        UserName=DOOMED_KEY_USER,
        SshPublicKeyId=imported,
    ) == {}
    remaining = [
        entry["SshPublicKeyId"]
        for entry in described_user(s3_endpoint, shared, DOOMED_KEY_USER)["SshPublicKeys"]
    ]
    assert imported not in remaining
    assert remaining == []
