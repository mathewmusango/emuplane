"""AWS Budgets on the wire: all 16 advertised operations, JSON 1.1.

The target prefix is `AWSBudgetServiceGateway`. A budget is keyed by name, so a
stable budget carries the read, update and tag tests while a create or delete
test makes its own. Notifications are keyed by
`(type, operator, threshold, thresholdType)`, so the notification and subscriber
tests each build a fresh budget to stay independent across sweeps.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "AWSBudgetServiceGateway"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
BUDGET = "ops-budget"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "budgets", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, action: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, action, payload)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def body(name: str, amount: str = "100") -> dict:
    return {
        "BudgetName": name,
        "BudgetType": "COST",
        "TimeUnit": "MONTHLY",
        "BudgetLimit": {"Amount": amount, "Unit": "USD"},
    }


def create_budget(endpoint, name: str) -> str:
    ok(endpoint, "CreateBudget", {"Budget": body(name)})
    return name


def ensure_budget(endpoint, name: str = BUDGET) -> str:
    status, text = call(endpoint, "CreateBudget", {"Budget": body(name)})
    assert status == 200 or "DuplicateRecordException" in text, text[:300]
    ok(endpoint, "DescribeBudget", {"BudgetName": name})
    return name


def made_budget(endpoint) -> str:
    return create_budget(endpoint, f"ops-budget-made-{time.time_ns()}")


def arn(name: str) -> str:
    return f"arn:aws:budgets::{ACCOUNT}:budget/{name}"


def notification(threshold: float = 80.0) -> dict:
    return {
        "NotificationType": "ACTUAL",
        "ComparisonOperator": "GREATER_THAN",
        "Threshold": threshold,
        "ThresholdType": "PERCENTAGE",
    }


def subscriber(address: str = "ops@example.com") -> dict:
    return {"SubscriptionType": "EMAIL", "Address": address}


def notifications(endpoint, name: str) -> list[dict]:
    return ok(endpoint, "DescribeNotificationsForBudget", {"BudgetName": name})["Notifications"]


def subscribers(endpoint, name: str, note: dict) -> list[dict]:
    return ok(
        endpoint,
        "DescribeSubscribersForNotification",
        {"BudgetName": name, "Notification": note},
    )["Subscribers"]


def budget_with_notification(endpoint, threshold: float = 80.0) -> tuple[str, dict]:
    name = made_budget(endpoint)
    note = notification(threshold)
    ok(endpoint, "CreateNotification", {"BudgetName": name, "Notification": note, "Subscribers": [subscriber()]})
    return name, note


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


def test_create_budget_is_read_back(endpoint):
    name = made_budget(endpoint)
    assert ok(endpoint, "DescribeBudget", {"BudgetName": name})["Budget"]["BudgetName"] == name


def test_describe_budget_reads_the_budget(endpoint):
    name = ensure_budget(endpoint)
    budget = ok(endpoint, "DescribeBudget", {"BudgetName": name})["Budget"]
    assert budget["BudgetType"] == "COST"
    assert budget["BudgetLimit"]["Unit"] == "USD"
    assert float(budget["BudgetLimit"]["Amount"]) > 0


def test_describe_budgets_lists_the_budget(endpoint):
    name = ensure_budget(endpoint)
    assert name in {item["BudgetName"] for item in ok(endpoint, "DescribeBudgets")["Budgets"]}


def test_update_budget_changes_the_limit(endpoint):
    name = ensure_budget(endpoint)
    updated = body(name, "200")
    ok(endpoint, "UpdateBudget", {"NewBudget": updated})
    assert ok(endpoint, "DescribeBudget", {"BudgetName": name})["Budget"]["BudgetLimit"]["Amount"] == "200"


def test_delete_budget_removes_the_budget_it_created(endpoint):
    name = made_budget(endpoint)
    ok(endpoint, "DeleteBudget", {"BudgetName": name})
    refused(endpoint, "DescribeBudget", {"BudgetName": name}, "NotFoundException")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def test_create_notification_is_read_back(endpoint):
    name = made_budget(endpoint)
    note = notification(80.0)
    ok(endpoint, "CreateNotification", {"BudgetName": name, "Notification": note, "Subscribers": [subscriber()]})
    assert 80.0 in {item["Threshold"] for item in notifications(endpoint, name)}


def test_delete_notification_removes_the_one_it_created(endpoint):
    name = made_budget(endpoint)
    note = notification(90.0)
    ok(endpoint, "CreateNotification", {"BudgetName": name, "Notification": note, "Subscribers": [subscriber()]})
    ok(endpoint, "DeleteNotification", {"BudgetName": name, "Notification": note})
    assert 90.0 not in {item["Threshold"] for item in notifications(endpoint, name)}


def test_update_notification_changes_the_threshold(endpoint):
    name = made_budget(endpoint)
    old = notification(80.0)
    new = notification(90.0)
    ok(endpoint, "CreateNotification", {"BudgetName": name, "Notification": old, "Subscribers": [subscriber()]})
    ok(endpoint, "UpdateNotification", {"BudgetName": name, "OldNotification": old, "NewNotification": new})
    thresholds = {item["Threshold"] for item in notifications(endpoint, name)}
    assert 90.0 in thresholds
    assert 80.0 not in thresholds


def test_describe_notifications_for_budget_lists_the_notification(endpoint):
    name, note = budget_with_notification(endpoint, 80.0)
    assert note["Threshold"] in {item["Threshold"] for item in notifications(endpoint, name)}


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------


def test_create_subscriber_is_read_back(endpoint):
    name = made_budget(endpoint)
    note = notification()
    ok(endpoint, "CreateNotification", {"BudgetName": name, "Notification": note, "Subscribers": [subscriber("seed@example.com")]})
    ok(
        endpoint,
        "CreateSubscriber",
        {"BudgetName": name, "Notification": note, "Subscriber": subscriber("ops@example.com")},
    )
    assert "ops@example.com" in {item["Address"] for item in subscribers(endpoint, name, note)}


def test_delete_subscriber_removes_the_one_it_created(endpoint):
    name = made_budget(endpoint)
    note = notification()
    ok(endpoint, "CreateNotification", {"BudgetName": name, "Notification": note, "Subscribers": [subscriber("seed@example.com")]})
    ok(endpoint, "CreateSubscriber", {"BudgetName": name, "Notification": note, "Subscriber": subscriber("doomed@example.com")})
    ok(
        endpoint,
        "DeleteSubscriber",
        {"BudgetName": name, "Notification": note, "Subscriber": subscriber("doomed@example.com")},
    )
    assert "doomed@example.com" not in {item["Address"] for item in subscribers(endpoint, name, note)}


def test_update_subscriber_changes_the_address(endpoint):
    name = made_budget(endpoint)
    note = notification()
    ok(endpoint, "CreateNotification", {"BudgetName": name, "Notification": note, "Subscribers": [subscriber("old@example.com")]})
    ok(
        endpoint,
        "UpdateSubscriber",
        {
            "BudgetName": name,
            "Notification": note,
            "OldSubscriber": subscriber("old@example.com"),
            "NewSubscriber": subscriber("new@example.com"),
        },
    )
    addresses = {item["Address"] for item in subscribers(endpoint, name, note)}
    assert "new@example.com" in addresses
    assert "old@example.com" not in addresses


def test_describe_subscribers_for_notification_lists_the_subscriber(endpoint):
    name, note = budget_with_notification(endpoint, 80.0)
    assert "ops@example.com" in {item["Address"] for item in subscribers(endpoint, name, note)}


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    name = ensure_budget(endpoint)
    ok(endpoint, "TagResource", {"ResourceARN": arn(name), "ResourceTags": [{"Key": "env", "Value": "ops"}]})
    tags = ok(endpoint, "ListTagsForResource", {"ResourceARN": arn(name)})["ResourceTags"]
    assert {"Key": "env", "Value": "ops"} in tags


def test_untag_resource_removes_the_key_it_names(endpoint):
    name = ensure_budget(endpoint)
    ok(endpoint, "TagResource", {"ResourceARN": arn(name), "ResourceTags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "UntagResource", {"ResourceARN": arn(name), "ResourceTagKeys": ["doomed"]})
    keys = {tag["Key"] for tag in ok(endpoint, "ListTagsForResource", {"ResourceARN": arn(name)})["ResourceTags"]}
    assert "doomed" not in keys


def test_list_tags_for_resource_lists_the_tags(endpoint):
    name = ensure_budget(endpoint)
    ok(endpoint, "TagResource", {"ResourceARN": arn(name), "ResourceTags": [{"Key": "team", "Value": "platform"}]})
    tags = ok(endpoint, "ListTagsForResource", {"ResourceARN": arn(name)})["ResourceTags"]
    assert {"Key": "team", "Value": "platform"} in tags
