"""AmazonMQ on the wire: every advertised operation, driven through the REST protocol.

MQ is metadata only, so nothing here expects a broker process to answer. A broker created
here is left in place; each delete action creates a resource of its own and removes that.
"""

from __future__ import annotations

import json
from urllib.parse import quote

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}

# Stable names and values, so a lab sweep that re-runs finds instead of conflicting.
SHARED = "ops-mq-shared"
CREATED = "ops-mq-created"
DELETED = "ops-mq-deleted"
ADMIN = "ops-mq-admin"
USER = "ops-mq-user"
DELETED_USER = "ops-mq-user-deleted"

SHARED_CONFIG = {
    "engineType": "ACTIVEMQ",
    "engineVersion": "5.19",
    "deploymentMode": "SINGLE_INSTANCE",
    "hostInstanceType": "mq.m5.large",
    "autoMinorVersionUpgrade": True,
    "publiclyAccessible": False,
    "users": [
        {
            "username": ADMIN,
            "password": "OpsMqAdmin123",
            "consoleAccess": True,
            "groups": ["admins"],
        }
    ],
    "tags": {"owner": "emuplane"},
}


def call(endpoint, method: str, path: str, body=""):
    return signed.request(
        endpoint, "mq", ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = call(endpoint, method, path, body)
    assert status in (200, 204), f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text) if text.strip() else {}


def brokers(endpoint) -> list[dict]:
    """Every page of ListBrokers: a lab may hold more than one page of them."""
    found: list[dict] = []
    path = "/v1/brokers?maxResults=100"
    while path:
        answer = ok(endpoint, "GET", path)
        found.extend(answer["brokerSummaries"])
        token = answer.get("nextToken")
        path = f"/v1/brokers?maxResults=100&nextToken={token}" if token else ""
    return found


def broker(endpoint, name: str) -> str | None:
    return next(
        (row["brokerId"] for row in brokers(endpoint) if row["brokerName"] == name),
        None,
    )


def ensure_broker(endpoint, name: str) -> str:
    """Find-or-create: a re-run finds the broker an earlier sweep deliberately left behind."""
    found = broker(endpoint, name)
    if found:
        return found
    body = json.dumps(dict(SHARED_CONFIG, brokerName=name))
    status, text = call(endpoint, "POST", "/v1/brokers", body)
    # The name is the address, so a concurrent sweep's create is the resource we want.
    assert status == 200 or "already exists" in text, f"CreateBroker answered {status}: {text[:400]}"
    found = broker(endpoint, name)
    assert found, "the created broker is not in ListBrokers"
    return found


def described(endpoint, broker_id: str) -> dict:
    return ok(endpoint, "GET", f"/v1/brokers/{broker_id}")


def broker_arn(endpoint, broker_id: str) -> str:
    return described(endpoint, broker_id)["brokerArn"]


def tags_path(resource_arn: str) -> str:
    return "/v1/tags/" + quote(resource_arn, safe="")


def users_path(broker_id: str) -> str:
    return f"/v1/brokers/{broker_id}/users"


def user_path(broker_id: str, username: str) -> str:
    return f"{users_path(broker_id)}/{quote(username, safe='')}"


def ensure_user(
    endpoint, broker_id: str, username: str, password: str, groups: list[str]
) -> None:
    """Find-or-create: the same user on a second sweep is the one the first left."""
    existing = [row["username"] for row in ok(endpoint, "GET", users_path(broker_id))["users"]]
    if username in existing:
        return
    body = json.dumps({"password": password, "consoleAccess": True, "groups": groups})
    status, text = call(endpoint, "POST", user_path(broker_id, username), body)
    assert status == 200 or "already exists" in text, f"CreateUser answered {status}: {text[:400]}"


def test_create_broker_is_read_back_by_describe(s3_endpoint):
    status, text = call(
        s3_endpoint, "POST", "/v1/brokers", json.dumps(dict(SHARED_CONFIG, brokerName=CREATED))
    )
    if status == 200:
        answer = json.loads(text)
        assert answer["brokerArn"].endswith(f":broker:{answer['brokerId']}")
        created = answer["brokerId"]
    else:
        # A re-run meets the broker it created before, addressed by its own name.
        assert status == 409 and "already exists" in text, text[:400]
        created = broker(s3_endpoint, CREATED)
        assert created
    assert described(s3_endpoint, created)["brokerName"] == CREATED


