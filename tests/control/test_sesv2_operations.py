"""SES v2 on the wire: every advertised REST/JSON operation under ``/v2/email/``.

The service is signed with the ``ses`` credential scope (the name the SDKs use for
both API versions); the ``ses`` module delegates a ``/v2/`` path to ``ses_v2``.

A create is proven by a read, never undone: identities, configuration sets,
event destinations, templates, tenants and dedicated IP pools are left in place,
and each create tolerates the ``AlreadyExists`` a second sweep meets. A delete
action builds a resource of its own (the ``*-doomed`` names) and removes only
that. Templates are shared with SES v1, so one test creates a template through
the v1 query API and reads it back through v2.

SES v2 has no mailbox simulator identity of its own, but the shared sandbox check
does: a send goes to ``success@simulator.amazonses.com`` so it is delivered
whether or not the account has production access.
"""

from __future__ import annotations

import json
from urllib.parse import quote, urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

SENDER = "ops-sesv2-sender@example.com"
DOOMED_IDENTITY = "ops-sesv2-doomed@example.com"
GUARDED_IDENTITY = "ops-sesv2-guarded@example.com"
IDENTITY_ARN = f"arn:aws:ses:{REGION}:{ACCOUNT}:identity/{SENDER}"
TOPIC_ARN = f"arn:aws:sns:{REGION}:{ACCOUNT}:ops-sesv2"
RECIPIENT = "success@simulator.amazonses.com"

CFG = "ops-sesv2-cfg"
CFG_READ_BACK = "ops-sesv2-cfg-created"
CFG_DOOMED = "ops-sesv2-cfg-doomed"
CFG_EVENTS = "ops-sesv2-cfg-events"

DESTINATION = "ops-sesv2-destination"
DESTINATION_DOOMED = "ops-sesv2-destination-doomed"

TEMPLATE = "ops-sesv2-template"
TEMPLATE_DOOMED = "ops-sesv2-template-doomed"
TEMPLATE_SUBJECT = "Hello {{name}}"

POOL = "ops-sesv2-pool"
POOL_DOOMED = "ops-sesv2-pool-doomed"

TENANT = "ops_sesv2_tenant"
TENANT_DELETED = "ops_sesv2_deleted"
TENANT_GUARDED = "ops_sesv2_guarded"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, method: str, path: str, body=""):
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return signed.request(
        endpoint, "ses", ACCOUNT, REGION, method, f"/v2/email{path}", body,
        JSON if body else None,
    )


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = call(endpoint, method, path, body)
    assert status in (200, 201, 204), (
        f"{method} /v2/email{path} answered {status}: {text[:400]}"
    )
    return json.loads(text) if text.strip() else {}


def rejected(endpoint, method: str, path: str, body="", status: int = 400) -> str:
    got, text = call(endpoint, method, path, body)
    assert got == status, f"{method} /v2/email{path} answered {got}: {text[:400]}"
    return text



# ---------------------------------------------------------------------------
# Find-or-create, so a re-run meets what the first sweep left
# ---------------------------------------------------------------------------


def ensure_identity(endpoint, identity: str = SENDER) -> None:
    ok(endpoint, "POST", "/identities", {"EmailIdentity": identity})


def ensure_config_set(endpoint, name: str = CFG) -> None:
    status, text = call(endpoint, "POST", "/configuration-sets", {"ConfigurationSetName": name})
    assert status in (200, 400), f"CreateConfigurationSet answered {status}: {text[:400]}"
    if status == 400:
        assert "AlreadyExists" in text


def ensure_template(endpoint, name: str = TEMPLATE) -> None:
    status, text = call(
        endpoint,
        "POST",
        "/templates",
        {
            "TemplateName": name,
            "TemplateContent": {
                "Subject": TEMPLATE_SUBJECT,
                "Text": "Body for {{name}}",
                "Html": "<p>Body for {{name}}</p>",
            },
        },
    )
    assert status in (200, 400), f"CreateEmailTemplate answered {status}: {text[:400]}"
    if status == 400:
        assert "AlreadyExists" in text


def ensure_pool(endpoint, name: str = POOL) -> None:
    status, text = call(endpoint, "POST", "/dedicated-ip-pools", {"PoolName": name})
    assert status in (200, 400), f"CreateDedicatedIpPool answered {status}: {text[:400]}"
    if status == 400:
        assert "AlreadyExists" in text


