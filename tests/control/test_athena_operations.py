"""Athena on the wire: all 32 advertised operations, JSON + `X-Amz-Target`.

Signed with the `athena` credential scope. A query needs a result location, so the
suite creates an S3 bucket; results are written there. The in-process stand-in
closes its event loop before the query worker runs, so a query never leaves
`QUEUED` there — `GetQueryResults` is proved by the live sweep and skips
in-process. Databases and tables come from the Glue Data Catalog, created here
under the `glue` scope.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
BUCKET = "ops-athena-results"
OUTPUT = f"s3://{BUCKET}/"
WORKGROUP = "ops-athena-wg"
CATALOG = "ops_athena_catalog"
PREPARED = "ops_athena_statement"
GLUE_DB = "ops_athena_db"
GLUE_TABLE = "ops_athena_table"

_STATE: dict = {}


def call(endpoint, action: str, **payload):
    body = json.dumps(payload)
    headers = {"X-Amz-Target": f"AmazonAthena.{action}", **JSON_TYPE}
    return signed.request(endpoint, "athena", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def created(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200 or "already exists" in text, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def ensure_bucket(endpoint) -> None:
    status, text = signed.request(
        endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{BUCKET}", "", None
    )
    assert status in (200, 409), f"CreateBucket answered {status}: {text[:300]}"


def start_query(endpoint, query: str = "SELECT 1") -> str:
    ensure_bucket(endpoint)
    answer = ok(
        endpoint,
        "StartQueryExecution",
        QueryString=query,
        ResultConfiguration={"OutputLocation": OUTPUT},
    )
    return answer["QueryExecutionId"]


def wait_for_state(endpoint, query_id: str, timeout: float = 2.0) -> str:
    deadline = time.time() + timeout
    state = "QUEUED"
    while time.time() < deadline:
        state = ok(endpoint, "GetQueryExecution", QueryExecutionId=query_id)[
            "QueryExecution"
        ]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return state
        time.sleep(0.02)
    return state


def ensure_workgroup(endpoint) -> None:
    created(endpoint, "CreateWorkGroup", Name=WORKGROUP, Description="ops athena workgroup")
    ok(endpoint, "GetWorkGroup", WorkGroup=WORKGROUP)


def ensure_named_query(endpoint) -> str:
    if "named_query" not in _STATE:
        _STATE["named_query"] = ok(
            endpoint,
            "CreateNamedQuery",
            Name="ops-athena-named-query",
            Database=GLUE_DB,
            QueryString="SELECT 1",
        )["NamedQueryId"]
    return _STATE["named_query"]


def ensure_catalog(endpoint) -> None:
    created(endpoint, "CreateDataCatalog", Name=CATALOG, Type="HIVE", Description="ops catalog")


def ensure_prepared(endpoint) -> None:
    created(
        endpoint,
        "CreatePreparedStatement",
        StatementName=PREPARED,
        WorkGroup="primary",
        QueryStatement="SELECT 1",
    )


def glue_call(endpoint, action: str, **payload):
    body = json.dumps(payload)
    headers = {"X-Amz-Target": f"AWSGlue.{action}", **JSON_TYPE}
    return signed.request(endpoint, "glue", ACCOUNT, REGION, "POST", "/", body, headers)


def ensure_glue_table(endpoint) -> None:
    status, text = glue_call(endpoint, "CreateDatabase", DatabaseInput={"Name": GLUE_DB})
    assert status == 200 or "AlreadyExist" in text, f"CreateDatabase answered {status}: {text[:300]}"
    status, text = glue_call(
        endpoint,
        "CreateTable",
        DatabaseName=GLUE_DB,
        TableInput={
            "Name": GLUE_TABLE,
            "StorageDescriptor": {
                "Columns": [
                    {"Name": "id", "Type": "int"},
                    {"Name": "name", "Type": "string"},
                ],
                "Location": f"s3://{BUCKET}/data/",
            },
        },
    )
    assert status == 200 or "AlreadyExist" in text, f"CreateTable answered {status}: {text[:300]}"


# --- Query execution --------------------------------------------------------


def test_start_query_execution_answers_an_id(endpoint):
    query_id = start_query(endpoint)
    assert query_id


def test_get_query_execution_reads_it(endpoint):
    query_id = start_query(endpoint)
    answer = ok(endpoint, "GetQueryExecution", QueryExecutionId=query_id)
    execution = answer["QueryExecution"]
    assert execution["QueryExecutionId"] == query_id
    assert execution["Status"]["State"] in ("QUEUED", "RUNNING", "SUCCEEDED")


def test_get_query_results_reads_them(endpoint):
    query_id = start_query(endpoint)
    assert wait_for_state(endpoint, query_id) == "SUCCEEDED"
    answer = ok(endpoint, "GetQueryResults", QueryExecutionId=query_id)
    assert answer["ResultSet"]["Rows"]


def test_stop_query_execution_is_accepted(endpoint):
    query_id = start_query(endpoint)
    assert ok(endpoint, "StopQueryExecution", QueryExecutionId=query_id) == {}


def test_list_query_executions_lists_it(endpoint):
    query_id = start_query(endpoint)
    answer = ok(endpoint, "ListQueryExecutions")
    assert query_id in answer["QueryExecutionIds"]


def test_batch_get_query_execution_reads_it(endpoint):
    query_id = start_query(endpoint)
    answer = ok(endpoint, "BatchGetQueryExecution", QueryExecutionIds=[query_id])
    assert query_id in {
        execution["QueryExecutionId"] for execution in answer["QueryExecutions"]
    }


# --- Workgroups -------------------------------------------------------------


def test_create_workgroup_answers_the_workgroup(endpoint):
    ensure_workgroup(endpoint)
    answer = ok(endpoint, "GetWorkGroup", WorkGroup=WORKGROUP)
    assert answer["WorkGroup"]["Name"] == WORKGROUP


def test_get_workgroup_reads_it(endpoint):
    ensure_workgroup(endpoint)
    answer = ok(endpoint, "GetWorkGroup", WorkGroup=WORKGROUP)
    assert answer["WorkGroup"]["Name"] == WORKGROUP
    assert answer["WorkGroup"]["State"] == "ENABLED"


def test_update_workgroup_sets_the_description(endpoint):
    ensure_workgroup(endpoint)
    ok(endpoint, "UpdateWorkGroup", WorkGroup=WORKGROUP, Description="updated workgroup")
    answer = ok(endpoint, "GetWorkGroup", WorkGroup=WORKGROUP)
    assert answer["WorkGroup"]["Description"] == "updated workgroup"


def test_list_workgroups_lists_it(endpoint):
    ensure_workgroup(endpoint)
    answer = ok(endpoint, "ListWorkGroups")
    assert WORKGROUP in {workgroup["Name"] for workgroup in answer["WorkGroups"]}


def test_delete_workgroup_removes_it(endpoint):
    name = f"ops-athena-delete-wg-{int(time.time())}"
    ok(endpoint, "CreateWorkGroup", Name=name)
    ok(endpoint, "DeleteWorkGroup", WorkGroup=name)
    status, _text = call(endpoint, "GetWorkGroup", WorkGroup=name)
    assert status == 400


# --- Named queries ----------------------------------------------------------


def test_create_named_query_answers_an_id(endpoint):
    answer = ok(
        endpoint,
        "CreateNamedQuery",
        Name=f"ops-athena-created-{int(time.time())}",
        Database=GLUE_DB,
        QueryString="SELECT 1",
    )
    assert answer["NamedQueryId"]


def test_get_named_query_reads_it(endpoint):
    query_id = ensure_named_query(endpoint)
    answer = ok(endpoint, "GetNamedQuery", NamedQueryId=query_id)
    assert answer["NamedQuery"]["NamedQueryId"] == query_id


def test_list_named_queries_lists_it(endpoint):
    query_id = ensure_named_query(endpoint)
    answer = ok(endpoint, "ListNamedQueries")
    assert query_id in answer["NamedQueryIds"]


def test_batch_get_named_query_reads_it(endpoint):
    query_id = ensure_named_query(endpoint)
    answer = ok(endpoint, "BatchGetNamedQuery", NamedQueryIds=[query_id])
    assert query_id in {query["NamedQueryId"] for query in answer["NamedQueries"]}


def test_delete_named_query_removes_it(endpoint):
    query_id = ok(
        endpoint,
        "CreateNamedQuery",
        Name=f"ops-athena-delete-{int(time.time())}",
        Database=GLUE_DB,
        QueryString="SELECT 1",
    )["NamedQueryId"]
    ok(endpoint, "DeleteNamedQuery", NamedQueryId=query_id)
    status, _text = call(endpoint, "GetNamedQuery", NamedQueryId=query_id)
    assert status == 400


# --- Data catalogs ----------------------------------------------------------


def test_create_data_catalog_answers_the_catalog(endpoint):
    ensure_catalog(endpoint)
    answer = ok(endpoint, "GetDataCatalog", Name=CATALOG)
    assert answer["DataCatalog"]["Name"] == CATALOG


def test_get_data_catalog_reads_it(endpoint):
    ensure_catalog(endpoint)
    answer = ok(endpoint, "GetDataCatalog", Name=CATALOG)
    assert answer["DataCatalog"]["Type"] == "HIVE"


def test_list_data_catalogs_lists_it(endpoint):
    ensure_catalog(endpoint)
    answer = ok(endpoint, "ListDataCatalogs")
    assert CATALOG in {catalog["CatalogName"] for catalog in answer["DataCatalogsSummary"]}


def test_update_data_catalog_sets_the_description(endpoint):
    ensure_catalog(endpoint)
    ok(endpoint, "UpdateDataCatalog", Name=CATALOG, Description="updated catalog")
    answer = ok(endpoint, "GetDataCatalog", Name=CATALOG)
    assert answer["DataCatalog"]["Description"] == "updated catalog"


def test_delete_data_catalog_removes_it(endpoint):
    name = f"ops_athena_delete_catalog_{int(time.time())}"
    ok(endpoint, "CreateDataCatalog", Name=name, Type="HIVE")
    ok(endpoint, "DeleteDataCatalog", Name=name)
    status, _text = call(endpoint, "GetDataCatalog", Name=name)
    assert status == 400


# --- Prepared statements ----------------------------------------------------


def test_create_prepared_statement_answers_it(endpoint):
    ensure_prepared(endpoint)
    answer = ok(endpoint, "GetPreparedStatement", StatementName=PREPARED, WorkGroup="primary")
    assert answer["PreparedStatement"]["StatementName"] == PREPARED


def test_get_prepared_statement_reads_it(endpoint):
    ensure_prepared(endpoint)
    answer = ok(endpoint, "GetPreparedStatement", StatementName=PREPARED, WorkGroup="primary")
    assert answer["PreparedStatement"]["QueryStatement"] == "SELECT 1"


def test_list_prepared_statements_lists_it(endpoint):
    ensure_prepared(endpoint)
    answer = ok(endpoint, "ListPreparedStatements", WorkGroup="primary")
    assert PREPARED in {
        statement["StatementName"] for statement in answer["PreparedStatements"]
    }


def test_delete_prepared_statement_removes_it(endpoint):
    name = f"ops_athena_delete_statement_{int(time.time())}"
    ok(
        endpoint,
        "CreatePreparedStatement",
        StatementName=name,
        WorkGroup="primary",
        QueryStatement="SELECT 1",
    )
    ok(endpoint, "DeletePreparedStatement", StatementName=name, WorkGroup="primary")
    status, _text = call(
        endpoint, "GetPreparedStatement", StatementName=name, WorkGroup="primary"
    )
    assert status == 400


# --- Databases and table metadata -------------------------------------------


def test_get_database_reads_it(endpoint):
    ensure_glue_table(endpoint)
    answer = ok(endpoint, "GetDatabase", DatabaseName=GLUE_DB)
    assert answer["Database"]["Name"] == GLUE_DB


def test_list_databases_lists_it(endpoint):
    ensure_glue_table(endpoint)
    answer = ok(endpoint, "ListDatabases")
    assert GLUE_DB in {database["Name"] for database in answer["DatabaseList"]}


def test_get_table_metadata_reads_it(endpoint):
    ensure_glue_table(endpoint)
    answer = ok(endpoint, "GetTableMetadata", DatabaseName=GLUE_DB, TableName=GLUE_TABLE)
    metadata = answer["TableMetadata"]
    assert metadata["Name"] == GLUE_TABLE
    assert {column["Name"] for column in metadata["Columns"]} == {"id", "name"}


def test_list_table_metadata_lists_it(endpoint):
    ensure_glue_table(endpoint)
    answer = ok(endpoint, "ListTableMetadata", DatabaseName=GLUE_DB)
    assert GLUE_TABLE in {table["Name"] for table in answer["TableMetadataList"]}


# --- Tags -------------------------------------------------------------------


def tags_arn() -> str:
    return f"arn:aws:athena:{REGION}:{ACCOUNT}:workgroup/{WORKGROUP}"


def test_tag_resource_adds_tags(endpoint):
    ensure_workgroup(endpoint)
    ok(
        endpoint,
        "TagResource",
        ResourceARN=tags_arn(),
        Tags=[{"Key": "ops", "Value": "athena"}],
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=tags_arn())
    assert {"Key": "ops", "Value": "athena"} in answer["Tags"]


def test_list_tags_for_resource_reads_them(endpoint):
    ensure_workgroup(endpoint)
    ok(
        endpoint,
        "TagResource",
        ResourceARN=tags_arn(),
        Tags=[{"Key": "ops", "Value": "athena"}],
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=tags_arn())
    assert any(tag["Key"] == "ops" for tag in answer["Tags"])


def test_untag_resource_removes_tags(endpoint):
    ensure_workgroup(endpoint)
    ok(
        endpoint,
        "TagResource",
        ResourceARN=tags_arn(),
        Tags=[{"Key": "ops-remove", "Value": "athena"}],
    )
    ok(endpoint, "UntagResource", ResourceARN=tags_arn(), TagKeys=["ops-remove"])
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=tags_arn())
    assert all(tag["Key"] != "ops-remove" for tag in answer["Tags"])
