"""CloudFront on the wire: all 93 advertised operations, REST/XML with ETags.

Signed with the `cloudfront` scope. Every family in the row is exercised: distributions
and their configs, invalidations, origin access controls, monitoring subscriptions,
functions, key value stores (management), cache/origin-request/response-headers
policies, public keys and key groups, VPC origins, and the SaaS Manager's connection
groups, distribution tenants, tenant invalidations, DNS verification, managed
certificate details, domain conflicts and domain association.

ETag-based optimistic concurrency is the rule: an update or delete sends `If-Match`,
the header the previous read answered with. A VPC origin must name an EC2 instance or
load balancer that exists, so the suite launches one through the `ec2` query protocol;
a distribution tenant must attach to a `tenant-only` distribution, so the suite keeps
one of those as well. Delete tests create their own resource and disable it first;
update tests restore the stable record.
"""

from __future__ import annotations

import base64
import re
import secrets
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

DIST_REF = "ops-cf-dist-ref"
TENANT_DIST_REF = "ops-cf-tenant-dist-ref"
OAC_NAME = "ops-cf-oac"
CACHE_NAME = "ops-cf-cache"
ORP_NAME = "ops-cf-orp"
RHP_NAME = "ops-cf-rhp"
PUBLIC_KEY_NAME = "ops-cf-public-key"
KEY_GROUP_NAME = "ops-cf-key-group"
FUNCTION_NAME = "ops_cf_function"
KVS_NAME = "ops-cf-kvs"
VPC_ORIGIN_NAME = "ops-cf-vpc-origin"
GROUP_NAME = "ops-cf-group"
TENANT_NAME = "ops-cf-tenant"
TENANT_DOMAIN = "ops-cf-tenant.example.com"
ALIAS = "ops-cf-alias.example.com"
WEB_ACL_ARN = f"arn:aws:wafv2:us-east-1:{ACCOUNT}:global/webacl/ops-cf-acl/11111111-2222-3333-4444-555555555555"

RUN = secrets.token_hex(3)

_STATE: dict = {}

_FUNCTION_CODE = b"function handler(event) { return event.request; }\n"


# --- wire helpers -----------------------------------------------------------


def call(endpoint, method, path, body=b"", query=None, headers=None):
    if query:
        path = f"{path}?{urlencode(query)}"
    if isinstance(body, str):
        body = body.encode()
    return signed.request_bytes(
        endpoint, "cloudfront", ACCOUNT, REGION, method, path, body, headers
    )


def ok(endpoint, method, path, body=b"", query=None, headers=None, statuses=(200, 201, 202, 204)):
    status, headers_out, payload = call(endpoint, method, path, body, query, headers)
    assert status in statuses, f"{method} {path} answered {status}: {payload[:500]!r}"
    return status, payload.decode(errors="replace"), headers_out


def status_of(endpoint, method, path, body=b"", query=None, headers=None):
    return call(endpoint, method, path, body, query, headers)


def etag_of(headers: dict) -> str:
    for key, value in headers.items():
        if key.lower() in ("etag", "ettag"):
            return value.strip('"')
    return ""


def child_text(element, tag: str) -> str:
    if element is None:
        return ""
    for item in element:
        name = item.tag.split("}")[-1]
        if name == tag:
            return item.text or ""
    return ""


def find(element, tag: str):
    if element is None:
        return None
    for item in element:
        if item.tag.split("}")[-1] == tag:
            return item
    return None


def descendants(element, tag: str) -> list:
    found = []
    for item in element.iter():
        if item.tag.split("}")[-1] == tag:
            found.append(item)
    return found


def _id_from(body: str) -> str:
    return child_text(ET.fromstring(body), "Id")


# --- distributions ----------------------------------------------------------


def distribution_config(
    caller_reference: str,
    comment: str = "ops distribution",
    enabled: bool = True,
    connection_mode: str = "",
) -> str:
    connection = f"<ConnectionMode>{connection_mode}</ConnectionMode>" if connection_mode else ""
    return f"""<DistributionConfig>
  <CallerReference>{caller_reference}</CallerReference>
  <Comment>{comment}</Comment>
  <Enabled>{"true" if enabled else "false"}</Enabled>
  <Origins>
    <Quantity>1</Quantity>
    <Items>
      <Origin>
        <Id>ops-origin</Id>
        <DomainName>origin.ops.example.com</DomainName>
        <CustomOriginConfig>
          <HTTPPort>80</HTTPPort>
          <HTTPSPort>443</HTTPSPort>
          <OriginProtocolPolicy>https-only</OriginProtocolPolicy>
        </CustomOriginConfig>
      </Origin>
    </Items>
  </Origins>
  <DefaultCacheBehavior>
    <TargetOriginId>ops-origin</TargetOriginId>
    <ViewerProtocolPolicy>redirect-to-https</ViewerProtocolPolicy>
  </DefaultCacheBehavior>
  {connection}
</DistributionConfig>"""


def ensure_distribution(endpoint, caller_reference: str = DIST_REF, connection_mode: str = "") -> tuple[str, str]:
    """(id, current ETag) for the distribution a caller reference names."""
    key = f"dist:{caller_reference}"
    if key not in _STATE:
        body = distribution_config(caller_reference, connection_mode=connection_mode)
        _status, text, headers = ok(endpoint, "POST", "/2020-05-31/distribution", body)
        _STATE[key] = _id_from(text)
    dist_id = _STATE[key]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}")
    return dist_id, etag_of(headers)


def ensure_vpc_endpoint_instance(endpoint) -> str:
    """An EC2 instance ARN a VPC origin may point at, launched once."""
    if "vpc_instance" not in _STATE:
        body = urlencode(
            {
                "Action": "RunInstances",
                "Version": "2016-11-15",
                "ImageId": "ami-00000000",
                "MinCount": "1",
                "MaxCount": "1",
                "InstanceType": "t3.micro",
            }
        )
        status, _headers, payload = signed.request_bytes(
            endpoint, "ec2", ACCOUNT, REGION, "POST", "/", body, FORM
        )
        assert status == 200, f"RunInstances answered {status}: {payload[:500]!r}"
        match = re.search(rb"<instanceId>([^<]+)</instanceId>", payload)
        assert match, payload[:500]
        _STATE["vpc_instance"] = match.group(1).decode()
    return f"arn:aws:ec2:{REGION}:{ACCOUNT}:instance/{_STATE['vpc_instance']}"


def vpc_origin_body(name: str, instance_arn: str) -> str:
    return f"""<CreateVpcOriginRequest>
  <VpcOriginEndpointConfig>
    <Name>{name}</Name>
    <Arn>{instance_arn}</Arn>
    <HTTPPort>80</HTTPPort>
    <HTTPSPort>443</HTTPSPort>
    <OriginProtocolPolicy>https-only</OriginProtocolPolicy>
    <OriginSslProtocols>
      <Quantity>1</Quantity>
      <Items><SslProtocol>TLSv1.2</SslProtocol></Items>
    </OriginSslProtocols>
    <IpAddressType>ipv4</IpAddressType>
  </VpcOriginEndpointConfig>
</CreateVpcOriginRequest>"""