def ensure_tenant(endpoint, name: str = TENANT) -> None:
    status, text = call(endpoint, "POST", "/tenants", {"TenantName": name})
    assert status in (200, 400), f"CreateTenant answered {status}: {text[:400]}"
    if status == 400:
        assert "AlreadyExists" in text


def ensure_destination(endpoint, name: str = DESTINATION) -> None:
    ensure_config_set(endpoint, CFG_EVENTS)
    definition = {
        "Enabled": True,
        "MatchingEventTypes": ["SEND"],
        "SnsDestination": {"TopicArn": TOPIC_ARN},
    }
    status, text = call(
        endpoint,
        "POST",
        f"/configuration-sets/{CFG_EVENTS}/event-destinations",
        {"EventDestinationName": name, "EventDestination": definition},
    )
    assert status in (200, 400), f"CreateConfigurationSetEventDestination answered {status}: {text[:400]}"
    if status == 400:
        assert "AlreadyExists" in text
        # A re-run meets the destination an update test left behind; put the
        # baseline types back so the read below sees the create's shape.
        ok(
            endpoint,
            "PUT",
            f"/configuration-sets/{CFG_EVENTS}/event-destinations/{name}",
            {"EventDestination": definition},
        )


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------


def test_create_email_identity_is_read_back_verified(endpoint):
    answer = ok(endpoint, "POST", "/identities", {"EmailIdentity": SENDER})
    assert answer["IdentityType"] == "EMAIL_ADDRESS"
    assert answer["VerifiedForSendingStatus"] is True

    identity = ok(endpoint, "GET", f"/identities/{SENDER}")
    assert identity["VerifiedForSendingStatus"] is True
    assert identity["VerificationStatus"] == "SUCCESS"


def test_get_email_identity_reports_the_domain_dkim_tokens(endpoint):
    domain = "ops-sesv2.example.com"
    answer = ok(endpoint, "POST", "/identities", {"EmailIdentity": domain})
    assert answer["IdentityType"] == "DOMAIN"

    identity = ok(endpoint, "GET", f"/identities/{domain}")
    assert identity["IdentityType"] == "DOMAIN"
    assert len(identity["DkimAttributes"]["Tokens"]) == 3


def test_list_email_identities_includes_the_created_identity(endpoint):
    ensure_identity(endpoint)
    answer = ok(endpoint, "GET", "/identities?PageSize=100")
    names = [item["IdentityName"] for item in answer["EmailIdentities"]]
    assert SENDER in names


def test_delete_email_identity_removes_the_identity_it_created(endpoint):
    ok(endpoint, "POST", "/identities", {"EmailIdentity": DOOMED_IDENTITY})
    ok(endpoint, "DELETE", f"/identities/{DOOMED_IDENTITY}")
    rejected(endpoint, "GET", f"/identities/{DOOMED_IDENTITY}", status=404)


def test_put_email_identity_configuration_set_attributes_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ensure_identity(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/identities/{SENDER}/configuration-set",
        {"ConfigurationSetName": CFG},
    )
    identity = ok(endpoint, "GET", f"/identities/{SENDER}")
    assert identity["ConfigurationSetName"] == CFG


# ---------------------------------------------------------------------------
# Configuration sets
# ---------------------------------------------------------------------------


def test_create_configuration_set_is_read_back_by_get(endpoint):
    ensure_config_set(endpoint, CFG_READ_BACK)
    created = ok(endpoint, "GET", f"/configuration-sets/{CFG_READ_BACK}")
    assert created["ConfigurationSetName"] == CFG_READ_BACK


def test_get_configuration_set_echoes_the_name_and_defaults(endpoint):
    # A set no option test edits, so its defaults are still the service's own
    # however many sweeps have run.
    ensure_config_set(endpoint, CFG_READ_BACK)
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG_READ_BACK}")
    assert config["ConfigurationSetName"] == CFG_READ_BACK
    # A newly created set carries the service defaults.
    assert config["ReputationOptions"]["ReputationMetricsEnabled"] is True
    assert config["SendingOptions"]["SendingEnabled"] is True


def test_list_configuration_sets_includes_the_named_set(endpoint):
    ensure_config_set(endpoint)
    answer = ok(endpoint, "GET", "/configuration-sets?PageSize=100")
    assert CFG in answer["ConfigurationSets"]


def test_delete_configuration_set_removes_the_set_it_created(endpoint):
    ensure_config_set(endpoint, CFG_DOOMED)
    ok(endpoint, "DELETE", f"/configuration-sets/{CFG_DOOMED}")
    rejected(endpoint, "GET", f"/configuration-sets/{CFG_DOOMED}", status=404)


