"""RDS Data API on the wire: `ExecuteStatement`, the one operation that answers without a database.

The service is REST-JSON under `/Execute`, `/BeginTransaction`, `/CommitTransaction`,
`/RollbackTransaction` and `/BatchExecute`. A serverless cluster has no compute
member, so the emulator answers statements from its in-memory stub and tracks the
databases and users the SQL names. The four operations that open a real connection
are blocked in `coverage/rds-data-api.json`, not silently omitted: a batch and a
transaction both bind a database connection, which the stub deliberately does not fake.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
JSON = {"Content-Type": "application/json"}
RDS_VERSION = "2014-10-31"
SM_VERSION_TARGET = "secretsmanager."

CLUSTER = "ops-rds-data-cluster"
SECRET = "ops/rds/data-api"
DATABASE = "opsdataapi"
CREDENTIALS = json.dumps({"username": "docadmin", "password": "password"})


def rds(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": RDS_VERSION, **params})
    return signed.request(endpoint, "rds", ACCOUNT, REGION, "POST", "/", body, FORM)


def secrets(endpoint, action: str, **params):
    headers = {"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": SM_VERSION_TARGET + action}
    return signed.request(
        endpoint, "secretsmanager", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:500]}"
    return match.group(1)


def ensure_cluster(endpoint) -> str:
    """A serverless cluster: no compute member, so statements take the stub path."""
    status, text = rds(
        endpoint,
        "CreateDBCluster",
        DBClusterIdentifier=CLUSTER,
        Engine="aurora-postgresql",
        EngineMode="serverless",
        MasterUsername="docadmin",
        MasterUserPassword="password",
        EnableHttpEndpoint="true",
        DatabaseName=DATABASE,
    )
    assert status == 200 or "AlreadyExist" in text, f"CreateDBCluster answered {status}: {text[:400]}"
    status, text = rds(endpoint, "DescribeDBClusters", DBClusterIdentifier=CLUSTER)
    assert status == 200, text[:400]
    return field(text, "DBClusterArn")


def ensure_secret(endpoint) -> str:
    status, text = secrets(endpoint, "CreateSecret", Name=SECRET, SecretString=CREDENTIALS)
    if status == 200:
        return json.loads(text)["ARN"]
    assert "ResourceExists" in text, f"CreateSecret answered {status}: {text[:400]}"
    listed = json.loads(secrets(endpoint, "ListSecrets")[1])["SecretList"]
    return next(item["ARN"] for item in listed if item["Name"] == SECRET)


def execute(endpoint, sql: str, **extra) -> tuple[int, dict]:
    body = json.dumps(
        {
            "resourceArn": ensure_cluster(endpoint),
            "secretArn": ensure_secret(endpoint),
            "database": DATABASE,
            "sql": sql,
            **extra,
        }
    )
    status, text = signed.request(endpoint, "rds-data", ACCOUNT, REGION, "POST", "/Execute", body, JSON)
    return status, json.loads(text or "{}")


def test_execute_statement_runs_against_the_in_memory_stub(endpoint):
    status, answer = execute(endpoint, f"CREATE DATABASE {DATABASE}")
    assert status == 200, answer
    assert answer["numberOfRecordsUpdated"] == 0
    assert answer["records"] == []

    status, listed = execute(endpoint, "SHOW DATABASES")
    assert status == 200, listed
    names = [record[0]["stringValue"] for record in listed["records"]]
    assert DATABASE in names