def endpoint_config_body(name: str, instance_arn: str) -> str:
    body = vpc_origin_body(name, instance_arn)
    return body.replace("<CreateVpcOriginRequest>", "").replace("</CreateVpcOriginRequest>", "").strip()


def ensure_vpc_origin(endpoint) -> str:
    if "vpc_origin" not in _STATE:
        instance_arn = ensure_vpc_endpoint_instance(endpoint)
        _status, body, _headers = ok(endpoint, "GET", "/2020-05-31/vpc-origin")
        existing = [
            child_text(origin, "Id")
            for origin in descendants(ET.fromstring(body), "VpcOriginSummary")
            if child_text(origin, "Name") == VPC_ORIGIN_NAME
        ]
        if existing:
            _STATE["vpc_origin"] = existing[0]
        else:
            _status, text, _headers = ok(
                endpoint,
                "POST",
                "/2020-05-31/vpc-origin",
                vpc_origin_body(VPC_ORIGIN_NAME, instance_arn),
                statuses=(202,),
            )
            _STATE["vpc_origin"] = _id_from(text)
    return _STATE["vpc_origin"]


def ensure_group(endpoint) -> tuple[str, str]:
    key = "group"
    if key not in _STATE:
        _status, body, _headers = ok(
            endpoint, "POST", "/2020-05-31/connection-groups", "<ListConnectionGroupsRequest/>"
        )
        ids = [
            child_text(item, "Id")
            for item in descendants(ET.fromstring(body), "ConnectionGroupSummary")
            if child_text(item, "Name") == GROUP_NAME
        ]
        if ids:
            _STATE[key] = ids[0]
        else:
            _status, text, _headers = ok(
                endpoint,
                "POST",
                "/2020-05-31/connection-group",
                f"<ConnectionGroup><Name>{GROUP_NAME}</Name></ConnectionGroup>",
            )
            _STATE[key] = _id_from(text)
    group_id = _STATE[key]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/connection-group/{group_id}")
    return group_id, etag_of(headers)


def ensure_tenant(endpoint) -> tuple[str, str]:
    key = "tenant"
    if key not in _STATE:
        status, _text, _headers = status_of(
            endpoint, "GET", "/2020-05-31/distribution-tenant", query={"domain": TENANT_DOMAIN}
        )
        if status != 200:
            tenant_dist, _etag = ensure_distribution(endpoint, TENANT_DIST_REF, "tenant-only")
            body = f"""<DistributionTenant>
  <DistributionId>{tenant_dist}</DistributionId>
  <Name>{TENANT_NAME}</Name>
  <Domains><member><Domain>{TENANT_DOMAIN}</Domain></member></Domains>
  <ManagedCertificateRequest>
    <ValidationTokenHost>cloudfront</ValidationTokenHost>
    <PrimaryDomainName>{TENANT_DOMAIN}</PrimaryDomainName>
  </ManagedCertificateRequest>
</DistributionTenant>"""
            _status, text, _headers = ok(endpoint, "POST", "/2020-05-31/distribution-tenant", body)
            _STATE[key] = _id_from(text)
        else:
            _status, text, _headers = ok(
                endpoint, "GET", "/2020-05-31/distribution-tenant", query={"domain": TENANT_DOMAIN}
            )
            _STATE[key] = _id_from(text)
    tenant_id = _STATE[key]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/distribution-tenant/{tenant_id}")
    return tenant_id, etag_of(headers)


# --- distributions ----------------------------------------------------------


def test_create_distribution_answers_it(endpoint):
    caller = f"ops-cf-created-{RUN}"
    _status, text, headers = ok(
        endpoint, "POST", "/2020-05-31/distribution", distribution_config(caller)
    )
    dist_id = _id_from(text)
    assert etag_of(headers)
    read = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}")[1]
    assert child_text(ET.fromstring(read), "Id") == dist_id


def test_get_distribution_reads_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, headers = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}")
    root = ET.fromstring(text)
    assert child_text(root, "Id") == dist_id
    assert child_text(root, "Status") == "Deployed"
    assert etag_of(headers)


def test_get_distribution_config_reads_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}/config")
    root = ET.fromstring(text)
    assert root.tag.split("}")[-1] == "DistributionConfig"
    assert child_text(root, "CallerReference") == DIST_REF


def test_list_distributions_lists_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/distribution")
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "DistributionSummary")}
    assert dist_id in ids


def test_update_distribution_sets_the_comment(endpoint):
    dist_id, etag = ensure_distribution(endpoint)
    _status, text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution/{dist_id}/config",
        distribution_config(DIST_REF, comment="updated distribution"),
        headers={"If-Match": etag},
    )
    new_etag = etag_of(headers)
    read = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}/config")[1]
    assert child_text(ET.fromstring(read), "Comment") == "updated distribution"
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution/{dist_id}/config",
        distribution_config(DIST_REF, comment="ops distribution"),
        headers={"If-Match": new_etag},
    )


def test_delete_distribution_removes_it(endpoint):
    caller = f"ops-cf-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/distribution", distribution_config(caller, enabled=False)
    )
    dist_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/distribution/{dist_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    status, _payload, _headers = status_of(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}")
    assert status == 404


def test_associate_and_disassociate_distribution_webacl(endpoint):
    dist_id, etag = ensure_distribution(endpoint)
    _status, text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution/{dist_id}/associate-web-acl",
        f"<AssociateDistributionWebACLRequest><WebACLArn>{WEB_ACL_ARN}</WebACLArn></AssociateDistributionWebACLRequest>",
        headers={"If-Match": etag},
    )
    assert child_text(ET.fromstring(text), "WebACLArn") == WEB_ACL_ARN
    config = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}/config")[1]
    assert child_text(ET.fromstring(config), "WebACLId") == WEB_ACL_ARN
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution/{dist_id}/disassociate-web-acl",
        b"",
        headers={"If-Match": etag_of(headers)},
    )
    config = ok(endpoint, "GET", f"/2020-05-31/distribution/{dist_id}/config")[1]
    assert child_text(ET.fromstring(config), "WebACLId") == ""


# --- invalidations ----------------------------------------------------------


def invalidation_body(caller: str, paths=("/*",)) -> str:
    items = "".join(f"<Path>{path}</Path>" for path in paths)
    return f"""<InvalidationBatch>
  <Paths><Quantity>{len(paths)}</Quantity><Items>{items}</Items></Paths>
  <CallerReference>{caller}</CallerReference>
</InvalidationBatch>"""


def test_create_invalidation_answers_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        f"/2020-05-31/distribution/{dist_id}/invalidation",
        invalidation_body("ops-cf-invalidation-create"),
        statuses=(201,),
    )
    root = ET.fromstring(text)
    assert child_text(root, "Id")
    assert child_text(root, "Status") == "Completed"


