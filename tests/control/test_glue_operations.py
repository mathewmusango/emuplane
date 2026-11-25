"""Glue on the wire: all 83 advertised operations, JSON + `X-Amz-Target`.

Signed with the `glue` credential scope. The Data Catalog is the book of record:
databases, tables, partitions, column statistics and partition indexes. The crawler,
job, trigger, workflow, connection, classifier and security-configuration records are
control-plane only — a crawler finishes after five seconds, a Spark job without Docker
succeeds immediately, and a job whose script is a plain Python file really runs it, so
the stop test uploads a script that sleeps.

Table optimizers are a real AWS capture: creating one requires a storage location and
an Iceberg `metadata_location` parameter, and with `AUTH=true` the optimizer role must
allow `glue:GetTable` and the location's bucket, so the suite creates an IAM role with
that inline policy (the in-process stand-in skips the check).
"""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

DB = "ops_glue_db"
TABLE = "ops_glue_table"
ICEBERG_TABLE = "ops_glue_iceberg"
PART_TABLE = "ops_glue_partitioned"
JOB = "ops_glue_job"
TRIGGER = "ops_glue_trigger"
WORKFLOW = "ops_glue_workflow"
UDF = "ops_glue_udf"
SECURITY = "ops_glue_security"
CLASSIFIER = "ops_glue_json"
CONNECTION = "ops_glue_conn"
CRAWLER = "ops_glue_crawler"
PARTITION_VALUES = ["2026-01-01"]
SECOND_PARTITION = ["2026-01-02"]
S3_BUCKET = "ops-glue-scripts"
SCRIPT_KEY = "sleep.py"
ROLE_NAME = "ops-glue-optimizer"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"

RUN = secrets.token_hex(3)

_STATE: dict = {}

_LOCATION = "s3://ops-glue-data/"
_TABLE_INPUT = {
    "Name": TABLE,
    "Description": "ops glue table",
    "StorageDescriptor": {
        "Columns": [{"Name": "id", "Type": "bigint"}, {"Name": "name", "Type": "string"}],
        "Location": f"{_LOCATION}{TABLE}/",
    },
    "PartitionKeys": [],
}
_PARTITIONED_INPUT = {
    "Name": PART_TABLE,
    "StorageDescriptor": {
        "Columns": [{"Name": "id", "Type": "bigint"}],
        "Location": f"{_LOCATION}{PART_TABLE}/",
    },
    "PartitionKeys": [{"Name": "dt", "Type": "string"}],
}
_ICEBERG_INPUT = {
    "Name": ICEBERG_TABLE,
    "StorageDescriptor": {
        "Columns": [{"Name": "id", "Type": "bigint"}],
        "Location": f"{_LOCATION}{ICEBERG_TABLE}/",
    },
    "Parameters": {
        "table_type": "ICEBERG",
        "metadata_location": f"{_LOCATION}{ICEBERG_TABLE}/metadata/00001.metadata.json",
    },
}
_TRUST = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "glue.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)
_ROLE_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "glue:GetTable",
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                "Resource": "*",
            }
        ],
    }
)


def call(endpoint, action: str, **payload):
    body = json.dumps(payload)
    headers = {"X-Amz-Target": f"AWSGlue.{action}", **JSON_TYPE}
    return signed.request(endpoint, "glue", ACCOUNT, REGION, "POST", "/", body, headers)


def call_status(endpoint, action: str, **payload):
    return call(endpoint, action, **payload)


def ok(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def created(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200 or "already exists" in text.lower(), (
        f"{action} answered {status}: {text[:500]}"
    )
    return json.loads(text or "{}")


def iam_call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": "2010-05-08", **params})
    return signed.request(endpoint, "iam", ACCOUNT, REGION, "POST", "/", body, FORM)


def ensure_role(endpoint) -> str:
    """The optimizer and crawler role, with the inline policy the live AUTH evaluator reads."""
    status, _text = iam_call(endpoint, "GetRole", RoleName=ROLE_NAME)
    if status != 200:
        status, text = iam_call(
            endpoint,
            "CreateRole",
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=_TRUST,
            Description="ops glue role",
        )
        assert status == 200 or "AlreadyExists" in text, f"CreateRole answered {status}: {text[:300]}"
    status, text = iam_call(
        endpoint,
        "PutRolePolicy",
        RoleName=ROLE_NAME,
        PolicyName="ops-glue-optimizer",
        PolicyDocument=_ROLE_POLICY,
    )
    assert status == 200, f"PutRolePolicy answered {status}: {text[:300]}"
    return ROLE_ARN


def ensure_database(endpoint, name: str = DB) -> str:
    key = f"db:{name}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetDatabase", Name=name)
        if status != 200:
            created(endpoint, "CreateDatabase", DatabaseInput={"Name": name, "Description": "ops glue database"})
        _STATE[key] = name
    return name


def ensure_table(endpoint, table_input: dict = _TABLE_INPUT, database: str = DB) -> str:
    ensure_database(endpoint, database)
    name = table_input["Name"]
    key = f"table:{database}:{name}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetTable", DatabaseName=database, Name=name)
        if status != 200:
            created(endpoint, "CreateTable", DatabaseName=database, TableInput=table_input)
        _STATE[key] = name
    return name


def ensure_partition(endpoint, values: list[str] = PARTITION_VALUES) -> list[str]:
    ensure_table(endpoint, _PARTITIONED_INPUT)
    key = f"partition:{values}"
    if key not in _STATE:
        status, _text = call_status(
            endpoint, "GetPartition", DatabaseName=DB, TableName=PART_TABLE, PartitionValues=values
        )
        if status != 200:
            created(
                endpoint,
                "CreatePartition",
                DatabaseName=DB,
                TableName=PART_TABLE,
                PartitionInput={
                    "Values": values,
                    "StorageDescriptor": {
                        "Columns": [{"Name": "id", "Type": "bigint"}],
                        "Location": f"{_LOCATION}{PART_TABLE}/dt={values[0]}/",
                    },
                },
            )
        _STATE[key] = values
    return values


def ensure_optimizer_table(endpoint) -> str:
    ensure_table(endpoint, _ICEBERG_INPUT)
    return ICEBERG_TABLE