def test_put_configuration_set_tracking_options_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG}/tracking-options",
        {"CustomRedirectDomain": "links.example.com"},
    )
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG}")
    assert config["TrackingOptions"]["CustomRedirectDomain"] == "links.example.com"


def test_put_configuration_set_delivery_options_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG}/delivery-options",
        {"TlsPolicy": "REQUIRE"},
    )
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG}")
    assert config["DeliveryOptions"]["TlsPolicy"] == "REQUIRE"


def test_put_configuration_set_reputation_options_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG}/reputation-options",
        {"ReputationMetricsEnabled": False},
    )
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG}")
    assert config["ReputationOptions"]["ReputationMetricsEnabled"] is False


def test_put_configuration_set_sending_options_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG}/sending",
        {"SendingEnabled": False},
    )
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG}")
    assert config["SendingOptions"]["SendingEnabled"] is False


def test_put_configuration_set_suppression_options_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG}/suppression-options",
        {"SuppressedReasons": ["BOUNCE"]},
    )
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG}")
    assert config["SuppressionOptions"]["SuppressedReasons"] == ["BOUNCE"]


def test_put_configuration_set_vdm_options_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG}/vdm-options",
        {"VdmOptions": {"DashboardOptions": {"EngagementMetrics": "ENABLED"}}},
    )
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG}")
    assert config["VdmOptions"]["DashboardOptions"]["EngagementMetrics"] == "ENABLED"


def test_put_configuration_set_archiving_options_is_read_back(endpoint):
    ensure_config_set(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG}/archiving-options",
        {"ArchiveArn": TOPIC_ARN},
    )
    config = ok(endpoint, "GET", f"/configuration-sets/{CFG}")
    assert config["ArchivingOptions"]["ArchiveArn"] == TOPIC_ARN


# ---------------------------------------------------------------------------
# Event destinations
# ---------------------------------------------------------------------------


def test_create_configuration_set_event_destination_is_read_back(endpoint):
    ensure_destination(endpoint)
    answer = ok(endpoint, "GET", f"/configuration-sets/{CFG_EVENTS}/event-destinations")
    names = [item["Name"] for item in answer["EventDestinations"]]
    assert DESTINATION in names


def test_get_configuration_set_event_destinations_shows_the_sns_target(endpoint):
    ensure_destination(endpoint)
    answer = ok(endpoint, "GET", f"/configuration-sets/{CFG_EVENTS}/event-destinations")
    stored = next(item for item in answer["EventDestinations"] if item["Name"] == DESTINATION)
    assert stored["SnsDestination"]["TopicArn"] == TOPIC_ARN
    assert stored["MatchingEventTypes"] == ["SEND"]


def test_update_configuration_set_event_destination_replaces_the_event_types(endpoint):
    ensure_destination(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/configuration-sets/{CFG_EVENTS}/event-destinations/{DESTINATION}",
        {
            "EventDestination": {
                "Enabled": True,
                "MatchingEventTypes": ["SEND", "DELIVERY"],
                "SnsDestination": {"TopicArn": TOPIC_ARN},
            }
        },
    )
    answer = ok(endpoint, "GET", f"/configuration-sets/{CFG_EVENTS}/event-destinations")
    stored = next(item for item in answer["EventDestinations"] if item["Name"] == DESTINATION)
    assert stored["MatchingEventTypes"] == ["DELIVERY", "SEND"]


def test_delete_configuration_set_event_destination_removes_the_one_it_created(endpoint):
    ensure_destination(endpoint, DESTINATION_DOOMED)
    ok(
        endpoint,
        "DELETE",
        f"/configuration-sets/{CFG_EVENTS}/event-destinations/{DESTINATION_DOOMED}",
    )
    answer = ok(endpoint, "GET", f"/configuration-sets/{CFG_EVENTS}/event-destinations")
    names = [item["Name"] for item in answer["EventDestinations"]]
    assert DESTINATION_DOOMED not in names


# ---------------------------------------------------------------------------
# Templates (shared with SES v1)
# ---------------------------------------------------------------------------


def test_create_email_template_is_read_back(endpoint):
    ensure_template(endpoint)
    template = ok(endpoint, "GET", f"/templates/{TEMPLATE}")
    assert template["TemplateContent"]["Subject"] == TEMPLATE_SUBJECT


