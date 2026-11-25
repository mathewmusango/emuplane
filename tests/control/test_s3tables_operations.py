"""S3 Tables on the wire: all 39 advertised control-plane operations, REST/JSON.

The bucket ARN is the address of everything else — namespaces and tables hang off
it, and the table ARN hangs off the bucket ARN. ARNs are percent-encoded into the
path, which is what the SDKs send and what the handler re-joins.

A create is proven by a read and left in place, tolerating the ``ConflictException``
a second sweep meets. A delete action builds a resource of its own (the ``doomed``
names) and removes only that. The rename test creates a table to rename and then
removes the renamed one, so a re-run starts from an empty name.

The emulator's Iceberg REST catalog at ``/iceberg`` is a data plane (Spark's
catalog, not an API operation), so it is not exercised here.
"""

from __future__ import annotations

import json
from urllib.parse import quote, urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}

BUCKET = "ops-s3tables-bucket"
BUCKET_DOOMED = "ops-s3tables-doomed"
BUCKET_ARN = f"arn:aws:s3tables:{REGION}:{ACCOUNT}:bucket/{BUCKET}"

NS = "ops_ns"
NS_DOOMED = "ops_ns_doomed"
TABLE = "ops_table"
TABLE_DOOMED = "ops_table_doomed"
TABLE_RENAME = "ops_table_rename"
TABLE_RENAMED = "ops_table_renamed"

POLICY = json.dumps({"Version": "2012-10-17", "Statement": []})
KMS = {"sseAlgorithm": "aws:kms"}
TIER = {"storageClass": "INTELLIGENT_TIERING"}


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def path_arn(arn: str) -> str:
    """An ARN as one path segment, the way a client encodes it."""
    return quote(arn, safe="")


def table_arn(namespace: str = NS, name: str = TABLE) -> str:
    return f"{BUCKET_ARN}/table/{namespace}/{name}"