def _optimizer_config(rate: int = 24) -> dict:
    return {
        "roleArn": ROLE_ARN,
        "compactionConfiguration": {"icebergConfiguration": {"strategy": "binpack"}},
        "orphanFileDeletionConfiguration": {"icebergConfiguration": {"runRateInHours": rate}},
    }


def ensure_optimizer(endpoint, optimizer_type: str = "compaction") -> None:
    ensure_role(endpoint)
    ensure_optimizer_table(endpoint)
    key = f"optimizer:{optimizer_type}"
    if key not in _STATE:
        status, _text = call_status(
            endpoint,
            "GetTableOptimizer",
            DatabaseName=DB,
            TableName=ICEBERG_TABLE,
            Type=optimizer_type,
        )
        if status != 200:
            created(
                endpoint,
                "CreateTableOptimizer",
                DatabaseName=DB,
                TableName=ICEBERG_TABLE,
                Type=optimizer_type,
                TableOptimizerConfiguration=_optimizer_config(),
            )
        _STATE[key] = optimizer_type


def ensure_job(endpoint) -> str:
    key = f"job:{JOB}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetJob", JobName=JOB)
        if status != 200:
            ensure_script(endpoint)
            created(
                endpoint,
                "CreateJob",
                Name=JOB,
                Role=ROLE_ARN,
                Command={"Name": "pythonshell", "ScriptLocation": f"s3://{S3_BUCKET}/{SCRIPT_KEY}"},
                Description="ops glue job",
            )
        _STATE[key] = JOB
    return JOB


def ensure_script(endpoint) -> None:
    status, _text = signed.request(endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{S3_BUCKET}", "")
    assert status in (200, 409), f"CreateBucket answered {status}"
    body = "import time\ntime.sleep(5)\n"
    status, text = signed.request(
        endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{S3_BUCKET}/{SCRIPT_KEY}", body
    )
    assert status == 200, f"PutObject answered {status}: {text[:300]}"


def ensure_trigger(endpoint) -> str:
    ensure_job(endpoint)
    key = f"trigger:{TRIGGER}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetTrigger", Name=TRIGGER)
        if status != 200:
            created(
                endpoint,
                "CreateTrigger",
                Name=TRIGGER,
                Type="ON_DEMAND",
                Actions=[{"JobName": JOB}],
                Description="ops glue trigger",
            )
        _STATE[key] = TRIGGER
    return TRIGGER


def ensure_workflow(endpoint) -> str:
    key = f"workflow:{WORKFLOW}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetWorkflow", Name=WORKFLOW)
        if status != 200:
            created(
                endpoint,
                "CreateWorkflow",
                Name=WORKFLOW,
                Description="ops glue workflow",
                DefaultRunProperties={"ops": "true"},
            )
        else:
            # A previous sweep's update test renames it; restore the reading state.
            ok(endpoint, "UpdateWorkflow", Name=WORKFLOW, Description="ops glue workflow")
        _STATE[key] = WORKFLOW
    return WORKFLOW


def ensure_udf(endpoint) -> str:
    ensure_database(endpoint)
    key = f"udf:{UDF}"
    if key not in _STATE:
        status, _text = call_status(
            endpoint, "GetUserDefinedFunction", DatabaseName=DB, FunctionName=UDF
        )
        if status != 200:
            created(
                endpoint,
                "CreateUserDefinedFunction",
                DatabaseName=DB,
                FunctionInput={
                    "FunctionName": UDF,
                    "ClassName": "com.example.OpsFunction",
                    "OwnerName": "ops",
                    "OwnerType": "USER",
                    "ResourceUris": [{"ResourceType": "JAR", "Uri": f"{_LOCATION}ops.jar"}],
                },
            )
        _STATE[key] = UDF
    return UDF


def ensure_security_configuration(endpoint) -> str:
    key = f"security:{SECURITY}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetSecurityConfiguration", Name=SECURITY)
        if status != 200:
            created(
                endpoint,
                "CreateSecurityConfiguration",
                Name=SECURITY,
                EncryptionConfiguration={"S3Encryptions": [{"S3EncryptionMode": "SSE-KMS"}]},
            )
        _STATE[key] = SECURITY
    return SECURITY


def ensure_classifier(endpoint) -> str:
    key = f"classifier:{CLASSIFIER}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetClassifier", Name=CLASSIFIER)
        if status != 200:
            created(
                endpoint,
                "CreateClassifier",
                JsonClassifier={"Name": CLASSIFIER, "JsonPath": "$[*]"},
            )
        _STATE[key] = CLASSIFIER
    return CLASSIFIER


def ensure_connection(endpoint) -> str:
    key = f"connection:{CONNECTION}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetConnection", Name=CONNECTION)
        if status != 200:
            created(
                endpoint,
                "CreateConnection",
                ConnectionInput={
                    "Name": CONNECTION,
                    "ConnectionType": "JDBC",
                    "ConnectionProperties": {"JDBC_CONNECTION_URL": "jdbc:postgresql://ops:5432/ops"},
                },
            )
        _STATE[key] = CONNECTION
    return CONNECTION


def ensure_crawler(endpoint) -> str:
    ensure_role(endpoint)
    ensure_database(endpoint)
    key = f"crawler:{CRAWLER}"
    if key not in _STATE:
        status, _text = call_status(endpoint, "GetCrawler", Name=CRAWLER)
        if status != 200:
            created(
                endpoint,
                "CreateCrawler",
                Name=CRAWLER,
                Role=ROLE_ARN,
                DatabaseName=DB,
                Targets={"S3Targets": [{"Path": _LOCATION}]},
            )
        _STATE[key] = CRAWLER
    return CRAWLER


def ensure_partition_index(endpoint) -> str:
    ensure_table(endpoint, _PARTITIONED_INPUT)
    name = "ops_glue_index"
    key = f"index:{name}"
    if key not in _STATE:
        indexes = ok(endpoint, "GetPartitionIndexes", DatabaseName=DB, TableName=PART_TABLE)[
            "PartitionIndexDescriptorList"
        ]
        if not any(index["IndexName"] == name for index in indexes):
            created(
                endpoint,
                "CreatePartitionIndex",
                DatabaseName=DB,
                TableName=PART_TABLE,
                PartitionIndex={"IndexName": name, "Keys": ["dt"]},
            )
        _STATE[key] = name
    return name


