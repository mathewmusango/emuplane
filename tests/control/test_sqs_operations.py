"""SQS on the wire: every advertised operation, driven through the query protocol.

Resources are left in the emulator — a create is proven by a read, never undone. A
delete action makes a queue of its own, so it can remove what it created. A message
test empties its own queue first, so a second run against the same lab starts clean.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2012-11-05"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

ATTRIBUTE_RE = re.compile(
    r"<Attribute><Name>([^<]*)</Name><Value>([^<]*)</Value></Attribute>"
)
TAG_RE = re.compile(r"<Tag><Key>([^<]*)</Key><Value>([^<]*)</Value></Tag>")
MESSAGE_RE = re.compile(
    r"<Message>.*?<ReceiptHandle>([^<]*)</ReceiptHandle>.*?<Body>([^<]*)</Body>.*?</Message>",
    re.S,
)


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "sqs", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def queue(endpoint, name: str) -> str:
    text = ok(endpoint, "CreateQueue", QueueName=name)
    return field(text, "QueueUrl")


def queue_with(endpoint, name: str, **attributes) -> str:
    """A queue born with settings; a queue already there answers its own URL."""
    params = {"QueueName": name}
    for index, (key, value) in enumerate(attributes.items(), 1):
        params[f"Attribute.{index}.Name"] = key
        params[f"Attribute.{index}.Value"] = value
    return field(ok(endpoint, "CreateQueue", **params), "QueueUrl")


def attributes(endpoint, url: str, *names: str) -> dict[str, str]:
    """The queue's attributes, all of them unless names are given."""
    params = {"QueueUrl": url}
    for index, name in enumerate(names or ("All",), 1):
        params[f"AttributeName.{index}"] = name
    text = ok(endpoint, "GetQueueAttributes", **params)
    return dict(ATTRIBUTE_RE.findall(text))


def tags(endpoint, url: str) -> dict[str, str]:
    text = ok(endpoint, "ListQueueTags", QueueUrl=url)
    return dict(TAG_RE.findall(text))


def delivered(text: str) -> list[tuple[str, str]]:
    """(body, receipt handle) for each <Message>, in the order received."""
    return [(body, receipt) for receipt, body in MESSAGE_RE.findall(text)]


def unique(label: str) -> str:
    """A body no earlier run used, so an assertion names the message it sent."""
    return f"{label}-{uuid.uuid4().hex}"


def empty(endpoint, url: str) -> None:
    """Clear this test's own queue's messages, so a second run starts clean."""
    ok(endpoint, "PurgeQueue", QueueUrl=url)