def test_get_email_template_echoes_every_part(endpoint):
    ensure_template(endpoint)
    template = ok(endpoint, "GET", f"/templates/{TEMPLATE}")["TemplateContent"]
    assert template["Subject"] == TEMPLATE_SUBJECT
    assert template["Text"] == "Body for {{name}}"
    assert template["Html"] == "<p>Body for {{name}}</p>"


def test_update_email_template_changes_the_stored_subject(endpoint):
    ensure_template(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/templates/{TEMPLATE}",
        {"TemplateContent": {"Subject": "Updated {{name}}", "Text": "Updated text"}},
    )
    template = ok(endpoint, "GET", f"/templates/{TEMPLATE}")
    assert template["TemplateContent"]["Subject"] == "Updated {{name}}"
    # Put the shared template back the way every other test expects to read it.
    ok(
        endpoint,
        "PUT",
        f"/templates/{TEMPLATE}",
        {
            "TemplateContent": {
                "Subject": TEMPLATE_SUBJECT,
                "Text": "Body for {{name}}",
                "Html": "<p>Body for {{name}}</p>",
            }
        },
    )


def test_list_email_templates_includes_the_created_template(endpoint):
    ensure_template(endpoint)
    answer = ok(endpoint, "GET", "/templates?PageSize=100")
    names = [item["TemplateName"] for item in answer["TemplatesMetadata"]]
    assert TEMPLATE in names


def test_delete_email_template_removes_the_template_it_created(endpoint):
    ensure_template(endpoint, TEMPLATE_DOOMED)
    ok(endpoint, "DELETE", f"/templates/{TEMPLATE_DOOMED}")
    rejected(endpoint, "GET", f"/templates/{TEMPLATE_DOOMED}", status=404)


def test_a_template_created_through_v1_is_read_by_v2(endpoint):
    name = "ops-sesv2-v1-shared"
    status, text = signed.request(
        endpoint,
        "ses",
        ACCOUNT,
        REGION,
        "POST",
        "/",
        urlencode(
            {
                "Action": "CreateTemplate",
                "Template.TemplateName": name,
                "Template.SubjectPart": "Shared through v1",
                "Template.TextPart": "Body",
            }
        ),
        FORM,
    )
    assert status in (200, 400), f"v1 CreateTemplate answered {status}: {text[:400]}"
    if status == 400:
        assert "AlreadyExists" in text
    template = ok(endpoint, "GET", f"/templates/{name}")
    assert template["TemplateContent"]["Subject"] == "Shared through v1"


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


def test_get_account_reports_a_healthy_sending_account(endpoint):
    account = ok(endpoint, "GET", "/account")
    assert account["SendingEnabled"] is True
    assert account["EnforcementStatus"] == "HEALTHY"
    assert account["SendQuota"]["Max24HourSend"] > 0


def test_put_account_details_is_read_back_by_get_account(endpoint):
    ok(
        endpoint,
        "POST",
        "/account/details",
        {
            "MailType": "TRANSACTIONAL",
            "WebsiteURL": "https://example.com",
            "ContactLanguage": "EN",
            "ProductionAccessEnabled": True,
        },
    )
    account = ok(endpoint, "GET", "/account")
    assert account["ProductionAccessEnabled"] is True
    assert account["Details"]["MailType"] == "TRANSACTIONAL"
    assert account["Details"]["WebsiteURL"] == "https://example.com"


def test_put_account_suppression_attributes_is_read_back(endpoint):
    ok(endpoint, "PUT", "/account/suppression", {"SuppressedReasons": ["BOUNCE"]})
    account = ok(endpoint, "GET", "/account")
    assert account["SuppressionAttributes"]["SuppressedReasons"] == ["BOUNCE"]


def test_list_suppressed_destinations_answers_a_list(endpoint):
    answer = ok(endpoint, "GET", "/suppression/addresses")
    assert isinstance(answer["SuppressedDestinationSummaries"], list)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_adds_a_tag_the_list_reads_back(endpoint):
    ensure_identity(endpoint)
    ok(
        endpoint,
        "POST",
        "/tags",
        {"ResourceArn": IDENTITY_ARN, "Tags": [{"Key": "env", "Value": "ops"}]},
    )
    answer = ok(endpoint, "GET", f"/tags?ResourceArn={quote(IDENTITY_ARN, safe='')}")
    tags = {tag["Key"]: tag["Value"] for tag in answer["Tags"]}
    assert tags["env"] == "ops"