def call(endpoint, method: str, path: str, body=""):
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return signed.request(
        endpoint, "s3tables", ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = call(endpoint, method, path, body)
    assert status in (200, 201, 204), (
        f"{method} {path} answered {status}: {text[:400]}"
    )
    return json.loads(text) if text.strip() else {}


def rejected(endpoint, method: str, path: str, body="", status: int = 400) -> str:
    got, text = call(endpoint, method, path, body)
    assert got == status, f"{method} {path} answered {got}: {text[:400]}"
    return text


def get_table(endpoint, namespace: str = NS, name: str = TABLE) -> dict:
    query = urlencode(
        {"tableBucketARN": BUCKET_ARN, "namespace": namespace, "name": name}
    )
    return ok(endpoint, "GET", f"/get-table?{query}")


# ---------------------------------------------------------------------------
# Find-or-create, so a re-run meets what the first sweep left
# ---------------------------------------------------------------------------


def ensure_bucket(endpoint, name: str = BUCKET) -> str:
    status, text = call(endpoint, "PUT", "/buckets", {"name": name})
    assert status in (200, 409), f"CreateTableBucket answered {status}: {text[:400]}"
    if status == 409:
        assert "already exists" in text
    return f"arn:aws:s3tables:{REGION}:{ACCOUNT}:bucket/{name}"


def ensure_namespace(endpoint, namespace: str = NS) -> None:
    status, text = call(
        endpoint, "PUT", f"/namespaces/{path_arn(BUCKET_ARN)}", {"namespace": [namespace]}
    )
    assert status in (200, 409), f"CreateNamespace answered {status}: {text[:400]}"
    if status == 409:
        assert "already exists" in text


def ensure_table(endpoint, name: str = TABLE, namespace: str = NS) -> None:
    status, text = call(
        endpoint,
        "PUT",
        f"/tables/{path_arn(BUCKET_ARN)}/{namespace}",
        {"name": name, "format": "ICEBERG"},
    )
    assert status in (200, 409), f"CreateTable answered {status}: {text[:400]}"
    if status == 409:
        assert "already exists" in text


def ensure_world(endpoint) -> None:
    ensure_bucket(endpoint)
    ensure_namespace(endpoint)
    ensure_table(endpoint)


# ---------------------------------------------------------------------------
# Table buckets
# ---------------------------------------------------------------------------


def test_create_table_bucket_is_read_back_by_get(endpoint):
    arn = ensure_bucket(endpoint)
    bucket = ok(endpoint, "GET", f"/buckets/{path_arn(arn)}")
    assert bucket["name"] == BUCKET
    assert bucket["arn"] == arn
    assert bucket["type"] == "customer"


def test_list_table_buckets_includes_the_created_bucket(endpoint):
    ensure_bucket(endpoint)
    answer = ok(endpoint, "GET", "/buckets?maxBuckets=100")
    assert BUCKET in [bucket["name"] for bucket in answer["tableBuckets"]]


def test_get_table_bucket_reports_the_owner(endpoint):
    ensure_bucket(endpoint)
    bucket = ok(endpoint, "GET", f"/buckets/{path_arn(BUCKET_ARN)}")
    assert bucket["ownerAccountId"] == ACCOUNT
    assert bucket["tableBucketId"]


def test_delete_table_bucket_removes_the_bucket_it_created(endpoint):
    arn = ensure_bucket(endpoint, BUCKET_DOOMED)
    ok(endpoint, "DELETE", f"/buckets/{path_arn(arn)}")
    rejected(endpoint, "GET", f"/buckets/{path_arn(arn)}", status=404)


# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------


def test_create_namespace_is_read_back_by_get(endpoint):
    ensure_bucket(endpoint)
    ensure_namespace(endpoint)
    namespace = ok(endpoint, "GET", f"/namespaces/{path_arn(BUCKET_ARN)}/{NS}")
    assert namespace["namespace"] == [NS]
    assert namespace["createdBy"] == ACCOUNT


def test_list_namespaces_includes_the_created_namespace(endpoint):
    ensure_world(endpoint)
    answer = ok(endpoint, "GET", f"/namespaces/{path_arn(BUCKET_ARN)}?maxNamespaces=100")
    names = [item["namespace"][0] for item in answer["namespaces"]]
    assert NS in names


def test_get_namespace_reports_the_owner(endpoint):
    ensure_world(endpoint)
    namespace = ok(endpoint, "GET", f"/namespaces/{path_arn(BUCKET_ARN)}/{NS}")
    assert namespace["ownerAccountId"] == ACCOUNT
    assert namespace["createdAt"]


def test_delete_namespace_removes_the_namespace_it_created(endpoint):
    ensure_bucket(endpoint)
    ensure_namespace(endpoint, NS_DOOMED)
    ok(endpoint, "DELETE", f"/namespaces/{path_arn(BUCKET_ARN)}/{NS_DOOMED}")
    rejected(
        endpoint,
        "GET",
        f"/namespaces/{path_arn(BUCKET_ARN)}/{NS_DOOMED}",
        status=404,
    )


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def test_create_table_is_read_back_by_get(endpoint):
    ensure_world(endpoint)
    table = get_table(endpoint)
    assert table["name"] == TABLE
    assert table["format"] == "ICEBERG"
    assert table["namespace"] == [NS]
    assert table["tableARN"] == table_arn()


def test_list_tables_includes_the_created_table(endpoint):
    ensure_world(endpoint)
    answer = ok(endpoint, "GET", f"/tables/{path_arn(BUCKET_ARN)}?namespace={NS}")
    assert TABLE in [table["name"] for table in answer["tables"]]


def test_get_table_reports_the_table_arn_and_owner(endpoint):
    ensure_world(endpoint)
    table = get_table(endpoint)
    assert table["tableARN"] == table_arn()
    assert table["ownerAccountId"] == ACCOUNT
    assert table["versionToken"]


def test_delete_table_removes_the_table_it_created(endpoint):
    ensure_world(endpoint)
    ensure_table(endpoint, TABLE_DOOMED)
    ok(
        endpoint,
        "DELETE",
        f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE_DOOMED}",
    )
    query = urlencode(
        {"tableBucketARN": BUCKET_ARN, "namespace": NS, "name": TABLE_DOOMED}
    )
    rejected(endpoint, "GET", f"/get-table?{query}", status=404)


def test_get_table_metadata_location_reads_the_initial_location(endpoint):
    ensure_world(endpoint)
    location = ok(
        endpoint, "GET", f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/metadata-location"
    )
    assert location["versionToken"]
    assert location["metadataLocation"].startswith(f"s3://{BUCKET}/{NS}/{TABLE}/metadata/")
    assert location["warehouseLocation"] == f"s3://{BUCKET}/{NS}/{TABLE}"


def test_update_table_metadata_location_advances_the_token(endpoint):
    ensure_world(endpoint)
    path = f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/metadata-location"
    before = ok(endpoint, "GET", path)
    moved = "s3://" + BUCKET + "/" + NS + "/" + TABLE + "/metadata/v1.metadata.json"
    answer = ok(
        endpoint,
        "PUT",
        path,
        {"versionToken": before["versionToken"], "metadataLocation": moved},
    )
    assert answer["metadataLocation"] == moved
    assert answer["versionToken"] != before["versionToken"]
    assert ok(endpoint, "GET", path)["metadataLocation"] == moved


