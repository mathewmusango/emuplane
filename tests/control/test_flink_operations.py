"""Managed Service for Apache Flink on the wire: all 15 advertised operations, JSON 1.1.

The target prefix is `KinesisAnalytics_20180523` and the credential scope is
`kinesisanalytics`. An application is a record, so without a data plane a
transitional status settles on the next read (`STARTING` and `UPDATING` become
`RUNNING`, `STOPPING` and `FORCE_STOPPING` become `READY`); the runtime used here
has no job image, which keeps these tests on the control plane. Snapshots,
logging options and tags are records too, and every delete test creates its own
to remove.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "KinesisAnalytics_20180523"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
ROLE = f"arn:aws:iam::{ACCOUNT}:role/ops-flink-role"
# No image is published for this runtime, so StartApplication never launches a job here.
RUNTIME = "FLINK-1_18"

APP = "ops-flink-app"
DELETE_APP = "ops-flink-delete"
LOGGING_APP = "ops-flink-logging"
LOGGING_DELETE_APP = "ops-flink-logging-delete"
SNAPSHOT = "ops-flink-snapshot"
DELETE_SNAPSHOT = "ops-flink-snapshot-delete"
LOG_STREAM = f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:ops-flink:log-stream:ops"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "kinesisanalytics", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def created(endpoint, action: str, payload: dict) -> tuple[int, str]:
    """A create is idempotent across sweeps: an existing record is not a failure."""
    status, text = call(endpoint, action, payload)
    assert status == 200 or "ResourceInUseException" in text, (
        f"{action} answered {status}: {text[:400]}"
    )
    return status, text


def detail(endpoint, name: str = APP) -> dict:
    return ok(endpoint, "DescribeApplication", {"ApplicationName": name})["ApplicationDetail"]


def ensure_application(endpoint, name: str = APP) -> dict:
    created(
        endpoint,
        "CreateApplication",
        {
            "ApplicationName": name,
            "RuntimeEnvironment": RUNTIME,
            "ServiceExecutionRole": ROLE,
        },
    )
    return detail(endpoint, name)


def ensure_ready(endpoint, name: str = APP) -> dict:
    application = ensure_application(endpoint, name)
    if application["ApplicationStatus"] == "RUNNING":
        ok(endpoint, "StopApplication", {"ApplicationName": name})
        application = detail(endpoint, name)
    return application


def ensure_running(endpoint, name: str = APP) -> dict:
    ensure_ready(endpoint, name)
    ok(
        endpoint,
        "StartApplication",
        {
            "ApplicationName": name,
            "RunConfiguration": {
                "ApplicationRestoreConfiguration": {
                    "ApplicationRestoreType": "SKIP_RESTORE_FROM_SNAPSHOT"
                }
            },
        },
    )
    return detail(endpoint, name)


def ensure_snapshot(endpoint, name: str = APP, snapshot: str = SNAPSHOT) -> dict:
    ensure_running(endpoint, name)
    created(endpoint, "CreateApplicationSnapshot", {"ApplicationName": name, "SnapshotName": snapshot})
    return ok(
        endpoint, "DescribeApplicationSnapshot", {"ApplicationName": name, "SnapshotName": snapshot}
    )["SnapshotDetails"]


def add_logging_option(endpoint, name: str) -> tuple[int, str]:
    """An application carries one logging option: a repeat add means it is already there."""
    status, text = call(
        endpoint,
        "AddApplicationCloudWatchLoggingOption",
        {"ApplicationName": name, "CloudWatchLoggingOption": {"LogStreamARN": LOG_STREAM}},
    )
    assert status == 200 or "only 1 logging option" in text, (
        f"AddApplicationCloudWatchLoggingOption answered {status}: {text[:400]}"
    )
    return status, text


# --- Applications -----------------------------------------------------------


def test_create_application_is_read_back(endpoint):
    application = ensure_application(endpoint, "ops-flink-create")
    assert application["ApplicationName"] == "ops-flink-create"
    assert application["RuntimeEnvironment"] == RUNTIME
    assert application["ApplicationStatus"] == "READY"
    assert application["ApplicationARN"].endswith(":application/ops-flink-create")


def test_describe_application_reports_its_runtime(endpoint):
    ensure_application(endpoint)
    application = detail(endpoint, APP)
    assert application["ApplicationName"] == APP
    assert application["RuntimeEnvironment"] == RUNTIME
    assert application["ServiceExecutionRole"] == ROLE
    assert application["ApplicationVersionId"] >= 1


def test_update_application_bumps_the_version(endpoint):
    before = ensure_ready(endpoint)
    answer = ok(
        endpoint,
        "UpdateApplication",
        {
            "ApplicationName": APP,
            "CurrentApplicationVersionId": before["ApplicationVersionId"],
            "ApplicationConfigurationUpdate": {
                "FlinkApplicationConfigurationUpdate": {
                    "ParallelismConfigurationUpdate": {
                        "ConfigurationTypeUpdate": "CUSTOM",
                        "ParallelismUpdate": 2,
                        "ParallelismPerKPUUpdate": 1,
                        "AutoScalingEnabledUpdate": False,
                    }
                }
            },
        },
    )
    updated = answer["ApplicationDetail"]
    assert updated["ApplicationVersionId"] == before["ApplicationVersionId"] + 1
    assert answer["OperationId"]
    parallelism = updated["ApplicationConfigurationDescription"][
        "FlinkApplicationConfigurationDescription"
    ]["ParallelismConfigurationDescription"]
    assert parallelism["Parallelism"] == 2


def test_delete_application_removes_it(endpoint):
    application = ensure_application(endpoint, DELETE_APP)
    ok(
        endpoint,
        "DeleteApplication",
        {
            "ApplicationName": DELETE_APP,
            "CreateTimestamp": application["CreateTimestamp"],
        },
    )
    status, text = call(endpoint, "DescribeApplication", {"ApplicationName": DELETE_APP})
    assert status == 400 and "ResourceNotFoundException" in text, text[:300]


# --- Start and stop ---------------------------------------------------------


def test_start_application_reaches_running(endpoint):
    ensure_ready(endpoint)
    answer = ok(
        endpoint,
        "StartApplication",
        {
            "ApplicationName": APP,
            "RunConfiguration": {
                "ApplicationRestoreConfiguration": {
                    "ApplicationRestoreType": "SKIP_RESTORE_FROM_SNAPSHOT"
                }
            },
        },
    )
    assert answer["OperationId"]
    assert detail(endpoint, APP)["ApplicationStatus"] == "RUNNING"


def test_stop_application_returns_to_ready(endpoint):
    ensure_running(endpoint)
    answer = ok(endpoint, "StopApplication", {"ApplicationName": APP})
    assert answer["OperationId"]
    assert detail(endpoint, APP)["ApplicationStatus"] == "READY"


# --- Snapshots --------------------------------------------------------------


def test_create_application_snapshot_is_read_back(endpoint):
    ensure_running(endpoint)
    created(
        endpoint,
        "CreateApplicationSnapshot",
        {"ApplicationName": APP, "SnapshotName": SNAPSHOT},
    )
    snapshot = ok(
        endpoint, "DescribeApplicationSnapshot", {"ApplicationName": APP, "SnapshotName": SNAPSHOT}
    )["SnapshotDetails"]
    assert snapshot["SnapshotName"] == SNAPSHOT
    assert snapshot["SnapshotStatus"] == "READY"


def test_list_application_snapshots_names_the_snapshot(endpoint):
    ensure_snapshot(endpoint)
    listed = ok(endpoint, "ListApplicationSnapshots", {"ApplicationName": APP})
    assert SNAPSHOT in {item["SnapshotName"] for item in listed["SnapshotSummaries"]}


def test_describe_application_snapshot_reports_its_version(endpoint):
    snapshot = ensure_snapshot(endpoint)
    assert snapshot["SnapshotName"] == SNAPSHOT
    assert snapshot["RuntimeEnvironment"] == RUNTIME
    assert snapshot["ApplicationVersionId"] >= 1


def test_delete_application_snapshot_removes_it(endpoint):
    snapshot = ensure_snapshot(endpoint, APP, DELETE_SNAPSHOT)
    ok(
        endpoint,
        "DeleteApplicationSnapshot",
        {
            "ApplicationName": APP,
            "SnapshotName": DELETE_SNAPSHOT,
            "SnapshotCreationTimestamp": snapshot["SnapshotCreationTimestamp"],
        },
    )
    status, text = call(
        endpoint,
        "DescribeApplicationSnapshot",
        {"ApplicationName": APP, "SnapshotName": DELETE_SNAPSHOT},
    )
    assert status == 400 and "ResourceNotFoundException" in text, text[:300]


# --- CloudWatch logging options ---------------------------------------------


def test_add_application_cloud_watch_logging_option_is_read_back(endpoint):
    ensure_application(endpoint, LOGGING_APP)
    add_logging_option(endpoint, LOGGING_APP)
    options = detail(endpoint, LOGGING_APP)["CloudWatchLoggingOptionDescriptions"]
    assert [option["LogStreamARN"] for option in options] == [LOG_STREAM]


def test_delete_application_cloud_watch_logging_option_removes_it(endpoint):
    ensure_application(endpoint, LOGGING_DELETE_APP)
    add_logging_option(endpoint, LOGGING_DELETE_APP)
    options = detail(endpoint, LOGGING_DELETE_APP)["CloudWatchLoggingOptionDescriptions"]
    answer = ok(
        endpoint,
        "DeleteApplicationCloudWatchLoggingOption",
        {
            "ApplicationName": LOGGING_DELETE_APP,
            "CloudWatchLoggingOptionId": options[0]["CloudWatchLoggingOptionId"],
        },
    )
    assert answer["ApplicationARN"].endswith(f":application/{LOGGING_DELETE_APP}")
    assert detail(endpoint, LOGGING_DELETE_APP)["CloudWatchLoggingOptionDescriptions"] == []


# --- Tags -------------------------------------------------------------------


def test_tag_resource_adds_a_tag(endpoint):
    resource = ensure_application(endpoint)["ApplicationARN"]
    ok(
        endpoint,
        "TagResource",
        {"ResourceARN": resource, "Tags": [{"Key": "team", "Value": "ops"}]},
    )
    tags = ok(endpoint, "ListTagsForResource", {"ResourceARN": resource})["Tags"]
    assert {"Key": "team", "Value": "ops"} in tags


def test_untag_resource_removes_the_key(endpoint):
    resource = ensure_application(endpoint)["ApplicationARN"]
    ok(
        endpoint,
        "TagResource",
        {"ResourceARN": resource, "Tags": [{"Key": "temporary", "Value": "yes"}]},
    )
    ok(endpoint, "UntagResource", {"ResourceARN": resource, "TagKeys": ["temporary"]})
    tags = ok(endpoint, "ListTagsForResource", {"ResourceARN": resource})["Tags"]
    assert "temporary" not in {tag["Key"] for tag in tags}


def test_list_tags_for_resource_reports_the_application(endpoint):
    resource = ensure_application(endpoint)["ApplicationARN"]
    ok(
        endpoint,
        "TagResource",
        {"ResourceARN": resource, "Tags": [{"Key": "env", "Value": "test"}]},
    )
    tags = {tag["Key"]: tag["Value"] for tag in ok(endpoint, "ListTagsForResource", {"ResourceARN": resource})["Tags"]}
    assert tags["env"] == "test"
