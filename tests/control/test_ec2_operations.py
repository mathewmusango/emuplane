"""EC2 on the wire: every advertised operation, driven through the query protocol.

An instance launched here is left running — a launch is proven by describing it. The
terminate action launches an instance of its own, so it can remove what it created, and
every other delete test builds the resource it removes.

Creates that have no natural name are found-or-created behind a stable `Name` tag, so a
second sweep of the same lab reuses the VPC, subnet, gateway or interface instead of
duplicating it. Instances are the exception (an instance has no name to look up), which
is why each test launches its own.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from urllib.parse import urlencode

import pytest
import signed
from conftest import ACCOUNT, requires

REGION = "us-east-1"
VERSION = "2016-11-15"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
AMI = "ami-12345678"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "ec2", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def ids(text: str, tag: str) -> list[str]:
    return re.findall(rf"<{tag}>([^<]+)</{tag}>", text)


def first_id(text: str, tag: str) -> str:
    found = ids(text, tag)
    assert found, f"no <{tag}> in {text[:400]}"
    return found[0]


def state(text: str) -> str:
    block = re.search(r"<instanceState>(.*?)</instanceState>", text, re.S)
    assert block, f"no instance state in {text[:400]}"
    match = re.search(r"<name>([^<]+)</name>", block.group(1))
    assert match, f"no state name in {block.group(1)[:200]}"
    return match.group(1)


def launch(endpoint, count: int = 1, **extra) -> list[str]:
    text = ok(
        endpoint,
        "RunInstances",
        ImageId=AMI,
        InstanceType="t3.micro",
        MinCount=str(count),
        MaxCount=str(count),
        **extra,
    )
    found = ids(text, "instanceId")
    assert len(found) == count, text[:400]
    return found


# ---------------------------------------------------------------------------
# Creating and finding what a test needs
# ---------------------------------------------------------------------------


def tagged(resource_type: str, name: str, **params) -> dict:
    """The `TagSpecification` that names a resource, so a later sweep can find it."""
    return {
        "TagSpecification.1.ResourceType": resource_type,
        "TagSpecification.1.Tag.1.Key": "Name",
        "TagSpecification.1.Tag.1.Value": name,
        **params,
    }


def labelled(endpoint, name: str, prefix: str) -> list[str]:
    """Ids carrying `Name=<name>`, which is how a create is found again on a later sweep."""
    text = ok(
        endpoint,
        "DescribeTags",
        **{
            "Filter.1.Name": "key",
            "Filter.1.Value.1": "Name",
            "Filter.2.Name": "value",
            "Filter.2.Value.1": name,
        },
    )
    return [rid for rid in ids(text, "resourceId") if rid.startswith(prefix)]


def find_or_create(endpoint, name: str, prefix: str, action: str, id_tag: str, **params) -> str:
    existing = labelled(endpoint, name, prefix)
    if existing:
        return existing[0]
    return first_id(ok(endpoint, action, **params), id_tag)


def security_group(endpoint, name: str, vpc_id: str | None = None) -> str:
    filters = {"Filter.1.Name": "group-name", "Filter.1.Value.1": name}
    if vpc_id:
        filters.update({"Filter.2.Name": "vpc-id", "Filter.2.Value.1": vpc_id})
    found = ids(ok(endpoint, "DescribeSecurityGroups", **filters), "groupId")
    if found:
        return found[0]
    extra = {"VpcId": vpc_id} if vpc_id else {}
    return field(
        ok(endpoint, "CreateSecurityGroup", GroupName=name, GroupDescription=name, **extra),
        "groupId",
    )


def placement_group(endpoint, name: str, **create) -> str:
    status, text = call(endpoint, "CreatePlacementGroup", GroupName=name, **create)
    assert status == 200 or "InvalidPlacementGroup.Duplicate" in text, text[:400]
    listing = ok(endpoint, "DescribePlacementGroups")
    match = re.search(
        rf"<groupName>{name}</groupName>.*?<groupId>([^<]+)</groupId>", listing, re.S
    )
    assert match, f"no placement group {name} in {listing[:400]}"
    return match.group(1)


def key_pair(endpoint, name: str) -> str:
    status, _text = call(endpoint, "DescribeKeyPairs", **{"KeyName.1": name})
    if status == 200:
        return name
    ok(endpoint, "CreateKeyPair", KeyName=name)
    return name


def instance_profile(endpoint, name: str) -> str:
    """An IAM instance profile is the dependant; EC2 only reads it from IAM."""
    body = urlencode({"Action": "GetInstanceProfile", "Version": "2010-05-08",
                      "InstanceProfileName": name})
    status, _text = signed.request(endpoint, "iam", ACCOUNT, REGION, "POST", "/", body)
    if status != 200:
        body = urlencode({"Action": "CreateInstanceProfile", "Version": "2010-05-08",
                          "InstanceProfileName": name})
        created, text = signed.request(endpoint, "iam", ACCOUNT, REGION, "POST", "/", body)
        assert created == 200, f"CreateInstanceProfile answered {created}: {text[:400]}"
    return f"arn:aws:iam::{ACCOUNT}:instance-profile/{name}"


def image(endpoint, name: str) -> str:
    filters = {"Filter.1.Name": "name", "Filter.1.Value.1": name}
    found = ids(ok(endpoint, "DescribeImages", **filters), "imageId")
    if found:
        return found[0]
    return first_id(ok(endpoint, "RegisterImage", Name=name, **tagged("image", name)), "imageId")


def vpc(endpoint, name: str, cidr: str = "10.99.0.0/16") -> str:
    return find_or_create(endpoint, name, "vpc-", "CreateVpc", "vpcId",
                          CidrBlock=cidr, **tagged("vpc", name))


def subnet(endpoint, name: str, vpc_id: str, cidr: str) -> str:
    return find_or_create(endpoint, name, "subnet-", "CreateSubnet", "subnetId",
                          VpcId=vpc_id, CidrBlock=cidr, **tagged("subnet", name))


def internet_gateway(endpoint, name: str) -> str:
    return find_or_create(endpoint, name, "igw-", "CreateInternetGateway", "internetGatewayId",
                          **tagged("internet-gateway", name))


def route_table(endpoint, name: str, vpc_id: str) -> str:
    return find_or_create(endpoint, name, "rtb-", "CreateRouteTable", "routeTableId",
                          VpcId=vpc_id, **tagged("route-table", name))


def network_interface(endpoint, name: str, subnet_id: str, sg_id: str) -> str:
    return find_or_create(endpoint, name, "eni-", "CreateNetworkInterface",
                          "networkInterfaceId", SubnetId=subnet_id,
                          **{"SecurityGroupId.1": sg_id}, **tagged("network-interface", name))


def elastic_ip(endpoint, name: str) -> str:
    return find_or_create(endpoint, name, "eipalloc-", "AllocateAddress", "allocationId",
                          Domain="vpc", **tagged("elastic-ip", name))


def nat_gateway(endpoint, name: str, subnet_id: str) -> str:
    return find_or_create(endpoint, name, "nat-", "CreateNatGateway", "natGatewayId",
                          SubnetId=subnet_id,
                          AllocationId=elastic_ip(endpoint, "emuplane-test-eip-nat"),
                          **tagged("natgateway", name))


def network_acl(endpoint, name: str, vpc_id: str) -> str:
    return find_or_create(endpoint, name, "acl-", "CreateNetworkAcl", "networkAclId",
                          VpcId=vpc_id, **tagged("network-acl", name))


def flow_log(endpoint, name: str, vpc_id: str) -> str:
    existing = labelled(endpoint, name, "fl-")
    if existing:
        return existing[0]
    text = ok(endpoint, "CreateFlowLogs", **{"ResourceId.1": vpc_id}, ResourceType="VPC",
              TrafficType="ALL", LogDestinationType="cloud-watch-logs", LogGroupName=name,
              **tagged("flow-log", name))
    match = re.search(r"<flowLogIdSet><item>([^<]+)</item>", text)
    assert match, text[:400]
    return match.group(1)


def vpc_peering(endpoint, name: str, vpc_id: str, peer_vpc_id: str) -> str:
    return find_or_create(endpoint, name, "pcx-", "CreateVpcPeeringConnection",
                          "vpcPeeringConnectionId", VpcId=vpc_id, PeerVpcId=peer_vpc_id,
                          **tagged("vpc-peering-connection", name))


def dhcp_options(endpoint, name: str) -> str:
    return find_or_create(
        endpoint, name, "dopt-", "CreateDhcpOptions", "dhcpOptionsId",
        **{
            "DhcpConfiguration.1.Key": "domain-name",
            "DhcpConfiguration.1.Value.1": "emuplane.internal",
        },
        **tagged("dhcp-options", name),
    )


def egress_gateway(endpoint, name: str, vpc_id: str) -> str:
    return find_or_create(endpoint, name, "eigw-", "CreateEgressOnlyInternetGateway",
                          "egressOnlyInternetGatewayId", VpcId=vpc_id,
                          **tagged("egress-only-internet-gateway", name))


def prefix_list(endpoint, name: str) -> str:
    return find_or_create(
        endpoint, name, "pl-", "CreateManagedPrefixList", "prefixListId",
        PrefixListName=name,
        MaxEntries="5",
        AddressFamily="IPv4",
        **{"Entry.1.Cidr": "10.20.0.0/16"},
        **tagged("prefix-list", name),
    )


def vpn_gateway(endpoint, name: str) -> str:
    return find_or_create(endpoint, name, "vgw-", "CreateVpnGateway", "vpnGatewayId",
                          Type="ipsec.1", **tagged("vpn-gateway", name))


def customer_gateway(endpoint, name: str) -> str:
    return find_or_create(endpoint, name, "cgw-", "CreateCustomerGateway",
                          "customerGatewayId", Type="ipsec.1", BgpAsn="65000",
                          IpAddress="203.0.113.9", **tagged("customer-gateway", name))


def vpc_endpoint(endpoint, name: str, vpc_id: str, route_table_id: str) -> str:
    return find_or_create(
        endpoint, name, "vpce-", "CreateVpcEndpoint", "vpcEndpointId",
        VpcId=vpc_id,
        ServiceName=f"com.amazonaws.{REGION}.s3",
        VpcEndpointType="Gateway",
        **{"RouteTableId.1": route_table_id},
        **tagged("vpc-endpoint", name),
    )


def launch_template(endpoint, name: str) -> str:
    found = ids(ok(endpoint, "DescribeLaunchTemplates",
                   **{"LaunchTemplateName.1": name}), "launchTemplateId")
    if found:
        return found[0]
    return field(
        ok(
            endpoint,
            "CreateLaunchTemplate",
            LaunchTemplateName=name,
            **{
                "LaunchTemplateData.ImageId": AMI,
                "LaunchTemplateData.InstanceType": "t3.micro",
            },
        ),
        "launchTemplateId",
    )


def acm_call(endpoint, action: str, payload: dict) -> dict:
    """One ACM call; `conftest` routes a credential's service name to a module and ACM
    has no entry there, so in-process the module answers directly and the lab answers
    over HTTP."""
    body = json.dumps(payload)
    if os.environ.get("EP_LAB_EMULATOR"):
        status, text = signed.request(endpoint, "acm", ACCOUNT, REGION, "POST", "/", body,
                                      {"X-Amz-Target": f"CertificateManager.{action}"})
        assert status == 200, f"ACM {action} answered {status}: {text[:400]}"
        return json.loads(text)
    from ministack.core.responses import request_scope  # noqa: PLC0415 - the harness seam
    from ministack.services import acm  # noqa: PLC0415

    with request_scope(ACCOUNT, REGION):
        status, _headers, raw = asyncio.run(
            acm.handle_request("POST", "/", {"x-amz-target": f"CertificateManager.{action}"},
                               body.encode(), {})
        )
    assert status == 200, f"ACM {action} answered {status}: {raw[:400]}"
    return json.loads(raw)


def certificate(endpoint, domain: str) -> str:
    """An ISSUED ACM certificate naming `domain`, found or requested."""
    for summary in acm_call(endpoint, "ListCertificates", {}).get("CertificateSummaryList", []):
        if summary["DomainName"] == domain and summary["Status"] == "ISSUED":
            return summary["CertificateArn"]
    return acm_call(endpoint, "RequestCertificate", {"DomainName": domain})["CertificateArn"]


def bucket(endpoint, name: str) -> str:
    status, _text = signed.request(endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{name}")
    assert status in (200, 409), f"CreateBucket answered {status}"
    return name


# ---------------------------------------------------------------------------
# Verified Access
# ---------------------------------------------------------------------------

VA_USER = {
    "TrustProviderType": "user",
    "UserTrustProviderType": "oidc",
    "PolicyReferenceName": "emuplane_va",
    "OidcOptions.Issuer": "https://issuer.emuplane.test",
    "OidcOptions.AuthorizationEndpoint": "https://issuer.emuplane.test/authorize",
    "OidcOptions.TokenEndpoint": "https://issuer.emuplane.test/token",
    "OidcOptions.UserInfoEndpoint": "https://issuer.emuplane.test/userinfo",
    "OidcOptions.ClientId": "emuplane",
    "OidcOptions.ClientSecret": "not-a-real-secret",
    "OidcOptions.Scope": "openid",
}


def va_instance(endpoint, name: str = "emuplane-test-va-instance") -> str:
    return find_or_create(endpoint, name, "vai-", "CreateVerifiedAccessInstance",
                          "verifiedAccessInstanceId",
                          **tagged("verified-access-instance", name))


def va_user_provider(endpoint, name: str = "emuplane-test-va-user") -> str:
    return find_or_create(endpoint, name, "vatp-", "CreateVerifiedAccessTrustProvider",
                          "verifiedAccessTrustProviderId",
                          **VA_USER, **tagged("verified-access-trust-provider", name))


def va_device_provider(endpoint, name: str) -> str:
    return find_or_create(
        endpoint, name, "vatp-", "CreateVerifiedAccessTrustProvider",
        "verifiedAccessTrustProviderId",
        TrustProviderType="device",
        DeviceTrustProviderType="jumpcloud",
        PolicyReferenceName="emuplane_va_device",
        **{"DeviceOptions.TenantId": "emuplane"},
        **tagged("verified-access-trust-provider", name),
    )


def va_attached(endpoint, instance_id: str, provider_id: str) -> bool:
    text = ok(endpoint, "DescribeVerifiedAccessInstances",
              **{"VerifiedAccessInstanceId.1": instance_id})
    return provider_id in ids(text, "verifiedAccessTrustProviderId")


def va_instance_with_user(endpoint) -> tuple[str, str]:
    instance_id = va_instance(endpoint)
    provider_id = va_user_provider(endpoint)
    if not va_attached(endpoint, instance_id, provider_id):
        ok(endpoint, "AttachVerifiedAccessTrustProvider",
           VerifiedAccessInstanceId=instance_id, VerifiedAccessTrustProviderId=provider_id)
    return instance_id, provider_id


def va_group(endpoint, name: str = "emuplane-test-va-group") -> str:
    instance_id, _provider = va_instance_with_user(endpoint)
    return find_or_create(endpoint, name, "vagr-", "CreateVerifiedAccessGroup",
                          "verifiedAccessGroupId", VerifiedAccessInstanceId=instance_id,
                          **tagged("verified-access-group", name))


def va_endpoint_params(endpoint, name: str, domain: str, vpc_id: str, sg_name: str) -> dict:
    group_id = va_group(endpoint)
    sg_id = security_group(endpoint, sg_name)
    subnet_id = subnet(endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    eni_id = network_interface(endpoint, f"{name}-eni", subnet_id, sg_id)
    cert = certificate(endpoint, "*.emuplane.test")
    return {
        "VerifiedAccessGroupId": group_id,
        "EndpointType": "network-interface",
        "AttachmentType": "vpc",
        "DomainCertificateArn": cert,
        "ApplicationDomain": domain,
        "EndpointDomainPrefix": "emuplane",
        "NetworkInterfaceOptions.NetworkInterfaceId": eni_id,
        "NetworkInterfaceOptions.Protocol": "http",
        "SecurityGroupId.1": sg_id,
        **tagged("verified-access-endpoint", name),
    }


def va_endpoint(endpoint, name: str, domain: str, vpc_id: str, sg_name: str) -> str:
    return find_or_create(
        endpoint, name, "vae-", "CreateVerifiedAccessEndpoint", "verifiedAccessEndpointId",
        **va_endpoint_params(endpoint, name, domain, vpc_id, sg_name),
    )


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------


def test_describe_instances_answers_a_reservation_set(s3_endpoint):
    text = ok(s3_endpoint, "DescribeInstances")
    assert "reservationSet" in text


def test_run_instances_is_read_back_by_describe(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    text = ok(s3_endpoint, "DescribeInstances", **{"InstanceId.1": instance})
    assert instance in text
    assert state(text) in {"pending", "running"}


def test_start_and_stop_instances_change_its_state(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    ok(s3_endpoint, "StopInstances", **{"InstanceId.1": instance})
    stopped = ok(s3_endpoint, "DescribeInstances", **{"InstanceId.1": instance})
    assert "stopped" in stopped
    ok(s3_endpoint, "StartInstances", **{"InstanceId.1": instance})
    started = ok(s3_endpoint, "DescribeInstances", **{"InstanceId.1": instance})
    assert "running" in started or "pending" in started


def test_terminate_instances_removes_the_instance_it_launched(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    ok(s3_endpoint, "TerminateInstances", **{"InstanceId.1": instance})
    text = ok(s3_endpoint, "DescribeInstances", **{"InstanceId.1": instance})
    assert "terminated" in text


def test_reboot_instances_leaves_it_running(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    text = ok(s3_endpoint, "RebootInstances", **{"InstanceId.1": instance})
    assert "<return>true</return>" in text
    assert state(ok(s3_endpoint, "DescribeInstances", **{"InstanceId.1": instance})) == "running"


def test_describe_instance_attribute_names_its_instance_type(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    text = ok(s3_endpoint, "DescribeInstanceAttribute", InstanceId=instance,
              Attribute="instanceType")
    assert field(text, "instanceId") == instance
    assert field(text, "value") == "t3.micro"


def test_describe_instance_types_lists_the_requested_type(s3_endpoint):
    text = ok(s3_endpoint, "DescribeInstanceTypes", **{"InstanceType.1": "t3.micro"})
    assert first_id(text, "instanceType") == "t3.micro"
    assert "<memoryInfo>" in text


def test_describe_instance_status_reports_system_and_instance_checks(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    text = ok(s3_endpoint, "DescribeInstanceStatus", **{"InstanceId.1": instance,
                                                         "IncludeAllInstances": "true"})
    assert instance in text
    assert "<systemStatus>" in text and "<instanceStatus>" in text


def test_describe_instance_credit_specifications_default_to_standard(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    text = ok(s3_endpoint, "DescribeInstanceCreditSpecifications", **{"InstanceId.1": instance})
    assert instance in text
    assert field(text, "cpuCredits") == "standard"


def test_modify_instance_maintenance_options_sets_auto_recovery(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    text = ok(s3_endpoint, "ModifyInstanceMaintenanceOptions", InstanceId=instance,
              AutoRecovery="disabled")
    assert field(text, "instanceId") == instance
    assert field(text, "autoRecovery") == "disabled"


def test_describe_instance_topology_answers_an_empty_set(s3_endpoint):
    assert "<instanceSet/>" in ok(s3_endpoint, "DescribeInstanceTopology")


def test_describe_spot_instance_requests_answers_an_empty_set(s3_endpoint):
    assert "<spotInstanceRequestSet/>" in ok(s3_endpoint, "DescribeSpotInstanceRequests")


def test_describe_capacity_reservations_answers_an_empty_set(s3_endpoint):
    assert "<capacityReservationSet/>" in ok(s3_endpoint, "DescribeCapacityReservations")


@pytest.mark.skip(
    reason="MiniStack 1.5.40 advertises DescribeInstanceMaintenanceOptions but its "
    "_ACTION_MAP has no handler, so the call answers InvalidAction (400)"
)
def test_describe_instance_maintenance_options(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    ok(s3_endpoint, "DescribeInstanceMaintenanceOptions", InstanceId=instance)


@pytest.mark.skip(
    reason="MiniStack 1.5.40 advertises DescribeInstanceAutoRecoveryAttribute but its "
    "_ACTION_MAP has no handler, so the call answers InvalidAction (400)"
)
def test_describe_instance_auto_recovery_attribute(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    ok(s3_endpoint, "DescribeInstanceAutoRecoveryAttribute", InstanceId=instance,
       Attribute="autoRecovery")


def test_describe_vpc_classic_link_answers_an_empty_set(s3_endpoint):
    assert "<vpcSet/>" in ok(s3_endpoint, "DescribeVpcClassicLink")


def test_describe_vpc_classic_link_dns_support_answers_an_empty_set(s3_endpoint):
    assert "<vpcs/>" in ok(s3_endpoint, "DescribeVpcClassicLinkDnsSupport")


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def test_describe_images_lists_the_stub_amis(s3_endpoint):
    text = ok(s3_endpoint, "DescribeImages", **{"Owner.1": "amazon"})
    assert "ami-0abcdef1234567890" in text


def test_register_image_is_read_back_by_describe(s3_endpoint):
    name = "emuplane-test-ami-registered"
    image_id = image(s3_endpoint, name)
    text = ok(s3_endpoint, "DescribeImages", **{"ImageId.1": image_id})
    assert image_id in text
    assert field(text, "name") == name


def test_deregister_image_removes_the_image_it_registered(s3_endpoint):
    name = "emuplane-test-ami-deregistered"
    image_id = image(s3_endpoint, name)
    ok(s3_endpoint, "DeregisterImage", ImageId=image_id)
    status, _text = call(s3_endpoint, "DescribeImages", **{"ImageId.1": image_id})
    assert status == 200  # an unknown ImageId.1 filter simply selects nothing


def test_modify_image_attribute_shares_the_image(s3_endpoint):
    image_id = image(s3_endpoint, "emuplane-test-ami-shared")
    ok(s3_endpoint, "ModifyImageAttribute", ImageId=image_id,
       **{"LaunchPermission.Add.1.Group": "all"})
    text = ok(s3_endpoint, "DescribeImageAttribute", ImageId=image_id, Attribute="launchPermission")
    assert field(text, "group") == "all"


def test_describe_image_attribute_answers_launch_permissions(s3_endpoint):
    image_id = image(s3_endpoint, "emuplane-test-ami-attribute")
    ok(s3_endpoint, "ModifyImageAttribute", ImageId=image_id,
       **{"LaunchPermission.Add.1.UserId": "222222222222"})
    text = ok(s3_endpoint, "DescribeImageAttribute", ImageId=image_id, Attribute="launchPermission")
    assert "222222222222" in text


def test_reset_image_attribute_clears_launch_permissions(s3_endpoint):
    image_id = image(s3_endpoint, "emuplane-test-ami-reset")
    ok(s3_endpoint, "ModifyImageAttribute", ImageId=image_id,
       **{"LaunchPermission.Add.1.UserId": "222222222222"})
    ok(s3_endpoint, "ResetImageAttribute", ImageId=image_id, Attribute="launchPermission")
    text = ok(s3_endpoint, "DescribeImageAttribute", ImageId=image_id, Attribute="launchPermission")
    assert "222222222222" not in text


# ---------------------------------------------------------------------------
# IAM instance profiles
# ---------------------------------------------------------------------------


def test_associate_iam_instance_profile_attaches_it(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    profile = instance_profile(s3_endpoint, "emuplane-test-instance-profile")
    text = ok(s3_endpoint, "AssociateIamInstanceProfile", InstanceId=instance,
              **{"IamInstanceProfile.Arn": profile})
    assert field(text, "state") == "associated"
    assert profile in text


def test_describe_iam_instance_profile_associations_lists_the_association(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    profile = instance_profile(s3_endpoint, "emuplane-test-instance-profile")
    association = field(
        ok(s3_endpoint, "AssociateIamInstanceProfile", InstanceId=instance,
           **{"IamInstanceProfile.Arn": profile}),
        "associationId",
    )
    text = ok(s3_endpoint, "DescribeIamInstanceProfileAssociations",
              **{"AssociationId.1": association})
    assert association in text
    assert instance in text


def test_disassociate_iam_instance_profile_detaches_it(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    profile = instance_profile(s3_endpoint, "emuplane-test-instance-profile")
    association = field(
        ok(s3_endpoint, "AssociateIamInstanceProfile", InstanceId=instance,
           **{"IamInstanceProfile.Arn": profile}),
        "associationId",
    )
    text = ok(s3_endpoint, "DisassociateIamInstanceProfile", AssociationId=association)
    assert field(text, "state") == "disassociated"


def test_replace_iam_instance_profile_association_swaps_the_profile(s3_endpoint):
    (instance,) = launch(s3_endpoint)
    first = instance_profile(s3_endpoint, "emuplane-test-instance-profile")
    second = instance_profile(s3_endpoint, "emuplane-test-instance-profile-two")
    association = field(
        ok(s3_endpoint, "AssociateIamInstanceProfile", InstanceId=instance,
           **{"IamInstanceProfile.Arn": first}),
        "associationId",
    )
    text = ok(s3_endpoint, "ReplaceIamInstanceProfileAssociation", AssociationId=association,
              **{"IamInstanceProfile.Arn": second})
    assert second in text
    assert field(text, "state") == "associated"


# ---------------------------------------------------------------------------
# Security groups
# ---------------------------------------------------------------------------


def test_create_security_group_is_read_back_by_describe(s3_endpoint):
    name = "emuplane-test-sg-created"
    group_id = security_group(s3_endpoint, name)
    text = ok(s3_endpoint, "DescribeSecurityGroups", **{"GroupId.1": group_id})
    assert field(text, "groupName") == name
    assert field(text, "groupId") == group_id


def test_delete_security_group_removes_the_group_it_created(s3_endpoint):
    name = "emuplane-test-sg-deleted"
    group_id = security_group(s3_endpoint, name)
    ok(s3_endpoint, "DeleteSecurityGroup", GroupId=group_id)
    status, text = call(s3_endpoint, "DescribeSecurityGroups", **{"GroupId.1": group_id})
    assert status == 400
    assert "InvalidGroup.NotFound" in text


def test_describe_security_groups_lists_the_default_group(s3_endpoint):
    text = ok(s3_endpoint, "DescribeSecurityGroups",
              **{"Filter.1.Name": "group-name", "Filter.1.Value.1": "default"})
    assert "default" in text
    assert ids(text, "groupId")


def test_authorize_security_group_ingress_adds_a_rule(s3_endpoint):
    group_id = security_group(s3_endpoint, "emuplane-test-sg-ingress")
    text = ok(
        s3_endpoint,
        "AuthorizeSecurityGroupIngress",
        GroupId=group_id,
        **{
            "IpPermissions.1.IpProtocol": "tcp",
            "IpPermissions.1.FromPort": "22",
            "IpPermissions.1.ToPort": "22",
            "IpPermissions.1.IpRanges.1.CidrIp": "198.51.100.0/24",
        },
    )
    assert "sgr-" in text
    described = ok(s3_endpoint, "DescribeSecurityGroups", **{"GroupId.1": group_id})
    assert "198.51.100.0/24" in described


def test_revoke_security_group_ingress_removes_its_rule(s3_endpoint):
    group_id = security_group(s3_endpoint, "emuplane-test-sg-revoke-ingress")
    rule = {
        "IpPermissions.1.IpProtocol": "tcp",
        "IpPermissions.1.FromPort": "8080",
        "IpPermissions.1.ToPort": "8080",
        "IpPermissions.1.IpRanges.1.CidrIp": "203.0.113.0/24",
    }
    ok(s3_endpoint, "AuthorizeSecurityGroupIngress", GroupId=group_id, **rule)
    ok(s3_endpoint, "RevokeSecurityGroupIngress", GroupId=group_id, **rule)
    described = ok(s3_endpoint, "DescribeSecurityGroups", **{"GroupId.1": group_id})
    assert "203.0.113.0/24" not in described


def test_authorize_security_group_egress_adds_a_rule(s3_endpoint):
    group_id = security_group(s3_endpoint, "emuplane-test-sg-egress")
    text = ok(
        s3_endpoint,
        "AuthorizeSecurityGroupEgress",
        GroupId=group_id,
        **{
            "IpPermissions.1.IpProtocol": "tcp",
            "IpPermissions.1.FromPort": "443",
            "IpPermissions.1.ToPort": "443",
            "IpPermissions.1.IpRanges.1.CidrIp": "192.0.2.0/24",
        },
    )
    assert "sgr-" in text
    described = ok(s3_endpoint, "DescribeSecurityGroups", **{"GroupId.1": group_id})
    assert "192.0.2.0/24" in described


def test_revoke_security_group_egress_removes_its_rule(s3_endpoint):
    group_id = security_group(s3_endpoint, "emuplane-test-sg-revoke-egress")
    rule = {
        "IpPermissions.1.IpProtocol": "udp",
        "IpPermissions.1.FromPort": "514",
        "IpPermissions.1.ToPort": "514",
        "IpPermissions.1.IpRanges.1.CidrIp": "198.18.0.0/15",
    }
    ok(s3_endpoint, "AuthorizeSecurityGroupEgress", GroupId=group_id, **rule)
    ok(s3_endpoint, "RevokeSecurityGroupEgress", GroupId=group_id, **rule)
    described = ok(s3_endpoint, "DescribeSecurityGroups", **{"GroupId.1": group_id})
    assert "198.18.0.0/15" not in described


def test_describe_security_group_rules_lists_the_ingress_rule(s3_endpoint):
    group_id = security_group(s3_endpoint, "emuplane-test-sg-rules")
    ok(
        s3_endpoint,
        "AuthorizeSecurityGroupIngress",
        GroupId=group_id,
        **{
            "IpPermissions.1.IpProtocol": "tcp",
            "IpPermissions.1.FromPort": "3306",
            "IpPermissions.1.ToPort": "3306",
            "IpPermissions.1.IpRanges.1.CidrIp": "10.10.0.0/16",
        },
    )
    text = ok(s3_endpoint, "DescribeSecurityGroupRules",
              **{"Filter.1.Name": "group-id", "Filter.1.Value.1": group_id})
    assert group_id in text
    assert "3306" in text
    assert "sgr-" in text


# ---------------------------------------------------------------------------
# Key pairs and placement groups
# ---------------------------------------------------------------------------


def test_create_key_pair_is_read_back_by_describe(s3_endpoint):
    name = "emuplane-test-key-created"
    status, text = call(s3_endpoint, "CreateKeyPair", KeyName=name)
    assert status == 200 or "InvalidKeyPair.Duplicate" in text
    if status == 200:
        assert field(text, "keyName") == name
        assert "BEGIN RSA PRIVATE KEY" in text
    described = ok(s3_endpoint, "DescribeKeyPairs", **{"KeyName.1": name})
    assert field(described, "keyName") == name


def test_delete_key_pair_removes_the_pair_it_created(s3_endpoint):
    name = "emuplane-test-key-deleted"
    ok(s3_endpoint, "CreateKeyPair", KeyName=name)
    ok(s3_endpoint, "DeleteKeyPair", KeyName=name)
    status, text = call(s3_endpoint, "DescribeKeyPairs", **{"KeyName.1": name})
    assert status == 400
    assert "InvalidKeyPair.NotFound" in text


def test_describe_key_pairs_lists_the_pair(s3_endpoint):
    name = key_pair(s3_endpoint, "emuplane-test-key-described")
    text = ok(s3_endpoint, "DescribeKeyPairs", **{"KeyName.1": name})
    assert field(text, "keyName") == name


def test_import_key_pair_keeps_the_public_material(s3_endpoint):
    name = "emuplane-test-key-imported"
    material = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEmuplaneTestKeyMaterial"
    text = ok(s3_endpoint, "ImportKeyPair", KeyName=name, PublicKeyMaterial=material)
    assert field(text, "keyName") == name
    described = ok(s3_endpoint, "DescribeKeyPairs", **{"KeyName.1": name,
                                                       "IncludePublicKey": "true"})
    assert "ssh-ed25519" in described


def test_create_placement_group_is_read_back_by_describe(s3_endpoint):
    name = "emuplane-test-placement"
    group_id = placement_group(s3_endpoint, name, Strategy="cluster")
    text = ok(s3_endpoint, "DescribePlacementGroups")
    assert group_id in text
    assert field(text, "groupName") == name
    assert field(text, "strategy") == "cluster"


def test_delete_placement_group_removes_the_group_it_created(s3_endpoint):
    name = "emuplane-test-placement-deleted"
    placement_group(s3_endpoint, name)
    ok(s3_endpoint, "DeletePlacementGroup", GroupName=name)
    status, text = call(s3_endpoint, "DescribePlacementGroups", **{"GroupName.1": name})
    assert status == 400
    assert "InvalidPlacementGroup.Unknown" in text


def test_describe_placement_groups_lists_the_group(s3_endpoint):
    name = "emuplane-test-placement-described"
    group_id = placement_group(s3_endpoint, name, Strategy="partition", PartitionCount="3")
    text = ok(s3_endpoint, "DescribePlacementGroups", **{"GroupId.1": group_id})
    assert name in text
    assert "<groupArn>" in text


# ---------------------------------------------------------------------------
# VPCs, subnets, internet gateways
# ---------------------------------------------------------------------------


def test_create_vpc_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    text = ok(s3_endpoint, "DescribeVpcs", **{"VpcId.1": vpc_id})
    assert field(text, "vpcId") == vpc_id
    assert field(text, "cidrBlock") == "10.99.0.0/16"


def test_delete_vpc_removes_the_vpc_it_created(s3_endpoint):
    created = field(ok(s3_endpoint, "CreateVpc", CidrBlock="10.98.0.0/16"), "vpcId")
    ok(s3_endpoint, "DeleteVpc", VpcId=created)
    status, text = call(s3_endpoint, "DescribeVpcs", **{"VpcId.1": created})
    assert status == 400
    assert "InvalidVpcID.NotFound" in text


def test_describe_vpcs_filters_by_tag(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    text = ok(s3_endpoint, "DescribeVpcs",
              **{"Filter.1.Name": "tag:Name", "Filter.1.Value.1": "emuplane-test-vpc"})
    assert vpc_id in text


def test_modify_vpc_attribute_enables_dns_hostnames(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    ok(s3_endpoint, "ModifyVpcAttribute", VpcId=vpc_id,
       **{"EnableDnsHostnames.Value": "true"})
    text = ok(s3_endpoint, "DescribeVpcAttribute", VpcId=vpc_id, Attribute="enableDnsHostnames")
    assert "<value>true</value>" in text


def test_describe_vpc_attribute_answers_dns_support(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    text = ok(s3_endpoint, "DescribeVpcAttribute", VpcId=vpc_id, Attribute="enableDnsSupport")
    assert field(text, "vpcId") == vpc_id
    assert "<enableDnsSupport>" in text


def test_create_subnet_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    text = ok(s3_endpoint, "DescribeSubnets", **{"SubnetId.1": subnet_id})
    assert field(text, "subnetId") == subnet_id
    assert field(text, "vpcId") == vpc_id


def test_delete_subnet_removes_the_subnet_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    created = field(
        ok(s3_endpoint, "CreateSubnet", VpcId=vpc_id, CidrBlock="10.99.99.0/24"), "subnetId"
    )
    ok(s3_endpoint, "DeleteSubnet", SubnetId=created)
    status, text = call(s3_endpoint, "DescribeSubnets", **{"SubnetId.1": created})
    assert status == 400
    assert "InvalidSubnetID.NotFound" in text


def test_describe_subnets_lists_the_subnet(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    text = ok(s3_endpoint, "DescribeSubnets",
              **{"Filter.1.Name": "vpc-id", "Filter.1.Value.1": vpc_id})
    assert subnet_id in text


def test_modify_subnet_attribute_maps_public_ip_on_launch(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    ok(s3_endpoint, "ModifySubnetAttribute", SubnetId=subnet_id,
       **{"MapPublicIpOnLaunch.Value": "true"})
    text = ok(s3_endpoint, "DescribeSubnets", **{"SubnetId.1": subnet_id})
    assert "<mapPublicIpOnLaunch>true</mapPublicIpOnLaunch>" in text


def test_create_internet_gateway_is_read_back_by_describe(s3_endpoint):
    igw_id = internet_gateway(s3_endpoint, "emuplane-test-igw")
    text = ok(s3_endpoint, "DescribeInternetGateways", **{"InternetGatewayId.1": igw_id})
    assert field(text, "internetGatewayId") == igw_id


def test_delete_internet_gateway_removes_the_gateway_it_created(s3_endpoint):
    created = field(ok(s3_endpoint, "CreateInternetGateway"), "internetGatewayId")
    ok(s3_endpoint, "DeleteInternetGateway", InternetGatewayId=created)
    status, text = call(s3_endpoint, "DescribeInternetGateways",
                        **{"InternetGatewayId.1": created})
    assert status == 400
    assert "InvalidInternetGatewayID.NotFound" in text


def test_describe_internet_gateways_lists_the_gateway(s3_endpoint):
    igw_id = internet_gateway(s3_endpoint, "emuplane-test-igw")
    text = ok(s3_endpoint, "DescribeInternetGateways",
              **{"Filter.1.Name": "internet-gateway-id", "Filter.1.Value.1": igw_id})
    assert igw_id in text


def test_attach_internet_gateway_attaches_it_to_the_vpc(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc-gateway")
    igw_id = internet_gateway(s3_endpoint, "emuplane-test-igw-attached")
    status, text = call(s3_endpoint, "AttachInternetGateway", InternetGatewayId=igw_id,
                        VpcId=vpc_id)
    assert status == 200 or "Resource.AlreadyAssociated" in text
    described = ok(s3_endpoint, "DescribeInternetGateways",
                   **{"Filter.1.Name": "attachment.vpc-id", "Filter.1.Value.1": vpc_id})
    assert igw_id in described


def test_detach_internet_gateway_detaches_it(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc-gateway")
    igw_id = internet_gateway(s3_endpoint, "emuplane-test-igw-detached")
    status, text = call(s3_endpoint, "AttachInternetGateway", InternetGatewayId=igw_id,
                        VpcId=vpc_id)
    assert status == 200 or "Resource.AlreadyAssociated" in text
    ok(s3_endpoint, "DetachInternetGateway", InternetGatewayId=igw_id, VpcId=vpc_id)
    described = ok(s3_endpoint, "DescribeInternetGateways", **{"InternetGatewayId.1": igw_id})
    assert f"<vpcId>{vpc_id}</vpcId>" not in described


# ---------------------------------------------------------------------------
# Route tables and routes
# ---------------------------------------------------------------------------


def test_create_route_table_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    text = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    assert field(text, "routeTableId") == table_id
    assert field(text, "vpcId") == vpc_id


def test_delete_route_table_removes_the_table_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    created = field(ok(s3_endpoint, "CreateRouteTable", VpcId=vpc_id), "routeTableId")
    ok(s3_endpoint, "DeleteRouteTable", RouteTableId=created)
    text = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": created})
    assert "<routeTableSet></routeTableSet>" in text


def test_describe_route_tables_lists_the_table(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    text = ok(s3_endpoint, "DescribeRouteTables",
              **{"Filter.1.Name": "vpc-id", "Filter.1.Value.1": vpc_id})
    assert table_id in text


def test_associate_route_table_answers_an_association(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    association = field(
        ok(s3_endpoint, "AssociateRouteTable", RouteTableId=table_id, SubnetId=subnet_id),
        "associationId",
    )
    assert association.startswith("rtbassoc-")
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    assert association in described
    assert subnet_id in described


def test_disassociate_route_table_drops_the_association(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    association = field(
        ok(s3_endpoint, "AssociateRouteTable", RouteTableId=table_id, SubnetId=subnet_id),
        "associationId",
    )
    ok(s3_endpoint, "DisassociateRouteTable", AssociationId=association)
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    assert association not in described


def test_replace_route_table_association_moves_it(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    old_table = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    new_table = route_table(s3_endpoint, "emuplane-test-rtb-two", vpc_id)
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    association = field(
        ok(s3_endpoint, "AssociateRouteTable", RouteTableId=old_table, SubnetId=subnet_id),
        "associationId",
    )
    replacement = field(
        ok(s3_endpoint, "ReplaceRouteTableAssociation", AssociationId=association,
           RouteTableId=new_table),
        "newAssociationId",
    )
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": new_table})
    assert replacement in described
    assert subnet_id in described


def test_create_route_adds_a_destination(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    igw_id = internet_gateway(s3_endpoint, "emuplane-test-igw")
    ok(s3_endpoint, "CreateRoute", RouteTableId=table_id,
       DestinationCidrBlock="172.16.0.0/16", GatewayId=igw_id)
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    assert "172.16.0.0/16" in described
    assert igw_id in described


def test_replace_route_changes_its_target(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    igw_id = internet_gateway(s3_endpoint, "emuplane-test-igw")
    sg_id = security_group(s3_endpoint, "emuplane-test-sg-routes")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    eni_id = network_interface(s3_endpoint, "emuplane-test-eni-route", subnet_id, sg_id)
    ok(s3_endpoint, "CreateRoute", RouteTableId=table_id,
       DestinationCidrBlock="172.17.0.0/16", GatewayId=igw_id)
    ok(s3_endpoint, "ReplaceRoute", RouteTableId=table_id,
       DestinationCidrBlock="172.17.0.0/16", NetworkInterfaceId=eni_id)
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    route = re.search(r"172\.17\.0\.0/16.*?</item>", described, re.S)
    assert route, described[:400]
    assert eni_id in route.group(0)
    assert igw_id not in route.group(0)


def test_delete_route_removes_the_destination(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    igw_id = internet_gateway(s3_endpoint, "emuplane-test-igw")
    ok(s3_endpoint, "CreateRoute", RouteTableId=table_id,
       DestinationCidrBlock="172.18.0.0/16", GatewayId=igw_id)
    ok(s3_endpoint, "DeleteRoute", RouteTableId=table_id,
       DestinationCidrBlock="172.18.0.0/16")
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    assert "172.18.0.0/16" not in described


# ---------------------------------------------------------------------------
# Network interfaces
# ---------------------------------------------------------------------------


def test_create_network_interface_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    sg_id = security_group(s3_endpoint, "emuplane-test-sg-eni")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    eni_id = network_interface(s3_endpoint, "emuplane-test-eni", subnet_id, sg_id)
    text = ok(s3_endpoint, "DescribeNetworkInterfaces", **{"NetworkInterfaceId.1": eni_id})
    assert field(text, "networkInterfaceId") == eni_id
    assert field(text, "subnetId") == subnet_id


def test_delete_network_interface_removes_the_interface_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    sg_id = security_group(s3_endpoint, "emuplane-test-sg-eni")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    created = field(
        ok(s3_endpoint, "CreateNetworkInterface", SubnetId=subnet_id,
           **{"SecurityGroupId.1": sg_id}),
        "networkInterfaceId",
    )
    ok(s3_endpoint, "DeleteNetworkInterface", NetworkInterfaceId=created)
    text = ok(s3_endpoint, "DescribeNetworkInterfaces",
              **{"NetworkInterfaceId.1": created})
    assert "<networkInterfaceSet></networkInterfaceSet>" in text


def test_describe_network_interfaces_lists_the_interface(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    sg_id = security_group(s3_endpoint, "emuplane-test-sg-eni")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    eni_id = network_interface(s3_endpoint, "emuplane-test-eni", subnet_id, sg_id)
    text = ok(s3_endpoint, "DescribeNetworkInterfaces",
              **{"Filter.1.Name": "subnet-id", "Filter.1.Value.1": subnet_id})
    assert eni_id in text


def test_attach_network_interface_attaches_it(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    sg_id = security_group(s3_endpoint, "emuplane-test-sg-eni")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    eni_id = network_interface(s3_endpoint, "emuplane-test-eni-attached", subnet_id, sg_id)
    (instance,) = launch(s3_endpoint, **{"SubnetId": subnet_id, "SecurityGroupId.1": sg_id})
    attachment = field(
        ok(s3_endpoint, "AttachNetworkInterface", NetworkInterfaceId=eni_id,
           InstanceId=instance, DeviceIndex="1"),
        "attachmentId",
    )
    described = ok(s3_endpoint, "DescribeNetworkInterfaces", **{"NetworkInterfaceId.1": eni_id})
    assert attachment in described
    assert instance in described
    assert "<status>in-use</status>" in described


def test_detach_network_interface_detaches_it(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    sg_id = security_group(s3_endpoint, "emuplane-test-sg-eni")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    eni_id = network_interface(s3_endpoint, "emuplane-test-eni-detached", subnet_id, sg_id)
    (instance,) = launch(s3_endpoint, **{"SubnetId": subnet_id, "SecurityGroupId.1": sg_id})
    attachment = field(
        ok(s3_endpoint, "AttachNetworkInterface", NetworkInterfaceId=eni_id,
           InstanceId=instance, DeviceIndex="1"),
        "attachmentId",
    )
    ok(s3_endpoint, "DetachNetworkInterface", AttachmentId=attachment)
    described = ok(s3_endpoint, "DescribeNetworkInterfaces", **{"NetworkInterfaceId.1": eni_id})
    assert attachment not in described
    assert "<status>available</status>" in described


# ---------------------------------------------------------------------------
# Elastic addresses
# ---------------------------------------------------------------------------


def test_describe_availability_zones_lists_three(s3_endpoint):
    text = ok(s3_endpoint, "DescribeAvailabilityZones")
    assert len(ids(text, "zoneName")) == 3
    assert "<zoneId>" in text


def test_allocate_address_is_read_back_by_describe(s3_endpoint):
    allocation = elastic_ip(s3_endpoint, "emuplane-test-eip")
    text = ok(s3_endpoint, "DescribeAddresses", **{"AllocationId.1": allocation})
    assert field(text, "allocationId") == allocation
    assert "<publicIp>" in text


def test_release_address_releases_the_address_it_allocated(s3_endpoint):
    created = field(ok(s3_endpoint, "AllocateAddress", Domain="vpc"), "allocationId")
    ok(s3_endpoint, "ReleaseAddress", AllocationId=created)
    text = ok(s3_endpoint, "DescribeAddresses", **{"AllocationId.1": created})
    assert "<addressesSet></addressesSet>" in text


def test_associate_address_associates_it_with_an_instance(s3_endpoint):
    allocation = elastic_ip(s3_endpoint, "emuplane-test-eip-associated")
    (instance,) = launch(s3_endpoint)
    text = ok(s3_endpoint, "AssociateAddress", AllocationId=allocation, InstanceId=instance)
    association = field(text, "associationId")
    described = ok(s3_endpoint, "DescribeAddresses", **{"AllocationId.1": allocation})
    assert association in described
    assert instance in described


def test_disassociate_address_clears_the_association(s3_endpoint):
    allocation = elastic_ip(s3_endpoint, "emuplane-test-eip-disassociated")
    (instance,) = launch(s3_endpoint)
    association = field(
        ok(s3_endpoint, "AssociateAddress", AllocationId=allocation, InstanceId=instance),
        "associationId",
    )
    ok(s3_endpoint, "DisassociateAddress", AssociationId=association)
    described = ok(s3_endpoint, "DescribeAddresses", **{"AllocationId.1": allocation})
    assert association not in described


def test_describe_addresses_lists_the_allocation(s3_endpoint):
    allocation = elastic_ip(s3_endpoint, "emuplane-test-eip")
    text = ok(s3_endpoint, "DescribeAddresses", **{"AllocationId.1": allocation})
    assert allocation in text
    assert "<domain>vpc</domain>" in text


def test_describe_addresses_attribute_answers_the_allocation(s3_endpoint):
    allocation = elastic_ip(s3_endpoint, "emuplane-test-eip")
    text = ok(s3_endpoint, "DescribeAddressesAttribute", **{"AllocationId.1": allocation})
    assert allocation in text
    assert "<ptrRecord>" in text


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_create_tags_adds_a_tag(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    ok(s3_endpoint, "CreateTags", **{
        "ResourceId.1": vpc_id, "Tag.1.Key": "emuplane-test-tag", "Tag.1.Value": "kept"
    })
    text = ok(s3_endpoint, "DescribeTags",
              **{"Filter.1.Name": "resource-id", "Filter.1.Value.1": vpc_id})
    assert "emuplane-test-tag" in text


def test_delete_tags_removes_the_tag(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    ok(s3_endpoint, "CreateTags", **{
        "ResourceId.1": vpc_id, "Tag.1.Key": "emuplane-test-removable", "Tag.1.Value": "gone"
    })
    ok(s3_endpoint, "DeleteTags", **{"ResourceId.1": vpc_id,
                                     "Tag.1.Key": "emuplane-test-removable"})
    text = ok(s3_endpoint, "DescribeTags",
              **{"Filter.1.Name": "resource-id", "Filter.1.Value.1": vpc_id,
                 "Filter.2.Name": "key", "Filter.2.Value.1": "emuplane-test-removable"})
    assert "emuplane-test-removable" not in text


def test_describe_tags_lists_the_tag(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    text = ok(s3_endpoint, "DescribeTags",
              **{"Filter.1.Name": "resource-id", "Filter.1.Value.1": vpc_id})
    assert vpc_id in text
    assert "emuplane-test-vpc" in text


# ---------------------------------------------------------------------------
# NAT gateways
# ---------------------------------------------------------------------------


def test_create_nat_gateway_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    nat_id = nat_gateway(s3_endpoint, "emuplane-test-nat", subnet_id)
    text = ok(s3_endpoint, "DescribeNatGateways", **{"NatGatewayId.1": nat_id})
    assert field(text, "natGatewayId") == nat_id
    assert field(text, "state") == "available"


def test_describe_nat_gateways_lists_the_gateway(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    nat_id = nat_gateway(s3_endpoint, "emuplane-test-nat", subnet_id)
    text = ok(s3_endpoint, "DescribeNatGateways",
              **{"Filter.1.Name": "vpc-id", "Filter.1.Value.1": vpc_id})
    assert nat_id in text
    assert "<natGatewayAddressSet>" in text


def test_delete_nat_gateway_marks_it_deleted(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    subnet_id = subnet(s3_endpoint, "emuplane-test-subnet", vpc_id, "10.99.1.0/24")
    created = field(
        ok(s3_endpoint, "CreateNatGateway", SubnetId=subnet_id,
           AllocationId=elastic_ip(s3_endpoint, "emuplane-test-eip-nat")),
        "natGatewayId",
    )
    text = ok(s3_endpoint, "DeleteNatGateway", NatGatewayId=created)
    assert field(text, "natGatewayId") == created
    described = ok(s3_endpoint, "DescribeNatGateways", **{"NatGatewayId.1": created})
    assert "<state>deleted</state>" in described


# ---------------------------------------------------------------------------
# Network ACLs
# ---------------------------------------------------------------------------


def test_create_network_acl_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    acl_id = network_acl(s3_endpoint, "emuplane-test-acl", vpc_id)
    text = ok(s3_endpoint, "DescribeNetworkAcls", **{"NetworkAclId.1": acl_id})
    assert field(text, "networkAclId") == acl_id
    assert field(text, "vpcId") == vpc_id


def test_describe_network_acls_lists_the_acl(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    acl_id = network_acl(s3_endpoint, "emuplane-test-acl", vpc_id)
    text = ok(s3_endpoint, "DescribeNetworkAcls",
              **{"Filter.1.Name": "vpc-id", "Filter.1.Value.1": vpc_id})
    assert acl_id in text


def test_delete_network_acl_removes_the_acl_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    created = field(ok(s3_endpoint, "CreateNetworkAcl", VpcId=vpc_id), "networkAclId")
    ok(s3_endpoint, "DeleteNetworkAcl", NetworkAclId=created)
    text = ok(s3_endpoint, "DescribeNetworkAcls", **{"NetworkAclId.1": created})
    assert "<networkAclSet></networkAclSet>" in text


def test_create_network_acl_entry_adds_an_entry(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    acl_id = network_acl(s3_endpoint, "emuplane-test-acl", vpc_id)
    ok(s3_endpoint, "CreateNetworkAclEntry", NetworkAclId=acl_id, RuleNumber="200",
       Protocol="6", RuleAction="allow", Egress="false", CidrBlock="192.0.2.0/24")
    text = ok(s3_endpoint, "DescribeNetworkAcls", **{"NetworkAclId.1": acl_id})
    assert "<ruleNumber>200</ruleNumber>" in text
    assert "192.0.2.0/24" in text


def test_delete_network_acl_entry_removes_the_entry(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    acl_id = network_acl(s3_endpoint, "emuplane-test-acl", vpc_id)
    ok(s3_endpoint, "CreateNetworkAclEntry", NetworkAclId=acl_id, RuleNumber="210",
       Protocol="6", RuleAction="allow", Egress="false", CidrBlock="198.51.100.0/24")
    ok(s3_endpoint, "DeleteNetworkAclEntry", NetworkAclId=acl_id, RuleNumber="210",
       Egress="false")
    text = ok(s3_endpoint, "DescribeNetworkAcls", **{"NetworkAclId.1": acl_id})
    assert "<ruleNumber>210</ruleNumber>" not in text


def test_replace_network_acl_entry_changes_the_cidr(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    acl_id = network_acl(s3_endpoint, "emuplane-test-acl", vpc_id)
    ok(s3_endpoint, "CreateNetworkAclEntry", NetworkAclId=acl_id, RuleNumber="220",
       Protocol="6", RuleAction="allow", Egress="false", CidrBlock="203.0.113.0/24")
    ok(s3_endpoint, "ReplaceNetworkAclEntry", NetworkAclId=acl_id, RuleNumber="220",
       Protocol="6", RuleAction="deny", Egress="false", CidrBlock="203.0.114.0/24")
    text = ok(s3_endpoint, "DescribeNetworkAcls", **{"NetworkAclId.1": acl_id})
    assert "203.0.114.0/24" in text
    assert "203.0.113.0/24" not in text


def test_replace_network_acl_association_moves_the_association(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    first = network_acl(s3_endpoint, "emuplane-test-acl", vpc_id)
    second = network_acl(s3_endpoint, "emuplane-test-acl-two", vpc_id)
    # No EC2 call creates an association from outside, so this one is the only source.
    opening = field(
        ok(s3_endpoint, "ReplaceNetworkAclAssociation", AssociationId="aclassoc-00000001",
           NetworkAclId=first),
        "newAssociationId",
    )
    moved = field(
        ok(s3_endpoint, "ReplaceNetworkAclAssociation", AssociationId=opening,
           NetworkAclId=second),
        "newAssociationId",
    )
    described = ok(s3_endpoint, "DescribeNetworkAcls", **{"NetworkAclId.1": second})
    assert moved in described
    assert opening not in described


# ---------------------------------------------------------------------------
# Flow logs
# ---------------------------------------------------------------------------


def test_create_flow_logs_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    log_id = flow_log(s3_endpoint, "emuplane-test-flow-log", vpc_id)
    text = ok(s3_endpoint, "DescribeFlowLogs", **{"FlowLogId.1": log_id})
    assert field(text, "flowLogId") == log_id
    assert field(text, "resourceId") == vpc_id


def test_describe_flow_logs_lists_the_log(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    log_id = flow_log(s3_endpoint, "emuplane-test-flow-log", vpc_id)
    text = ok(s3_endpoint, "DescribeFlowLogs",
              **{"Filter.1.Name": "resource-id", "Filter.1.Value.1": vpc_id})
    assert log_id in text
    assert "<flowLogStatus>ACTIVE</flowLogStatus>" in text


def test_delete_flow_logs_removes_the_log_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    created = re.search(
        r"<flowLogIdSet><item>([^<]+)</item>",
        ok(s3_endpoint, "CreateFlowLogs", **{"ResourceId.1": vpc_id}, ResourceType="VPC",
           TrafficType="ALL", LogDestinationType="cloud-watch-logs",
           LogGroupName="emuplane-test-flow-log-deleted"),
    ).group(1)
    ok(s3_endpoint, "DeleteFlowLogs", **{"FlowLogId.1": created})
    text = ok(s3_endpoint, "DescribeFlowLogs", **{"FlowLogId.1": created})
    assert "<flowLogSet></flowLogSet>" in text


# ---------------------------------------------------------------------------
# VPC peering
# ---------------------------------------------------------------------------


def peer_pair(endpoint) -> tuple[str, str]:
    requester = vpc(endpoint, "emuplane-test-vpc")
    accepter = vpc(endpoint, "emuplane-test-vpc-peer", "10.97.0.0/16")
    return requester, accepter


def test_create_vpc_peering_connection_is_pending(s3_endpoint):
    requester, accepter = peer_pair(s3_endpoint)
    peering = vpc_peering(s3_endpoint, "emuplane-test-peering", requester, accepter)
    text = ok(s3_endpoint, "DescribeVpcPeeringConnections",
              **{"VpcPeeringConnectionId.1": peering})
    assert requester in text
    assert accepter in text


def test_accept_vpc_peering_connection_activates_it(s3_endpoint):
    requester, accepter = peer_pair(s3_endpoint)
    peering = vpc_peering(s3_endpoint, "emuplane-test-peering-accepted", requester, accepter)
    text = ok(s3_endpoint, "AcceptVpcPeeringConnection", VpcPeeringConnectionId=peering)
    assert "<code>active</code>" in text
    described = ok(s3_endpoint, "DescribeVpcPeeringConnections",
                   **{"VpcPeeringConnectionId.1": peering})
    assert "<code>active</code>" in described


def test_describe_vpc_peering_connections_lists_it(s3_endpoint):
    requester, accepter = peer_pair(s3_endpoint)
    peering = vpc_peering(s3_endpoint, "emuplane-test-peering", requester, accepter)
    text = ok(s3_endpoint, "DescribeVpcPeeringConnections")
    assert peering in text
    assert "<vpcPeeringConnectionSet>" in text


def test_delete_vpc_peering_connection_marks_it_deleted(s3_endpoint):
    requester, accepter = peer_pair(s3_endpoint)
    created = field(
        ok(s3_endpoint, "CreateVpcPeeringConnection", VpcId=requester, PeerVpcId=accepter),
        "vpcPeeringConnectionId",
    )
    ok(s3_endpoint, "DeleteVpcPeeringConnection", VpcPeeringConnectionId=created)
    described = ok(s3_endpoint, "DescribeVpcPeeringConnections",
                   **{"VpcPeeringConnectionId.1": created})
    assert "<code>deleted</code>" in described


# ---------------------------------------------------------------------------
# DHCP options
# ---------------------------------------------------------------------------


def test_create_dhcp_options_is_read_back_by_describe(s3_endpoint):
    options_id = dhcp_options(s3_endpoint, "emuplane-test-dhcp")
    text = ok(s3_endpoint, "DescribeDhcpOptions", **{"DhcpOptionsId.1": options_id})
    assert field(text, "dhcpOptionsId") == options_id
    assert "domain-name" in text


def test_associate_dhcp_options_sets_the_vpc_options(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc-dhcp", "10.96.0.0/16")
    options_id = dhcp_options(s3_endpoint, "emuplane-test-dhcp")
    ok(s3_endpoint, "AssociateDhcpOptions", DhcpOptionsId=options_id, VpcId=vpc_id)
    text = ok(s3_endpoint, "DescribeVpcs", **{"VpcId.1": vpc_id})
    assert f"<dhcpOptionsId>{options_id}</dhcpOptionsId>" in text


def test_describe_dhcp_options_lists_the_options(s3_endpoint):
    options_id = dhcp_options(s3_endpoint, "emuplane-test-dhcp")
    text = ok(s3_endpoint, "DescribeDhcpOptions")
    assert options_id in text
    assert "<dhcpOptionsSet>" in text


def test_delete_dhcp_options_removes_the_options_it_created(s3_endpoint):
    created = field(
        ok(s3_endpoint, "CreateDhcpOptions",
           **{"DhcpConfiguration.1.Key": "domain-name",
              "DhcpConfiguration.1.Value.1": "deleted.emuplane.internal"}),
        "dhcpOptionsId",
    )
    ok(s3_endpoint, "DeleteDhcpOptions", DhcpOptionsId=created)
    text = ok(s3_endpoint, "DescribeDhcpOptions", **{"DhcpOptionsId.1": created})
    assert "<dhcpOptionsSet></dhcpOptionsSet>" in text


# ---------------------------------------------------------------------------
# Egress-only internet gateways
# ---------------------------------------------------------------------------


def test_create_egress_only_internet_gateway_is_attached(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    gateway = egress_gateway(s3_endpoint, "emuplane-test-eigw", vpc_id)
    text = ok(s3_endpoint, "DescribeEgressOnlyInternetGateways",
              **{"EgressOnlyInternetGatewayId.1": gateway})
    assert field(text, "egressOnlyInternetGatewayId") == gateway
    assert f"<vpcId>{vpc_id}</vpcId>" in text


def test_describe_egress_only_internet_gateways_lists_it(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    gateway = egress_gateway(s3_endpoint, "emuplane-test-eigw", vpc_id)
    text = ok(s3_endpoint, "DescribeEgressOnlyInternetGateways")
    assert gateway in text
    assert "<attachmentSet>" in text


def test_delete_egress_only_internet_gateway_removes_the_one_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    created = field(ok(s3_endpoint, "CreateEgressOnlyInternetGateway", VpcId=vpc_id),
                    "egressOnlyInternetGatewayId")
    ok(s3_endpoint, "DeleteEgressOnlyInternetGateway", EgressOnlyInternetGatewayId=created)
    text = ok(s3_endpoint, "DescribeEgressOnlyInternetGateways",
              **{"EgressOnlyInternetGatewayId.1": created})
    assert "<egressOnlyInternetGatewaySet></egressOnlyInternetGatewaySet>" in text


# ---------------------------------------------------------------------------
# Prefix lists
# ---------------------------------------------------------------------------


def test_describe_prefix_lists_answers_the_aws_managed_lists(s3_endpoint):
    text = ok(s3_endpoint, "DescribePrefixLists")
    assert "<prefixListSet>" in text
    assert "com.amazonaws." in text


def test_create_managed_prefix_list_is_read_back(s3_endpoint):
    list_id = prefix_list(s3_endpoint, "emuplane-test-prefix-list")
    text = ok(s3_endpoint, "DescribeManagedPrefixLists", **{"PrefixListId.1": list_id})
    assert field(text, "prefixListId") == list_id
    assert field(text, "addressFamily") == "IPv4"
    assert field(text, "maxEntries") == "5"


def test_describe_managed_prefix_lists_lists_the_list(s3_endpoint):
    list_id = prefix_list(s3_endpoint, "emuplane-test-prefix-list")
    text = ok(s3_endpoint, "DescribeManagedPrefixLists",
              **{"Filter.1.Name": "prefix-list-id", "Filter.1.Value.1": list_id})
    assert list_id in text
    assert "emuplane-test-prefix-list" in text


def test_get_managed_prefix_list_entries_answers_the_cidrs(s3_endpoint):
    list_id = prefix_list(s3_endpoint, "emuplane-test-prefix-list")
    text = ok(s3_endpoint, "GetManagedPrefixListEntries", PrefixListId=list_id)
    assert "10.20.0.0/16" in text


def test_modify_managed_prefix_list_adds_an_entry(s3_endpoint):
    list_id = prefix_list(s3_endpoint, "emuplane-test-prefix-list")
    ok(s3_endpoint, "ModifyManagedPrefixList", PrefixListId=list_id,
       **{"AddEntry.1.Cidr": "10.21.0.0/16", "AddEntry.1.Description": "added"})
    text = ok(s3_endpoint, "GetManagedPrefixListEntries", PrefixListId=list_id)
    assert "10.21.0.0/16" in text


def test_delete_managed_prefix_list_removes_the_one_it_created(s3_endpoint):
    created = field(
        ok(s3_endpoint, "CreateManagedPrefixList", PrefixListName="emuplane-test-prefix-deleted",
           MaxEntries="5", AddressFamily="IPv4", **{"Entry.1.Cidr": "10.22.0.0/16"}),
        "prefixListId",
    )
    ok(s3_endpoint, "DeleteManagedPrefixList", PrefixListId=created)
    text = ok(s3_endpoint, "DescribeManagedPrefixLists", **{"PrefixListId.1": created})
    assert "<prefixListSet></prefixListSet>" in text


# ---------------------------------------------------------------------------
# VPN and customer gateways
# ---------------------------------------------------------------------------


def test_create_vpn_gateway_is_read_back(s3_endpoint):
    gateway = vpn_gateway(s3_endpoint, "emuplane-test-vgw")
    text = ok(s3_endpoint, "DescribeVpnGateways", **{"VpnGatewayId.1": gateway})
    assert field(text, "vpnGatewayId") == gateway
    assert field(text, "type") == "ipsec.1"


def test_describe_vpn_gateways_lists_the_gateway(s3_endpoint):
    gateway = vpn_gateway(s3_endpoint, "emuplane-test-vgw")
    text = ok(s3_endpoint, "DescribeVpnGateways")
    assert gateway in text
    assert "<vpnGatewaySet>" in text


def test_attach_vpn_gateway_attaches_it(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    gateway = vpn_gateway(s3_endpoint, "emuplane-test-vgw-attached")
    text = ok(s3_endpoint, "AttachVpnGateway", VpnGatewayId=gateway, VpcId=vpc_id)
    assert f"<vpcId>{vpc_id}</vpcId>" in text
    described = ok(s3_endpoint, "DescribeVpnGateways",
                   **{"Filter.1.Name": "attachment.vpc-id", "Filter.1.Value.1": vpc_id})
    assert gateway in described


def test_detach_vpn_gateway_detaches_it(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    gateway = vpn_gateway(s3_endpoint, "emuplane-test-vgw-attached")
    ok(s3_endpoint, "AttachVpnGateway", VpnGatewayId=gateway, VpcId=vpc_id)
    ok(s3_endpoint, "DetachVpnGateway", VpnGatewayId=gateway, VpcId=vpc_id)
    described = ok(s3_endpoint, "DescribeVpnGateways", **{"VpnGatewayId.1": gateway})
    assert f"<vpcId>{vpc_id}</vpcId>" not in described


def test_delete_vpn_gateway_removes_the_one_it_created(s3_endpoint):
    created = field(ok(s3_endpoint, "CreateVpnGateway", Type="ipsec.1"), "vpnGatewayId")
    ok(s3_endpoint, "DeleteVpnGateway", VpnGatewayId=created)
    text = ok(s3_endpoint, "DescribeVpnGateways", **{"VpnGatewayId.1": created})
    assert "<vpnGatewaySet></vpnGatewaySet>" in text


def test_enable_vgw_route_propagation_records_the_gateway(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    gateway = vpn_gateway(s3_endpoint, "emuplane-test-vgw")
    ok(s3_endpoint, "EnableVgwRoutePropagation", RouteTableId=table_id, GatewayId=gateway)
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    assert f"<gatewayId>{gateway}</gatewayId>" in described


def test_disable_vgw_route_propagation_removes_the_gateway(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    gateway = vpn_gateway(s3_endpoint, "emuplane-test-vgw")
    ok(s3_endpoint, "EnableVgwRoutePropagation", RouteTableId=table_id, GatewayId=gateway)
    ok(s3_endpoint, "DisableVgwRoutePropagation", RouteTableId=table_id, GatewayId=gateway)
    described = ok(s3_endpoint, "DescribeRouteTables", **{"RouteTableId.1": table_id})
    assert f"<gatewayId>{gateway}</gatewayId>" not in described


def test_create_customer_gateway_is_read_back(s3_endpoint):
    gateway = customer_gateway(s3_endpoint, "emuplane-test-cgw")
    text = ok(s3_endpoint, "DescribeCustomerGateways", **{"CustomerGatewayId.1": gateway})
    assert field(text, "customerGatewayId") == gateway
    assert field(text, "ipAddress") == "203.0.113.9"


def test_describe_customer_gateways_lists_the_gateway(s3_endpoint):
    gateway = customer_gateway(s3_endpoint, "emuplane-test-cgw")
    text = ok(s3_endpoint, "DescribeCustomerGateways")
    assert gateway in text
    assert "<customerGatewaySet>" in text


def test_delete_customer_gateway_removes_the_one_it_created(s3_endpoint):
    created = field(
        ok(s3_endpoint, "CreateCustomerGateway", Type="ipsec.1", BgpAsn="65000",
           IpAddress="198.51.100.10"),
        "customerGatewayId",
    )
    ok(s3_endpoint, "DeleteCustomerGateway", CustomerGatewayId=created)
    text = ok(s3_endpoint, "DescribeCustomerGateways", **{"CustomerGatewayId.1": created})
    assert "<customerGatewaySet></customerGatewaySet>" in text


# ---------------------------------------------------------------------------
# Launch templates and fleets
# ---------------------------------------------------------------------------


def test_create_launch_template_is_read_back_by_describe(s3_endpoint):
    name = "emuplane-test-launch-template"
    template_id = launch_template(s3_endpoint, name)
    text = ok(s3_endpoint, "DescribeLaunchTemplates", **{"LaunchTemplateName.1": name})
    assert field(text, "launchTemplateId") == template_id
    assert field(text, "launchTemplateName") == name


def test_describe_launch_templates_lists_the_template(s3_endpoint):
    name = "emuplane-test-launch-template"
    template_id = launch_template(s3_endpoint, name)
    text = ok(s3_endpoint, "DescribeLaunchTemplates")
    assert template_id in text
    assert "<launchTemplates>" in text


def test_create_launch_template_version_adds_a_version(s3_endpoint):
    template_id = launch_template(s3_endpoint, "emuplane-test-launch-template-versioned")
    text = ok(s3_endpoint, "CreateLaunchTemplateVersion", LaunchTemplateId=template_id,
              VersionDescription="second",
              **{"LaunchTemplateData.InstanceType": "t3.small"})
    assert field(text, "launchTemplateId") == template_id
    assert int(field(text, "versionNumber")) >= 2
    assert field(text, "instanceType") == "t3.small"


def test_describe_launch_template_versions_lists_the_versions(s3_endpoint):
    template_id = launch_template(s3_endpoint, "emuplane-test-launch-template-versioned")
    ok(s3_endpoint, "CreateLaunchTemplateVersion", LaunchTemplateId=template_id,
       **{"LaunchTemplateData.InstanceType": "t3.small"})
    text = ok(s3_endpoint, "DescribeLaunchTemplateVersions", LaunchTemplateId=template_id)
    assert template_id in text
    assert "<versionNumber>1</versionNumber>" in text


def test_modify_launch_template_sets_the_default_version(s3_endpoint):
    template_id = launch_template(s3_endpoint, "emuplane-test-launch-template-versioned")
    created = ok(s3_endpoint, "CreateLaunchTemplateVersion", LaunchTemplateId=template_id,
                 **{"LaunchTemplateData.InstanceType": "t3.small"})
    version = field(created, "versionNumber")
    text = ok(s3_endpoint, "ModifyLaunchTemplate", LaunchTemplateId=template_id,
              SetDefaultVersion=version)
    assert field(text, "defaultVersionNumber") == version


def test_delete_launch_template_removes_the_one_it_created(s3_endpoint):
    name = "emuplane-test-launch-template-deleted"
    template_id = launch_template(s3_endpoint, name)
    ok(s3_endpoint, "DeleteLaunchTemplate", LaunchTemplateId=template_id)
    text = ok(s3_endpoint, "DescribeLaunchTemplates")
    assert template_id not in text


def test_create_fleet_launches_an_instance(s3_endpoint):
    template_id = launch_template(s3_endpoint, "emuplane-test-launch-template")
    text = ok(
        s3_endpoint,
        "CreateFleet",
        Type="instant",
        **{
            "TargetCapacitySpecification.TotalTargetCapacity": "1",
            "TargetCapacitySpecification.DefaultTargetCapacityType": "on-demand",
            "LaunchTemplateConfigs.1.LaunchTemplateSpecification.LaunchTemplateId": template_id,
            "LaunchTemplateConfigs.1.LaunchTemplateSpecification.Version": "$Default",
        },
    )
    assert field(text, "fleetId").startswith("fleet-")
    assert re.search(r"<instanceIds><item>i-[0-9a-f]+</item>", text), text[:400]


def test_describe_fleets_lists_the_fleet(s3_endpoint):
    template_id = launch_template(s3_endpoint, "emuplane-test-launch-template")
    fleet = field(
        ok(
            s3_endpoint,
            "CreateFleet",
            Type="instant",
            **{
                "TargetCapacitySpecification.TotalTargetCapacity": "1",
                "LaunchTemplateConfigs.1.LaunchTemplateSpecification.LaunchTemplateId": template_id,
            },
        ),
        "fleetId",
    )
    text = ok(s3_endpoint, "DescribeFleets", **{"FleetId.1": fleet})
    assert fleet in text
    assert "<fleetState>active</fleetState>" in text


# ---------------------------------------------------------------------------
# VPC endpoints
# ---------------------------------------------------------------------------


def test_create_vpc_endpoint_is_read_back_by_describe(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    endpoint_id = vpc_endpoint(s3_endpoint, "emuplane-test-vpce", vpc_id, table_id)
    text = ok(s3_endpoint, "DescribeVpcEndpoints", **{"VpcEndpointId.1": endpoint_id})
    assert field(text, "vpcEndpointId") == endpoint_id
    assert field(text, "vpcId") == vpc_id


def test_describe_vpc_endpoints_lists_the_endpoint(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    endpoint_id = vpc_endpoint(s3_endpoint, "emuplane-test-vpce", vpc_id, table_id)
    text = ok(s3_endpoint, "DescribeVpcEndpoints")
    assert endpoint_id in text
    assert "<vpcEndpointSet>" in text


def test_modify_vpc_endpoint_sets_the_policy(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    table_id = route_table(s3_endpoint, "emuplane-test-rtb", vpc_id)
    endpoint_id = vpc_endpoint(s3_endpoint, "emuplane-test-vpce", vpc_id, table_id)
    ok(s3_endpoint, "ModifyVpcEndpoint", VpcEndpointId=endpoint_id,
       PolicyDocument="allow")
    text = ok(s3_endpoint, "DescribeVpcEndpoints", **{"VpcEndpointId.1": endpoint_id})
    assert "<policyDocument>allow</policyDocument>" in text


def test_delete_vpc_endpoints_removes_the_one_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    created = field(
        ok(s3_endpoint, "CreateVpcEndpoint", VpcId=vpc_id,
           ServiceName=f"com.amazonaws.{REGION}.dynamodb", VpcEndpointType="Gateway"),
        "vpcEndpointId",
    )
    ok(s3_endpoint, "DeleteVpcEndpoints", **{"VpcEndpointId.1": created})
    text = ok(s3_endpoint, "DescribeVpcEndpoints", **{"VpcEndpointId.1": created})
    assert "<vpcEndpointSet></vpcEndpointSet>" in text


# ---------------------------------------------------------------------------
# Verified Access
# ---------------------------------------------------------------------------


def test_create_verified_access_instance_is_read_back(s3_endpoint):
    instance_id = va_instance(s3_endpoint)
    text = ok(s3_endpoint, "DescribeVerifiedAccessInstances",
              **{"VerifiedAccessInstanceId.1": instance_id})
    assert field(text, "verifiedAccessInstanceId") == instance_id


def test_describe_verified_access_instances_lists_the_instance(s3_endpoint):
    instance_id = va_instance(s3_endpoint)
    text = ok(s3_endpoint, "DescribeVerifiedAccessInstances")
    assert instance_id in text
    assert "<verifiedAccessInstanceSet>" in text


def test_modify_verified_access_instance_changes_the_description(s3_endpoint):
    instance_id = va_instance(s3_endpoint)
    text = ok(s3_endpoint, "ModifyVerifiedAccessInstance", VerifiedAccessInstanceId=instance_id,
              Description="changed by the test")
    assert field(text, "description") == "changed by the test"


def test_delete_verified_access_instance_removes_the_one_it_created(s3_endpoint):
    created = find_or_create(
        s3_endpoint, "emuplane-test-va-instance-deleted", "vai-",
        "CreateVerifiedAccessInstance", "verifiedAccessInstanceId",
        **tagged("verified-access-instance", "emuplane-test-va-instance-deleted"),
    )
    ok(s3_endpoint, "DeleteVerifiedAccessInstance", VerifiedAccessInstanceId=created)
    status, text = call(s3_endpoint, "DescribeVerifiedAccessInstances",
                        **{"VerifiedAccessInstanceId.1": created})
    assert status == 400
    assert "InvalidVerifiedAccessInstanceId.NotFound" in text


def test_create_verified_access_trust_provider_is_read_back(s3_endpoint):
    provider_id = va_user_provider(s3_endpoint)
    text = ok(s3_endpoint, "DescribeVerifiedAccessTrustProviders",
              **{"VerifiedAccessTrustProviderId.1": provider_id})
    assert field(text, "verifiedAccessTrustProviderId") == provider_id
    assert field(text, "trustProviderType") == "user"
    assert field(text, "clientSecret") == "REDACTED"


def test_describe_verified_access_trust_providers_lists_the_provider(s3_endpoint):
    provider_id = va_user_provider(s3_endpoint)
    text = ok(s3_endpoint, "DescribeVerifiedAccessTrustProviders")
    assert provider_id in text
    assert "<verifiedAccessTrustProviderSet>" in text


def test_modify_verified_access_trust_provider_changes_the_description(s3_endpoint):
    provider_id = va_user_provider(s3_endpoint)
    text = ok(s3_endpoint, "ModifyVerifiedAccessTrustProvider",
              VerifiedAccessTrustProviderId=provider_id, Description="changed by the test")
    assert field(text, "description") == "changed by the test"


def test_delete_verified_access_trust_provider_removes_the_one_it_created(s3_endpoint):
    created = va_device_provider(s3_endpoint, "emuplane-test-va-provider-deleted")
    ok(s3_endpoint, "DeleteVerifiedAccessTrustProvider",
       VerifiedAccessTrustProviderId=created)
    status, text = call(s3_endpoint, "DescribeVerifiedAccessTrustProviders",
                        **{"VerifiedAccessTrustProviderId.1": created})
    assert status == 400
    assert "InvalidVerifiedAccessTrustProviderId.NotFound" in text


def test_attach_verified_access_trust_provider_attaches_it(s3_endpoint):
    instance_id = va_instance(s3_endpoint, "emuplane-test-va-instance-attach")
    provider_id = va_device_provider(s3_endpoint, "emuplane-test-va-provider-attach")
    if va_attached(s3_endpoint, instance_id, provider_id):
        # A previous sweep left it attached; the provider attaches once.
        ok(s3_endpoint, "DetachVerifiedAccessTrustProvider",
           VerifiedAccessInstanceId=instance_id, VerifiedAccessTrustProviderId=provider_id)
    text = ok(s3_endpoint, "AttachVerifiedAccessTrustProvider",
              VerifiedAccessInstanceId=instance_id, VerifiedAccessTrustProviderId=provider_id)
    assert "deviceOptions" in text
    assert va_attached(s3_endpoint, instance_id, provider_id)


def test_detach_verified_access_trust_provider_detaches_it(s3_endpoint):
    instance_id = va_instance(s3_endpoint, "emuplane-test-va-instance-attach")
    provider_id = va_device_provider(s3_endpoint, "emuplane-test-va-provider-attach")
    if not va_attached(s3_endpoint, instance_id, provider_id):
        ok(s3_endpoint, "AttachVerifiedAccessTrustProvider",
           VerifiedAccessInstanceId=instance_id, VerifiedAccessTrustProviderId=provider_id)
    ok(s3_endpoint, "DetachVerifiedAccessTrustProvider",
       VerifiedAccessInstanceId=instance_id, VerifiedAccessTrustProviderId=provider_id)
    assert not va_attached(s3_endpoint, instance_id, provider_id)


def test_modify_verified_access_instance_logging_configuration_enables_s3(s3_endpoint):
    instance_id = va_instance(s3_endpoint)
    logs = bucket(s3_endpoint, "emuplane-verified-access-logs")
    text = ok(
        s3_endpoint,
        "ModifyVerifiedAccessInstanceLoggingConfiguration",
        VerifiedAccessInstanceId=instance_id,
        **{
            "AccessLogs.S3.Enabled": "true",
            "AccessLogs.S3.BucketName": logs,
            "AccessLogs.LogVersion": "ocsf-1.0.0-rc.2",
        },
    )
    assert field(text, "verifiedAccessInstanceId") == instance_id
    assert f"<bucketName>{logs}</bucketName>" in text


def test_describe_verified_access_instance_logging_configurations_lists_it(s3_endpoint):
    instance_id = va_instance(s3_endpoint)
    text = ok(s3_endpoint, "DescribeVerifiedAccessInstanceLoggingConfigurations",
              **{"VerifiedAccessInstanceId.1": instance_id})
    assert instance_id in text
    assert "<loggingConfigurationSet>" in text


def test_create_verified_access_group_is_read_back(s3_endpoint):
    group_id = va_group(s3_endpoint)
    text = ok(s3_endpoint, "DescribeVerifiedAccessGroups",
              **{"VerifiedAccessGroupId.1": group_id})
    assert field(text, "verifiedAccessGroupId") == group_id
    assert "<verifiedAccessGroupArn>" in text


def test_describe_verified_access_groups_lists_the_group(s3_endpoint):
    group_id = va_group(s3_endpoint)
    text = ok(s3_endpoint, "DescribeVerifiedAccessGroups")
    assert group_id in text
    assert "<verifiedAccessGroupSet>" in text


def test_modify_verified_access_group_changes_the_description(s3_endpoint):
    group_id = va_group(s3_endpoint)
    text = ok(s3_endpoint, "ModifyVerifiedAccessGroup", VerifiedAccessGroupId=group_id,
              Description="changed by the test")
    assert field(text, "description") == "changed by the test"


def test_delete_verified_access_group_removes_the_one_it_created(s3_endpoint):
    created = va_group(s3_endpoint, "emuplane-test-va-group-deleted")
    ok(s3_endpoint, "DeleteVerifiedAccessGroup", VerifiedAccessGroupId=created)
    status, text = call(s3_endpoint, "DescribeVerifiedAccessGroups",
                        **{"VerifiedAccessGroupId.1": created})
    assert status == 400
    assert "InvalidVerifiedAccessGroupId.NotFound" in text


def test_modify_verified_access_group_policy_sets_the_document(s3_endpoint):
    group_id = va_group(s3_endpoint)
    text = ok(s3_endpoint, "ModifyVerifiedAccessGroupPolicy", VerifiedAccessGroupId=group_id,
              PolicyEnabled="true",
              PolicyDocument="permit(principal, action, resource);")
    assert field(text, "policyEnabled") == "true"
    assert "permit(principal" in text


def test_get_verified_access_group_policy_answers_the_document(s3_endpoint):
    group_id = va_group(s3_endpoint)
    ok(s3_endpoint, "ModifyVerifiedAccessGroupPolicy", VerifiedAccessGroupId=group_id,
       PolicyEnabled="true", PolicyDocument="permit(principal, action, resource);")
    text = ok(s3_endpoint, "GetVerifiedAccessGroupPolicy", VerifiedAccessGroupId=group_id)
    assert field(text, "policyEnabled") == "true"
    assert field(text, "policyDocument") == "permit(principal, action, resource);"


def test_create_verified_access_endpoint_is_read_back(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    endpoint = va_endpoint(s3_endpoint, "emuplane-test-va-endpoint", "va.emuplane.test",
                           vpc_id, "emuplane-test-sg-va")
    text = ok(s3_endpoint, "DescribeVerifiedAccessEndpoints",
              **{"VerifiedAccessEndpointId.1": endpoint})
    assert field(text, "verifiedAccessEndpointId") == endpoint
    assert field(text, "applicationDomain") == "va.emuplane.test"


def test_describe_verified_access_endpoints_lists_the_endpoint(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    endpoint = va_endpoint(s3_endpoint, "emuplane-test-va-endpoint", "va.emuplane.test",
                           vpc_id, "emuplane-test-sg-va")
    text = ok(s3_endpoint, "DescribeVerifiedAccessEndpoints")
    assert endpoint in text
    assert "<verifiedAccessEndpointSet>" in text


def test_modify_verified_access_endpoint_changes_the_description(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    endpoint = va_endpoint(s3_endpoint, "emuplane-test-va-endpoint", "va.emuplane.test",
                           vpc_id, "emuplane-test-sg-va")
    text = ok(s3_endpoint, "ModifyVerifiedAccessEndpoint", VerifiedAccessEndpointId=endpoint,
              Description="changed by the test")
    assert field(text, "description") == "changed by the test"


def test_delete_verified_access_endpoint_removes_the_one_it_created(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    created = field(
        ok(s3_endpoint, "CreateVerifiedAccessEndpoint",
           **va_endpoint_params(s3_endpoint, "emuplane-test-va-endpoint-deleted",
                                "va-delete.emuplane.test", vpc_id, "emuplane-test-sg-va")),
        "verifiedAccessEndpointId",
    )
    text = ok(s3_endpoint, "DeleteVerifiedAccessEndpoint", VerifiedAccessEndpointId=created)
    assert "<status><code>deleting</code></status>" in text
    # A deleted endpoint is listed once more, then dropped from the store.
    ok(s3_endpoint, "DescribeVerifiedAccessEndpoints")
    ok(s3_endpoint, "DescribeVerifiedAccessEndpoints")


def test_modify_verified_access_endpoint_policy_sets_the_document(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    endpoint = va_endpoint(s3_endpoint, "emuplane-test-va-endpoint", "va.emuplane.test",
                           vpc_id, "emuplane-test-sg-va")
    text = ok(s3_endpoint, "ModifyVerifiedAccessEndpointPolicy",
              VerifiedAccessEndpointId=endpoint, PolicyEnabled="true",
              PolicyDocument="permit(principal, action, resource);")
    assert field(text, "policyEnabled") == "true"


def test_get_verified_access_endpoint_policy_answers_the_document(s3_endpoint):
    vpc_id = vpc(s3_endpoint, "emuplane-test-vpc")
    endpoint = va_endpoint(s3_endpoint, "emuplane-test-va-endpoint", "va.emuplane.test",
                           vpc_id, "emuplane-test-sg-va")
    ok(s3_endpoint, "ModifyVerifiedAccessEndpointPolicy", VerifiedAccessEndpointId=endpoint,
       PolicyEnabled="true", PolicyDocument="permit(principal, action, resource);")
    text = ok(s3_endpoint, "GetVerifiedAccessEndpointPolicy",
              VerifiedAccessEndpointId=endpoint)
    assert field(text, "policyEnabled") == "true"
    assert field(text, "policyDocument") == "permit(principal, action, resource);"


# --- Transit Gateway and secondary VPC CIDR blocks (1.5.44) -----------------


def transit_gateway(endpoint) -> str:
    """A transit gateway of this test's own: it has no name to look up."""
    return field(ok(endpoint, "CreateTransitGateway", Description="ops transit gateway"),
                 "transitGatewayId")