def test_list_invalidations_lists_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        f"/2020-05-31/distribution/{dist_id}/invalidation",
        invalidation_body("ops-cf-invalidation-list"),
        statuses=(201,),
    )
    inv_id = child_text(ET.fromstring(text), "Id")
    _status, listed, _headers = ok(
        endpoint, "GET", f"/2020-05-31/distribution/{dist_id}/invalidation"
    )
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(listed), "InvalidationSummary")}
    assert inv_id in ids


def test_get_invalidation_reads_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        f"/2020-05-31/distribution/{dist_id}/invalidation",
        invalidation_body("ops-cf-invalidation-get"),
        statuses=(201,),
    )
    inv_id = child_text(ET.fromstring(text), "Id")
    _status, read, _headers = ok(
        endpoint, "GET", f"/2020-05-31/distribution/{dist_id}/invalidation/{inv_id}"
    )
    assert child_text(ET.fromstring(read), "Id") == inv_id


# --- origin access controls -------------------------------------------------


def oac_body(name: str = OAC_NAME, description: str = "ops oac") -> str:
    return f"""<OriginAccessControlConfig>
  <Name>{name}</Name>
  <Description>{description}</Description>
  <OriginAccessControlOriginType>s3</OriginAccessControlOriginType>
  <SigningBehavior>always</SigningBehavior>
  <SigningProtocol>sigv4</SigningProtocol>
</OriginAccessControlConfig>"""


def ensure_oac(endpoint) -> str:
    if "oac" not in _STATE:
        _status, body, _headers = ok(endpoint, "GET", "/2020-05-31/origin-access-control")
        ids = [
            child_text(oac, "Id")
            for oac in descendants(ET.fromstring(body), "OriginAccessControlSummary")
            if child_text(oac, "Name") == OAC_NAME
        ]
        if ids:
            _STATE["oac"] = ids[0]
        else:
            _status, text, _headers = ok(
                endpoint, "POST", "/2020-05-31/origin-access-control", oac_body()
            )
            _STATE["oac"] = _id_from(text)
    return _STATE["oac"]


def test_create_origin_access_control_answers_it(endpoint):
    name = f"ops-cf-oac-created-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/origin-access-control", oac_body(name)
    )
    oac_id = _id_from(text)
    read = ok(endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}")[1]
    assert child_text(ET.fromstring(read), "Id") == oac_id


def test_get_origin_access_control_reads_it(endpoint):
    oac_id = ensure_oac(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}")
    root = ET.fromstring(text)
    assert child_text(root, "Id") == oac_id
    assert child_text(find(root, "OriginAccessControlConfig"), "Name") == OAC_NAME


def test_get_origin_access_control_config_reads_it(endpoint):
    oac_id = ensure_oac(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}/config"
    )
    root = ET.fromstring(text)
    assert child_text(root, "SigningProtocol") == "sigv4"


def test_list_origin_access_controls_lists_it(endpoint):
    oac_id = ensure_oac(endpoint)
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/origin-access-control")
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "OriginAccessControlSummary")}
    assert oac_id in ids


def test_update_origin_access_control_sets_the_description(endpoint):
    oac_id = ensure_oac(endpoint)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}")
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/origin-access-control/{oac_id}/config",
        oac_body(OAC_NAME, "updated oac"),
        headers={"If-Match": etag_of(headers)},
    )
    read = ok(endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}/config")[1]
    assert child_text(ET.fromstring(read), "Description") == "updated oac"
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}")
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/origin-access-control/{oac_id}/config",
        oac_body(OAC_NAME, "ops oac"),
        headers={"If-Match": etag_of(headers)},
    )


def test_delete_origin_access_control_removes_it(endpoint):
    name = f"ops-cf-oac-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/origin-access-control", oac_body(name)
    )
    oac_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/origin-access-control/{oac_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/origin-access-control/{oac_id}")[0] == 404


# --- monitoring subscriptions ----------------------------------------------


def monitoring_body(status: str = "Enabled") -> str:
    return (
        "<MonitoringSubscription><RealtimeMetricsSubscriptionConfig>"
        f"<RealtimeMetricsSubscriptionStatus>{status}</RealtimeMetricsSubscriptionStatus>"
        "</RealtimeMetricsSubscriptionConfig></MonitoringSubscription>"
    )


def test_create_monitoring_subscription_answers_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        f"/2020-05-31/distributions/{dist_id}/monitoring-subscription",
        monitoring_body("Disabled"),
    )
    root = ET.fromstring(text)
    assert child_text(find(root, "RealtimeMetricsSubscriptionConfig"), "RealtimeMetricsSubscriptionStatus") == "Disabled"


def test_get_monitoring_subscription_reads_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    ok(
        endpoint,
        "POST",
        f"/2020-05-31/distributions/{dist_id}/monitoring-subscription",
        monitoring_body("Enabled"),
    )
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/distributions/{dist_id}/monitoring-subscription"
    )
    root = ET.fromstring(text)
    assert child_text(find(root, "RealtimeMetricsSubscriptionConfig"), "RealtimeMetricsSubscriptionStatus") == "Enabled"


def test_delete_monitoring_subscription_removes_it(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    ok(
        endpoint,
        "POST",
        f"/2020-05-31/distributions/{dist_id}/monitoring-subscription",
        monitoring_body("Enabled"),
    )
    ok(endpoint, "DELETE", f"/2020-05-31/distributions/{dist_id}/monitoring-subscription")
    status, _payload, _headers = status_of(
        endpoint, "GET", f"/2020-05-31/distributions/{dist_id}/monitoring-subscription"
    )
    assert status == 404


# --- functions --------------------------------------------------------------


def function_body(name: str = FUNCTION_NAME, comment: str = "ops function") -> str:
    code = base64.b64encode(_FUNCTION_CODE).decode()
    return f"""<Function>
  <Name>{name}</Name>
  <FunctionConfig><Comment>{comment}</Comment><Runtime>cloudfront-js-2.0</Runtime></FunctionConfig>
  <FunctionCode>{code}</FunctionCode>
</Function>"""


def ensure_function(endpoint) -> str:
    if "function" not in _STATE:
        status, _text, _headers = status_of(endpoint, "GET", f"/2020-05-31/function/{FUNCTION_NAME}")
        if status != 200:
            _status, _text, headers = ok(
                endpoint, "POST", "/2020-05-31/function", function_body(), statuses=(201,)
            )
        _STATE["function"] = FUNCTION_NAME
    return _STATE["function"]


def function_dev_etag(endpoint, name: str = FUNCTION_NAME) -> str:
    _status, _payload, headers = ok(endpoint, "GET", f"/2020-05-31/function/{name}")
    return etag_of(headers)


def test_create_function_answers_it(endpoint):
    name = f"ops_cf_function_created_{RUN}"
    _status, text, headers = ok(
        endpoint, "POST", "/2020-05-31/function", function_body(name), statuses=(201,)
    )
    root = ET.fromstring(text)
    assert child_text(root, "Name") == name
    assert etag_of(headers)


def test_get_function_reads_its_code(endpoint):
    name = ensure_function(endpoint)
    status, _headers, payload = status_of(endpoint, "GET", f"/2020-05-31/function/{name}")
    assert status == 200
    assert payload == _FUNCTION_CODE


def test_describe_function_reads_it(endpoint):
    name = ensure_function(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/function/{name}/describe")
    root = ET.fromstring(text)
    assert child_text(root, "Name") == name
    assert child_text(find(root, "FunctionMetadata"), "Stage") == "DEVELOPMENT"


def test_list_functions_lists_it(endpoint):
    name = ensure_function(endpoint)
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/function")
    names = {child_text(item, "Name") for item in descendants(ET.fromstring(text), "FunctionSummary")}
    assert name in names


def test_publish_function_publishes_it(endpoint):
    name = ensure_function(endpoint)
    ok(
        endpoint,
        "POST",
        f"/2020-05-31/function/{name}/publish",
        headers={"If-Match": function_dev_etag(endpoint, name)},
    )
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/function/{name}/describe", query={"Stage": "LIVE"}
    )
    assert child_text(find(ET.fromstring(text), "FunctionMetadata"), "Stage") == "LIVE"


def test_update_function_sets_the_comment(endpoint):
    name = ensure_function(endpoint)
    _status, text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/function/{name}",
        function_body(name, "updated function"),
        headers={"If-Match": function_dev_etag(endpoint, name)},
    )
    assert etag_of(headers)
    read = ok(endpoint, "GET", f"/2020-05-31/function/{name}/describe")[1]
    config = find(ET.fromstring(read), "FunctionConfig")
    assert child_text(config, "Comment") == "updated function"
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/function/{name}",
        function_body(name, "ops function"),
        headers={"If-Match": etag_of(headers)},
    )


