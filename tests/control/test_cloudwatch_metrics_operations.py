"""CloudWatch Metrics on the wire: all 20 advertised operations, JSON protocol.

Every call is signed with the ``monitoring`` credential scope and addressed by
``X-Amz-Target: GraniteServiceVersion20100801.<Action>``. The emulator also answers
CBOR and the legacy Query protocol; this module pins the JSON surface.

Published data points are additive, so a re-run adds to what the first sweep
wrote. The statistics tests therefore aggregate the returned points and assert a
floor rather than an exact total. Alarms and dashboards are upserts; a delete
action builds a resource of its own (the ``doomed`` names) and removes only that.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "GraniteServiceVersion20100801."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

NS = "Ops/CloudWatch"
METRIC = "OpsMetric"
DIMENSIONS = [{"Name": "Env", "Value": "ops"}]
UNIT = "Count"

ALARM = "ops-cw-alarm"
ALARM_DOOMED = "ops-cw-alarm-doomed"
COMPOSITE = "ops-cw-composite"
ALARM_ARN = f"arn:aws:cloudwatch:{REGION}:{ACCOUNT}:alarm:{ALARM}"

DASHBOARD = "ops-cw-dashboard"
DASHBOARD_DOOMED = "ops-cw-dashboard-doomed"
DASHBOARD_BODY = '{"widgets": []}'


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "monitoring", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def rejected(endpoint, action: str, status: int, **params) -> str:
    got, text = call(endpoint, action, **params)
    assert got == status, f"{action} answered {got}: {text[:400]}"
    return text


def window() -> tuple[int, int]:
    """An hour either side of now, so a point published at any second is in range."""
    now = int(time.time())
    return now - 3600, now + 3600


def publish(endpoint, name: str = METRIC, value: float = 5.0) -> None:
    ok(
        endpoint,
        "PutMetricData",
        Namespace=NS,
        MetricData=[
            {
                "MetricName": name,
                "Value": value,
                "Unit": UNIT,
                "Dimensions": DIMENSIONS,
                "Timestamp": int(time.time()),
            }
        ],
    )


def ensure_alarm(endpoint, name: str = ALARM) -> None:
    ok(
        endpoint,
        "PutMetricAlarm",
        AlarmName=name,
        AlarmDescription="ops alarm",
        MetricName=METRIC,
        Namespace=NS,
        Statistic="Sum",
        Period=60,
        EvaluationPeriods=1,
        Threshold=10.0,
        ComparisonOperator="GreaterThanThreshold",
        Dimensions=DIMENSIONS,
    )


def alarms(endpoint, **params) -> dict:
    """DescribeAlarms, keyed by name, over both alarm types."""
    answer = ok(endpoint, "DescribeAlarms", **params)
    found = {
        alarm["AlarmName"]: alarm
        for key in ("MetricAlarms", "CompositeAlarms")
        for alarm in answer.get(key, [])
    }
    return found


# ---------------------------------------------------------------------------
# Metric data
# ---------------------------------------------------------------------------


def test_put_metric_data_is_read_back_by_list_metrics(endpoint):
    publish(endpoint)
    answer = ok(endpoint, "ListMetrics", Namespace=NS)
    names = [metric["MetricName"] for metric in answer["Metrics"]]
    assert METRIC in names


def test_get_metric_statistics_aggregates_the_published_point(endpoint):
    publish(endpoint)
    start, end = window()
    answer = ok(
        endpoint,
        "GetMetricStatistics",
        Namespace=NS,
        MetricName=METRIC,
        StartTime=start,
        EndTime=end,
        Period=60,
        Statistics=["Sum", "Average"],
        Dimensions=DIMENSIONS,
    )
    assert answer["Label"] == METRIC
    assert answer["Datapoints"]
    assert sum(point["Sum"] for point in answer["Datapoints"]) >= 5.0
    # Every point published here is the same value, so a bucket's average is that value.
    assert all(point["Average"] == 5.0 for point in answer["Datapoints"])
    assert all(point["Unit"] == UNIT for point in answer["Datapoints"])


def test_get_metric_data_answers_a_complete_series(endpoint):
    publish(endpoint)
    start, end = window()
    answer = ok(
        endpoint,
        "GetMetricData",
        MetricDataQueries=[
            {
                "Id": "m1",
                "MetricStat": {
                    "Metric": {"Namespace": NS, "MetricName": METRIC, "Dimensions": DIMENSIONS},
                    "Period": 60,
                    "Stat": "Sum",
                },
            }
        ],
        StartTime=start,
        EndTime=end,
    )
    result = answer["MetricDataResults"][0]
    assert result["Id"] == "m1"
    assert result["StatusCode"] == "Complete"
    assert sum(result["Values"]) >= 5.0


def test_list_metrics_includes_the_published_metric(endpoint):
    publish(endpoint)
    answer = ok(endpoint, "ListMetrics", Namespace=NS)
    metric = next(m for m in answer["Metrics"] if m["MetricName"] == METRIC)
    assert metric["Namespace"] == NS
    assert metric["Dimensions"] == DIMENSIONS


# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------


def test_put_metric_alarm_is_read_back_by_describe_alarms(endpoint):
    ensure_alarm(endpoint)
    found = alarms(endpoint, AlarmNames=[ALARM])
    assert ALARM in found
    assert found[ALARM]["Namespace"] == NS
    assert found[ALARM]["MetricName"] == METRIC
    assert found[ALARM]["Threshold"] == 10.0


def test_put_composite_alarm_is_read_back_by_describe_alarms(endpoint):
    ensure_alarm(endpoint)
    ok(endpoint, "PutCompositeAlarm", AlarmName=COMPOSITE, AlarmRule=f'ALARM("{ALARM}")')
    found = alarms(endpoint, AlarmNames=[COMPOSITE], AlarmTypes=["CompositeAlarm"])
    assert found[COMPOSITE]["AlarmRule"] == f'ALARM("{ALARM}")'


def test_describe_alarms_reports_the_alarm_shape(endpoint):
    ensure_alarm(endpoint)
    found = alarms(endpoint, AlarmNames=[ALARM])
    assert found[ALARM]["AlarmArn"] == ALARM_ARN
    assert found[ALARM]["ComparisonOperator"] == "GreaterThanThreshold"
    assert found[ALARM]["Dimensions"] == DIMENSIONS


def test_describe_alarms_for_metric_finds_the_alarm(endpoint):
    ensure_alarm(endpoint)
    answer = ok(endpoint, "DescribeAlarmsForMetric", Namespace=NS, MetricName=METRIC)
    assert ALARM in [alarm["AlarmName"] for alarm in answer["MetricAlarms"]]


def test_describe_alarm_history_records_a_state_change(endpoint):
    ensure_alarm(endpoint)
    # Two transitions guarantee an entry whatever state the previous sweep left.
    ok(endpoint, "SetAlarmState", AlarmName=ALARM, StateValue="ALARM", StateReason="ops history")
    ok(endpoint, "SetAlarmState", AlarmName=ALARM, StateValue="OK", StateReason="ops history")
    answer = ok(endpoint, "DescribeAlarmHistory", AlarmName=ALARM)
    assert answer["AlarmHistoryItems"]
    assert {item["AlarmName"] for item in answer["AlarmHistoryItems"]} == {ALARM}


def test_delete_alarms_removes_the_alarm_it_created(endpoint):
    ensure_alarm(endpoint, ALARM_DOOMED)
    ok(endpoint, "DeleteAlarms", AlarmNames=[ALARM_DOOMED])
    assert ALARM_DOOMED not in alarms(endpoint, AlarmNames=[ALARM_DOOMED])


def test_set_alarm_state_is_read_back_by_describe_alarms(endpoint):
    ensure_alarm(endpoint)
    ok(endpoint, "SetAlarmState", AlarmName=ALARM, StateValue="ALARM", StateReason="ops set state")
    assert alarms(endpoint, AlarmNames=[ALARM])[ALARM]["StateValue"] == "ALARM"


def test_enable_alarm_actions_turns_actions_on(endpoint):
    ensure_alarm(endpoint)
    ok(endpoint, "DisableAlarmActions", AlarmNames=[ALARM])
    ok(endpoint, "EnableAlarmActions", AlarmNames=[ALARM])
    assert alarms(endpoint, AlarmNames=[ALARM])[ALARM]["ActionsEnabled"] is True


def test_disable_alarm_actions_turns_actions_off(endpoint):
    ensure_alarm(endpoint)
    ok(endpoint, "DisableAlarmActions", AlarmNames=[ALARM])
    assert alarms(endpoint, AlarmNames=[ALARM])[ALARM]["ActionsEnabled"] is False


# ---------------------------------------------------------------------------
# Tags (on an alarm ARN)
# ---------------------------------------------------------------------------


def test_tag_resource_adds_a_tag_the_list_reads_back(endpoint):
    ensure_alarm(endpoint)
    ok(endpoint, "TagResource", ResourceARN=ALARM_ARN, Tags=[{"Key": "env", "Value": "ops"}])
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=ALARM_ARN)
    assert {"Key": "env", "Value": "ops"} in answer["Tags"]


def test_untag_resource_removes_the_key_it_names(endpoint):
    ensure_alarm(endpoint)
    ok(endpoint, "TagResource", ResourceARN=ALARM_ARN, Tags=[{"Key": "doomed", "Value": "yes"}])
    ok(endpoint, "UntagResource", ResourceARN=ALARM_ARN, TagKeys=["doomed"])
    assert "doomed" not in {tag["Key"] for tag in ok(endpoint, "ListTagsForResource", ResourceARN=ALARM_ARN)["Tags"]}


def test_list_tags_for_resource_shows_the_tags(endpoint):
    ensure_alarm(endpoint)
    ok(endpoint, "TagResource", ResourceARN=ALARM_ARN, Tags=[{"Key": "team", "Value": "platform"}])
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=ALARM_ARN)
    assert {"Key": "team", "Value": "platform"} in answer["Tags"]


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------


def test_put_dashboard_is_read_back_by_get(endpoint):
    answer = ok(endpoint, "PutDashboard", DashboardName=DASHBOARD, DashboardBody=DASHBOARD_BODY)
    assert answer["DashboardValidationMessages"] == []
    dashboard = ok(endpoint, "GetDashboard", DashboardName=DASHBOARD)
    assert dashboard["DashboardBody"] == DASHBOARD_BODY


def test_get_dashboard_reports_the_name_and_arn(endpoint):
    ok(endpoint, "PutDashboard", DashboardName=DASHBOARD, DashboardBody=DASHBOARD_BODY)
    dashboard = ok(endpoint, "GetDashboard", DashboardName=DASHBOARD)
    assert dashboard["DashboardName"] == DASHBOARD
    assert dashboard["DashboardArn"].endswith(f"dashboard/{DASHBOARD}")


def test_delete_dashboards_removes_the_dashboard_it_created(endpoint):
    ok(endpoint, "PutDashboard", DashboardName=DASHBOARD_DOOMED, DashboardBody=DASHBOARD_BODY)
    ok(endpoint, "DeleteDashboards", DashboardNames=[DASHBOARD_DOOMED])
    rejected(endpoint, "GetDashboard", 404, DashboardName=DASHBOARD_DOOMED)


def test_list_dashboards_includes_the_dashboard(endpoint):
    ok(endpoint, "PutDashboard", DashboardName=DASHBOARD, DashboardBody=DASHBOARD_BODY)
    answer = ok(endpoint, "ListDashboards", DashboardNamePrefix="ops-cw-")
    assert DASHBOARD in [entry["DashboardName"] for entry in answer["DashboardEntries"]]