def table_statistics() -> dict:
    return {
        "ColumnName": "id",
        "ColumnType": "bigint",
        "StatisticsData": {
            "Type": "LONG",
            "LongColumnStatisticsData": {
                "MinimumValue": 1,
                "MaximumValue": 9,
                "NumberOfNulls": 0,
                "NumberOfDistinctValues": 3,
            },
        },
    }


def ensure_table_statistics(endpoint) -> None:
    ok(
        endpoint,
        "UpdateColumnStatisticsForTable",
        DatabaseName=DB,
        TableName=TABLE,
        ColumnStatisticsList=[table_statistics()],
    )


def ensure_partition_statistics(endpoint) -> None:
    ensure_partition(endpoint)
    ok(
        endpoint,
        "UpdateColumnStatisticsForPartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionValues=PARTITION_VALUES,
        ColumnStatisticsList=[table_statistics()],
    )


# --- Databases --------------------------------------------------------------


def test_create_database_answers_it(endpoint):
    name = f"ops_glue_created_{RUN}"
    ok(endpoint, "CreateDatabase", DatabaseInput={"Name": name, "Description": "created"})
    answer = ok(endpoint, "GetDatabase", Name=name)
    assert answer["Database"]["Description"] == "created"


def test_get_database_reads_it(endpoint):
    ensure_database(endpoint)
    answer = ok(endpoint, "GetDatabase", Name=DB)
    assert answer["Database"]["Name"] == DB


def test_get_databases_lists_it(endpoint):
    ensure_database(endpoint)
    names = {db["Name"] for db in ok(endpoint, "GetDatabases")["DatabaseList"]}
    assert DB in names


def test_update_database_sets_the_description(endpoint):
    ensure_database(endpoint)
    ok(endpoint, "UpdateDatabase", Name=DB, DatabaseInput={"Description": "updated database"})
    assert ok(endpoint, "GetDatabase", Name=DB)["Database"]["Description"] == "updated database"
    ok(endpoint, "UpdateDatabase", Name=DB, DatabaseInput={"Description": "ops glue database"})


def test_delete_database_removes_it(endpoint):
    name = f"ops_glue_deleted_{RUN}"
    ok(endpoint, "CreateDatabase", DatabaseInput={"Name": name})
    ok(endpoint, "DeleteDatabase", Name=name)
    status, _text = call_status(endpoint, "GetDatabase", Name=name)
    assert status == 400


# --- Tables -----------------------------------------------------------------


def test_create_table_answers_it(endpoint):
    ensure_database(endpoint)
    name = f"ops_glue_created_table_{RUN}"
    ok(
        endpoint,
        "CreateTable",
        DatabaseName=DB,
        TableInput={
            "Name": name,
            "StorageDescriptor": {
                "Columns": [{"Name": "id", "Type": "bigint"}],
                "Location": f"{_LOCATION}{name}/",
            },
        },
    )
    answer = ok(endpoint, "GetTable", DatabaseName=DB, Name=name)
    assert answer["Table"]["Name"] == name
    assert answer["Table"]["VersionId"] == "1"


def test_get_table_reads_it(endpoint):
    ensure_table(endpoint)
    answer = ok(endpoint, "GetTable", DatabaseName=DB, Name=TABLE)
    assert answer["Table"]["DatabaseName"] == DB


def test_get_tables_lists_it(endpoint):
    ensure_table(endpoint)
    tables = ok(endpoint, "GetTables", DatabaseName=DB)["TableList"]
    assert TABLE in {table["Name"] for table in tables}
    filtered = ok(endpoint, "GetTables", DatabaseName=DB, Expression="ops_glue_tab*")["TableList"]
    assert TABLE in {table["Name"] for table in filtered}


def test_update_table_sets_the_description(endpoint):
    ensure_table(endpoint)
    ok(
        endpoint,
        "UpdateTable",
        DatabaseName=DB,
        TableInput={"Name": TABLE, "Description": "updated table"},
    )
    assert ok(endpoint, "GetTable", DatabaseName=DB, Name=TABLE)["Table"]["Description"] == "updated table"
    ok(
        endpoint,
        "UpdateTable",
        DatabaseName=DB,
        TableInput={"Name": TABLE, "Description": "ops glue table"},
    )


def test_delete_table_removes_it(endpoint):
    ensure_database(endpoint)
    name = f"ops_glue_deleted_table_{RUN}"
    ok(
        endpoint,
        "CreateTable",
        DatabaseName=DB,
        TableInput={"Name": name, "StorageDescriptor": {"Columns": [], "Location": f"{_LOCATION}{name}/"}},
    )
    ok(endpoint, "DeleteTable", DatabaseName=DB, Name=name)
    status, _text = call_status(endpoint, "GetTable", DatabaseName=DB, Name=name)
    assert status == 400


def test_batch_delete_table_removes_them(endpoint):
    ensure_database(endpoint)
    names = [f"ops_glue_batch_{RUN}_1", f"ops_glue_batch_{RUN}_2"]
    for name in names:
        ok(
            endpoint,
            "CreateTable",
            DatabaseName=DB,
            TableInput={"Name": name, "StorageDescriptor": {"Columns": [], "Location": f"{_LOCATION}{name}/"}},
        )
    answer = ok(endpoint, "BatchDeleteTable", DatabaseName=DB, TablesToDelete=names)
    assert answer["Errors"] == []
    for name in names:
        status, _text = call_status(endpoint, "GetTable", DatabaseName=DB, Name=name)
        assert status == 400


# --- Table optimizers -------------------------------------------------------


def test_create_table_optimizer_answers_it(endpoint):
    ensure_optimizer(endpoint)
    answer = ok(
        endpoint,
        "GetTableOptimizer",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="compaction",
    )
    assert answer["TableOptimizer"]["type"] == "compaction"
    assert answer["TableOptimizer"]["configurationSource"] == "table"


def test_get_table_optimizer_reads_it(endpoint):
    ensure_optimizer(endpoint)
    answer = ok(
        endpoint,
        "GetTableOptimizer",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="compaction",
    )
    assert answer["TableName"] == ICEBERG_TABLE