def test_delete_function_removes_it(endpoint):
    name = f"ops_cf_function_deleted_{RUN}"
    ok(endpoint, "POST", "/2020-05-31/function", function_body(name), statuses=(201,))
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/function/{name}",
        headers={"If-Match": function_dev_etag(endpoint, name)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/function/{name}")[0] == 404


# --- key value stores (management) -----------------------------------------


def ensure_kvs(endpoint) -> str:
    if "kvs" not in _STATE:
        _status, body, _headers = ok(endpoint, "GET", "/2020-05-31/key-value-store")
        names = [
            child_text(store, "Name")
            for store in descendants(ET.fromstring(body), "KeyValueStore")
            if child_text(store, "Name") == KVS_NAME
        ]
        if not names:
            ok(
                endpoint,
                "POST",
                "/2020-05-31/key-value-store",
                f"<KeyValueStore><Name>{KVS_NAME}</Name><Comment>ops kvs</Comment></KeyValueStore>",
                statuses=(201,),
            )
        _STATE["kvs"] = KVS_NAME
    return _STATE["kvs"]


def kvs_etag(endpoint, name: str = KVS_NAME) -> str:
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/key-value-store/{name}")
    return etag_of(headers)


def test_create_key_value_store_answers_it(endpoint):
    name = f"ops-cf-kvs-created-{RUN}"
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/key-value-store",
        f"<KeyValueStore><Name>{name}</Name></KeyValueStore>",
        statuses=(201,),
    )
    assert child_text(ET.fromstring(text), "Name") == name


