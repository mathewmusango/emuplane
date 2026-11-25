"""RDS Data API against a real database container: the batch and the three transactions.

The in-process emulator has no Docker socket, so `_connect` fails and these four
operations cannot run there. On a lab whose emulator can reach a Docker-compatible
socket (see `deployment/docker-podman.md`), an instance really starts its database
container, and each operation is proven by reading its effect back.

The module skips when the instance never reports a container-backed endpoint, so a
lab without the socket is a missing dependant rather than a failure. The instance is
**stopped**, not deleted, when the module finishes: the record stays in the console
and is not respawned on restart. MiniStack 1.5.40's `StopDBInstance` flips the
record only, so a lab that must not leave compute running also stops the container
with the runtime.
"""

from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urlencode

import pytest

import signed
from conftest import ACCOUNT

pytestmark = pytest.mark.skipif(
    not os.environ.get("EP_LAB_EMULATOR"),
    reason="needs a lab whose emulator can start a database container (Docker-compatible socket)",
)

REGION = "us-east-1"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
JSON = {"Content-Type": "application/json"}
SM_HEADERS = {
    "Content-Type": "application/x-amz-json-1.0",
    "X-Amz-Target": "secretsmanager.CreateSecret",
}
RDS_VERSION = "2014-10-31"

INSTANCE = "ops-rds-data-live-db"
SECRET = "ops/rds/data-api-live"
DATABASE = "postgres"
USER = "ops"
PASSWORD = "password"


def rds(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": RDS_VERSION, **params})
    return signed.request(endpoint, "rds", ACCOUNT, REGION, "POST", "/", body, FORM)


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def ensure_instance(endpoint) -> str:
    """Create (or meet) the instance and wait for its container-backed endpoint."""
    status, text = rds(
        endpoint,
        "CreateDBInstance",
        DBInstanceIdentifier=INSTANCE,
        DBInstanceClass="db.t3.micro",
        Engine="postgres",
        AllocatedStorage="20",
        MasterUsername=USER,
        MasterUserPassword=PASSWORD,
    )
    assert status == 200 or "AlreadyExist" in text, f"CreateDBInstance answered {status}: {text[:300]}"
    deadline = time.time() + 120
    while time.time() < deadline:
        status, text = rds(endpoint, "DescribeDBInstances", DBInstanceIdentifier=INSTANCE)
        assert status == 200, text[:300]
        if field(text, "DBInstanceStatus") == "available" and "<Address>" in text:
            return field(text, "DBInstanceArn")
        time.sleep(3)
    pytest.skip("the instance never got a container-backed endpoint (no Docker-compatible socket)")


def ensure_secret(endpoint) -> str:
    value = json.dumps({"username": USER, "password": PASSWORD})
    status, text = signed.request(
        endpoint,
        "secretsmanager",
        ACCOUNT,
        REGION,
        "POST",
        "/",
        json.dumps({"Name": SECRET, "SecretString": value}),
        SM_HEADERS,
    )
    if status == 200:
        return json.loads(text)["ARN"]
    assert "ResourceExists" in text, f"CreateSecret answered {status}: {text[:300]}"
    listed = signed.request(
        endpoint,
        "secretsmanager",
        ACCOUNT,
        REGION,
        "POST",
        "/",
        json.dumps({"Filters": [{"Key": "name", "Values": [SECRET]}]}),
        {"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "secretsmanager.ListSecrets"},
    )
    secrets = json.loads(listed[1] or "{}").get("SecretList", [])
    return next(item["ARN"] for item in secrets if item["Name"] == SECRET)


@pytest.fixture(scope="module", autouse=True)
def stop_the_instance_after_the_run(endpoint):
    """Leave the record, stop the compute: the lab's containers should not outlive a run."""
    yield
    status, text = rds(endpoint, "StopDBInstance", DBInstanceIdentifier=INSTANCE)
    if status != 200:
        print(f"could not stop {INSTANCE}: {status} {text[:200]}")


def data(endpoint, path: str, sql: str, **extra) -> tuple[int, dict]:
    payload = {
        "resourceArn": ensure_instance(endpoint),
        "secretArn": ensure_secret(endpoint),
        "database": DATABASE,
        "sql": sql,
        **extra,
    }
    status, text = signed.request(
        endpoint, "rds-data", ACCOUNT, REGION, "POST", path, json.dumps(payload), JSON
    )
    return status, json.loads(text or "{}")


def count(endpoint, table: str) -> int:
    status, answer = data(endpoint, "/Execute", f"SELECT count(*) FROM {table}")
    assert status == 200, answer
    return answer["records"][0][0]["longValue"]


def test_batch_execute_statement_inserts_every_parameter_set(endpoint):
    status, answer = data(endpoint, "/Execute", "CREATE TABLE IF NOT EXISTS ops_batch (note text)")
    assert status == 200, answer
    status, answer = data(
        endpoint,
        "/BatchExecute",
        "INSERT INTO ops_batch (note) VALUES (:note)",
        parameterSets=[
            [{"name": "note", "value": {"stringValue": "one"}}],
            [{"name": "note", "value": {"stringValue": "two"}}],
        ],
    )
    assert status == 200, answer
    assert len(answer["updateResults"]) == 2
    assert count(endpoint, "ops_batch") == 2


def test_begin_transaction_returns_an_id(endpoint):
    status, answer = data(endpoint, "/BeginTransaction", "SELECT 1")
    assert status == 200, answer
    assert answer["transactionId"]
    # A transaction left open holds a connection; close it.
    status, _ = data(
        endpoint, "/RollbackTransaction", "SELECT 1", transactionId=answer["transactionId"]
    )
    assert status == 200


def test_commit_transaction_keeps_the_write(endpoint):
    status, answer = data(endpoint, "/Execute", "CREATE TABLE IF NOT EXISTS ops_commit (note text)")
    assert status == 200, answer
    status, started = data(endpoint, "/BeginTransaction", "SELECT 1")
    txn = started["transactionId"]
    status, answer = data(
        endpoint, "/Execute", "INSERT INTO ops_commit (note) VALUES ('kept')", transactionId=txn
    )
    assert status == 200, answer
    status, answer = data(endpoint, "/CommitTransaction", "SELECT 1", transactionId=txn)
    assert status == 200, answer
    assert answer["transactionStatus"] == "Transaction Committed"
    assert count(endpoint, "ops_commit") == 1


def test_rollback_transaction_discards_the_write(endpoint):
    status, answer = data(endpoint, "/Execute", "CREATE TABLE IF NOT EXISTS ops_rollback (note text)")
    assert status == 200, answer
    status, started = data(endpoint, "/BeginTransaction", "SELECT 1")
    txn = started["transactionId"]
    status, answer = data(
        endpoint, "/Execute", "INSERT INTO ops_rollback (note) VALUES ('gone')", transactionId=txn
    )
    assert status == 200, answer
    status, answer = data(endpoint, "/RollbackTransaction", "SELECT 1", transactionId=txn)
    assert status == 200, answer
    assert answer["transactionStatus"] == "Transaction Rolled Back"
    assert count(endpoint, "ops_rollback") == 0