def test_update_table_optimizer_sets_the_run_rate(endpoint):
    ensure_optimizer(endpoint, "orphan_file_deletion")
    ok(
        endpoint,
        "UpdateTableOptimizer",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="orphan_file_deletion",
        TableOptimizerConfiguration=_optimizer_config(rate=48),
    )
    read = ok(
        endpoint,
        "GetTableOptimizer",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="orphan_file_deletion",
    )["TableOptimizer"]
    assert read["configuration"]["orphanFileDeletionConfiguration"]["icebergConfiguration"]["runRateInHours"] == 48
    ok(
        endpoint,
        "UpdateTableOptimizer",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="orphan_file_deletion",
        TableOptimizerConfiguration=_optimizer_config(rate=24),
    )


def test_delete_table_optimizer_removes_it(endpoint):
    ensure_optimizer(endpoint, "retention")
    ok(
        endpoint,
        "DeleteTableOptimizer",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="retention",
    )
    status, _text = call_status(
        endpoint,
        "GetTableOptimizer",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="retention",
    )
    assert status == 400


def test_batch_get_table_optimizer_reads_them(endpoint):
    ensure_optimizer(endpoint)
    answer = ok(
        endpoint,
        "BatchGetTableOptimizer",
        Entries=[
            {
                "catalogId": ACCOUNT,
                "databaseName": DB,
                "tableName": ICEBERG_TABLE,
                "type": "compaction",
            },
            {
                "catalogId": ACCOUNT,
                "databaseName": DB,
                "tableName": f"ops_glue_missing_{RUN}",
                "type": "compaction",
            },
        ],
    )
    assert [found["tableName"] for found in answer["TableOptimizers"]] == [ICEBERG_TABLE]
    assert len(answer["Failures"]) == 1


def test_list_table_optimizer_runs_lists_none(endpoint):
    ensure_optimizer(endpoint)
    answer = ok(
        endpoint,
        "ListTableOptimizerRuns",
        DatabaseName=DB,
        TableName=ICEBERG_TABLE,
        Type="compaction",
    )
    assert answer["TableOptimizerRuns"] == []


# --- Partitions -------------------------------------------------------------


def test_create_partition_answers_it(endpoint):
    ensure_table(endpoint, _PARTITIONED_INPUT)
    values = [f"created-{RUN}"]
    ok(
        endpoint,
        "CreatePartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionInput={
            "Values": values,
            "StorageDescriptor": {
                "Columns": [{"Name": "id", "Type": "bigint"}],
                "Location": f"{_LOCATION}{PART_TABLE}/dt={values[0]}/",
            },
        },
    )
    answer = ok(
        endpoint, "GetPartition", DatabaseName=DB, TableName=PART_TABLE, PartitionValues=values
    )
    assert answer["Partition"]["Values"] == values


def test_get_partition_reads_it(endpoint):
    ensure_partition(endpoint)
    answer = ok(
        endpoint,
        "GetPartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionValues=PARTITION_VALUES,
    )
    assert answer["Partition"]["Values"] == PARTITION_VALUES


def test_get_partitions_filters_and_pages(endpoint):
    ensure_partition(endpoint)
    ensure_partition(endpoint, SECOND_PARTITION)
    answer = ok(
        endpoint,
        "GetPartitions",
        DatabaseName=DB,
        TableName=PART_TABLE,
        Expression="dt = '2026-01-01'",
    )
    assert [part["Values"] for part in answer["Partitions"]] == [PARTITION_VALUES]
    page = ok(endpoint, "GetPartitions", DatabaseName=DB, TableName=PART_TABLE, MaxResults=1)
    assert len(page["Partitions"]) == 1
    assert page.get("NextToken")
    second = ok(
        endpoint,
        "GetPartitions",
        DatabaseName=DB,
        TableName=PART_TABLE,
        MaxResults=1,
        NextToken=page["NextToken"],
    )
    assert second["Partitions"][0]["Values"] != page["Partitions"][0]["Values"]


def test_delete_partition_removes_it(endpoint):
    ensure_table(endpoint, _PARTITIONED_INPUT)
    values = [f"deleted-{RUN}"]
    ok(
        endpoint,
        "CreatePartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionInput={
            "Values": values,
            "StorageDescriptor": {"Columns": [], "Location": f"{_LOCATION}{PART_TABLE}/dt={values[0]}/"},
        },
    )
    ok(endpoint, "DeletePartition", DatabaseName=DB, TableName=PART_TABLE, PartitionValues=values)
    status, _text = call_status(
        endpoint, "GetPartition", DatabaseName=DB, TableName=PART_TABLE, PartitionValues=values
    )
    assert status == 400


def test_batch_create_partition_answers_them(endpoint):
    ensure_database(endpoint)
    name = f"ops_glue_batch_part_{RUN}"
    ok(
        endpoint,
        "CreateTable",
        DatabaseName=DB,
        TableInput={
            "Name": name,
            "StorageDescriptor": {"Columns": [{"Name": "id", "Type": "bigint"}], "Location": f"{_LOCATION}{name}/"},
            "PartitionKeys": [{"Name": "dt", "Type": "string"}],
        },
    )
    values = [["2026-02-01"], ["2026-02-02"]]
    answer = ok(
        endpoint,
        "BatchCreatePartition",
        DatabaseName=DB,
        TableName=name,
        PartitionInputList=[
            {
                "Values": entry,
                "StorageDescriptor": {"Columns": [], "Location": f"{_LOCATION}{name}/dt={entry[0]}/"},
            }
            for entry in values
        ],
    )
    assert answer["Errors"] == []
    parts = ok(endpoint, "GetPartitions", DatabaseName=DB, TableName=name)["Partitions"]
    assert {tuple(part["Values"]) for part in parts} == {tuple(entry) for entry in values}


def test_batch_get_partition_reads_them(endpoint):
    ensure_partition(endpoint)
    ensure_partition(endpoint, SECOND_PARTITION)
    answer = ok(
        endpoint,
        "BatchGetPartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionsToGet=[
            {"Values": PARTITION_VALUES},
            {"Values": SECOND_PARTITION},
            {"Values": [f"missing-{RUN}"]},
        ],
    )
    assert {tuple(part["Values"]) for part in answer["Partitions"]} == {
        tuple(PARTITION_VALUES),
        tuple(SECOND_PARTITION),
    }
    assert answer["UnprocessedKeys"] == [{"Values": [f"missing-{RUN}"]}]