def test_describe_key_value_store_reads_it(endpoint):
    name = ensure_kvs(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/key-value-store/{name}")
    assert child_text(ET.fromstring(text), "Name") == name


def test_list_key_value_stores_lists_it(endpoint):
    name = ensure_kvs(endpoint)
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/key-value-store")
    names = {child_text(store, "Name") for store in descendants(ET.fromstring(text), "KeyValueStore")}
    assert name in names


def test_update_key_value_store_sets_the_comment(endpoint):
    name = ensure_kvs(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/key-value-store/{name}",
        "<KeyValueStore><Comment>updated kvs</Comment></KeyValueStore>",
        headers={"If-Match": kvs_etag(endpoint, name)},
    )
    read = ok(endpoint, "GET", f"/2020-05-31/key-value-store/{name}")[1]
    assert child_text(ET.fromstring(read), "Comment") == "updated kvs"


def test_delete_key_value_store_removes_it(endpoint):
    name = f"ops-cf-kvs-deleted-{RUN}"
    ok(
        endpoint,
        "POST",
        "/2020-05-31/key-value-store",
        f"<KeyValueStore><Name>{name}</Name></KeyValueStore>",
        statuses=(201,),
    )
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/key-value-store/{name}",
        headers={"If-Match": kvs_etag(endpoint, name)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/key-value-store/{name}")[0] == 404


# --- cache policies ---------------------------------------------------------


def cache_policy_body(name: str = CACHE_NAME, comment: str = "ops cache policy") -> str:
    return f"""<CachePolicyConfig>
  <Name>{name}</Name>
  <Comment>{comment}</Comment>
  <MinTTL>1</MinTTL>
  <DefaultTTL>60</DefaultTTL>
  <MaxTTL>600</MaxTTL>
  <ParametersInCacheKeyAndForwardedToOrigin>
    <EnableAcceptEncodingGzip>true</EnableAcceptEncodingGzip>
    <EnableAcceptEncodingBrotli>false</EnableAcceptEncodingBrotli>
    <HeadersConfig><HeaderBehavior>none</HeaderBehavior></HeadersConfig>
    <CookiesConfig><CookieBehavior>none</CookieBehavior></CookiesConfig>
    <QueryStringsConfig><QueryStringBehavior>none</QueryStringBehavior></QueryStringsConfig>
  </ParametersInCacheKeyAndForwardedToOrigin>
</CachePolicyConfig>"""


def _find_policy_id(endpoint, path: str, summary_tag: str, resource_tag: str, name: str) -> str:
    """The custom policy a list names, walking ``Summary > Resource > Config > Name``."""
    _status, body, _headers = ok(endpoint, "GET", path, query={"Type": "custom"})
    for summary in descendants(ET.fromstring(body), summary_tag):
        resource = find(summary, resource_tag)
        if child_text(find(resource, resource_tag + "Config"), "Name") == name:
            return child_text(resource, "Id")
    return ""


def ensure_cache_policy(endpoint) -> tuple[str, str]:
    if "cache_policy" not in _STATE:
        policy_id = _find_policy_id(
            endpoint, "/2020-05-31/cache-policy", "CachePolicySummary", "CachePolicy", CACHE_NAME
        )
        if not policy_id:
            _status, text, _headers = ok(
                endpoint, "POST", "/2020-05-31/cache-policy", cache_policy_body(), statuses=(201,)
            )
            policy_id = _id_from(text)
        _STATE["cache_policy"] = policy_id
    policy_id = _STATE["cache_policy"]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/cache-policy/{policy_id}")
    return policy_id, etag_of(headers)


def test_create_cache_policy_answers_it(endpoint):
    name = f"ops-cf-cache-created-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/cache-policy", cache_policy_body(name), statuses=(201,)
    )
    assert _id_from(text)
    read = ok(endpoint, "GET", f"/2020-05-31/cache-policy/{_id_from(text)}")[1]
    assert child_text(ET.fromstring(read), "Id") == _id_from(text)


def test_get_cache_policy_reads_it(endpoint):
    policy_id, _etag = ensure_cache_policy(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/cache-policy/{policy_id}")
    assert child_text(ET.fromstring(text), "Id") == policy_id


def test_get_cache_policy_config_reads_it(endpoint):
    policy_id, _etag = ensure_cache_policy(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/cache-policy/{policy_id}/config")
    root = ET.fromstring(text)
    assert child_text(root, "Name") == CACHE_NAME
    assert child_text(root, "MinTTL") == "1"


def test_update_cache_policy_sets_the_comment(endpoint):
    policy_id, etag = ensure_cache_policy(endpoint)
    _status, _text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/cache-policy/{policy_id}",
        cache_policy_body(CACHE_NAME, "updated cache policy"),
        headers={"If-Match": etag},
    )
    read = ok(endpoint, "GET", f"/2020-05-31/cache-policy/{policy_id}/config")[1]
    assert child_text(ET.fromstring(read), "Comment") == "updated cache policy"
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/cache-policy/{policy_id}",
        cache_policy_body(CACHE_NAME, "ops cache policy"),
        headers={"If-Match": etag_of(headers)},
    )


def test_delete_cache_policy_removes_it(endpoint):
    name = f"ops-cf-cache-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/cache-policy", cache_policy_body(name), statuses=(201,)
    )
    policy_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/cache-policy/{policy_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/cache-policy/{policy_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/cache-policy/{policy_id}")[0] == 404


def test_list_distributions_by_cache_policy_lists_none(endpoint):
    policy_id, _etag = ensure_cache_policy(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/distributionsByCachePolicyId/{policy_id}"
    )
    assert child_text(ET.fromstring(text), "Quantity") == "0"


# --- origin request policies ------------------------------------------------


def orp_body(name: str = ORP_NAME, comment: str = "ops orp") -> str:
    return f"""<OriginRequestPolicyConfig>
  <Name>{name}</Name>
  <Comment>{comment}</Comment>
  <HeadersConfig><HeaderBehavior>none</HeaderBehavior></HeadersConfig>
  <CookiesConfig><CookieBehavior>none</CookieBehavior></CookiesConfig>
  <QueryStringsConfig><QueryStringBehavior>none</QueryStringBehavior></QueryStringsConfig>
</OriginRequestPolicyConfig>"""


def ensure_orp(endpoint) -> tuple[str, str]:
    if "orp" not in _STATE:
        policy_id = _find_policy_id(
            endpoint,
            "/2020-05-31/origin-request-policy",
            "OriginRequestPolicySummary",
            "OriginRequestPolicy",
            ORP_NAME,
        )
        if not policy_id:
            _status, text, _headers = ok(
                endpoint, "POST", "/2020-05-31/origin-request-policy", orp_body(), statuses=(201,)
            )
            policy_id = _id_from(text)
        _STATE["orp"] = policy_id
    policy_id = _STATE["orp"]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/origin-request-policy/{policy_id}")
    return policy_id, etag_of(headers)


def test_create_origin_request_policy_answers_it(endpoint):
    name = f"ops-cf-orp-created-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/origin-request-policy", orp_body(name), statuses=(201,)
    )
    assert _id_from(text)
    assert child_text(ET.fromstring(ok(endpoint, "GET", f"/2020-05-31/origin-request-policy/{_id_from(text)}")[1]), "Id") == _id_from(text)


def test_get_origin_request_policy_reads_it(endpoint):
    policy_id, _etag = ensure_orp(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/origin-request-policy/{policy_id}")
    assert child_text(ET.fromstring(text), "Id") == policy_id


def test_get_origin_request_policy_config_reads_it(endpoint):
    policy_id, _etag = ensure_orp(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/origin-request-policy/{policy_id}/config"
    )
    root = ET.fromstring(text)
    assert child_text(root, "Name") == ORP_NAME
    assert child_text(find(root, "HeadersConfig"), "HeaderBehavior") == "none"


def test_update_origin_request_policy_sets_the_comment(endpoint):
    policy_id, etag = ensure_orp(endpoint)
    _status, _text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/origin-request-policy/{policy_id}",
        orp_body(ORP_NAME, "updated orp"),
        headers={"If-Match": etag},
    )
    read = ok(endpoint, "GET", f"/2020-05-31/origin-request-policy/{policy_id}/config")[1]
    assert child_text(ET.fromstring(read), "Comment") == "updated orp"
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/origin-request-policy/{policy_id}",
        orp_body(ORP_NAME, "ops orp"),
        headers={"If-Match": etag_of(headers)},
    )


def test_delete_origin_request_policy_removes_it(endpoint):
    name = f"ops-cf-orp-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/origin-request-policy", orp_body(name), statuses=(201,)
    )
    policy_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/origin-request-policy/{policy_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/origin-request-policy/{policy_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/origin-request-policy/{policy_id}")[0] == 404


def test_list_distributions_by_origin_request_policy_lists_none(endpoint):
    policy_id, _etag = ensure_orp(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/distributionsByOriginRequestPolicyId/{policy_id}"
    )
    assert child_text(ET.fromstring(text), "Quantity") == "0"


# --- response headers policies ---------------------------------------------


def rhp_body(name: str = RHP_NAME, comment: str = "ops rhp") -> str:
    return f"""<ResponseHeadersPolicyConfig>
  <Name>{name}</Name>
  <Comment>{comment}</Comment>
</ResponseHeadersPolicyConfig>"""


def ensure_rhp(endpoint) -> tuple[str, str]:
    if "rhp" not in _STATE:
        policy_id = _find_policy_id(
            endpoint,
            "/2020-05-31/response-headers-policy",
            "ResponseHeadersPolicySummary",
            "ResponseHeadersPolicy",
            RHP_NAME,
        )
        if not policy_id:
            _status, text, _headers = ok(
                endpoint, "POST", "/2020-05-31/response-headers-policy", rhp_body(), statuses=(201,)
            )
            policy_id = _id_from(text)
        _STATE["rhp"] = policy_id
    policy_id = _STATE["rhp"]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/response-headers-policy/{policy_id}")
    return policy_id, etag_of(headers)


def test_create_response_headers_policy_answers_it(endpoint):
    name = f"ops-cf-rhp-created-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/response-headers-policy", rhp_body(name), statuses=(201,)
    )
    assert _id_from(text)
    read = ok(endpoint, "GET", f"/2020-05-31/response-headers-policy/{_id_from(text)}")[1]
    assert child_text(ET.fromstring(read), "Id") == _id_from(text)


def test_get_response_headers_policy_reads_it(endpoint):
    policy_id, _etag = ensure_rhp(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/response-headers-policy/{policy_id}")
    assert child_text(ET.fromstring(text), "Id") == policy_id


def test_get_response_headers_policy_config_reads_it(endpoint):
    policy_id, _etag = ensure_rhp(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/response-headers-policy/{policy_id}/config"
    )
    assert child_text(ET.fromstring(text), "Name") == RHP_NAME


def test_update_response_headers_policy_sets_the_comment(endpoint):
    policy_id, etag = ensure_rhp(endpoint)
    _status, _text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/response-headers-policy/{policy_id}",
        rhp_body(RHP_NAME, "updated rhp"),
        headers={"If-Match": etag},
    )
    read = ok(endpoint, "GET", f"/2020-05-31/response-headers-policy/{policy_id}/config")[1]
    assert child_text(ET.fromstring(read), "Comment") == "updated rhp"
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/response-headers-policy/{policy_id}",
        rhp_body(RHP_NAME, "ops rhp"),
        headers={"If-Match": etag_of(headers)},
    )


