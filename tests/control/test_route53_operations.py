"""Route 53 on the wire: all 19 advertised operations, REST/XML.

Signed with the `route53` credential scope under `/2013-04-01`. A hosted zone and
a health check are keyed by their IDs; a stable zone and check carry the
read/update/tag tests while a create or delete test makes its own. Zone and
health-check creation is idempotent on `CallerReference`.
"""

from __future__ import annotations

import re
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
BASE = "/2013-04-01"
XML = {"Content-Type": "application/xml"}
ZONE = "ops-route53.example.com."
CALLER = "ops-route53-caller"
HC_CALLER = "ops-route53-health-caller"


def call(endpoint, method: str, path: str, body: str = ""):
    return signed.request(endpoint, "route53", ACCOUNT, REGION, method, BASE + path, body, XML)


def ok(endpoint, method: str, path: str, body: str = "", statuses=(200,)) -> str:
    status, text = call(endpoint, method, path, body)
    assert status in statuses, f"{method} {path} answered {status}: {text[:400]}"
    return text


def refused(endpoint, method: str, path: str, body: str = "") -> str:
    status, text = call(endpoint, method, path, body)
    assert status >= 400, f"{method} {path} unexpectedly answered {status}: {text[:400]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def zone_body(name: str, caller: str, comment: str = "", vpc: str = "") -> str:
    vpc_xml = ""
    if vpc:
        vpc_xml = f"<VPC><VPCRegion>{REGION}</VPCRegion><VPCId>{vpc}</VPCId></VPC>"
    return (
        "<CreateHostedZoneRequest>"
        f"<Name>{name}</Name><CallerReference>{caller}</CallerReference>"
        f"<HostedZoneConfig><Comment>{comment}</Comment></HostedZoneConfig>{vpc_xml}"
        "</CreateHostedZoneRequest>"
    )


def ensure_zone(endpoint, name: str = ZONE, caller: str = CALLER) -> str:
    text = ok(endpoint, "POST", "/hostedzone", zone_body(name, caller), statuses=(200, 201))
    return field(text, "Id").rsplit("/", 1)[-1]


def health_body(caller: str, path: str = "/") -> str:
    return (
        "<CreateHealthCheckRequest>"
        f"<CallerReference>{caller}</CallerReference>"
        "<HealthCheckConfig><Type>HTTP</Type>"
        "<FullyQualifiedDomainName>ops.example.com</FullyQualifiedDomainName>"
        f"<Port>80</Port><ResourcePath>{path}</ResourcePath>"
        "<RequestInterval>30</RequestInterval><FailureThreshold>3</FailureThreshold>"
        "</HealthCheckConfig></CreateHealthCheckRequest>"
    )


def ensure_health_check(endpoint, caller: str = HC_CALLER) -> str:
    text = ok(endpoint, "POST", "/healthcheck", health_body(caller), statuses=(200, 201))
    return field(text, "Id")


def record_body(action: str, name: str, value: str) -> str:
    return (
        "<ChangeResourceRecordSetsRequest><ChangeBatch><Changes><Change>"
        f"<Action>{action}</Action><ResourceRecordSet><Name>{name}</Name><Type>A</Type><TTL>300</TTL>"
        f"<ResourceRecords><ResourceRecord><Value>{value}</Value></ResourceRecord></ResourceRecords>"
        "</ResourceRecordSet></Change></Changes></ChangeBatch></ChangeResourceRecordSetsRequest>"
    )


# ---------------------------------------------------------------------------
# Hosted zones
# ---------------------------------------------------------------------------


def test_create_hosted_zone_is_read_back(endpoint):
    caller = f"ops-zone-{time.time_ns()}"
    created = ok(endpoint, "POST", "/hostedzone", zone_body(f"ops-{time.time_ns()}.example.com.", caller), statuses=(200, 201))
    zone_id = field(created, "Id").rsplit("/", 1)[-1]
    assert zone_id in ok(endpoint, "GET", f"/hostedzone/{zone_id}")