def test_batch_delete_partition_removes_them(endpoint):
    ensure_database(endpoint)
    name = f"ops_glue_delete_part_{RUN}"
    ok(
        endpoint,
        "CreateTable",
        DatabaseName=DB,
        TableInput={
            "Name": name,
            "StorageDescriptor": {"Columns": [{"Name": "id", "Type": "bigint"}], "Location": f"{_LOCATION}{name}/"},
            "PartitionKeys": [{"Name": "dt", "Type": "string"}],
        },
    )
    values = [["2026-03-01"], ["2026-03-02"]]
    ok(
        endpoint,
        "BatchCreatePartition",
        DatabaseName=DB,
        TableName=name,
        PartitionInputList=[
            {
                "Values": entry,
                "StorageDescriptor": {"Columns": [], "Location": f"{_LOCATION}{name}/dt={entry[0]}/"},
            }
            for entry in values
        ],
    )
    answer = ok(
        endpoint,
        "BatchDeletePartition",
        DatabaseName=DB,
        TableName=name,
        PartitionsToDelete=[{"Values": entry} for entry in values],
    )
    assert answer["Errors"] == []
    assert ok(endpoint, "GetPartitions", DatabaseName=DB, TableName=name)["Partitions"] == []


# --- Partition indexes ------------------------------------------------------


def test_create_partition_index_answers_it(endpoint):
    ensure_partition_index(endpoint)
    indexes = ok(endpoint, "GetPartitionIndexes", DatabaseName=DB, TableName=PART_TABLE)[
        "PartitionIndexDescriptorList"
    ]
    created_index = next(index for index in indexes if index["IndexName"] == "ops_glue_index")
    assert created_index["IndexStatus"] == "ACTIVE"
    assert created_index["Keys"] == [{"Name": "dt"}]


def test_get_partition_indexes_lists_it(endpoint):
    ensure_partition_index(endpoint)
    names = {
        index["IndexName"]
        for index in ok(endpoint, "GetPartitionIndexes", DatabaseName=DB, TableName=PART_TABLE)[
            "PartitionIndexDescriptorList"
        ]
    }
    assert "ops_glue_index" in names


# --- Column statistics ------------------------------------------------------


def test_update_column_statistics_for_table_answers_them(endpoint):
    ensure_table(endpoint)
    answer = ok(
        endpoint,
        "UpdateColumnStatisticsForTable",
        DatabaseName=DB,
        TableName=TABLE,
        ColumnStatisticsList=[table_statistics()],
    )
    assert answer["Errors"] == []


def test_get_column_statistics_for_table_reads_them(endpoint):
    ensure_table_statistics(endpoint)
    answer = ok(
        endpoint,
        "GetColumnStatisticsForTable",
        DatabaseName=DB,
        TableName=TABLE,
        ColumnNames=["id"],
    )
    assert answer["ColumnStatisticsList"][0]["ColumnName"] == "id"
    assert answer["Errors"] == []


def test_delete_column_statistics_for_table_removes_them(endpoint):
    ensure_table_statistics(endpoint)
    ok(
        endpoint,
        "DeleteColumnStatisticsForTable",
        DatabaseName=DB,
        TableName=TABLE,
        ColumnName="id",
    )
    answer = ok(
        endpoint,
        "GetColumnStatisticsForTable",
        DatabaseName=DB,
        TableName=TABLE,
        ColumnNames=["id"],
    )
    assert answer["ColumnStatisticsList"] == []
    assert answer["Errors"][0]["Error"]["ErrorCode"] == "EntityNotFoundException"
    ensure_table_statistics(endpoint)


def test_update_column_statistics_for_partition_answers_them(endpoint):
    ensure_partition(endpoint)
    answer = ok(
        endpoint,
        "UpdateColumnStatisticsForPartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionValues=PARTITION_VALUES,
        ColumnStatisticsList=[table_statistics()],
    )
    assert answer["Errors"] == []


def test_get_column_statistics_for_partition_reads_them(endpoint):
    ensure_partition_statistics(endpoint)
    answer = ok(
        endpoint,
        "GetColumnStatisticsForPartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionValues=PARTITION_VALUES,
        ColumnNames=["id"],
    )
    assert answer["ColumnStatisticsList"][0]["ColumnName"] == "id"
    assert answer["Errors"] == []


def test_delete_column_statistics_for_partition_removes_them(endpoint):
    ensure_partition_statistics(endpoint)
    ok(
        endpoint,
        "DeleteColumnStatisticsForPartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionValues=PARTITION_VALUES,
        ColumnName="id",
    )
    answer = ok(
        endpoint,
        "GetColumnStatisticsForPartition",
        DatabaseName=DB,
        TableName=PART_TABLE,
        PartitionValues=PARTITION_VALUES,
        ColumnNames=["id"],
    )
    assert answer["ColumnStatisticsList"] == []
    ensure_partition_statistics(endpoint)


# --- Connections ------------------------------------------------------------


def test_create_connection_answers_it(endpoint):
    name = f"ops_glue_conn_created_{RUN}"
    ok(
        endpoint,
        "CreateConnection",
        ConnectionInput={
            "Name": name,
            "ConnectionType": "JDBC",
            "ConnectionProperties": {"JDBC_CONNECTION_URL": "jdbc:postgresql://ops:5432/ops"},
        },
    )
    answer = ok(endpoint, "GetConnection", Name=name)
    assert answer["Connection"]["ConnectionType"] == "JDBC"


def test_get_connection_reads_it(endpoint):
    ensure_connection(endpoint)
    answer = ok(endpoint, "GetConnection", Name=CONNECTION)
    assert answer["Connection"]["Name"] == CONNECTION


def test_get_connections_lists_it(endpoint):
    ensure_connection(endpoint)
    names = {conn["Name"] for conn in ok(endpoint, "GetConnections")["ConnectionList"]}
    assert CONNECTION in names


def test_delete_connection_removes_it(endpoint):
    name = f"ops_glue_conn_deleted_{RUN}"
    ok(
        endpoint,
        "CreateConnection",
        ConnectionInput={
            "Name": name,
            "ConnectionType": "JDBC",
            "ConnectionProperties": {"JDBC_CONNECTION_URL": "jdbc:postgresql://ops:5432/ops"},
        },
    )
    ok(endpoint, "DeleteConnection", ConnectionName=name)
    status, _text = call_status(endpoint, "GetConnection", Name=name)
    assert status == 400


# --- Crawlers ---------------------------------------------------------------