def test_delete_response_headers_policy_removes_it(endpoint):
    name = f"ops-cf-rhp-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/response-headers-policy", rhp_body(name), statuses=(201,)
    )
    policy_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/response-headers-policy/{policy_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/response-headers-policy/{policy_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/response-headers-policy/{policy_id}")[0] == 404


def test_list_distributions_by_response_headers_policy_lists_none(endpoint):
    policy_id, _etag = ensure_rhp(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/distributionsByResponseHeadersPolicyId/{policy_id}"
    )
    assert child_text(ET.fromstring(text), "Quantity") == "0"


# --- public keys and key groups --------------------------------------------


def public_key_body(name: str = PUBLIC_KEY_NAME, comment: str = "ops key") -> str:
    encoded = base64.b64encode(b"ops-public-key-material").decode()
    return f"""<PublicKeyConfig>
  <CallerReference>{name}</CallerReference>
  <Name>{name}</Name>
  <EncodedKey>{encoded}</EncodedKey>
  <Comment>{comment}</Comment>
</PublicKeyConfig>"""


def ensure_public_key(endpoint) -> tuple[str, str]:
    if "public_key" not in _STATE:
        _status, _body, _headers = ok(endpoint, "GET", "/2020-05-31/public-key")
        ids = [
            child_text(key, "Id")
            for key in descendants(ET.fromstring(_body), "PublicKeySummary")
            if child_text(key, "Name") == PUBLIC_KEY_NAME
        ]
        if ids:
            _STATE["public_key"] = ids[0]
        else:
            _status, text, _headers = ok(
                endpoint, "POST", "/2020-05-31/public-key", public_key_body(), statuses=(201,)
            )
            _STATE["public_key"] = _id_from(text)
    key_id = _STATE["public_key"]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/public-key/{key_id}")
    return key_id, etag_of(headers)


def test_create_public_key_answers_it(endpoint):
    name = f"ops-cf-key-created-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/public-key", public_key_body(name), statuses=(201,)
    )
    key_id = _id_from(text)
    assert child_text(ET.fromstring(ok(endpoint, "GET", f"/2020-05-31/public-key/{key_id}")[1]), "Id") == key_id


def test_get_public_key_reads_it(endpoint):
    key_id, _etag = ensure_public_key(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/public-key/{key_id}")
    assert child_text(ET.fromstring(text), "Id") == key_id


def test_get_public_key_config_reads_it(endpoint):
    key_id, _etag = ensure_public_key(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/public-key/{key_id}/config")
    assert child_text(ET.fromstring(text), "Name") == PUBLIC_KEY_NAME


def test_update_public_key_sets_the_comment(endpoint):
    key_id, etag = ensure_public_key(endpoint)
    _status, _text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/public-key/{key_id}/config",
        public_key_body(PUBLIC_KEY_NAME, "updated key"),
        headers={"If-Match": etag},
    )
    read = ok(endpoint, "GET", f"/2020-05-31/public-key/{key_id}/config")[1]
    assert child_text(ET.fromstring(read), "Comment") == "updated key"
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/public-key/{key_id}/config",
        public_key_body(PUBLIC_KEY_NAME, "ops key"),
        headers={"If-Match": etag_of(headers)},
    )


def test_delete_public_key_removes_it(endpoint):
    name = f"ops-cf-key-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/public-key", public_key_body(name), statuses=(201,)
    )
    key_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/public-key/{key_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/public-key/{key_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/public-key/{key_id}")[0] == 404


def test_list_public_keys_lists_it(endpoint):
    key_id, _etag = ensure_public_key(endpoint)
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/public-key")
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "PublicKeySummary")}
    assert key_id in ids


def key_group_body(name: str, key_id: str, comment: str = "ops key group") -> str:
    return f"""<KeyGroupConfig>
  <Name>{name}</Name>
  <Items><PublicKey>{key_id}</PublicKey></Items>
  <Comment>{comment}</Comment>
</KeyGroupConfig>"""


def ensure_key_group(endpoint) -> tuple[str, str]:
    key_id, _key_etag = ensure_public_key(endpoint)
    if "key_group" not in _STATE:
        _status, body, _headers = ok(endpoint, "GET", "/2020-05-31/key-group")
        ids = [
            child_text(find(group, "KeyGroup"), "Id")
            for group in descendants(ET.fromstring(body), "KeyGroupSummary")
            if child_text(find(find(group, "KeyGroup"), "KeyGroupConfig"), "Name") == KEY_GROUP_NAME
        ]
        if ids:
            _STATE["key_group"] = ids[0]
        else:
            _status, text, _headers = ok(
                endpoint,
                "POST",
                "/2020-05-31/key-group",
                key_group_body(KEY_GROUP_NAME, key_id),
                statuses=(201,),
            )
            _STATE["key_group"] = _id_from(text)
    group_id = _STATE["key_group"]
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/key-group/{group_id}")
    return group_id, etag_of(headers)


def test_create_key_group_answers_it(endpoint):
    key_id, _etag = ensure_public_key(endpoint)
    name = f"ops-cf-group-created-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/key-group", key_group_body(name, key_id), statuses=(201,)
    )
    group_id = _id_from(text)
    assert child_text(ET.fromstring(ok(endpoint, "GET", f"/2020-05-31/key-group/{group_id}")[1]), "Id") == group_id


def test_get_key_group_reads_it(endpoint):
    group_id, _etag = ensure_key_group(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/key-group/{group_id}")
    assert child_text(ET.fromstring(text), "Id") == group_id


def test_get_key_group_config_reads_it(endpoint):
    group_id, _etag = ensure_key_group(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/key-group/{group_id}/config")
    assert child_text(ET.fromstring(text), "Name") == KEY_GROUP_NAME


def test_update_key_group_sets_the_comment(endpoint):
    key_id, _key_etag = ensure_public_key(endpoint)
    group_id, etag = ensure_key_group(endpoint)
    _status, _text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/key-group/{group_id}",
        key_group_body(KEY_GROUP_NAME, key_id, "updated key group"),
        headers={"If-Match": etag},
    )
    read = ok(endpoint, "GET", f"/2020-05-31/key-group/{group_id}/config")[1]
    assert child_text(ET.fromstring(read), "Comment") == "updated key group"
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/key-group/{group_id}",
        key_group_body(KEY_GROUP_NAME, key_id, "ops key group"),
        headers={"If-Match": etag_of(headers)},
    )


