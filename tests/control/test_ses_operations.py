"""SES v1 on the wire: every advertised action, through the query protocol.

The v1 API is form-encoded `Action=` on a POST and answers XML. Mail is stored in the
emulator, never sent, so a send is proven by its `MessageId`; the sandbox rule is proven
by refusing an unverified sender.

Identities are idempotent to verify, configuration sets / templates / receipt rule sets
are named, so a lab sweep that re-runs finds what the first sweep left; every delete
action creates a resource of its own and removes only that. Nothing shared is deleted.

`SetIdentityNotificationTopic` has no v1 read path, so its effect is proven the way a
customer sees it: a bounce to the mailbox simulator reaches the SNS topic set on the
sender's identity, read back from a queue subscribed to it.
"""

from __future__ import annotations

import base64
import html
import json
import re
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2010-12-01"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

# Stable names and addresses, so a second sweep meets its own resources instead of
# colliding with them.
SENDER = "ops-ses-sender@ops-ses.example"
LEGACY = "ops-ses-legacy@ops-ses.example"
DELETED_IDENTITY = "ops-ses-deleted@ops-ses.example"
DOMAIN = "ops-ses-domain.example"
UNVERIFIED = "ops-ses-unverified@ops-ses-unverified.example"
NOTIFY_SENDER = "ops-ses-notify@ops-ses.example"

SUCCESS = "success@simulator.amazonses.com"
BOUNCE = "bounce@simulator.amazonses.com"

CONFIG_SET = "ops-ses-config-set"
CONFIG_SET_DELETED = "ops-ses-config-set-deleted"

TEMPLATE = "ops-ses-template"
TEMPLATE_DELETED = "ops-ses-template-deleted"
TEMPLATE_SUBJECT = "Hello {{name}}"
TEMPLATE_TEXT = "Body for {{name}}"
TEMPLATE_HTML = "<p>Body for {{name}}</p>"

RULE_SET = "ops-ses-rule-set"
RULE_SET_DELETED = "ops-ses-rule-set-deleted"
ACTIVE_RULE_SET = "ops-ses-active-rule-set"
RULE = "ops-ses-rule"
RULE_DELETED = "ops-ses-rule-deleted"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------