def test_create_crawler_answers_it(endpoint):
    ensure_role(endpoint)
    ensure_database(endpoint)
    name = f"ops_glue_crawler_created_{RUN}"
    ok(
        endpoint,
        "CreateCrawler",
        Name=name,
        Role=ROLE_ARN,
        DatabaseName=DB,
        Targets={"S3Targets": [{"Path": _LOCATION}]},
    )
    answer = ok(endpoint, "GetCrawler", Name=name)
    assert answer["Crawler"]["State"] == "READY"


def test_get_crawler_reads_it(endpoint):
    ensure_crawler(endpoint)
    answer = ok(endpoint, "GetCrawler", Name=CRAWLER)
    assert answer["Crawler"]["DatabaseName"] == DB


def test_get_crawlers_lists_it(endpoint):
    ensure_crawler(endpoint)
    names = {crawler["Name"] for crawler in ok(endpoint, "GetCrawlers")["Crawlers"]}
    assert CRAWLER in names


def test_update_crawler_sets_the_description(endpoint):
    ensure_crawler(endpoint)
    ok(
        endpoint,
        "UpdateCrawler",
        Name=CRAWLER,
        Description="updated crawler",
        Targets={"S3Targets": [{"Path": _LOCATION}]},
    )
    assert ok(endpoint, "GetCrawler", Name=CRAWLER)["Crawler"]["Description"] == "updated crawler"
    ok(endpoint, "UpdateCrawler", Name=CRAWLER, Description="", Targets={"S3Targets": [{"Path": _LOCATION}]})


def test_start_crawler_runs_it(endpoint):
    ensure_crawler(endpoint)
    status, text = call_status(endpoint, "StartCrawler", Name=CRAWLER)
    assert status == 200 or "already running" in text, f"StartCrawler answered {status}: {text[:300]}"
    assert ok(endpoint, "GetCrawler", Name=CRAWLER)["Crawler"]["State"] in ("RUNNING", "READY")


def test_stop_crawler_stops_it(endpoint):
    ensure_crawler(endpoint)
    call_status(endpoint, "StartCrawler", Name=CRAWLER)
    ok(endpoint, "StopCrawler", Name=CRAWLER)
    assert ok(endpoint, "GetCrawler", Name=CRAWLER)["Crawler"]["State"] == "READY"


def test_get_crawler_metrics_reads_them(endpoint):
    ensure_crawler(endpoint)
    answer = ok(endpoint, "GetCrawlerMetrics", CrawlerNameList=[CRAWLER])
    assert answer["CrawlerMetricsList"][0]["CrawlerName"] == CRAWLER


def test_delete_crawler_removes_it(endpoint):
    ensure_role(endpoint)
    ensure_database(endpoint)
    name = f"ops_glue_crawler_deleted_{RUN}"
    ok(
        endpoint,
        "CreateCrawler",
        Name=name,
        Role=ROLE_ARN,
        DatabaseName=DB,
        Targets={"S3Targets": [{"Path": _LOCATION}]},
    )
    ok(endpoint, "DeleteCrawler", Name=name)
    status, _text = call_status(endpoint, "GetCrawler", Name=name)
    assert status == 400


# --- Jobs -------------------------------------------------------------------


def test_create_job_answers_it(endpoint):
    ensure_script(endpoint)
    name = f"ops_glue_job_created_{RUN}"
    answer = ok(
        endpoint,
        "CreateJob",
        Name=name,
        Role=ROLE_ARN,
        Command={"Name": "pythonshell", "ScriptLocation": f"s3://{S3_BUCKET}/{SCRIPT_KEY}"},
    )
    assert answer["Name"] == name
    assert ok(endpoint, "GetJob", JobName=name)["Job"]["Name"] == name


def test_get_job_reads_it(endpoint):
    ensure_job(endpoint)
    answer = ok(endpoint, "GetJob", JobName=JOB)
    assert answer["Job"]["Role"] == ROLE_ARN


def test_get_jobs_lists_it(endpoint):
    ensure_job(endpoint)
    names = {job["Name"] for job in ok(endpoint, "GetJobs")["Jobs"]}
    assert JOB in names


def test_update_job_sets_the_description(endpoint):
    ensure_job(endpoint)
    ok(
        endpoint,
        "UpdateJob",
        JobName=JOB,
        JobUpdate={"Description": "updated job", "Command": {"Name": "pythonshell", "ScriptLocation": f"s3://{S3_BUCKET}/{SCRIPT_KEY}"}},
    )
    assert ok(endpoint, "GetJob", JobName=JOB)["Job"]["Description"] == "updated job"
    ok(
        endpoint,
        "UpdateJob",
        JobName=JOB,
        JobUpdate={
            "Description": "ops glue job",
            "Command": {"Name": "pythonshell", "ScriptLocation": f"s3://{S3_BUCKET}/{SCRIPT_KEY}"},
        },
    )


def test_start_job_run_answers_a_run(endpoint):
    ensure_job(endpoint)
    run_id = ok(endpoint, "StartJobRun", JobName=JOB)["JobRunId"]
    answer = ok(endpoint, "GetJobRun", JobName=JOB, RunId=run_id)
    assert answer["JobRun"]["Id"] == run_id
    assert answer["JobRun"]["JobName"] == JOB


def test_get_job_run_reads_it(endpoint):
    ensure_job(endpoint)
    run_id = ok(endpoint, "StartJobRun", JobName=JOB)["JobRunId"]
    assert ok(endpoint, "GetJobRun", JobName=JOB, RunId=run_id)["JobRun"]["Id"] == run_id


def test_get_job_runs_lists_it(endpoint):
    ensure_job(endpoint)
    run_id = ok(endpoint, "StartJobRun", JobName=JOB)["JobRunId"]
    runs = ok(endpoint, "GetJobRuns", JobName=JOB)["JobRuns"]
    assert run_id in {run["Id"] for run in runs}


def test_batch_stop_job_run_stops_it(endpoint):
    ensure_job(endpoint)
    run_id = ok(endpoint, "StartJobRun", JobName=JOB)["JobRunId"]
    answer = ok(endpoint, "BatchStopJobRun", JobName=JOB, JobRunIds=[run_id])
    assert [entry["JobRunId"] for entry in answer["SuccessfulSubmissions"]] == [run_id]