def test_list_brokers_summarises_the_shared_broker(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    row = next(row for row in brokers(s3_endpoint) if row["brokerId"] == shared)
    assert row["brokerName"] == SHARED
    assert row["engineType"] == "ACTIVEMQ"
    assert row["deploymentMode"] == "SINGLE_INSTANCE"
    assert row["hostInstanceType"] == "mq.m5.large"
    assert row["brokerState"]


def test_list_brokers_refuses_a_page_below_the_floor(s3_endpoint):
    status, text = call(s3_endpoint, "GET", "/v1/brokers?maxResults=1")
    assert status == 400
    assert "maxResults must be an integer from 5 to 100" in text


def test_describe_broker_returns_the_configuration_it_created(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    answer = described(s3_endpoint, shared)
    assert answer["brokerId"] == shared
    assert answer["brokerName"] == SHARED
    assert answer["engineType"] == "ACTIVEMQ"
    assert answer["engineVersion"] == "5.19"
    assert answer["brokerArn"] == f"arn:aws:mq:{REGION}:{ACCOUNT}:broker:{shared}"
    assert ADMIN in [user["username"] for user in answer["users"]]
    assert answer["tags"]["owner"] == "emuplane"
    assert call(s3_endpoint, "GET", "/v1/brokers/ops-mq-does-not-exist")[0] == 404


def test_delete_broker_removes_the_broker_it_created(s3_endpoint):
    doomed = ensure_broker(s3_endpoint, DELETED)
    answer = ok(s3_endpoint, "DELETE", f"/v1/brokers/{doomed}")
    assert answer["brokerId"] == doomed
    assert broker(s3_endpoint, DELETED) is None
    assert call(s3_endpoint, "GET", f"/v1/brokers/{doomed}")[0] == 404


def test_update_broker_is_read_back_by_describe(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    body = json.dumps({"logs": {"general": True}, "autoMinorVersionUpgrade": True})
    answer = ok(s3_endpoint, "PUT", f"/v1/brokers/{shared}", body)
    assert answer["brokerId"] == shared
    assert answer["logs"] == {"general": True}
    after = described(s3_endpoint, shared)
    assert after["logs"] == {"general": True}
    assert after["autoMinorVersionUpgrade"] is True


def test_reboot_broker_answers_for_the_shared_broker(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    assert ok(s3_endpoint, "POST", f"/v1/brokers/{shared}/reboot") == {}


def test_describe_broker_engine_types_lists_activemq_versions(s3_endpoint):
    answer = ok(s3_endpoint, "GET", "/v1/broker-engine-types?engineType=ACTIVEMQ")
    entry = next(
        row for row in answer["brokerEngineTypes"] if row["engineType"] == "ACTIVEMQ"
    )
    assert "5.19" in [version["name"] for version in entry["engineVersions"]]
    assert answer["maxResults"] == 20


def test_describe_broker_instance_options_filters_by_engine(s3_endpoint):
    answer = ok(s3_endpoint, "GET", "/v1/broker-instance-options?engineType=ACTIVEMQ")
    options = answer["brokerInstanceOptions"]
    assert options
    assert all(option["engineType"] == "ACTIVEMQ" for option in options)
    assert any(
        option["hostInstanceType"] == "mq.m5.large" and option["storageType"] == "EBS"
        for option in options
    )


def test_create_tags_are_read_back_by_list_tags(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    path = tags_path(broker_arn(s3_endpoint, shared))
    status, _text = call(s3_endpoint, "POST", path, json.dumps({"tags": {"ops-created": "yes"}}))
    assert status == 204
    assert ok(s3_endpoint, "GET", path)["tags"]["ops-created"] == "yes"


def test_list_tags_returns_the_tags_the_broker_carries(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    path = tags_path(broker_arn(s3_endpoint, shared))
    assert call(s3_endpoint, "POST", path, json.dumps({"tags": {"owner": "emuplane"}}))[0] == 204
    tags = ok(s3_endpoint, "GET", path)["tags"]
    assert tags["owner"] == "emuplane"


def test_delete_tags_removes_only_the_named_tag(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    path = tags_path(broker_arn(s3_endpoint, shared))
    body = json.dumps({"tags": {"ops-doomed": "yes", "ops-kept": "yes"}})
    assert call(s3_endpoint, "POST", path, body)[0] == 204
    assert call(s3_endpoint, "DELETE", f"{path}?tagKeys=ops-doomed")[0] == 204
    remaining = ok(s3_endpoint, "GET", path)["tags"]
    assert "ops-doomed" not in remaining
    assert remaining["ops-kept"] == "yes"


def test_create_user_is_read_back_by_describe_user(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    body = json.dumps({"password": "OpsMqUser123", "consoleAccess": True, "groups": ["ops"]})
    status, text = call(s3_endpoint, "POST", user_path(shared, USER), body)
    if status != 200:
        # A re-run meets the user it created before, addressed by its username.
        assert status == 409 and "already exists" in text, text[:400]
    answer = ok(s3_endpoint, "GET", user_path(shared, USER))
    assert answer["username"] == USER
    assert answer["consoleAccess"] is True
    assert USER in [row["username"] for row in ok(s3_endpoint, "GET", users_path(shared))["users"]]


def test_delete_user_removes_the_user_it_created(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, DELETED_USER, "OpsMqUser123", ["ops"])
    assert ok(s3_endpoint, "DELETE", user_path(shared, DELETED_USER)) == {}
    assert DELETED_USER not in [
        row["username"] for row in ok(s3_endpoint, "GET", users_path(shared))["users"]
    ]
    assert call(s3_endpoint, "GET", user_path(shared, DELETED_USER))[0] == 404


def test_list_users_lists_the_shared_broker_users(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, USER, "OpsMqUser123", ["ops"])
    usernames = [row["username"] for row in ok(s3_endpoint, "GET", users_path(shared))["users"]]
    assert ADMIN in usernames
    assert USER in usernames


def test_update_user_is_read_back_by_describe_user(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, USER, "OpsMqUser123", ["ops"])
    body = json.dumps({"consoleAccess": True, "groups": ["admins", "ops"]})
    assert ok(s3_endpoint, "PUT", user_path(shared, USER), body) == {}
    answer = ok(s3_endpoint, "GET", user_path(shared, USER))
    assert answer["groups"] == ["admins", "ops"]
    assert answer["consoleAccess"] is True


def test_describe_user_returns_the_user_configured_on_the_broker(s3_endpoint):
    shared = ensure_broker(s3_endpoint, SHARED)
    ensure_user(s3_endpoint, shared, ADMIN, "OpsMqAdmin123", ["admins"])
    answer = ok(s3_endpoint, "GET", user_path(shared, ADMIN))
    assert answer["brokerId"] == shared
    assert answer["username"] == ADMIN
    assert answer["consoleAccess"] is True
    assert answer["replicationUser"] is False
    assert "admins" in answer["groups"]