def test_list_tags_for_resource_shows_the_identity_tags(endpoint):
    ensure_identity(endpoint)
    ok(
        endpoint,
        "POST",
        "/tags",
        {"ResourceArn": IDENTITY_ARN, "Tags": [{"Key": "team", "Value": "platform"}]},
    )
    answer = ok(endpoint, "GET", f"/tags?ResourceArn={quote(IDENTITY_ARN, safe='')}")
    assert {"Key": "team", "Value": "platform"} in answer["Tags"]


def test_untag_resource_removes_the_key_it_names(endpoint):
    ensure_identity(endpoint)
    ok(
        endpoint,
        "POST",
        "/tags",
        {"ResourceArn": IDENTITY_ARN, "Tags": [{"Key": "doomed", "Value": "yes"}]},
    )
    ok(
        endpoint,
        "DELETE",
        f"/tags?ResourceArn={quote(IDENTITY_ARN, safe='')}&TagKeys=doomed",
    )
    answer = ok(endpoint, "GET", f"/tags?ResourceArn={quote(IDENTITY_ARN, safe='')}")
    assert "doomed" not in {tag["Key"] for tag in answer["Tags"]}


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------


def test_create_tenant_is_read_back_by_get(endpoint):
    ensure_tenant(endpoint)
    tenant = ok(endpoint, "POST", "/tenants/get", {"TenantName": TENANT})["Tenant"]
    assert tenant["TenantName"] == TENANT
    assert tenant["TenantId"].startswith("tn-")
    assert tenant["SendingStatus"] == "ENABLED"


def test_get_tenant_returns_the_tenant_and_its_arn(endpoint):
    ensure_tenant(endpoint)
    tenant = ok(endpoint, "POST", "/tenants/get", {"TenantName": TENANT})["Tenant"]
    assert tenant["TenantArn"].endswith(f"tenant/{TENANT}/{tenant['TenantId']}")
    assert tenant["TenantName"] == TENANT


def test_list_tenants_includes_the_created_tenant(endpoint):
    ensure_tenant(endpoint)
    answer = ok(endpoint, "POST", "/tenants/list", {"PageSize": 100})
    assert TENANT in [item["TenantName"] for item in answer["Tenants"]]


def test_delete_tenant_removes_the_tenant_it_created(endpoint):
    ensure_tenant(endpoint, TENANT_DELETED)
    ok(endpoint, "POST", "/tenants/delete", {"TenantName": TENANT_DELETED})
    rejected(
        endpoint,
        "POST",
        "/tenants/get",
        {"TenantName": TENANT_DELETED},
        status=404,
    )


def test_create_tenant_resource_association_is_read_back_by_list(endpoint):
    ensure_tenant(endpoint)
    ensure_identity(endpoint)
    status, text = call(
        endpoint,
        "POST",
        "/tenants/resources",
        {"TenantName": TENANT, "ResourceArn": IDENTITY_ARN},
    )
    assert status in (200, 400), f"CreateTenantResourceAssociation answered {status}: {text[:400]}"
    if status == 400:
        assert "already been associated" in text
    answer = ok(
        endpoint, "POST", "/tenants/resources/list", {"TenantName": TENANT}
    )
    arns = [item["ResourceArn"] for item in answer["TenantResources"]]
    assert IDENTITY_ARN in arns


def test_list_tenant_resources_shows_the_resource_type(endpoint):
    ensure_tenant(endpoint)
    ensure_identity(endpoint)
    write = call(
        endpoint,
        "POST",
        "/tenants/resources",
        {"TenantName": TENANT, "ResourceArn": IDENTITY_ARN},
    )
    assert write[0] in (200, 400), write[1][:400]
    answer = ok(
        endpoint, "POST", "/tenants/resources/list", {"TenantName": TENANT}
    )
    kinds = {
        item["ResourceArn"]: item["ResourceType"] for item in answer["TenantResources"]
    }
    assert kinds.get(IDENTITY_ARN) == "EMAIL_IDENTITY"


def test_list_resource_tenants_names_the_tenant_of_a_resource(endpoint):
    ensure_tenant(endpoint)
    ensure_identity(endpoint)
    write = call(
        endpoint,
        "POST",
        "/tenants/resources",
        {"TenantName": TENANT, "ResourceArn": IDENTITY_ARN},
    )
    assert write[0] in (200, 400), write[1][:400]
    answer = ok(
        endpoint, "POST", "/resources/tenants/list", {"ResourceArn": IDENTITY_ARN}
    )
    assert TENANT in [item["TenantName"] for item in answer["ResourceTenants"]]