def test_rename_table_moves_the_table_to_its_new_name(endpoint):
    ensure_world(endpoint)
    ensure_table(endpoint, TABLE_RENAME)
    table = get_table(endpoint, NS, TABLE_RENAME)
    ok(
        endpoint,
        "PUT",
        f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE_RENAME}/rename",
        {"newName": TABLE_RENAMED, "versionToken": table["versionToken"]},
    )
    renamed = get_table(endpoint, NS, TABLE_RENAMED)
    assert renamed["name"] == TABLE_RENAMED
    assert renamed["versionToken"] != table["versionToken"]
    # The test removes only the table it renamed, so a re-run starts clean.
    ok(endpoint, "DELETE", f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE_RENAMED}")


# ---------------------------------------------------------------------------
# Table bucket configuration
# ---------------------------------------------------------------------------


def test_get_table_bucket_encryption_answers_a_configuration(endpoint):
    ensure_bucket(endpoint)
    answer = ok(endpoint, "GET", f"/buckets/{path_arn(BUCKET_ARN)}/encryption")
    assert answer["encryptionConfiguration"]["sseAlgorithm"]


def test_put_table_bucket_encryption_is_read_back(endpoint):
    ensure_bucket(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/buckets/{path_arn(BUCKET_ARN)}/encryption",
        {"encryptionConfiguration": KMS},
    )
    answer = ok(endpoint, "GET", f"/buckets/{path_arn(BUCKET_ARN)}/encryption")
    assert answer["encryptionConfiguration"] == KMS