def transit_gateway_route_table(endpoint, tgw_id: str) -> str:
    return field(
        ok(endpoint, "CreateTransitGatewayRouteTable", TransitGatewayId=tgw_id),
        "transitGatewayRouteTableId",
    )


def transit_gateway_attachment(endpoint, tgw_id: str) -> str:
    vpc_id = vpc(endpoint, "ops-tgw-vpc", "10.97.0.0/16")
    subnet_id = subnet(endpoint, "ops-tgw-subnet", vpc_id, "10.97.1.0/24")
    return field(
        ok(
            endpoint,
            "CreateTransitGatewayVpcAttachment",
            TransitGatewayId=tgw_id,
            VpcId=vpc_id,
            **{"SubnetIds.1": subnet_id},
        ),
        "transitGatewayAttachmentId",
    )


def transit_gateway_route(endpoint, rtb_id: str, attachment: str, cidr: str) -> str:
    return ok(
        endpoint,
        "CreateTransitGatewayRoute",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
        DestinationCidrBlock=cidr,
    )


def test_create_transit_gateway_answers_it(s3_endpoint):
    requires("ec2", "CreateTransitGateway")
    tgw_id = transit_gateway(s3_endpoint)
    assert tgw_id.startswith("tgw-")
    assert tgw_id in ok(
        s3_endpoint, "DescribeTransitGateways", **{"TransitGatewayIds.1": tgw_id}
    )