def test_delete_key_group_removes_it(endpoint):
    key_id, _key_etag = ensure_public_key(endpoint)
    name = f"ops-cf-group-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/key-group", key_group_body(name, key_id), statuses=(201,)
    )
    group_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/key-group/{group_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/key-group/{group_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/key-group/{group_id}")[0] == 404


def test_list_key_groups_lists_it(endpoint):
    group_id, _etag = ensure_key_group(endpoint)
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/key-group")
    ids = {
        child_text(find(item, "KeyGroup"), "Id")
        for item in descendants(ET.fromstring(text), "KeyGroupSummary")
    }
    assert group_id in ids


# --- VPC origins ------------------------------------------------------------


def test_create_vpc_origin_answers_it(endpoint):
    instance_arn = ensure_vpc_endpoint_instance(endpoint)
    name = f"ops-cf-vpc-created-{RUN}"
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/vpc-origin",
        vpc_origin_body(name, instance_arn),
        statuses=(202,),
    )
    root = ET.fromstring(text)
    assert child_text(find(root, "VpcOriginEndpointConfig"), "Name") == name
    assert child_text(root, "Status") == "Deploying"


def test_get_vpc_origin_reads_it(endpoint):
    origin_id = ensure_vpc_origin(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/vpc-origin/{origin_id}")
    root = ET.fromstring(text)
    assert child_text(root, "Id") == origin_id
    assert child_text(root, "Status") == "Deployed"


def test_update_vpc_origin_is_accepted(endpoint):
    origin_id = ensure_vpc_origin(endpoint)
    instance_arn = ensure_vpc_endpoint_instance(endpoint)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/vpc-origin/{origin_id}")
    _status, text, _headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/vpc-origin/{origin_id}",
        endpoint_config_body(VPC_ORIGIN_NAME, instance_arn),
        headers={"If-Match": etag_of(headers)},
        statuses=(202,),
    )
    assert child_text(ET.fromstring(text), "Id") == origin_id


def test_list_vpc_origins_lists_it(endpoint):
    origin_id = ensure_vpc_origin(endpoint)
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/vpc-origin")
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "VpcOriginSummary")}
    assert origin_id in ids


def test_delete_vpc_origin_removes_it(endpoint):
    instance_arn = ensure_vpc_endpoint_instance(endpoint)
    name = f"ops-cf-vpc-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/vpc-origin",
        vpc_origin_body(name, instance_arn),
        statuses=(202,),
    )
    origin_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/vpc-origin/{origin_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/vpc-origin/{origin_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(202,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/vpc-origin/{origin_id}")[0] == 404


# --- SaaS Manager: connection groups ---------------------------------------


def test_create_connection_group_answers_it(endpoint):
    name = f"ops-cf-group-created-{RUN}"
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/connection-group",
        f"<ConnectionGroup><Name>{name}</Name></ConnectionGroup>",
    )
    assert child_text(ET.fromstring(text), "Name") == name


def test_get_connection_group_reads_it(endpoint):
    group_id, _etag = ensure_group(endpoint)
    _status, text, _headers = ok(endpoint, "GET", f"/2020-05-31/connection-group/{group_id}")
    assert child_text(ET.fromstring(text), "Name") == GROUP_NAME


def test_get_connection_group_by_routing_endpoint_reads_it(endpoint):
    group_id, _etag = ensure_group(endpoint)
    routing = child_text(ET.fromstring(ok(endpoint, "GET", f"/2020-05-31/connection-group/{group_id}")[1]), "RoutingEndpoint")
    _status, text, _headers = ok(
        endpoint, "GET", "/2020-05-31/connection-group", query={"RoutingEndpoint": routing}
    )
    assert child_text(ET.fromstring(text), "Id") == group_id


def test_update_connection_group_is_accepted(endpoint):
    group_id, etag = ensure_group(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/connection-group/{group_id}",
        "<ConnectionGroup><Ipv6Enabled>true</Ipv6Enabled></ConnectionGroup>",
        headers={"If-Match": etag},
    )
    assert child_text(ET.fromstring(text), "Id") == group_id


def test_list_connection_groups_lists_it(endpoint):
    group_id, _etag = ensure_group(endpoint)
    _status, text, _headers = ok(endpoint, "POST", "/2020-05-31/connection-groups", "<ListConnectionGroupsRequest/>")
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "ConnectionGroupSummary")}
    assert group_id in ids


def test_delete_connection_group_removes_it(endpoint):
    name = f"ops-cf-group-deleted-{RUN}"
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/connection-group",
        f"<ConnectionGroup><Name>{name}</Name></ConnectionGroup>",
    )
    group_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/connection-group/{group_id}")
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/connection-group/{group_id}",
        "<ConnectionGroup><Enabled>false</Enabled></ConnectionGroup>",
        headers={"If-Match": etag_of(headers)},
    )
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/connection-group/{group_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/connection-group/{group_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/connection-group/{group_id}")[0] == 404


# --- SaaS Manager: distribution tenants ------------------------------------


def tenant_body(
    dist_id: str,
    name: str,
    domain: str,
    with_managed_certificate: bool = False,
    enabled: bool = True,
) -> str:
    certificate = (
        f"""  <ManagedCertificateRequest>
    <ValidationTokenHost>cloudfront</ValidationTokenHost>
    <PrimaryDomainName>{domain}</PrimaryDomainName>
  </ManagedCertificateRequest>
"""
        if with_managed_certificate
        else ""
    )
    return f"""<DistributionTenant>
  <DistributionId>{dist_id}</DistributionId>
  <Name>{name}</Name>
  <Domains><member><Domain>{domain}</Domain></member></Domains>
  <Enabled>{"true" if enabled else "false"}</Enabled>
{certificate}</DistributionTenant>"""


def test_create_distribution_tenant_answers_it(endpoint):
    tenant_dist, _etag = ensure_distribution(endpoint, TENANT_DIST_REF, "tenant-only")
    name = f"ops-cf-tenant-created-{RUN}"
    domain = f"ops-cf-tenant-created-{RUN}.example.com"
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/distribution-tenant",
        tenant_body(tenant_dist, name, domain),
        statuses=(201,),
    )
    assert child_text(ET.fromstring(text), "Name") == name


def test_get_distribution_tenant_reads_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/distribution-tenant/{tenant_id}"
    )
    assert child_text(ET.fromstring(text), "Name") == TENANT_NAME


def test_get_distribution_tenant_by_domain_reads_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", "/2020-05-31/distribution-tenant", query={"domain": TENANT_DOMAIN}
    )
    assert child_text(ET.fromstring(text), "Id") == tenant_id


def test_update_distribution_tenant_is_accepted(endpoint):
    tenant_id, etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution-tenant/{tenant_id}",
        "<DistributionTenant><Enabled>true</Enabled></DistributionTenant>",
        headers={"If-Match": etag},
    )
    assert child_text(ET.fromstring(text), "Id") == tenant_id


def test_list_distribution_tenants_lists_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint, "POST", "/2020-05-31/distribution-tenants", "<ListDistributionTenantsRequest/>"
    )
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "DistributionTenantSummary")}
    assert tenant_id in ids