def test_delete_table_bucket_encryption_returns_the_default(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/encryption"
    ok(endpoint, "PUT", path, {"encryptionConfiguration": KMS})
    ok(endpoint, "DELETE", path)
    answer = ok(endpoint, "GET", path)
    assert answer["encryptionConfiguration"]["sseAlgorithm"] == "AES256"


def test_get_table_bucket_maintenance_configuration_answers_the_defaults(endpoint):
    ensure_bucket(endpoint)
    answer = ok(endpoint, "GET", f"/buckets/{path_arn(BUCKET_ARN)}/maintenance")
    removal = answer["configuration"]["icebergUnreferencedFileRemoval"]
    assert removal["settings"]["icebergUnreferencedFileRemoval"]["unreferencedDays"] == 3


def test_put_table_bucket_maintenance_configuration_is_read_back(endpoint):
    ensure_bucket(endpoint)
    base = f"/buckets/{path_arn(BUCKET_ARN)}/maintenance"
    kind = "icebergUnreferencedFileRemoval"
    ok(endpoint, "PUT", f"{base}/{kind}", {"value": {"status": "disabled"}})
    assert (
        ok(endpoint, "GET", base)["configuration"][kind]["status"] == "disabled"
    )
    # Restore the default so the read test above still sees it on a re-run.
    ok(endpoint, "PUT", f"{base}/{kind}", {"value": {"status": "enabled"}})


def test_get_table_bucket_policy_reads_the_policy_it_puts(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/policy"
    ok(endpoint, "PUT", path, {"resourcePolicy": POLICY})
    assert ok(endpoint, "GET", path)["resourcePolicy"] == POLICY


def test_put_table_bucket_policy_replaces_the_policy(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/policy"
    replacement = json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Deny"}]})
    ok(endpoint, "PUT", path, {"resourcePolicy": replacement})
    assert ok(endpoint, "GET", path)["resourcePolicy"] == replacement


def test_delete_table_bucket_policy_removes_the_policy_it_created(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/policy"
    ok(endpoint, "PUT", path, {"resourcePolicy": POLICY})
    ok(endpoint, "DELETE", path)
    rejected(endpoint, "GET", path, status=404)


def test_get_table_bucket_storage_class_answers_a_configuration(endpoint):
    ensure_bucket(endpoint)
    answer = ok(endpoint, "GET", f"/buckets/{path_arn(BUCKET_ARN)}/storage-class")
    assert answer["storageClassConfiguration"]["storageClass"]


def test_put_table_bucket_storage_class_is_read_back(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/storage-class"
    ok(endpoint, "PUT", path, {"storageClassConfiguration": TIER})
    assert ok(endpoint, "GET", path)["storageClassConfiguration"] == TIER


def test_get_table_bucket_metrics_configuration_reads_the_id(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/metrics"
    ok(endpoint, "PUT", path)
    answer = ok(endpoint, "GET", path)
    assert answer["id"]
    assert answer["tableBucketARN"] == BUCKET_ARN


def test_put_table_bucket_metrics_configuration_answers_an_id(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/metrics"
    ok(endpoint, "PUT", path)
    assert ok(endpoint, "GET", path)["id"]


def test_delete_table_bucket_metrics_configuration_removes_the_configuration(endpoint):
    ensure_bucket(endpoint)
    path = f"/buckets/{path_arn(BUCKET_ARN)}/metrics"
    ok(endpoint, "PUT", path)
    ok(endpoint, "DELETE", path)
    rejected(endpoint, "GET", path, status=404)


# ---------------------------------------------------------------------------
# Table configuration
# ---------------------------------------------------------------------------


def test_get_table_encryption_answers_a_configuration(endpoint):
    ensure_world(endpoint)
    answer = ok(
        endpoint, "GET", f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/encryption"
    )
    assert answer["encryptionConfiguration"]["sseAlgorithm"]


def test_get_table_storage_class_answers_a_configuration(endpoint):
    ensure_world(endpoint)
    answer = ok(
        endpoint, "GET", f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/storage-class"
    )
    assert answer["storageClassConfiguration"]["storageClass"]


def test_get_table_maintenance_configuration_answers_the_defaults(endpoint):
    ensure_world(endpoint)
    answer = ok(
        endpoint, "GET", f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/maintenance"
    )
    compaction = answer["configuration"]["icebergCompaction"]
    assert compaction["settings"]["icebergCompaction"]["targetFileSizeMB"] == 512


def test_put_table_maintenance_configuration_is_read_back(endpoint):
    ensure_world(endpoint)
    base = f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/maintenance"
    kind = "icebergCompaction"
    ok(endpoint, "PUT", f"{base}/{kind}", {"value": {"status": "disabled"}})
    assert ok(endpoint, "GET", base)["configuration"][kind]["status"] == "disabled"
    # Restore the default so the read test above still sees it on a re-run.
    ok(endpoint, "PUT", f"{base}/{kind}", {"value": {"status": "enabled"}})


def test_get_table_maintenance_job_status_reports_never_run(endpoint):
    ensure_world(endpoint)
    answer = ok(
        endpoint,
        "GET",
        f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/maintenance-job-status",
    )
    assert answer["status"]["icebergCompaction"]["status"] == "Not_Yet_Run"
    assert set(answer["status"]) == {
        "icebergCompaction",
        "icebergSnapshotManagement",
        "icebergUnreferencedFileRemoval",
    }


def test_get_table_policy_reads_the_policy_it_puts(endpoint):
    ensure_world(endpoint)
    path = f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/policy"
    ok(endpoint, "PUT", path, {"resourcePolicy": POLICY})
    assert ok(endpoint, "GET", path)["resourcePolicy"] == POLICY


def test_put_table_policy_replaces_the_policy(endpoint):
    ensure_world(endpoint)
    path = f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/policy"
    replacement = json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow"}]})
    ok(endpoint, "PUT", path, {"resourcePolicy": replacement})
    assert ok(endpoint, "GET", path)["resourcePolicy"] == replacement


def test_delete_table_policy_removes_the_policy_it_created(endpoint):
    ensure_world(endpoint)
    path = f"/tables/{path_arn(BUCKET_ARN)}/{NS}/{TABLE}/policy"
    ok(endpoint, "PUT", path, {"resourcePolicy": POLICY})
    ok(endpoint, "DELETE", path)
    rejected(endpoint, "GET", path, status=404)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_adds_a_tag_the_list_reads_back(endpoint):
    ensure_bucket(endpoint)
    path = f"/tag/{path_arn(BUCKET_ARN)}"
    ok(endpoint, "POST", path, {"tags": {"env": "ops"}})
    assert ok(endpoint, "GET", path)["tags"]["env"] == "ops"


def test_list_tags_for_resource_shows_every_tag(endpoint):
    ensure_bucket(endpoint)
    path = f"/tag/{path_arn(BUCKET_ARN)}"
    ok(endpoint, "POST", path, {"tags": {"team": "platform"}})
    assert ok(endpoint, "GET", path)["tags"]["team"] == "platform"


def test_untag_resource_removes_the_key_it_names(endpoint):
    ensure_bucket(endpoint)
    path = f"/tag/{path_arn(BUCKET_ARN)}"
    ok(endpoint, "POST", path, {"tags": {"doomed": "yes"}})
    ok(endpoint, "DELETE", f"{path}?tagKeys=doomed")
    assert "doomed" not in ok(endpoint, "GET", path)["tags"]