def test_modify_transit_gateway_updates_the_description(s3_endpoint):
    requires("ec2", "ModifyTransitGateway")
    tgw_id = transit_gateway(s3_endpoint)
    text = ok(
        s3_endpoint,
        "ModifyTransitGateway",
        TransitGatewayId=tgw_id,
        Description="ops modified",
    )
    assert tgw_id in text
    described = ok(
        s3_endpoint, "DescribeTransitGateways", **{"TransitGatewayIds.1": tgw_id}
    )
    assert "ops modified" in described


def test_delete_transit_gateway_marks_it_deleted(s3_endpoint):
    requires("ec2", "DeleteTransitGateway")
    tgw_id = transit_gateway(s3_endpoint)
    ok(s3_endpoint, "DeleteTransitGateway", TransitGatewayId=tgw_id)
    assert "deleted" in ok(
        s3_endpoint, "DescribeTransitGateways", **{"TransitGatewayIds.1": tgw_id}
    )


def test_create_transit_gateway_route_table_answers_it(s3_endpoint):
    requires("ec2", "CreateTransitGatewayRouteTable")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    assert rtb_id.startswith("tgw-rtb-")
    assert rtb_id in ok(
        s3_endpoint,
        "DescribeTransitGatewayRouteTables",
        **{"TransitGatewayRouteTableIds.1": rtb_id},
    )