def test_delete_tenant_resource_association_removes_the_association(endpoint):
    ensure_tenant(endpoint)
    ensure_identity(endpoint)
    write = call(
        endpoint,
        "POST",
        "/tenants/resources",
        {"TenantName": TENANT, "ResourceArn": IDENTITY_ARN},
    )
    assert write[0] in (200, 400), write[1][:400]
    ok(
        endpoint,
        "POST",
        "/tenants/resources/delete",
        {"TenantName": TENANT, "ResourceArn": IDENTITY_ARN},
    )
    answer = ok(
        endpoint, "POST", "/tenants/resources/list", {"TenantName": TENANT}
    )
    assert IDENTITY_ARN not in [item["ResourceArn"] for item in answer["TenantResources"]]


def test_put_tenant_suppression_attributes_is_read_back(endpoint):
    ensure_tenant(endpoint)
    ok(
        endpoint,
        "POST",
        "/tenant/suppression",
        {
            "TenantName": TENANT,
            "SuppressedReasons": ["COMPLAINT"],
            "SuppressionScope": "TENANT",
        },
    )
    tenant = ok(endpoint, "POST", "/tenants/get", {"TenantName": TENANT})["Tenant"]
    assert tenant["SuppressionAttributes"]["SuppressedReasons"] == ["COMPLAINT"]
    assert tenant["SuppressionAttributes"]["SuppressionScope"] == "TENANT"


def test_a_resource_delete_is_refused_while_a_tenant_is_associated(endpoint):
    ensure_identity(endpoint, GUARDED_IDENTITY)
    ensure_tenant(endpoint, TENANT_GUARDED)
    guarded_arn = f"arn:aws:ses:{REGION}:{ACCOUNT}:identity/{GUARDED_IDENTITY}"
    write = call(
        endpoint,
        "POST",
        "/tenants/resources",
        {"TenantName": TENANT_GUARDED, "ResourceArn": guarded_arn},
    )
    assert write[0] in (200, 400), write[1][:400]
    # The documented rule: an associated resource cannot be deleted until the
    # association is removed. The identity is this test's own, so the delete that
    # follows removing the association removes only what it created.
    text = rejected(endpoint, "DELETE", f"/identities/{GUARDED_IDENTITY}")
    assert "tenant associations" in text
    ok(
        endpoint,
        "POST",
        "/tenants/resources/delete",
        {"TenantName": TENANT_GUARDED, "ResourceArn": guarded_arn},
    )
    ok(endpoint, "DELETE", f"/identities/{GUARDED_IDENTITY}")
    rejected(endpoint, "GET", f"/identities/{GUARDED_IDENTITY}", status=404)


# ---------------------------------------------------------------------------
# Dedicated IP pools
# ---------------------------------------------------------------------------


def test_create_dedicated_ip_pool_is_read_back_by_get(endpoint):
    ensure_pool(endpoint)
    pool = ok(endpoint, "GET", f"/dedicated-ip-pools/{POOL}")["DedicatedIpPool"]
    assert pool["PoolName"] == POOL
    assert pool["ScalingMode"] == "STANDARD"


def test_get_dedicated_ip_pool_names_the_pool(endpoint):
    ensure_pool(endpoint)
    answer = ok(endpoint, "GET", f"/dedicated-ip-pools/{POOL}")
    assert answer["DedicatedIpPool"]["PoolName"] == POOL


def test_list_dedicated_ip_pools_includes_the_pool(endpoint):
    ensure_pool(endpoint)
    answer = ok(endpoint, "GET", "/dedicated-ip-pools?PageSize=100")
    assert POOL in answer["DedicatedIpPools"]


def test_delete_dedicated_ip_pool_removes_the_pool_it_created(endpoint):
    ensure_pool(endpoint, POOL_DOOMED)
    ok(endpoint, "DELETE", f"/dedicated-ip-pools/{POOL_DOOMED}")
    rejected(endpoint, "GET", f"/dedicated-ip-pools/{POOL_DOOMED}", status=404)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


def test_send_email_answers_a_message_id(endpoint):
    ensure_identity(endpoint)
    answer = ok(
        endpoint,
        "POST",
        "/outbound-emails",
        {
            "FromEmailAddress": SENDER,
            "Destination": {"ToAddresses": [RECIPIENT]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": "Hello from Emuplane"},
                    "Body": {"Text": {"Data": "Body"}},
                }
            },
        },
    )
    assert answer["MessageId"].endswith("@email.amazonses.com")