def call(endpoint, service: str, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, service, ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, "ses", action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return text


def other(endpoint, service: str, action: str, **params) -> str:
    """The same call to a service this file only touches to prove an SES side effect."""
    status, text = call(endpoint, service, action, **params)
    assert status == 200, f"{service} {action} answered {status}: {text[:400]}"
    return text


def rejected(endpoint, action: str, code: str, **params) -> str:
    """The XML error a v1 action answers instead of a result."""
    status, text = call(endpoint, "ses", action, **params)
    assert status == 400, f"{action} answered {status}: {text[:400]}"
    assert f"<Code>{code}</Code>" in text, f"expected {code}: {text[:400]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def members(endpoint, action: str, **params) -> list[str]:
    """Every page of a list action, as the inner text of each `<member>` block."""
    found: list[str] = []
    token = ""
    while True:
        page = dict(params)
        if token:
            page["NextToken"] = token
        text = ok(endpoint, action, **page)
        found.extend(re.findall(r"<member>(.*?)</member>", text, re.S))
        match = re.search(r"<NextToken>([^<]*)</NextToken>", text)
        if not match:
            return found
        token = match.group(1)


def message_id(text: str) -> str:
    found = field(text, "MessageId")
    assert found.endswith("@email.amazonses.com"), f"odd MessageId: {found}"
    return found


def send(endpoint, source: str = SENDER, recipient: str = SUCCESS, subject: str = "ops") -> str:
    return message_id(
        ok(
            endpoint,
            "SendEmail",
            Source=source,
            **{"Destination.ToAddresses.member.1": recipient},
            **{"Message.Subject.Data": subject, "Message.Body.Text.Data": "body"},
        )
    )


# ---------------------------------------------------------------------------
# Shared resources: create-or-find, so a re-run keeps the same ones
# ---------------------------------------------------------------------------

def ensure_config_set(endpoint, name: str) -> None:
    status, text = call(
        endpoint, "ses", "CreateConfigurationSet", **{"ConfigurationSet.Name": name}
    )
    # A lab keeps the set an earlier sweep created; the name is the identity.
    assert status == 200 or "ConfigurationSetAlreadyExists" in text, (
        f"CreateConfigurationSet answered {status}: {text[:400]}"
    )


def ensure_template(endpoint, name: str) -> None:
    status, text = call(
        endpoint,
        "ses",
        "CreateTemplate",
        **{
            "Template.TemplateName": name,
            "Template.SubjectPart": TEMPLATE_SUBJECT,
            "Template.TextPart": TEMPLATE_TEXT,
            "Template.HtmlPart": TEMPLATE_HTML,
        },
    )
    assert status == 200 or "AlreadyExists" in text, (
        f"CreateTemplate answered {status}: {text[:400]}"
    )
    # Fixed content, so a sweep reads the same parts whatever an earlier one stored.
    ok(
        endpoint,
        "UpdateTemplate",
        **{
            "Template.TemplateName": name,
            "Template.SubjectPart": TEMPLATE_SUBJECT,
            "Template.TextPart": TEMPLATE_TEXT,
            "Template.HtmlPart": TEMPLATE_HTML,
        },
    )


def ensure_rule_set(endpoint, name: str) -> None:
    status, text = call(endpoint, "ses", "CreateReceiptRuleSet", RuleSetName=name)
    assert status == 200 or "AlreadyExists" in text, (
        f"CreateReceiptRuleSet answered {status}: {text[:400]}"
    )


def rule_params(name: str, header: str) -> dict:
    return {
        "Rule.Name": name,
        "Rule.Enabled": "true",
        "Rule.TlsPolicy": "Optional",
        "Rule.ScanEnabled": "true",
        "Rule.Recipients.member.1": "ops-ses-recipient@ops-ses-domain.example",
        "Rule.Actions.member.1.AddHeaderAction.HeaderName": header,
        "Rule.Actions.member.1.AddHeaderAction.HeaderValue": "emuplane",
    }


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------

def test_verify_email_identity_is_read_back_as_verified(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    attributes = ok(
        s3_endpoint,
        "GetIdentityVerificationAttributes",
        **{"Identities.member.1": SENDER},
    )
    assert f"<key>{SENDER}</key>" in attributes
    assert field(attributes, "VerificationStatus") == "Success"


def test_verify_email_address_verifies_the_legacy_way(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailAddress", EmailAddress=LEGACY)
    assert LEGACY in ok(s3_endpoint, "ListVerifiedEmailAddresses")


def test_verify_domain_identity_returns_a_token(s3_endpoint):
    token = field(ok(s3_endpoint, "VerifyDomainIdentity", Domain=DOMAIN), "VerificationToken")
    assert re.fullmatch(r"[0-9a-f]{32}", token), f"unexpected token: {token}"


def test_verify_domain_dkim_returns_three_tokens(s3_endpoint):
    tokens = re.findall(r"<member>([^<]*)</member>", ok(s3_endpoint, "VerifyDomainDkim", Domain=DOMAIN))
    assert len(tokens) == 3, f"expected three DKIM tokens: {tokens}"
    assert all(re.fullmatch(r"[0-9a-f]{32}", token) for token in tokens)


def test_get_identity_dkim_attributes_reports_the_dkim_tokens(s3_endpoint):
    ok(s3_endpoint, "VerifyDomainDkim", Domain=DOMAIN)
    attributes = ok(
        s3_endpoint,
        "GetIdentityDkimAttributes",
        **{"Identities.member.1": DOMAIN},
    )
    assert f"<key>{DOMAIN}</key>" in attributes
    assert field(attributes, "DkimEnabled") == "true"
    assert field(attributes, "DkimVerificationStatus") == "Success"
    assert "<DkimTokens>" in attributes
    assert len(re.findall(r"<member>[0-9a-f]{32}</member>", attributes)) == 3


def test_get_identity_verification_attributes_reports_an_unknown_identity_as_pending(s3_endpoint):
    attributes = ok(
        s3_endpoint,
        "GetIdentityVerificationAttributes",
        **{"Identities.member.1": "ops-ses-never-verified@ops-ses-unverified.example"},
    )
    assert field(attributes, "VerificationStatus") == "Pending"


def test_list_identities_includes_both_identity_kinds(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    ok(s3_endpoint, "VerifyDomainIdentity", Domain=DOMAIN)
    identities = members(s3_endpoint, "ListIdentities", MaxItems="1000")
    assert SENDER in identities
    assert DOMAIN in identities


def test_list_identities_filters_by_identity_type(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    ok(s3_endpoint, "VerifyDomainIdentity", Domain=DOMAIN)
    emails = members(s3_endpoint, "ListIdentities", IdentityType="EmailAddress", MaxItems="1000")
    assert SENDER in emails
    assert DOMAIN not in emails


def test_list_verified_email_addresses_holds_the_email_identities(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    ok(s3_endpoint, "VerifyDomainIdentity", Domain=DOMAIN)
    verified = ok(s3_endpoint, "ListVerifiedEmailAddresses")
    assert SENDER in verified
    assert f"<member>{DOMAIN}</member>" not in verified


def test_delete_identity_removes_the_identity_it_created(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=DELETED_IDENTITY)
    assert DELETED_IDENTITY in members(s3_endpoint, "ListIdentities", MaxItems="1000")
    ok(s3_endpoint, "DeleteIdentity", Identity=DELETED_IDENTITY)
    assert DELETED_IDENTITY not in members(s3_endpoint, "ListIdentities", MaxItems="1000")
    assert DELETED_IDENTITY not in ok(s3_endpoint, "ListVerifiedEmailAddresses")


# ---------------------------------------------------------------------------
# Sends: stored, never delivered, and only as a verified identity
# ---------------------------------------------------------------------------

def test_send_email_answers_a_message_id(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    sent = ok(
        s3_endpoint,
        "SendEmail",
        Source=SENDER,
        **{"Destination.ToAddresses.member.1": SUCCESS},
        **{
            "Message.Subject.Data": "ops-ses sent",
            "Message.Body.Text.Data": "plain body",
            "Message.Body.Html.Data": "<p>html body</p>",
        },
    )
    assert message_id(sent)


def test_send_email_rejects_an_unverified_sender(s3_endpoint):
    text = rejected(
        s3_endpoint,
        "SendEmail",
        "MessageRejected",
        Source=UNVERIFIED,
        **{"Destination.ToAddresses.member.1": SUCCESS},
        **{"Message.Subject.Data": "ops-ses rejected", "Message.Body.Text.Data": "body"},
    )
    assert "Email address is not verified" in text
    assert UNVERIFIED in text


def test_send_email_rejects_an_address_without_a_domain(s3_endpoint):
    rejected(
        s3_endpoint,
        "SendEmail",
        "InvalidParameterValue",
        Source="ops-ses-sender",
        **{"Destination.ToAddresses.member.1": SUCCESS},
        **{"Message.Subject.Data": "ops-ses no domain", "Message.Body.Text.Data": "body"},
    )


def test_send_raw_email_answers_a_message_id(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    raw = (
        f"From: {SENDER}\r\n"
        f"To: {SUCCESS}\r\n"
        "Subject: ops-ses raw\r\n"
        "Content-Type: text/plain; charset=UTF-8\r\n"
        "\r\n"
        "raw body\r\n"
    )
    sent = ok(
        s3_endpoint,
        "SendRawEmail",
        Source=SENDER,
        **{
            "RawMessage.Data": base64.b64encode(raw.encode()).decode(),
            "Destinations.member.1": SUCCESS,
        },
    )
    assert message_id(sent)


def test_send_templated_email_answers_a_message_id(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    ensure_template(s3_endpoint, TEMPLATE)
    sent = ok(
        s3_endpoint,
        "SendTemplatedEmail",
        Source=SENDER,
        Template=TEMPLATE,
        TemplateData=json.dumps({"name": "World"}),
        **{"Destination.ToAddresses.member.1": SUCCESS},
    )
    assert message_id(sent)


def test_send_templated_email_names_a_missing_template(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    text = rejected(
        s3_endpoint,
        "SendTemplatedEmail",
        "TemplateDoesNotExist",
        Source=SENDER,
        Template="ops-ses-template-never-created",
        TemplateData="{}",
        **{"Destination.ToAddresses.member.1": SUCCESS},
    )
    assert "ops-ses-template-never-created" in text


def test_send_bulk_templated_email_answers_a_status_per_destination(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    ensure_template(s3_endpoint, TEMPLATE)
    sent = ok(
        s3_endpoint,
        "SendBulkTemplatedEmail",
        Source=SENDER,
        Template=TEMPLATE,
        DefaultTemplateData=json.dumps({"name": "Bulk"}),
        **{
            "Destinations.member.1.Destination.ToAddresses.member.1": SUCCESS,
            "Destinations.member.1.ReplacementTemplateData": json.dumps({"name": "One"}),
            "Destinations.member.2.Destination.ToAddresses.member.1": "ooto@simulator.amazonses.com",
        },
    )
    statuses = re.findall(
        r"<member><Status>(Success|MessageRejected)</Status>(.*?)</member>", sent, re.S
    )
    assert [status for status, _detail in statuses] == ["Success", "Success"]
    for _status, detail in statuses:
        assert field(detail, "MessageId").endswith("@email.amazonses.com")


# ---------------------------------------------------------------------------
# Quota and statistics
# ---------------------------------------------------------------------------

def test_get_send_quota_reports_the_daily_limit_and_what_was_sent(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    send(s3_endpoint)
    quota = ok(s3_endpoint, "GetSendQuota")
    assert float(field(quota, "Max24HourSend")) == 50000.0
    assert float(field(quota, "MaxSendRate")) == 14.0
    assert float(field(quota, "SentLast24Hours")) >= 1.0


def test_get_send_statistics_reports_a_fifteen_minute_bucket(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    send(s3_endpoint)
    points = re.findall(
        r"<member><Timestamp>([^<]*)</Timestamp>"
        r"<DeliveryAttempts>(\d+)</DeliveryAttempts>"
        r"<Bounces>(\d+)</Bounces>"
        r"<Complaints>(\d+)</Complaints>"
        r"<Rejects>(\d+)</Rejects></member>",
        ok(s3_endpoint, "GetSendStatistics"),
    )
    assert points, "no SendDataPoints after a send"
    stamp, attempts, _bounces, _complaints, _rejects = points[-1]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp), stamp
    assert sum(int(point[1]) for point in points) >= 1
    assert int(attempts) >= 1


# ---------------------------------------------------------------------------
# Notification settings, read back through the services that receive them
# ---------------------------------------------------------------------------

def sns_topic(endpoint, name: str) -> str:
    return field(other(endpoint, "sns", "CreateTopic", Name=name), "TopicArn")


def sqs_queue(endpoint, name: str) -> str:
    return field(other(endpoint, "sqs", "CreateQueue", QueueName=name), "QueueUrl")


def queue_arn(endpoint, url: str) -> str:
    return field(
        other(
            endpoint, "sqs", "GetQueueAttributes", QueueUrl=url,
            **{"AttributeName.1": "QueueArn"},
        ),
        "Value",
    )


def allow_topic(endpoint, queue_url: str, arn: str, topic_arn: str) -> None:
    """A live emulator enforces the queue policy, so the topic must be allowed to send."""
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
    other(
        endpoint, "sqs", "SetQueueAttributes", QueueUrl=queue_url,
        **{"Attribute.1.Name": "Policy", "Attribute.1.Value": policy},
    )


def subscribe_queue(endpoint, topic_arn: str, arn: str) -> str:
    return field(
        other(endpoint, "sns", "Subscribe", TopicArn=topic_arn, Protocol="sqs", Endpoint=arn),
        "SubscriptionArn",
    )


def received(endpoint, queue_url: str, needle: str, attempts: int = 12) -> str:
    """Poll a queue until a message carrying `needle` arrives, deleting what is consumed."""
    seen: list[str] = []
    for _attempt in range(attempts):
        status, text = call(
            endpoint,
            "sqs",
            "ReceiveMessage",
            QueueUrl=queue_url,
            MaxNumberOfMessages="10",
            WaitTimeSeconds="1",
        )
        assert status == 200, f"ReceiveMessage answered {status}: {text[:400]}"
        bodies = re.findall(r"<Body>(.*?)</Body>", text, re.S)
        seen.extend(bodies)
        for handle in re.findall(r"<ReceiptHandle>([^<]*)</ReceiptHandle>", text):
            call(endpoint, "sqs", "DeleteMessage", QueueUrl=queue_url, ReceiptHandle=handle)
        for body in bodies:
            if needle in body:
                return body
    raise AssertionError(f"{needle} never arrived; received {seen}")


def test_set_identity_notification_topic_publishes_the_bounce(s3_endpoint):
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=NOTIFY_SENDER)
    topic_arn = sns_topic(s3_endpoint, "ops-ses-notifications")
    queue_url = sqs_queue(s3_endpoint, "ops-ses-notifications")
    arn = queue_arn(s3_endpoint, queue_url)
    allow_topic(s3_endpoint, queue_url, arn, topic_arn)
    subscribe_queue(s3_endpoint, topic_arn, arn)

    ok(
        s3_endpoint,
        "SetIdentityNotificationTopic",
        Identity=NOTIFY_SENDER,
        NotificationType="Bounce",
        SnsTopic=topic_arn,
    )
    sent = send(s3_endpoint, source=NOTIFY_SENDER, recipient=BOUNCE, subject="ops-ses bounce")
    body = received(s3_endpoint, queue_url, sent)
    assert "notificationType" in body
    assert "Bounce" in body
    assert NOTIFY_SENDER in body


def test_set_identity_feedback_forwarding_is_accepted_both_ways(s3_endpoint):
    """No v1 action reads the flag back, so the contract proven is the empty result
    for each value; the send path above is where the emulator reads its neighbours."""
    ok(s3_endpoint, "VerifyEmailIdentity", EmailAddress=SENDER)
    assert "<SetIdentityFeedbackForwardingEnabledResult" in ok(
        s3_endpoint, "SetIdentityFeedbackForwardingEnabled", Identity=SENDER, ForwardingEnabled="false"
    )
    assert "<SetIdentityFeedbackForwardingEnabledResult" in ok(
        s3_endpoint, "SetIdentityFeedbackForwardingEnabled", Identity=SENDER, ForwardingEnabled="true"
    )


# ---------------------------------------------------------------------------
# Configuration sets
# ---------------------------------------------------------------------------

def config_set_names(endpoint) -> list[str]:
    return [
        field(block, "Name")
        for block in members(endpoint, "ListConfigurationSets", MaxItems="1000")
    ]


def test_create_configuration_set_is_read_back_by_list(s3_endpoint):
    status, text = call(
        s3_endpoint, "ses", "CreateConfigurationSet", **{"ConfigurationSet.Name": CONFIG_SET}
    )
    assert status == 200 or "ConfigurationSetAlreadyExists" in text, (
        f"CreateConfigurationSet answered {status}: {text[:400]}"
    )
    assert CONFIG_SET in config_set_names(s3_endpoint)


def test_create_configuration_set_requires_a_name(s3_endpoint):
    rejected(s3_endpoint, "CreateConfigurationSet", "ValidationError")


def test_create_configuration_set_refuses_a_duplicate_name(s3_endpoint):
    ensure_config_set(s3_endpoint, CONFIG_SET)
    rejected(
        s3_endpoint,
        "CreateConfigurationSet",
        "ConfigurationSetAlreadyExists",
        **{"ConfigurationSet.Name": CONFIG_SET},
    )


def test_list_configuration_sets_includes_the_named_set(s3_endpoint):
    ensure_config_set(s3_endpoint, CONFIG_SET)
    assert CONFIG_SET in config_set_names(s3_endpoint)


def test_describe_configuration_set_echoes_the_name(s3_endpoint):
    ensure_config_set(s3_endpoint, CONFIG_SET)
    described = ok(s3_endpoint, "DescribeConfigurationSet", ConfigurationSetName=CONFIG_SET)
    assert field(described, "Name") == CONFIG_SET


def test_describe_configuration_set_names_a_missing_set(s3_endpoint):
    text = rejected(
        s3_endpoint,
        "DescribeConfigurationSet",
        "ConfigurationSetDoesNotExist",
        ConfigurationSetName="ops-ses-config-set-never-created",
    )
    assert "ops-ses-config-set-never-created" in text


def test_delete_configuration_set_removes_the_set_it_created(s3_endpoint):
    ok(s3_endpoint, "CreateConfigurationSet", **{"ConfigurationSet.Name": CONFIG_SET_DELETED})
    assert CONFIG_SET_DELETED in config_set_names(s3_endpoint)
    ok(s3_endpoint, "DeleteConfigurationSet", ConfigurationSetName=CONFIG_SET_DELETED)
    assert CONFIG_SET_DELETED not in config_set_names(s3_endpoint)
    rejected(
        s3_endpoint,
        "DeleteConfigurationSet",
        "ConfigurationSetDoesNotExist",
        ConfigurationSetName=CONFIG_SET_DELETED,
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def template_parts(endpoint, name: str) -> tuple[str, str, str]:
    got = ok(endpoint, "GetTemplate", TemplateName=name)
    return tuple(
        html.unescape(field(got, part)) for part in ("SubjectPart", "TextPart", "HtmlPart")
    )


def test_create_template_is_read_back(s3_endpoint):
    ensure_template(s3_endpoint, TEMPLATE)
    assert (TEMPLATE_SUBJECT, TEMPLATE_TEXT, TEMPLATE_HTML) == template_parts(s3_endpoint, TEMPLATE)


def test_create_template_refuses_a_duplicate_name(s3_endpoint):
    ensure_template(s3_endpoint, TEMPLATE)
    text = rejected(
        s3_endpoint,
        "CreateTemplate",
        "AlreadyExists",
        **{"Template.TemplateName": TEMPLATE, "Template.SubjectPart": TEMPLATE_SUBJECT},
    )
    assert TEMPLATE in text


def test_get_template_echoes_every_part(s3_endpoint):
    ensure_template(s3_endpoint, TEMPLATE)
    assert template_parts(s3_endpoint, TEMPLATE) == (
        TEMPLATE_SUBJECT,
        TEMPLATE_TEXT,
        TEMPLATE_HTML,
    )


def test_get_template_names_a_missing_template(s3_endpoint):
    text = rejected(
        s3_endpoint, "GetTemplate", "TemplateDoesNotExist", TemplateName="ops-ses-never-created"
    )
    assert "ops-ses-never-created" in text


def test_update_template_changes_the_stored_subject(s3_endpoint):
    ensure_template(s3_endpoint, TEMPLATE)
    ok(
        s3_endpoint,
        "UpdateTemplate",
        **{
            "Template.TemplateName": TEMPLATE,
            "Template.SubjectPart": "Updated {{name}}",
            "Template.TextPart": "Updated text",
        },
    )
    assert template_parts(s3_endpoint, TEMPLATE)[:2] == ("Updated {{name}}", "Updated text")
    # Put the shared template back the way every other test expects to read it.
    ensure_template(s3_endpoint, TEMPLATE)
    assert template_parts(s3_endpoint, TEMPLATE)[0] == TEMPLATE_SUBJECT


def test_list_templates_includes_the_created_template(s3_endpoint):
    ensure_template(s3_endpoint, TEMPLATE)
    names = [
        field(block, "Name")
        for block in members(s3_endpoint, "ListTemplates", MaxItems="100")
    ]
    assert TEMPLATE in names


def test_delete_template_removes_the_template_it_created(s3_endpoint):
    ok(
        s3_endpoint,
        "CreateTemplate",
        **{"Template.TemplateName": TEMPLATE_DELETED, "Template.SubjectPart": "Delete me"},
    )
    ok(s3_endpoint, "DeleteTemplate", TemplateName=TEMPLATE_DELETED)
    rejected(s3_endpoint, "GetTemplate", "TemplateDoesNotExist", TemplateName=TEMPLATE_DELETED)


# ---------------------------------------------------------------------------
# Receipt rule sets and the rules inside them
# ---------------------------------------------------------------------------

def rule_set_names(endpoint) -> list[str]:
    return [
        field(block, "Name")
        for block in members(endpoint, "ListReceiptRuleSets", MaxItems="100")
    ]


def test_create_receipt_rule_set_is_read_back_by_list(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    assert RULE_SET in rule_set_names(s3_endpoint)


def test_create_receipt_rule_set_refuses_a_duplicate_name(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    rejected(s3_endpoint, "CreateReceiptRuleSet", "AlreadyExists", RuleSetName=RULE_SET)


def test_create_receipt_rule_set_requires_a_name(s3_endpoint):
    rejected(s3_endpoint, "CreateReceiptRuleSet", "ValidationError")


def test_list_receipt_rule_sets_includes_the_named_set(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    assert RULE_SET in rule_set_names(s3_endpoint)


def test_describe_receipt_rule_set_echoes_the_metadata(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    described = ok(s3_endpoint, "DescribeReceiptRuleSet", RuleSetName=RULE_SET)
    assert "<Metadata>" in described
    assert field(described, "Name") == RULE_SET
    assert "<Rules>" in described


def test_describe_receipt_rule_set_names_a_missing_set(s3_endpoint):
    text = rejected(
        s3_endpoint,
        "DescribeReceiptRuleSet",
        "RuleSetDoesNotExist",
        RuleSetName="ops-ses-rule-set-never-created",
    )
    assert "ops-ses-rule-set-never-created" in text


def test_delete_receipt_rule_set_removes_the_set_it_created(s3_endpoint):
    ok(s3_endpoint, "CreateReceiptRuleSet", RuleSetName=RULE_SET_DELETED)
    assert RULE_SET_DELETED in rule_set_names(s3_endpoint)
    ok(s3_endpoint, "DeleteReceiptRuleSet", RuleSetName=RULE_SET_DELETED)
    assert RULE_SET_DELETED not in rule_set_names(s3_endpoint)
    rejected(
        s3_endpoint, "DescribeReceiptRuleSet", "RuleSetDoesNotExist", RuleSetName=RULE_SET_DELETED
    )


def test_set_active_receipt_rule_set_is_read_back_by_describe_active(s3_endpoint):
    ensure_rule_set(s3_endpoint, ACTIVE_RULE_SET)
    ok(s3_endpoint, "SetActiveReceiptRuleSet", RuleSetName=ACTIVE_RULE_SET)
    active = ok(s3_endpoint, "DescribeActiveReceiptRuleSet")
    assert "<Metadata>" in active
    assert field(active, "Name") == ACTIVE_RULE_SET


def test_create_receipt_rule_is_read_back_by_describe(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    status, text = call(
        s3_endpoint,
        "ses",
        "CreateReceiptRule",
        RuleSetName=RULE_SET,
        **rule_params(RULE, "X-Ops-Ses"),
    )
    assert status == 200 or "AlreadyExists" in text, (
        f"CreateReceiptRule answered {status}: {text[:400]}"
    )
    described = ok(s3_endpoint, "DescribeReceiptRule", RuleSetName=RULE_SET, RuleName=RULE)
    assert field(described, "Name") == RULE
    assert field(described, "Enabled") == "true"
    assert field(described, "TlsPolicy") == "Optional"
    assert field(described, "HeaderName") == "X-Ops-Ses"
    assert field(described, "HeaderValue") == "emuplane"
    assert "ops-ses-recipient@ops-ses-domain.example" in described


def test_create_receipt_rule_refuses_a_duplicate_name(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    status, text = call(
        s3_endpoint, "ses", "CreateReceiptRule", RuleSetName=RULE_SET, **rule_params(RULE, "X-Ops-Ses")
    )
    assert status == 200 or "AlreadyExists" in text
    rejected(
        s3_endpoint,
        "CreateReceiptRule",
        "AlreadyExists",
        RuleSetName=RULE_SET,
        **rule_params(RULE, "X-Ops-Ses"),
    )


def test_create_receipt_rule_names_a_missing_rule_set(s3_endpoint):
    rejected(
        s3_endpoint,
        "CreateReceiptRule",
        "RuleSetDoesNotExist",
        RuleSetName="ops-ses-rule-set-never-created",
        **rule_params("ops-ses-rule-missing-set", "X-Ops-Ses"),
    )


def test_describe_receipt_rule_names_a_missing_rule(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    rejected(
        s3_endpoint,
        "DescribeReceiptRule",
        "RuleDoesNotExist",
        RuleSetName=RULE_SET,
        RuleName="ops-ses-rule-never-created",
    )


def test_delete_receipt_rule_removes_the_rule_it_created(s3_endpoint):
    ensure_rule_set(s3_endpoint, RULE_SET)
    ok(s3_endpoint, "CreateReceiptRule", RuleSetName=RULE_SET, **rule_params(RULE_DELETED, "X-Delete-Me"))
    described = ok(s3_endpoint, "DescribeReceiptRule", RuleSetName=RULE_SET, RuleName=RULE_DELETED)
    assert field(described, "Name") == RULE_DELETED
    ok(s3_endpoint, "DeleteReceiptRule", RuleSetName=RULE_SET, RuleName=RULE_DELETED)
    rejected(
        s3_endpoint,
        "DescribeReceiptRule",
        "RuleDoesNotExist",
        RuleSetName=RULE_SET,
        RuleName=RULE_DELETED,
    )