def test_delete_transit_gateway_route_table_marks_it_deleted(s3_endpoint):
    requires("ec2", "DeleteTransitGatewayRouteTable")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    ok(s3_endpoint, "DeleteTransitGatewayRouteTable", TransitGatewayRouteTableId=rtb_id)
    assert "deleted" in ok(
        s3_endpoint,
        "DescribeTransitGatewayRouteTables",
        **{"TransitGatewayRouteTableIds.1": rtb_id},
    )


def test_create_transit_gateway_vpc_attachment_answers_it(s3_endpoint):
    requires("ec2", "CreateTransitGatewayVpcAttachment")
    tgw_id = transit_gateway(s3_endpoint)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    assert attachment.startswith("tgw-attach-")
    assert attachment in ok(
        s3_endpoint,
        "DescribeTransitGatewayVpcAttachments",
        **{"TransitGatewayAttachmentIds.1": attachment},
    )


def test_describe_transit_gateway_attachments_lists_it(s3_endpoint):
    requires("ec2", "DescribeTransitGatewayAttachments")
    tgw_id = transit_gateway(s3_endpoint)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    assert attachment in ok(s3_endpoint, "DescribeTransitGatewayAttachments")


def test_modify_transit_gateway_vpc_attachment_answers_it(s3_endpoint):
    requires("ec2", "ModifyTransitGatewayVpcAttachment")
    tgw_id = transit_gateway(s3_endpoint)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    text = ok(
        s3_endpoint,
        "ModifyTransitGatewayVpcAttachment",
        TransitGatewayAttachmentId=attachment,
    )
    assert attachment in text