def test_get_hosted_zone_reads_the_zone(endpoint):
    zone_id = ensure_zone(endpoint)
    assert ZONE in ok(endpoint, "GET", f"/hostedzone/{zone_id}")


def test_delete_hosted_zone_removes_the_zone_it_created(endpoint):
    caller = f"ops-zone-del-{time.time_ns()}"
    created = ok(endpoint, "POST", "/hostedzone", zone_body(f"ops-del-{time.time_ns()}.example.com.", caller), statuses=(200, 201))
    zone_id = field(created, "Id").rsplit("/", 1)[-1]
    ok(endpoint, "DELETE", f"/hostedzone/{zone_id}")
    refused(endpoint, "GET", f"/hostedzone/{zone_id}")


def test_list_hosted_zones_lists_the_zone(endpoint):
    zone_id = ensure_zone(endpoint)
    assert zone_id in ok(endpoint, "GET", "/hostedzone")


def test_list_hosted_zones_by_name_lists_the_zone(endpoint):
    ensure_zone(endpoint)
    assert ZONE in ok(endpoint, "GET", f"/hostedzonesbyname?dnsname={ZONE}")


def test_update_hosted_zone_comment_changes_it(endpoint):
    zone_id = ensure_zone(endpoint)
    body = "<UpdateHostedZoneCommentRequest><Comment>managed by ops</Comment></UpdateHostedZoneCommentRequest>"
    ok(endpoint, "POST", f"/hostedzone/{zone_id}", body)
    assert "managed by ops" in ok(endpoint, "GET", f"/hostedzone/{zone_id}")


def test_associate_vpc_with_hosted_zone_adds_the_vpc(endpoint):
    caller = f"ops-priv-{time.time_ns()}"
    created = ok(
        endpoint,
        "POST",
        "/hostedzone",
        zone_body(f"ops-priv-{time.time_ns()}.example.com.", caller, vpc="vpc-ops1"),
        statuses=(200, 201),
    )
    zone_id = field(created, "Id").rsplit("/", 1)[-1]
    body = "<AssociateVPCWithHostedZoneRequest><VPC><VPCRegion>us-east-1</VPCRegion><VPCId>vpc-ops2</VPCId></VPC></AssociateVPCWithHostedZoneRequest>"
    assert "ChangeInfo" in ok(endpoint, "POST", f"/hostedzone/{zone_id}/associatevpc", body)


def test_disassociate_vpc_from_hosted_zone_removes_the_vpc(endpoint):
    caller = f"ops-priv-{time.time_ns()}"
    created = ok(
        endpoint,
        "POST",
        "/hostedzone",
        zone_body(f"ops-priv-{time.time_ns()}.example.com.", caller, vpc="vpc-ops3"),
        statuses=(200, 201),
    )
    zone_id = field(created, "Id").rsplit("/", 1)[-1]
    ok(endpoint, "POST", f"/hostedzone/{zone_id}/associatevpc", "<AssociateVPCWithHostedZoneRequest><VPC><VPCRegion>us-east-1</VPCRegion><VPCId>vpc-ops4</VPCId></VPC></AssociateVPCWithHostedZoneRequest>")
    body = "<DisassociateVPCFromHostedZoneRequest><VPC><VPCRegion>us-east-1</VPCRegion><VPCId>vpc-ops4</VPCId></VPC></DisassociateVPCFromHostedZoneRequest>"
    assert "ChangeInfo" in ok(endpoint, "POST", f"/hostedzone/{zone_id}/disassociatevpc", body)


def test_list_hosted_zones_by_vpc_lists_the_zone(endpoint):
    caller = f"ops-priv-{time.time_ns()}"
    ok(
        endpoint,
        "POST",
        "/hostedzone",
        zone_body(f"ops-priv-{time.time_ns()}.example.com.", caller, vpc="vpc-ops5"),
        statuses=(200, 201),
    )
    assert "HostedZone" in ok(endpoint, "GET", "/hostedzonesbyvpc?vpcid=vpc-ops5&vpcregion=us-east-1")