def test_delete_job_removes_it(endpoint):
    ensure_script(endpoint)
    name = f"ops_glue_job_deleted_{RUN}"
    ok(
        endpoint,
        "CreateJob",
        Name=name,
        Role=ROLE_ARN,
        Command={"Name": "pythonshell", "ScriptLocation": f"s3://{S3_BUCKET}/{SCRIPT_KEY}"},
    )
    ok(endpoint, "DeleteJob", JobName=name)
    status, _text = call_status(endpoint, "GetJob", JobName=name)
    assert status == 400


# --- Triggers ---------------------------------------------------------------


def test_create_trigger_answers_it(endpoint):
    ensure_job(endpoint)
    name = f"ops_glue_trigger_created_{RUN}"
    answer = ok(
        endpoint,
        "CreateTrigger",
        Name=name,
        Type="ON_DEMAND",
        Actions=[{"JobName": JOB}],
    )
    assert answer["Name"] == name


def test_get_trigger_reads_it(endpoint):
    ensure_trigger(endpoint)
    answer = ok(endpoint, "GetTrigger", Name=TRIGGER)
    assert answer["Trigger"]["Type"] == "ON_DEMAND"


def test_update_trigger_sets_the_description(endpoint):
    ensure_trigger(endpoint)
    ok(
        endpoint,
        "UpdateTrigger",
        Name=TRIGGER,
        TriggerUpdate={"Description": "updated trigger", "Actions": [{"JobName": JOB}]},
    )
    assert ok(endpoint, "GetTrigger", Name=TRIGGER)["Trigger"]["Description"] == "updated trigger"
    ok(
        endpoint,
        "UpdateTrigger",
        Name=TRIGGER,
        TriggerUpdate={"Description": "ops glue trigger", "Actions": [{"JobName": JOB}]},
    )


def test_start_and_stop_trigger(endpoint):
    ensure_trigger(endpoint)
    ok(endpoint, "StartTrigger", Name=TRIGGER)
    assert ok(endpoint, "GetTrigger", Name=TRIGGER)["Trigger"]["State"] == "ACTIVATED"
    ok(endpoint, "StopTrigger", Name=TRIGGER)
    assert ok(endpoint, "GetTrigger", Name=TRIGGER)["Trigger"]["State"] == "DEACTIVATED"


def test_list_triggers_lists_it(endpoint):
    ensure_trigger(endpoint)
    names = ok(endpoint, "ListTriggers")["TriggerNames"]
    assert TRIGGER in names
    dependent = ok(endpoint, "ListTriggers", DependentJobName=JOB)["TriggerNames"]
    assert TRIGGER in dependent


def test_batch_get_triggers_reads_them(endpoint):
    ensure_trigger(endpoint)
    answer = ok(
        endpoint, "BatchGetTriggers", TriggerNames=[TRIGGER, f"ops_glue_missing_{RUN}"]
    )
    assert [trigger["Name"] for trigger in answer["Triggers"]] == [TRIGGER]
    assert answer["TriggersNotFound"] == [f"ops_glue_missing_{RUN}"]


def test_get_triggers_lists_them(endpoint):
    ensure_trigger(endpoint)
    names = {trigger["Name"] for trigger in ok(endpoint, "GetTriggers", DependentJobName=JOB)["Triggers"]}
    assert TRIGGER in names


def test_delete_trigger_removes_it(endpoint):
    ensure_job(endpoint)
    name = f"ops_glue_trigger_deleted_{RUN}"
    ok(endpoint, "CreateTrigger", Name=name, Type="ON_DEMAND", Actions=[{"JobName": JOB}])
    ok(endpoint, "DeleteTrigger", Name=name)
    status, _text = call_status(endpoint, "GetTrigger", Name=name)
    assert status == 400


# --- Workflows --------------------------------------------------------------


def test_create_workflow_answers_it(endpoint):
    name = f"ops_glue_workflow_created_{RUN}"
    answer = ok(endpoint, "CreateWorkflow", Name=name, Description="created workflow")
    assert answer["Name"] == name


def test_get_workflow_reads_it(endpoint):
    ensure_workflow(endpoint)
    answer = ok(endpoint, "GetWorkflow", Name=WORKFLOW)
    assert answer["Workflow"]["Description"] == "ops glue workflow"


def test_update_workflow_sets_the_description(endpoint):
    ensure_workflow(endpoint)
    ok(endpoint, "UpdateWorkflow", Name=WORKFLOW, Description="updated workflow")
    assert ok(endpoint, "GetWorkflow", Name=WORKFLOW)["Workflow"]["Description"] == "updated workflow"
    ok(endpoint, "UpdateWorkflow", Name=WORKFLOW, Description="ops glue workflow")


def test_start_workflow_run_answers_a_run(endpoint):
    ensure_workflow(endpoint)
    run_id = ok(
        endpoint, "StartWorkflowRun", Name=WORKFLOW, RunProperties={"ops": "run"}
    )["RunId"]
    workflow = ok(endpoint, "GetWorkflow", Name=WORKFLOW)["Workflow"]
    assert workflow["LastRun"]["WorkflowRunId"] == run_id


def test_delete_workflow_removes_it(endpoint):
    name = f"ops_glue_workflow_deleted_{RUN}"
    ok(endpoint, "CreateWorkflow", Name=name)
    ok(endpoint, "DeleteWorkflow", Name=name)
    status, _text = call_status(endpoint, "GetWorkflow", Name=name)
    assert status == 400


# --- User-defined functions -------------------------------------------------


def test_create_user_defined_function_answers_it(endpoint):
    ensure_database(endpoint)
    name = f"ops_glue_udf_created_{RUN}"
    ok(
        endpoint,
        "CreateUserDefinedFunction",
        DatabaseName=DB,
        FunctionInput={
            "FunctionName": name,
            "ClassName": "com.example.Created",
            "ResourceUris": [{"ResourceType": "JAR", "Uri": f"{_LOCATION}ops.jar"}],
        },
    )
    answer = ok(endpoint, "GetUserDefinedFunction", DatabaseName=DB, FunctionName=name)
    assert answer["UserDefinedFunction"]["ClassName"] == "com.example.Created"


def test_get_user_defined_function_reads_it(endpoint):
    ensure_udf(endpoint)
    answer = ok(endpoint, "GetUserDefinedFunction", DatabaseName=DB, FunctionName=UDF)
    assert answer["UserDefinedFunction"]["FunctionName"] == UDF