def test_delete_transit_gateway_vpc_attachment_marks_it_deleted(s3_endpoint):
    requires("ec2", "DeleteTransitGatewayVpcAttachment")
    tgw_id = transit_gateway(s3_endpoint)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    ok(
        s3_endpoint,
        "DeleteTransitGatewayVpcAttachment",
        TransitGatewayAttachmentId=attachment,
    )
    assert "deleted" in ok(
        s3_endpoint,
        "DescribeTransitGatewayVpcAttachments",
        **{"TransitGatewayAttachmentIds.1": attachment},
    )


def test_create_transit_gateway_route_answers_it(s3_endpoint):
    requires("ec2", "CreateTransitGatewayRoute")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    text = transit_gateway_route(s3_endpoint, rtb_id, attachment, "10.50.0.0/16")
    assert field(text, "destinationCidrBlock") == "10.50.0.0/16"


def test_search_transit_gateway_routes_reads_it(s3_endpoint):
    requires("ec2", "SearchTransitGatewayRoutes")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    transit_gateway_route(s3_endpoint, rtb_id, attachment, "10.51.0.0/16")
    text = ok(
        s3_endpoint,
        "SearchTransitGatewayRoutes",
        TransitGatewayRouteTableId=rtb_id,
        **{
            "Filter.1.Name": "route-search.exact-match",
            "Filter.1.Value.1": "10.51.0.0/16",
        },
    )
    assert "10.51.0.0/16" in text