def test_create_queue_is_read_back_by_url(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-created")
    assert url.endswith("/ops-sqs-created")
    assert queue(s3_endpoint, "ops-sqs-created") == url


def test_send_message_then_receive_returns_the_body(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-messages")
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody="first message")
    text = ok(s3_endpoint, "ReceiveMessage", QueueUrl=url, MaxNumberOfMessages="1")
    assert field(text, "Body") == "first message"


def test_purge_queue_empties_it(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-purged")
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody="discard me")
    ok(s3_endpoint, "PurgeQueue", QueueUrl=url)
    text = ok(s3_endpoint, "ReceiveMessage", QueueUrl=url, MaxNumberOfMessages="1")
    assert "<Message>" not in text


def test_delete_queue_removes_the_queue_it_created(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-deleted")
    ok(s3_endpoint, "DeleteQueue", QueueUrl=url)
    status, text = call(s3_endpoint, "GetQueueUrl", QueueName="ops-sqs-deleted")
    assert status == 400, text[:300]
    assert "NonExistentQueue" in text


def test_list_queues_pages_through_a_prefix(s3_endpoint):
    first = queue(s3_endpoint, "ops-sqs-listed-a")
    second = queue(s3_endpoint, "ops-sqs-listed-b")
    page = ok(
        s3_endpoint,
        "ListQueues",
        QueueNamePrefix="ops-sqs-listed-",
        MaxResults="1",
    )
    listed = re.findall(r"<QueueUrl>([^<]*)</QueueUrl>", page)
    assert len(listed) == 1, page[:400]
    assert listed[0] in (first, second)
    rest = ok(
        s3_endpoint,
        "ListQueues",
        QueueNamePrefix="ops-sqs-listed-",
        MaxResults="1",
        NextToken=field(page, "NextToken"),
    )
    remaining = re.findall(r"<QueueUrl>([^<]*)</QueueUrl>", rest)
    assert len(remaining) == 1, rest[:400]
    assert {listed[0], remaining[0]} == {first, second}
    assert "<NextToken>" not in rest


def test_get_queue_url_names_the_queue_it_created(s3_endpoint):
    created = queue(s3_endpoint, "ops-sqs-url")
    found = ok(s3_endpoint, "GetQueueUrl", QueueName="ops-sqs-url")
    assert field(found, "QueueUrl") == created


def test_get_queue_attributes_reads_what_creation_set(s3_endpoint):
    url = queue_with(s3_endpoint, "ops-sqs-attributes", VisibilityTimeout="45")
    every = attributes(s3_endpoint, url)
    assert every["QueueArn"].endswith(":ops-sqs-attributes")
    assert every["VisibilityTimeout"] == "45"
    assert "ApproximateNumberOfMessages" in every
    only = attributes(s3_endpoint, url, "VisibilityTimeout")
    assert only == {"VisibilityTimeout": "45"}


def test_set_queue_attributes_changes_what_attributes_report(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-attributes-set")
    ok(
        s3_endpoint,
        "SetQueueAttributes",
        QueueUrl=url,
        **{
            "Attribute.1.Name": "VisibilityTimeout",
            "Attribute.1.Value": "45",
            "Attribute.2.Name": "DelaySeconds",
            "Attribute.2.Value": "5",
        },
    )
    assert attributes(s3_endpoint, url, "VisibilityTimeout", "DelaySeconds") == {
        "VisibilityTimeout": "45",
        "DelaySeconds": "5",
    }


def test_delete_message_removes_the_received_message(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-delete-message")
    empty(s3_endpoint, url)
    body = unique("delete-me")
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody=body)
    got = delivered(
        ok(
            s3_endpoint,
            "ReceiveMessage",
            QueueUrl=url,
            MaxNumberOfMessages="1",
            VisibilityTimeout="0",
        )
    )
    assert len(got) == 1, got
    received_body, receipt = got[0]
    assert received_body == body
    ok(s3_endpoint, "DeleteMessage", QueueUrl=url, ReceiptHandle=receipt)
    after = ok(s3_endpoint, "ReceiveMessage", QueueUrl=url, MaxNumberOfMessages="10")
    assert body not in after
    status, text = call(
        s3_endpoint, "DeleteMessage", QueueUrl=url, ReceiptHandle="not-a-handle"
    )
    assert status == 400, text[:300]
    assert "ReceiptHandleIsInvalid" in text


def test_change_message_visibility_hides_then_returns_the_message(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-visibility")
    empty(s3_endpoint, url)
    body = unique("visibility")
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody=body)
    got = delivered(
        ok(
            s3_endpoint,
            "ReceiveMessage",
            QueueUrl=url,
            MaxNumberOfMessages="1",
            VisibilityTimeout="0",
        )
    )
    assert len(got) == 1, got
    received_body, receipt = got[0]
    assert received_body == body
    ok(
        s3_endpoint,
        "ChangeMessageVisibility",
        QueueUrl=url,
        ReceiptHandle=receipt,
        VisibilityTimeout="30",
    )
    hidden = ok(s3_endpoint, "ReceiveMessage", QueueUrl=url, MaxNumberOfMessages="1")
    assert "<Message>" not in hidden
    ok(
        s3_endpoint,
        "ChangeMessageVisibility",
        QueueUrl=url,
        ReceiptHandle=receipt,
        VisibilityTimeout="0",
    )
    again = ok(s3_endpoint, "ReceiveMessage", QueueUrl=url, MaxNumberOfMessages="1")
    assert body in again


def test_change_message_visibility_batch_reports_each_entry(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-visibility-batch")
    empty(s3_endpoint, url)
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody=unique("visible-one"))
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody=unique("visible-two"))
    got = delivered(
        ok(
            s3_endpoint,
            "ReceiveMessage",
            QueueUrl=url,
            MaxNumberOfMessages="2",
            VisibilityTimeout="0",
        )
    )
    assert len(got) == 2, got
    text = ok(
        s3_endpoint,
        "ChangeMessageVisibilityBatch",
        QueueUrl=url,
        **{
            "ChangeMessageVisibilityBatchRequestEntry.1.Id": "visible",
            "ChangeMessageVisibilityBatchRequestEntry.1.ReceiptHandle": got[0][1],
            "ChangeMessageVisibilityBatchRequestEntry.1.VisibilityTimeout": "30",
            "ChangeMessageVisibilityBatchRequestEntry.2.Id": "unknown",
            "ChangeMessageVisibilityBatchRequestEntry.2.ReceiptHandle": "not-a-handle",
            "ChangeMessageVisibilityBatchRequestEntry.2.VisibilityTimeout": "0",
        },
    )
    assert "<ChangeMessageVisibilityBatchResultEntry>" in text
    assert "<Id>visible</Id>" in text
    assert "<BatchResultErrorEntry>" in text
    assert "<Id>unknown</Id>" in text
    assert "<Code>ReceiptHandleIsInvalid</Code>" in text


def test_send_message_batch_delivers_every_entry(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-send-batch")
    empty(s3_endpoint, url)
    bodies = {"first": unique("batch-one"), "second": unique("batch-two")}
    text = ok(
        s3_endpoint,
        "SendMessageBatch",
        QueueUrl=url,
        **{
            "SendMessageBatchRequestEntry.1.Id": "first",
            "SendMessageBatchRequestEntry.1.MessageBody": bodies["first"],
            "SendMessageBatchRequestEntry.2.Id": "second",
            "SendMessageBatchRequestEntry.2.MessageBody": bodies["second"],
        },
    )
    assert text.count("<SendMessageBatchResultEntry>") == 2, text[:400]
    assert "<BatchResultErrorEntry>" not in text
    received = delivered(
        ok(s3_endpoint, "ReceiveMessage", QueueUrl=url, MaxNumberOfMessages="10")
    )
    assert sorted(body for body, _receipt in received) == sorted(bodies.values())


def test_delete_message_batch_removes_every_entry(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-delete-batch")
    empty(s3_endpoint, url)
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody=unique("batch-delete-one"))
    ok(s3_endpoint, "SendMessage", QueueUrl=url, MessageBody=unique("batch-delete-two"))
    got = delivered(
        ok(
            s3_endpoint,
            "ReceiveMessage",
            QueueUrl=url,
            MaxNumberOfMessages="10",
            VisibilityTimeout="0",
        )
    )
    assert len(got) == 2, got
    text = ok(
        s3_endpoint,
        "DeleteMessageBatch",
        QueueUrl=url,
        **{
            "DeleteMessageBatchRequestEntry.1.Id": "one",
            "DeleteMessageBatchRequestEntry.1.ReceiptHandle": got[0][1],
            "DeleteMessageBatchRequestEntry.2.Id": "two",
            "DeleteMessageBatchRequestEntry.2.ReceiptHandle": got[1][1],
        },
    )
    assert text.count("<DeleteMessageBatchResultEntry>") == 2, text[:400]
    assert "<BatchResultErrorEntry>" not in text
    after = ok(s3_endpoint, "ReceiveMessage", QueueUrl=url, MaxNumberOfMessages="10")
    assert "<Message>" not in after


def test_tag_queue_writes_the_tags_it_reads_back(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-tagged")
    ok(
        s3_endpoint,
        "TagQueue",
        QueueUrl=url,
        **{
            "Tag.1.Key": "team",
            "Tag.1.Value": "platform",
            "Tag.2.Key": "stage",
            "Tag.2.Value": "test",
        },
    )
    assert tags(s3_endpoint, url) == {"team": "platform", "stage": "test"}


def test_untag_queue_removes_only_the_named_key(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-untagged")
    ok(
        s3_endpoint,
        "TagQueue",
        QueueUrl=url,
        **{
            "Tag.1.Key": "keep",
            "Tag.1.Value": "one",
            "Tag.2.Key": "drop",
            "Tag.2.Value": "two",
        },
    )
    ok(s3_endpoint, "UntagQueue", QueueUrl=url, **{"TagKey.1": "drop"})
    assert tags(s3_endpoint, url) == {"keep": "one"}


def test_list_queue_tags_reports_the_tags(s3_endpoint):
    url = queue(s3_endpoint, "ops-sqs-tags-listed")
    ok(
        s3_endpoint,
        "TagQueue",
        QueueUrl=url,
        **{"Tag.1.Key": "env", "Tag.1.Value": "test"},
    )
    text = ok(s3_endpoint, "ListQueueTags", QueueUrl=url)
    assert "<Tag><Key>env</Key><Value>test</Value></Tag>" in text
    assert tags(s3_endpoint, url) == {"env": "test"}