# ---------------------------------------------------------------------------
# Record sets
# ---------------------------------------------------------------------------


def test_change_resource_record_sets_upserts_a_record(endpoint):
    zone_id = ensure_zone(endpoint)
    ok(endpoint, "POST", f"/hostedzone/{zone_id}/rrset", record_body("UPSERT", "www.ops-route53.example.com.", "192.0.2.10"))
    assert "www.ops-route53.example.com." in ok(endpoint, "GET", f"/hostedzone/{zone_id}/rrset")


def test_list_resource_record_sets_lists_the_record(endpoint):
    zone_id = ensure_zone(endpoint)
    ok(endpoint, "POST", f"/hostedzone/{zone_id}/rrset", record_body("UPSERT", "api.ops-route53.example.com.", "192.0.2.11"))
    assert "api.ops-route53.example.com." in ok(endpoint, "GET", f"/hostedzone/{zone_id}/rrset")


def test_get_change_reads_the_change(endpoint):
    zone_id = ensure_zone(endpoint)
    created = ok(endpoint, "POST", f"/hostedzone/{zone_id}/rrset", record_body("UPSERT", "change.ops-route53.example.com.", "192.0.2.12"))
    change_id = field(created, "Id").rsplit("/", 1)[-1]
    assert "ChangeInfo" in ok(endpoint, "GET", f"/change/{change_id}")


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


def test_create_health_check_is_read_back(endpoint):
    caller = f"ops-hc-{time.time_ns()}"
    created = ok(endpoint, "POST", "/healthcheck", health_body(caller), statuses=(200, 201))
    hc_id = field(created, "Id")
    assert hc_id in ok(endpoint, "GET", f"/healthcheck/{hc_id}")


def test_get_health_check_reads_the_check(endpoint):
    hc_id = ensure_health_check(endpoint)
    assert HC_CALLER in ok(endpoint, "GET", f"/healthcheck/{hc_id}")


def test_delete_health_check_removes_the_check_it_created(endpoint):
    caller = f"ops-hc-del-{time.time_ns()}"
    created = ok(endpoint, "POST", "/healthcheck", health_body(caller), statuses=(200, 201))
    hc_id = field(created, "Id")
    ok(endpoint, "DELETE", f"/healthcheck/{hc_id}")
    refused(endpoint, "GET", f"/healthcheck/{hc_id}")


def test_list_health_checks_lists_the_check(endpoint):
    hc_id = ensure_health_check(endpoint)
    assert hc_id in ok(endpoint, "GET", "/healthcheck")


def test_update_health_check_changes_the_path(endpoint):
    hc_id = ensure_health_check(endpoint)
    body = "<UpdateHealthCheckRequest><ResourcePath>/ops</ResourcePath></UpdateHealthCheckRequest>"
    assert "/ops" in ok(endpoint, "POST", f"/healthcheck/{hc_id}", body)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_change_tags_for_resource_adds_a_tag(endpoint):
    zone_id = ensure_zone(endpoint)
    body = "<ChangeTagsForResourceRequest><AddTags><Tag><Key>env</Key><Value>ops</Value></Tag></AddTags></ChangeTagsForResourceRequest>"
    ok(endpoint, "POST", f"/tags/hostedzone/{zone_id}", body)
    assert "<Key>env</Key>" in ok(endpoint, "GET", f"/tags/hostedzone/{zone_id}")


def test_list_tags_for_resource_lists_the_tags(endpoint):
    zone_id = ensure_zone(endpoint)
    body = "<ChangeTagsForResourceRequest><AddTags><Tag><Key>team</Key><Value>platform</Value></Tag></AddTags></ChangeTagsForResourceRequest>"
    ok(endpoint, "POST", f"/tags/hostedzone/{zone_id}", body)
    assert "<Key>team</Key>" in ok(endpoint, "GET", f"/tags/hostedzone/{zone_id}")