def test_delete_transit_gateway_route_removes_it(s3_endpoint):
    requires("ec2", "DeleteTransitGatewayRoute")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    transit_gateway_route(s3_endpoint, rtb_id, attachment, "10.52.0.0/16")
    ok(
        s3_endpoint,
        "DeleteTransitGatewayRoute",
        TransitGatewayRouteTableId=rtb_id,
        DestinationCidrBlock="10.52.0.0/16",
    )
    text = ok(
        s3_endpoint,
        "SearchTransitGatewayRoutes",
        TransitGatewayRouteTableId=rtb_id,
        **{
            "Filter.1.Name": "route-search.exact-match",
            "Filter.1.Value.1": "10.52.0.0/16",
        },
    )
    assert "10.52.0.0/16" not in text


def test_associate_transit_gateway_route_table_answers_it(s3_endpoint):
    requires("ec2", "AssociateTransitGatewayRouteTable")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    text = ok(
        s3_endpoint,
        "AssociateTransitGatewayRouteTable",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    assert attachment in text


def test_disassociate_transit_gateway_route_table_answers_it(s3_endpoint):
    requires("ec2", "DisassociateTransitGatewayRouteTable")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    ok(
        s3_endpoint,
        "AssociateTransitGatewayRouteTable",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    text = ok(
        s3_endpoint,
        "DisassociateTransitGatewayRouteTable",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    assert attachment in text


def test_enable_transit_gateway_route_table_propagation_answers_it(s3_endpoint):
    requires("ec2", "EnableTransitGatewayRouteTablePropagation")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    text = ok(
        s3_endpoint,
        "EnableTransitGatewayRouteTablePropagation",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    assert attachment in text


def test_disable_transit_gateway_route_table_propagation_answers_it(s3_endpoint):
    requires("ec2", "DisableTransitGatewayRouteTablePropagation")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    ok(
        s3_endpoint,
        "EnableTransitGatewayRouteTablePropagation",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    text = ok(
        s3_endpoint,
        "DisableTransitGatewayRouteTablePropagation",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    assert attachment in text


def test_get_transit_gateway_route_table_associations_lists_it(s3_endpoint):
    requires("ec2", "GetTransitGatewayRouteTableAssociations")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    ok(
        s3_endpoint,
        "AssociateTransitGatewayRouteTable",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    text = ok(
        s3_endpoint,
        "GetTransitGatewayRouteTableAssociations",
        TransitGatewayRouteTableId=rtb_id,
    )
    assert attachment in text


def test_get_transit_gateway_route_table_propagations_lists_it(s3_endpoint):
    requires("ec2", "GetTransitGatewayRouteTablePropagations")
    tgw_id = transit_gateway(s3_endpoint)
    rtb_id = transit_gateway_route_table(s3_endpoint, tgw_id)
    attachment = transit_gateway_attachment(s3_endpoint, tgw_id)
    ok(
        s3_endpoint,
        "EnableTransitGatewayRouteTablePropagation",
        TransitGatewayRouteTableId=rtb_id,
        TransitGatewayAttachmentId=attachment,
    )
    text = ok(
        s3_endpoint,
        "GetTransitGatewayRouteTablePropagations",
        TransitGatewayRouteTableId=rtb_id,
    )
    assert attachment in text


def test_associate_vpc_cidr_block_answers_the_association(s3_endpoint):
    requires("ec2", "AssociateVpcCidrBlock")
    vpc_id = vpc(s3_endpoint, "ops-cidr-vpc", "10.120.0.0/16")
    text = ok(
        s3_endpoint,
        "AssociateVpcCidrBlock",
        VpcId=vpc_id,
        CidrBlock="10.121.0.0/24",
    )
    assert field(text, "associationId").startswith("vpc-cidr-assoc-")


def test_disassociate_vpc_cidr_block_removes_it(s3_endpoint):
    requires("ec2", "DisassociateVpcCidrBlock")
    vpc_id = vpc(s3_endpoint, "ops-cidr-vpc-2", "10.122.0.0/16")
    association = field(
        ok(
            s3_endpoint,
            "AssociateVpcCidrBlock",
            VpcId=vpc_id,
            CidrBlock="10.123.0.0/24",
        ),
        "associationId",
    )
    ok(s3_endpoint, "DisassociateVpcCidrBlock", AssociationId=association)
    text = ok(s3_endpoint, "DescribeVpcs", **{"VpcId.1": vpc_id})
    assert "disassociated" in text
