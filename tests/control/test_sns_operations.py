"""SNS on the wire: every action the emulator advertises, through the query protocol.

A topic created here is left in place. A publish is proven by delivering to a queue it
subscribes; every delete action creates the resource it removes.

`ConfirmSubscription` needs the token the emulator only hands to the subscriber. The
in-process harness ends each request's event loop before the confirmation POST is sent,
so offline the token is read from the emulator's own state; the lab's emulator runs in a
container and posts to a listener the container can reach, named by
`EP_LAB_SNS_CALLBACK_HOST` (default `host.containers.internal`).
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2010-03-31"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
LIVE = os.environ.get("EP_LAB_EMULATOR")
CALLBACK_HOST = os.environ.get("EP_LAB_SNS_CALLBACK_HOST") or (
    "host.containers.internal" if LIVE else "127.0.0.1"
)


def call(endpoint, service: str, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, service, ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, service: str, action: str, **params) -> str:
    status, text = call(endpoint, service, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def attribute(text: str, key: str) -> str:
    """One `<entry><key>…</key><value>…</value></entry>` pair, unescaped."""
    match = re.search(rf"<key>{key}</key><value>([^<]*)</value>", text)
    assert match, f"no {key} attribute in {text[:400]}"
    return html.unescape(match.group(1))


def members(endpoint, action: str, **params) -> list[str]:
    """Every page of a list action, as its `<member>` blocks."""
    found, token = [], ""
    while True:
        page = dict(params)
        if token:
            page["NextToken"] = token
        text = ok(endpoint, "sns", action, **page)
        found.extend(re.findall(r"<member>(.*?)</member>", text, re.S))
        match = re.search(r"<NextToken>([^<]*)</NextToken>", text)
        if not match:
            return found
        token = match.group(1)


def topic(endpoint, name: str) -> str:
    return field(ok(endpoint, "sns", "CreateTopic", Name=name), "TopicArn")


def queue(endpoint, name: str) -> str:
    return field(ok(endpoint, "sqs", "CreateQueue", QueueName=name), "QueueUrl")


def queue_arn(endpoint, url: str) -> str:
    return field(
        ok(
            endpoint,
            "sqs",
            "GetQueueAttributes",
            QueueUrl=url,
            **{"AttributeName.1": "QueueArn"},
        ),
        "Value",
    )


def subscribe_queue(endpoint, topic_arn: str, queue_url: str) -> str:
    """Let the topic post to a queue and subscribe it; returns the subscription ARN."""
    arn = queue_arn(endpoint, queue_url)
    # A live emulator enforces the queue policy, so the topic must be allowed to send.
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "sns.amazonaws.com"},
                    "Action": "sqs:SendMessage",
                    "Resource": arn,
                    "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}},
                }
            ],
        }
    )
    ok(
        endpoint,
        "sqs",
        "SetQueueAttributes",
        QueueUrl=queue_url,
        **{"Attribute.1.Name": "Policy", "Attribute.1.Value": policy},
    )
    return field(
        ok(endpoint, "sns", "Subscribe", TopicArn=topic_arn, Protocol="sqs", Endpoint=arn),
        "SubscriptionArn",
    )


def delivered(endpoint, queue_url: str, expected: set[str], attempts: int = 12) -> list[str]:
    """Poll a queue until every expected text appears in a delivered message.

    A body is the SNS envelope (raw delivery is off by default), so the check is a
    substring. Each received message is deleted like a consumer would, so a re-run meets
    its own messages instead of the ones the queue collected on earlier runs.
    """
    seen: list[str] = []
    missing = set(expected)
    for _attempt in range(attempts):
        text = ok(
            endpoint,
            "sqs",
            "ReceiveMessage",
            QueueUrl=queue_url,
            MaxNumberOfMessages="10",
            WaitTimeSeconds="1",
        )
        bodies = re.findall(r"<Body>(.*?)</Body>", text, re.S)
        if not bodies:
            continue
        seen.extend(bodies)
        for handle in re.findall(r"<ReceiptHandle>([^<]*)</ReceiptHandle>", text):
            ok(endpoint, "sqs", "DeleteMessage", QueueUrl=queue_url, ReceiptHandle=handle)
        missing = {item for item in expected if not any(item in body for body in seen)}
        if not missing:
            return seen
    assert not missing, f"not delivered: {sorted(missing)}; received {seen}"
    return seen


def confirmation_listener():
    """A host-side listener for the emulator's SubscriptionConfirmation POST."""
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            try:
                received.append(json.loads(body.decode(errors="replace")))
            except ValueError:
                pass
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):  # keep the test output readable
            pass

    bind = "0.0.0.0" if LIVE else "127.0.0.1"
    server = ThreadingHTTPServer((bind, 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, received


def stored_token(topic_arn: str, endpoint: str) -> str:
    """The token a pending subscription holds, read from the in-process emulator."""
    from ministack.services import sns as emulator_sns

    topic_state = emulator_sns._topics.get_scoped(ACCOUNT, REGION, topic_arn)
    assert topic_state, f"no topic {topic_arn} in the in-process emulator"
    for sub in topic_state["subscriptions"]:
        if sub["endpoint"] == endpoint and sub.get("token"):
            return sub["token"]
    raise AssertionError(f"no pending token for {endpoint}")


def posted_token(received: list[dict], topic_arn: str, seconds: float = 20.0) -> str:
    """Wait for the confirmation POST the live emulator sends to the listener."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for payload in list(received):
            if (
                payload.get("Type") == "SubscriptionConfirmation"
                and payload.get("TopicArn") == topic_arn
                and payload.get("Token")
            ):
                return payload["Token"]
        time.sleep(0.25)
    raise AssertionError("the emulator never delivered the SubscriptionConfirmation")


def platform_application(endpoint, name: str, platform: str = "GCM", **attrs) -> str:
    params = {"Name": name, "Platform": platform}
    for index, (key, value) in enumerate(attrs.items(), start=1):
        params[f"Attributes.entry.{index}.key"] = key
        params[f"Attributes.entry.{index}.value"] = value
    return field(ok(endpoint, "sns", "CreatePlatformApplication", **params),
                 "PlatformApplicationArn")


def platform_endpoint(endpoint, application_arn: str, token: str, **params) -> str:
    return field(
        ok(
            endpoint,
            "sns",
            "CreatePlatformEndpoint",
            PlatformApplicationArn=application_arn,
            Token=token,
            **params,
        ),
        "EndpointArn",
    )


def test_create_topic_is_read_back_by_list(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-created")
    listed = ok(s3_endpoint, "sns", "ListTopics")
    assert arn in listed


def test_list_topics_includes_every_created_topic(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-listed-topic")
    assert any(arn in member for member in members(s3_endpoint, "ListTopics"))


def test_publish_reaches_a_subscribed_queue(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-published")
    queue_url = queue(s3_endpoint, "ops-sns-target")
    subscribe_queue(s3_endpoint, arn, queue_url)
    ok(s3_endpoint, "sns", "Publish", TopicArn=arn, Message="fan out")
    delivered(s3_endpoint, queue_url, {"fan out"})


def test_delete_topic_removes_the_topic_it_created(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-deleted")
    ok(s3_endpoint, "sns", "DeleteTopic", TopicArn=arn)
    status, text = call(s3_endpoint, "sns", "GetTopicAttributes", TopicArn=arn)
    assert status in (400, 404), text[:300]
    assert "NotFound" in text


# ---------------------------------------------------------------------------
# Topic attributes and permissions
# ---------------------------------------------------------------------------

def test_get_topic_attributes_reads_the_topic_back(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-attributes")
    attrs = ok(s3_endpoint, "sns", "GetTopicAttributes", TopicArn=arn)
    assert attribute(attrs, "TopicArn") == arn
    assert attribute(attrs, "Owner") == ACCOUNT
    assert attribute(attrs, "DisplayName") == ""
    assert "<key>Policy</key>" in attrs


def test_set_topic_attributes_changes_the_display_name(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-renamed")
    ok(
        s3_endpoint,
        "sns",
        "SetTopicAttributes",
        TopicArn=arn,
        AttributeName="DisplayName",
        AttributeValue="ops display",
    )
    attrs = ok(s3_endpoint, "sns", "GetTopicAttributes", TopicArn=arn)
    assert attribute(attrs, "DisplayName") == "ops display"
    ok(
        s3_endpoint,
        "sns",
        "SetTopicAttributes",
        TopicArn=arn,
        AttributeName="DisplayName",
        AttributeValue="ops display renamed",
    )
    attrs = ok(s3_endpoint, "sns", "GetTopicAttributes", TopicArn=arn)
    assert attribute(attrs, "DisplayName") == "ops display renamed"


def test_add_permission_writes_a_policy_statement(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-permissioned")
    status, text = call(
        s3_endpoint,
        "sns",
        "AddPermission",
        TopicArn=arn,
        Label="allow-publish",
        **{"AWSAccountId.member.1": ACCOUNT, "ActionName.member.1": "Publish"},
    )
    # A re-run meets the statement this test wrote last time; the emulator says so.
    assert status == 200 or "Already exists" in text, text[:400]
    assert "allow-publish" in ok(s3_endpoint, "sns", "GetTopicAttributes", TopicArn=arn)


def test_remove_permission_deletes_the_policy_statement(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-permission-removed")
    status, text = call(
        s3_endpoint,
        "sns",
        "AddPermission",
        TopicArn=arn,
        Label="remove-me",
        **{"AWSAccountId.member.1": ACCOUNT, "ActionName.member.1": "Publish"},
    )
    assert status == 200 or "Already exists" in text, text[:400]
    ok(s3_endpoint, "sns", "RemovePermission", TopicArn=arn, Label="remove-me")
    assert "remove-me" not in ok(
        s3_endpoint, "sns", "GetTopicAttributes", TopicArn=arn
    )


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

def test_subscribe_returns_a_confirmed_subscription(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-subscribed")
    url = queue(s3_endpoint, "ops-sns-subscribe-target")
    subscription = subscribe_queue(s3_endpoint, arn, url)
    assert subscription.startswith(f"{arn}:")


def test_unsubscribe_removes_the_subscription_it_created(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-unsubscribed")
    url = queue(s3_endpoint, "ops-sns-unsubscribe-target")
    subscription = subscribe_queue(s3_endpoint, arn, url)
    ok(s3_endpoint, "sns", "Unsubscribe", SubscriptionArn=subscription)
    status, text = call(
        s3_endpoint, "sns", "GetSubscriptionAttributes", SubscriptionArn=subscription
    )
    assert status == 404, text[:300]
    assert "NotFound" in text
    assert subscription not in ok(
        s3_endpoint, "sns", "ListSubscriptionsByTopic", TopicArn=arn
    )


def test_list_subscriptions_includes_the_subscription(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-subscription-listed")
    url = queue(s3_endpoint, "ops-sns-list-target")
    subscription = subscribe_queue(s3_endpoint, arn, url)
    found = members(s3_endpoint, "ListSubscriptions")
    assert any(subscription in member and arn in member for member in found)


def test_list_subscriptions_by_topic_includes_the_subscription(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-listed-by-topic")
    url = queue(s3_endpoint, "ops-sns-list-by-topic-target")
    subscription = subscribe_queue(s3_endpoint, arn, url)
    found = members(s3_endpoint, "ListSubscriptionsByTopic", TopicArn=arn)
    assert any(subscription in member for member in found)
    assert all(f"<TopicArn>{arn}</TopicArn>" in member for member in found)


def test_get_subscription_attributes_reads_the_subscription(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-subscription-read")
    url = queue(s3_endpoint, "ops-sns-read-target")
    subscription = subscribe_queue(s3_endpoint, arn, url)
    attrs = ok(
        s3_endpoint, "sns", "GetSubscriptionAttributes", SubscriptionArn=subscription
    )
    assert attribute(attrs, "SubscriptionArn") == subscription
    assert attribute(attrs, "TopicArn") == arn
    assert attribute(attrs, "Protocol") == "sqs"
    assert attribute(attrs, "Endpoint") == queue_arn(s3_endpoint, url)
    assert attribute(attrs, "PendingConfirmation") == "false"


def test_set_subscription_attributes_toggles_raw_delivery(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-subscription-set")
    url = queue(s3_endpoint, "ops-sns-set-target")
    subscription = subscribe_queue(s3_endpoint, arn, url)
    ok(
        s3_endpoint,
        "sns",
        "SetSubscriptionAttributes",
        SubscriptionArn=subscription,
        AttributeName="RawMessageDelivery",
        AttributeValue="true",
    )
    attrs = ok(
        s3_endpoint, "sns", "GetSubscriptionAttributes", SubscriptionArn=subscription
    )
    assert attribute(attrs, "RawMessageDelivery") == "true"
    ok(
        s3_endpoint,
        "sns",
        "SetSubscriptionAttributes",
        SubscriptionArn=subscription,
        AttributeName="RawMessageDelivery",
        AttributeValue="false",
    )
    attrs = ok(
        s3_endpoint, "sns", "GetSubscriptionAttributes", SubscriptionArn=subscription
    )
    assert attribute(attrs, "RawMessageDelivery") == "false"


def test_confirm_subscription_confirms_a_pending_http_subscription(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-confirmed")
    server, received = confirmation_listener()
    try:
        # A unique path each run, so the emulator holds a fresh pending subscription
        # instead of returning the one this test confirmed last time.
        endpoint = (
            f"http://{CALLBACK_HOST}:{server.server_address[1]}"
            f"/ops-sns/{uuid.uuid4().hex}"
        )
        pending = field(
            ok(
                s3_endpoint, "sns", "Subscribe",
                TopicArn=arn, Protocol="http", Endpoint=endpoint,
            ),
            "SubscriptionArn",
        )
        assert pending == "pending confirmation"
        token = posted_token(received, arn) if LIVE else stored_token(arn, endpoint)
        subscription = field(
            ok(s3_endpoint, "sns", "ConfirmSubscription", TopicArn=arn, Token=token),
            "SubscriptionArn",
        )
        attrs = ok(
            s3_endpoint, "sns", "GetSubscriptionAttributes", SubscriptionArn=subscription
        )
        assert attribute(attrs, "PendingConfirmation") == "false"
        assert attribute(attrs, "ConfirmationWasAuthenticated") == "true"
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def test_publish_batch_delivers_every_entry(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-batched")
    url = queue(s3_endpoint, "ops-sns-batch-target")
    subscribe_queue(s3_endpoint, arn, url)
    text = ok(
        s3_endpoint,
        "sns",
        "PublishBatch",
        TopicArn=arn,
        **{
            "PublishBatchRequestEntries.member.1.Id": "first",
            "PublishBatchRequestEntries.member.1.Message": "batch one",
            "PublishBatchRequestEntries.member.2.Id": "second",
            "PublishBatchRequestEntries.member.2.Message": "batch two",
        },
    )
    assert "<Failed></Failed>" in text, text[:400]
    assert "<Id>first</Id>" in text and "<Id>second</Id>" in text
    delivered(s3_endpoint, url, {"batch one", "batch two"})


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def test_tag_resource_adds_a_tag(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-tagged")
    ok(
        s3_endpoint,
        "sns",
        "TagResource",
        ResourceArn=arn,
        **{"Tags.member.1.Key": "team", "Tags.member.1.Value": "ops"},
    )
    tags = ok(s3_endpoint, "sns", "ListTagsForResource", ResourceArn=arn)
    assert "<Key>team</Key>" in tags
    assert "<Value>ops</Value>" in tags


def test_untag_resource_removes_the_tag(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-untagged-topic")
    ok(
        s3_endpoint,
        "sns",
        "TagResource",
        ResourceArn=arn,
        **{"Tags.member.1.Key": "stale", "Tags.member.1.Value": "yes"},
    )
    assert "<Key>stale</Key>" in ok(
        s3_endpoint, "sns", "ListTagsForResource", ResourceArn=arn
    )
    ok(
        s3_endpoint,
        "sns",
        "UntagResource",
        ResourceArn=arn,
        **{"TagKeys.member.1": "stale"},
    )
    assert "<Key>stale</Key>" not in ok(
        s3_endpoint, "sns", "ListTagsForResource", ResourceArn=arn
    )


def test_list_tags_for_resource_reads_the_topic_tags(s3_endpoint):
    arn = topic(s3_endpoint, "ops-sns-tag-read")
    ok(
        s3_endpoint,
        "sns",
        "TagResource",
        ResourceArn=arn,
        **{
            "Tags.member.1.Key": "cost-centre",
            "Tags.member.1.Value": "1234",
            "Tags.member.2.Key": "owner",
            "Tags.member.2.Value": "ops",
        },
    )
    tags = ok(s3_endpoint, "sns", "ListTagsForResource", ResourceArn=arn)
    assert "<Key>cost-centre</Key>" in tags
    assert "<Key>owner</Key>" in tags


# ---------------------------------------------------------------------------
# Platform applications and endpoints
# ---------------------------------------------------------------------------

def test_create_platform_application_is_read_back(s3_endpoint):
    arn = platform_application(s3_endpoint, "ops-sns-app")
    assert arn.endswith(":app/GCM/ops-sns-app")
    attrs = ok(
        s3_endpoint,
        "sns",
        "GetPlatformApplicationAttributes",
        PlatformApplicationArn=arn,
    )
    assert attribute(attrs, "Enabled") == "true"


def test_list_platform_applications_includes_the_application(s3_endpoint):
    arn = platform_application(
        s3_endpoint, "ops-sns-app-listed", PlatformCredential="ops-credential"
    )
    assert any(arn in member for member in members(s3_endpoint, "ListPlatformApplications"))


def test_get_platform_application_attributes_reads_the_application(s3_endpoint):
    arn = platform_application(
        s3_endpoint, "ops-sns-app-read", PlatformCredential="ops-credential"
    )
    attrs = ok(
        s3_endpoint,
        "sns",
        "GetPlatformApplicationAttributes",
        PlatformApplicationArn=arn,
    )
    assert attribute(attrs, "PlatformCredential") == "ops-credential"
    assert attribute(attrs, "Enabled") == "true"


def test_set_platform_application_attributes_updates_enabled(s3_endpoint):
    arn = platform_application(s3_endpoint, "ops-sns-app-set")
    for value in ("false", "true"):
        ok(
            s3_endpoint,
            "sns",
            "SetPlatformApplicationAttributes",
            PlatformApplicationArn=arn,
            **{"Attributes.entry.1.key": "Enabled", "Attributes.entry.1.value": value},
        )
        attrs = ok(
            s3_endpoint,
            "sns",
            "GetPlatformApplicationAttributes",
            PlatformApplicationArn=arn,
        )
        assert attribute(attrs, "Enabled") == value


def test_create_platform_endpoint_is_read_back(s3_endpoint):
    application = platform_application(s3_endpoint, "ops-sns-app-endpoint")
    arn = platform_endpoint(s3_endpoint, application, "ops-token-endpoint")
    assert arn.startswith(f"{application}/")
    attrs = ok(s3_endpoint, "sns", "GetEndpointAttributes", EndpointArn=arn)
    assert attribute(attrs, "Token") == "ops-token-endpoint"
    assert attribute(attrs, "Enabled") == "true"


def test_get_endpoint_attributes_reads_the_endpoint(s3_endpoint):
    application = platform_application(s3_endpoint, "ops-sns-app-endpoint-read")
    arn = platform_endpoint(
        s3_endpoint, application, "ops-token-read", CustomUserData="ops-user"
    )
    attrs = ok(s3_endpoint, "sns", "GetEndpointAttributes", EndpointArn=arn)
    assert attribute(attrs, "Token") == "ops-token-read"
    assert attribute(attrs, "CustomUserData") == "ops-user"


def test_set_endpoint_attributes_updates_enabled(s3_endpoint):
    application = platform_application(s3_endpoint, "ops-sns-app-endpoint-set")
    arn = platform_endpoint(s3_endpoint, application, "ops-token-set")
    for value in ("false", "true"):
        ok(
            s3_endpoint,
            "sns",
            "SetEndpointAttributes",
            EndpointArn=arn,
            **{"Attributes.entry.1.key": "Enabled", "Attributes.entry.1.value": value},
        )
        attrs = ok(s3_endpoint, "sns", "GetEndpointAttributes", EndpointArn=arn)
        assert attribute(attrs, "Enabled") == value


def test_delete_endpoint_removes_the_endpoint_it_created(s3_endpoint):
    application = platform_application(s3_endpoint, "ops-sns-app-endpoint-deleted")
    arn = platform_endpoint(s3_endpoint, application, "ops-token-deleted")
    ok(s3_endpoint, "sns", "DeleteEndpoint", EndpointArn=arn)
    status, text = call(s3_endpoint, "sns", "GetEndpointAttributes", EndpointArn=arn)
    assert status == 404, text[:300]
    assert "NotFound" in text


def test_delete_platform_application_removes_the_application_it_created(s3_endpoint):
    arn = platform_application(s3_endpoint, "ops-sns-app-removed")
    endpoint = platform_endpoint(s3_endpoint, arn, "ops-token-removed")
    ok(s3_endpoint, "sns", "DeletePlatformApplication", PlatformApplicationArn=arn)
    status, text = call(
        s3_endpoint, "sns", "GetPlatformApplicationAttributes", PlatformApplicationArn=arn
    )
    assert status == 404, text[:300]
    assert "NotFound" in text
    status, text = call(s3_endpoint, "sns", "GetEndpointAttributes", EndpointArn=endpoint)
    assert status == 404, text[:300]
    assert "NotFound" in text