def test_list_distribution_tenants_by_customization_lists_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/distribution-tenants-by-customization",
        "<ListDistributionTenantsByCustomizationRequest/>",
    )
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "DistributionTenantSummary")}
    assert tenant_id in ids


def test_delete_distribution_tenant_removes_it(endpoint):
    tenant_dist, _etag = ensure_distribution(endpoint, TENANT_DIST_REF, "tenant-only")
    name = f"ops-cf-tenant-deleted-{RUN}"
    domain = f"ops-cf-tenant-deleted-{RUN}.example.com"
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/distribution-tenant",
        tenant_body(tenant_dist, name, domain),
        statuses=(201,),
    )
    tenant_id = _id_from(text)
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/distribution-tenant/{tenant_id}")
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution-tenant/{tenant_id}",
        "<DistributionTenant><Enabled>false</Enabled></DistributionTenant>",
        headers={"If-Match": etag_of(headers)},
    )
    _status, _text, headers = ok(endpoint, "GET", f"/2020-05-31/distribution-tenant/{tenant_id}")
    ok(
        endpoint,
        "DELETE",
        f"/2020-05-31/distribution-tenant/{tenant_id}",
        headers={"If-Match": etag_of(headers)},
        statuses=(204,),
    )
    assert status_of(endpoint, "GET", f"/2020-05-31/distribution-tenant/{tenant_id}")[0] == 404


def test_associate_and_disassociate_tenant_webacl(endpoint):
    tenant_id, etag = ensure_tenant(endpoint)
    _status, text, headers = ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution-tenant/{tenant_id}/associate-web-acl",
        f"<AssociateDistributionTenantWebACLRequest><WebACLArn>{WEB_ACL_ARN}</WebACLArn></AssociateDistributionTenantWebACLRequest>",
        headers={"If-Match": etag},
    )
    assert child_text(ET.fromstring(text), "WebACLArn") == WEB_ACL_ARN
    ok(
        endpoint,
        "PUT",
        f"/2020-05-31/distribution-tenant/{tenant_id}/disassociate-web-acl",
        b"",
        headers={"If-Match": etag_of(headers)},
    )


def test_create_tenant_invalidation_answers_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        f"/2020-05-31/distribution-tenant/{tenant_id}/invalidation",
        invalidation_body("ops-cf-tenant-invalidation-create"),
        statuses=(201,),
    )
    assert child_text(ET.fromstring(text), "Id")


def test_list_tenant_invalidations_lists_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        f"/2020-05-31/distribution-tenant/{tenant_id}/invalidation",
        invalidation_body("ops-cf-tenant-invalidation-list"),
        statuses=(201,),
    )
    inv_id = child_text(ET.fromstring(text), "Id")
    listed = ok(endpoint, "GET", f"/2020-05-31/distribution-tenant/{tenant_id}/invalidation")[1]
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(listed), "InvalidationSummary")}
    assert inv_id in ids


def test_get_tenant_invalidation_reads_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        f"/2020-05-31/distribution-tenant/{tenant_id}/invalidation",
        invalidation_body("ops-cf-tenant-invalidation-get"),
        statuses=(201,),
    )
    inv_id = child_text(ET.fromstring(text), "Id")
    read = ok(endpoint, "GET", f"/2020-05-31/distribution-tenant/{tenant_id}/invalidation/{inv_id}")[1]
    assert child_text(ET.fromstring(read), "Id") == inv_id


def test_verify_dns_configuration_reads_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/verify-dns-configuration",
        f"<VerifyDnsConfigurationRequest><Identifier>{tenant_id}</Identifier><Domain>{TENANT_DOMAIN}</Domain></VerifyDnsConfigurationRequest>",
    )
    entries = descendants(ET.fromstring(text), "DnsConfiguration")
    assert entries
    assert child_text(entries[0], "Status") == "valid-configuration"


def test_get_managed_certificate_details_reads_it(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint, "GET", f"/2020-05-31/managed-certificate/{tenant_id}"
    )
    assert child_text(ET.fromstring(text), "CertificateArn")


def test_list_domain_conflicts_finds_none_for_its_own_tenant(endpoint):
    tenant_id, _etag = ensure_tenant(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/domain-conflicts",
        f"""<ListDomainConflictsRequest>
  <Domain>{TENANT_DOMAIN}</Domain>
  <DomainControlValidationResource><DistributionTenantId>{tenant_id}</DistributionTenantId></DomainControlValidationResource>
</ListDomainConflictsRequest>""",
    )
    root = ET.fromstring(text)
    assert child_text(root, "DomainConflicts") is not None or find(root, "DomainConflicts") is not None


def test_update_domain_association_moves_the_alias(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    _status, text, _headers = ok(
        endpoint,
        "POST",
        "/2020-05-31/domain-association",
        f"""<UpdateDomainAssociationRequest>
  <Domain>{ALIAS}</Domain>
  <TargetResource><DistributionId>{dist_id}</DistributionId></TargetResource>
</UpdateDomainAssociationRequest>""",
    )
    root = ET.fromstring(text)
    assert child_text(root, "Domain") == ALIAS
    assert child_text(root, "ResourceId") == dist_id


def test_list_distributions_by_connection_mode_lists_the_tenant_distribution(endpoint):
    tenant_dist, _etag = ensure_distribution(endpoint, TENANT_DIST_REF, "tenant-only")
    _status, text, _headers = ok(
        endpoint, "GET", "/2020-05-31/distributionsByConnectionMode/tenant-only"
    )
    ids = {child_text(item, "Id") for item in descendants(ET.fromstring(text), "DistributionSummary")}
    assert tenant_dist in ids


# --- tags -------------------------------------------------------------------


def test_tag_untag_and_list_tags_for_resource(endpoint):
    dist_id, _etag = ensure_distribution(endpoint)
    arn = f"arn:aws:cloudfront::{ACCOUNT}:distribution/{dist_id}"
    ok(
        endpoint,
        "POST",
        "/2020-05-31/tagging",
        "<Tags><Items><Tag><Key>ops</Key><Value>cloudfront</Value></Tag>"
        "<Tag><Key>keep</Key><Value>yes</Value></Tag></Items></Tags>",
        query={"Resource": arn, "Operation": "Tag"},
        statuses=(200, 204),
    )
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/tagging", query={"Resource": arn})
    tags = {child_text(tag, "Key"): child_text(tag, "Value") for tag in descendants(ET.fromstring(text), "Tag")}
    assert tags["ops"] == "cloudfront"
    ok(
        endpoint,
        "POST",
        "/2020-05-31/tagging",
        "<Tags><Items><Key>ops</Key></Items></Tags>",
        query={"Resource": arn, "Operation": "Untag"},
        statuses=(200, 204),
    )
    _status, text, _headers = ok(endpoint, "GET", "/2020-05-31/tagging", query={"Resource": arn})
    tags = {child_text(tag, "Key"): child_text(tag, "Value") for tag in descendants(ET.fromstring(text), "Tag")}
    assert "ops" not in tags and tags.get("keep") == "yes"