def test_update_user_defined_function_sets_the_class(endpoint):
    ensure_udf(endpoint)
    ok(
        endpoint,
        "UpdateUserDefinedFunction",
        DatabaseName=DB,
        FunctionName=UDF,
        FunctionInput={"FunctionName": UDF, "ClassName": "com.example.Updated"},
    )
    answer = ok(endpoint, "GetUserDefinedFunction", DatabaseName=DB, FunctionName=UDF)
    assert answer["UserDefinedFunction"]["ClassName"] == "com.example.Updated"
    ok(
        endpoint,
        "UpdateUserDefinedFunction",
        DatabaseName=DB,
        FunctionName=UDF,
        FunctionInput={"FunctionName": UDF, "ClassName": "com.example.OpsFunction"},
    )


def test_get_user_defined_functions_lists_it(endpoint):
    ensure_udf(endpoint)
    names = {
        function["FunctionName"]
        for function in ok(endpoint, "GetUserDefinedFunctions", DatabaseName=DB)["UserDefinedFunctions"]
    }
    assert UDF in names
    pattern = ok(
        endpoint, "GetUserDefinedFunctions", DatabaseName=DB, Pattern=r"^ops_glue_udf$"
    )["UserDefinedFunctions"]
    assert [function["FunctionName"] for function in pattern] == [UDF]


def test_delete_user_defined_function_removes_it(endpoint):
    ensure_database(endpoint)
    name = f"ops_glue_udf_deleted_{RUN}"
    ok(
        endpoint,
        "CreateUserDefinedFunction",
        DatabaseName=DB,
        FunctionInput={"FunctionName": name, "ClassName": "com.example.Deleted"},
    )
    ok(endpoint, "DeleteUserDefinedFunction", DatabaseName=DB, FunctionName=name)
    status, _text = call_status(
        endpoint, "GetUserDefinedFunction", DatabaseName=DB, FunctionName=name
    )
    assert status == 400


# --- Security configurations ------------------------------------------------


def test_create_security_configuration_answers_it(endpoint):
    name = f"ops_glue_security_created_{RUN}"
    answer = ok(
        endpoint,
        "CreateSecurityConfiguration",
        Name=name,
        EncryptionConfiguration={"S3Encryptions": [{"S3EncryptionMode": "SSE-KMS"}]},
    )
    assert answer["Name"] == name
    assert ok(endpoint, "GetSecurityConfiguration", Name=name)["SecurityConfiguration"]["Name"] == name


def test_get_security_configuration_reads_it(endpoint):
    ensure_security_configuration(endpoint)
    answer = ok(endpoint, "GetSecurityConfiguration", Name=SECURITY)
    assert answer["SecurityConfiguration"]["Name"] == SECURITY


def test_get_security_configurations_lists_it(endpoint):
    ensure_security_configuration(endpoint)
    names = {
        config["Name"]
        for config in ok(endpoint, "GetSecurityConfigurations")["SecurityConfigurations"]
    }
    assert SECURITY in names


def test_delete_security_configuration_removes_it(endpoint):
    name = f"ops_glue_security_deleted_{RUN}"
    ok(
        endpoint,
        "CreateSecurityConfiguration",
        Name=name,
        EncryptionConfiguration={"S3Encryptions": [{"S3EncryptionMode": "SSE-KMS"}]},
    )
    ok(endpoint, "DeleteSecurityConfiguration", Name=name)
    status, _text = call_status(endpoint, "GetSecurityConfiguration", Name=name)
    assert status == 400


# --- Classifiers ------------------------------------------------------------


def test_create_classifier_answers_it(endpoint):
    name = f"ops_glue_classifier_created_{RUN}"
    ok(endpoint, "CreateClassifier", JsonClassifier={"Name": name, "JsonPath": "$[*]"})
    answer = ok(endpoint, "GetClassifier", Name=name)
    assert answer["Classifier"]["JsonClassifier"]["Name"] == name


def test_get_classifier_reads_it(endpoint):
    ensure_classifier(endpoint)
    answer = ok(endpoint, "GetClassifier", Name=CLASSIFIER)
    assert answer["Classifier"]["JsonClassifier"]["JsonPath"] == "$[*]"


def test_get_classifiers_lists_it(endpoint):
    ensure_classifier(endpoint)
    listed = ok(endpoint, "GetClassifiers")["Classifiers"]
    assert any(CLASSIFIER in entry.get("JsonClassifier", {}).get("Name", "") for entry in listed)


def test_delete_classifier_removes_it(endpoint):
    name = f"ops_glue_classifier_deleted_{RUN}"
    ok(endpoint, "CreateClassifier", JsonClassifier={"Name": name, "JsonPath": "$[*]"})
    ok(endpoint, "DeleteClassifier", Name=name)
    status, _text = call_status(endpoint, "GetClassifier", Name=name)
    assert status == 400


# --- Tags -------------------------------------------------------------------


def test_tag_untag_get_tags(endpoint):
    arn = f"arn:aws:glue:{REGION}:{ACCOUNT}:job/ops-glue-tagged"
    ok(endpoint, "TagResource", ResourceArn=arn, TagsToAdd={"ops": "glue", "keep": "yes"})
    assert ok(endpoint, "GetTags", ResourceArn=arn)["Tags"]["ops"] == "glue"
    ok(endpoint, "UntagResource", ResourceArn=arn, TagsToRemove=["ops"])
    tags = ok(endpoint, "GetTags", ResourceArn=arn)["Tags"]
    assert "ops" not in tags and tags.get("keep") == "yes"


def test_get_tags_reads_the_created_table(endpoint):
    ensure_table(endpoint)
    arn = f"arn:aws:glue:{REGION}:{ACCOUNT}:table/{DB}/{TABLE}"
    ok(endpoint, "TagResource", ResourceArn=arn, TagsToAdd={"ops": "table"})
    assert ok(endpoint, "GetTags", ResourceArn=arn)["Tags"]["ops"] == "table"


def test_tag_resource_refuses_a_foreign_arn(endpoint):
    status, text = call_status(
        endpoint, "TagResource", ResourceArn="arn:aws:glue:eu-west-1:999999999999:job/nope", TagsToAdd={"ops": "x"}
    )
    assert status == 400
    assert "Invalid Glue resource ARN" in text
