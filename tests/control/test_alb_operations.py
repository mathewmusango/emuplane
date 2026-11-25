"""Elastic Load Balancing v2 (ALB) on the wire: all 32 advertised operations.

Query/XML under the `elasticloadbalancing` credential scope. A load balancer, a
target group, a listener and a rule are keyed by their ARNs, so a stable pair
carries the read/modify/tag tests while a create or delete test makes its own.
Nothing is provisioned beyond the records.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2015-12-01"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
LB = "ops-alb"
TG = "ops-tg"
CERT_DOMAIN = "ops-alb.example.com"


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "elasticloadbalancing", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def ensure_lb(endpoint, name: str = LB) -> str:
    status, text = call(
        endpoint,
        "CreateLoadBalancer",
        Name=name,
        Scheme="internet-facing",
        Type="application",
        **{"Subnets.member.1": "subnet-ops1", "Subnets.member.2": "subnet-ops2"},
    )
    assert status == 200 or "DuplicateLoadBalancerName" in text, text[:300]
    return field(ok(endpoint, "DescribeLoadBalancers", **{"Names.member.1": name}), "LoadBalancerArn")


def ensure_tg(endpoint, name: str = TG) -> str:
    status, text = call(endpoint, "CreateTargetGroup", Name=name, Protocol="HTTP", Port="80", VpcId="vpc-ops")
    assert status == 200 or "DuplicateTargetGroupName" in text, text[:300]
    return field(ok(endpoint, "DescribeTargetGroups", **{"Names.member.1": name}), "TargetGroupArn")


def ensure_listener(endpoint, lb_arn: str) -> str:
    existing = ok(endpoint, "DescribeListeners", LoadBalancerArn=lb_arn)
    match = re.search(r"<ListenerArn>([^<]+)</ListenerArn>", existing)
    if match:
        return match.group(1)
    tg = ensure_tg(endpoint)
    text = ok(
        endpoint,
        "CreateListener",
        LoadBalancerArn=lb_arn,
        Protocol="HTTP",
        Port="80",
        **{"DefaultActions.member.1.Type": "forward", "DefaultActions.member.1.TargetGroupArn": tg},
    )
    return field(text, "ListenerArn")


def new_lb(endpoint) -> str:
    name = f"ops-alb-{time.time_ns() % 100000000}"
    ok(endpoint, "CreateLoadBalancer", Name=name, Scheme="internet-facing", Type="application")
    return field(ok(endpoint, "DescribeLoadBalancers", **{"Names.member.1": name}), "LoadBalancerArn")


def new_rule(endpoint, listener_arn: str) -> str:
    tg = ensure_tg(endpoint)
    text = ok(
        endpoint,
        "CreateRule",
        ListenerArn=listener_arn,
        Priority=str(int(time.time_ns() % 40000) + 1),
        **{
            "Conditions.member.1.Field": "path-pattern",
            "Conditions.member.1.Values.member.1": "/ops",
            "Actions.member.1.Type": "forward",
            "Actions.member.1.TargetGroupArn": tg,
        },
    )
    return field(text, "RuleArn")


def ensure_certificate(endpoint) -> str:
    target = {"X-Amz-Target": "CertificateManager.ListCertificates", "Content-Type": "application/x-amz-json-1.1"}
    status, text = signed.request(endpoint, "acm", ACCOUNT, REGION, "POST", "/", "{}", target)
    assert status == 200, text[:300]
    for cert in json.loads(text or "{}").get("CertificateSummaryList", []):
        if cert.get("DomainName") == CERT_DOMAIN:
            return cert["CertificateArn"]
    target["X-Amz-Target"] = "CertificateManager.RequestCertificate"
    status, text = signed.request(endpoint, "acm", ACCOUNT, REGION, "POST", "/", json.dumps({"DomainName": CERT_DOMAIN}), target)
    assert status == 200, text[:300]
    return json.loads(text)["CertificateArn"]


def context(endpoint):
    lb = ensure_lb(endpoint)
    return lb, ensure_tg(endpoint), ensure_listener(endpoint, lb)


# ---------------------------------------------------------------------------
# Load balancers
# ---------------------------------------------------------------------------


def test_create_load_balancer_is_read_back(endpoint):
    name = f"ops-alb-created-{time.time_ns() % 100000000}"
    created = ok(endpoint, "CreateLoadBalancer", Name=name, Type="application")
    arn = field(created, "LoadBalancerArn")
    assert arn.startswith("arn:aws:elasticloadbalancing:")
    assert arn in ok(endpoint, "DescribeLoadBalancers", **{"LoadBalancerArns.member.1": arn})


def test_describe_load_balancers_lists_the_balancer(endpoint):
    arn = ensure_lb(endpoint)
    assert arn in ok(endpoint, "DescribeLoadBalancers")


def test_delete_load_balancer_removes_the_balancer_it_created(endpoint):
    arn = new_lb(endpoint)
    ok(endpoint, "DeleteLoadBalancer", LoadBalancerArn=arn)
    status, _ = call(endpoint, "DescribeLoadBalancers", **{"LoadBalancerArns.member.1": arn})
    assert status >= 400


def test_describe_load_balancer_attributes_reads_them(endpoint):
    arn = ensure_lb(endpoint)
    assert "idle_timeout.timeout_seconds" in ok(endpoint, "DescribeLoadBalancerAttributes", LoadBalancerArn=arn)


def test_modify_load_balancer_attributes_changes_the_timeout(endpoint):
    arn = ensure_lb(endpoint)
    ok(
        endpoint,
        "ModifyLoadBalancerAttributes",
        LoadBalancerArn=arn,
        **{"Attributes.member.1.Key": "idle_timeout.timeout_seconds", "Attributes.member.1.Value": "120"},
    )
    text = ok(endpoint, "DescribeLoadBalancerAttributes", LoadBalancerArn=arn)
    assert "<Value>120</Value>" in text


def test_set_subnets_changes_the_subnets(endpoint):
    arn = ensure_lb(endpoint)
    text = ok(endpoint, "SetSubnets", LoadBalancerArn=arn, **{"Subnets.member.1": "subnet-ops3"})
    assert "<SubnetId>subnet-ops3</SubnetId>" in text


def test_set_ip_address_type_sets_the_type(endpoint):
    arn = ensure_lb(endpoint)
    assert "<IpAddressType>dualstack</IpAddressType>" in ok(
        endpoint, "SetIpAddressType", LoadBalancerArn=arn, IpAddressType="dualstack"
    )


def test_set_security_groups_sets_the_groups(endpoint):
    arn = ensure_lb(endpoint)
    assert "<member>sg-ops</member>" in ok(
        endpoint, "SetSecurityGroups", LoadBalancerArn=arn, **{"SecurityGroups.member.1": "sg-ops"}
    )


# ---------------------------------------------------------------------------
# Target groups
# ---------------------------------------------------------------------------


def test_create_target_group_is_read_back(endpoint):
    name = f"ops-tg-{time.time_ns() % 100000000}"
    created = ok(endpoint, "CreateTargetGroup", Name=name, Protocol="HTTP", Port="80", VpcId="vpc-ops")
    arn = field(created, "TargetGroupArn")
    assert arn in ok(endpoint, "DescribeTargetGroups", **{"TargetGroupArns.member.1": arn})


def test_describe_target_groups_lists_the_group(endpoint):
    arn = ensure_tg(endpoint)
    assert arn in ok(endpoint, "DescribeTargetGroups")


def test_modify_target_group_changes_the_health_check_path(endpoint):
    arn = ensure_tg(endpoint)
    ok(endpoint, "ModifyTargetGroup", TargetGroupArn=arn, HealthCheckPath="/ops")
    assert "<HealthCheckPath>/ops</HealthCheckPath>" in ok(endpoint, "DescribeTargetGroups", **{"TargetGroupArns.member.1": arn})


def test_delete_target_group_removes_the_group_it_created(endpoint):
    name = f"ops-tg-del-{time.time_ns() % 100000000}"
    arn = field(ok(endpoint, "CreateTargetGroup", Name=name, Protocol="HTTP", Port="80", VpcId="vpc-ops"), "TargetGroupArn")
    ok(endpoint, "DeleteTargetGroup", TargetGroupArn=arn)
    status, _ = call(endpoint, "DescribeTargetGroups", **{"TargetGroupArns.member.1": arn})
    assert status >= 400


def test_describe_target_group_attributes_reads_them(endpoint):
    arn = ensure_tg(endpoint)
    assert "deregistration_delay.timeout_seconds" in ok(endpoint, "DescribeTargetGroupAttributes", TargetGroupArn=arn)


def test_modify_target_group_attributes_changes_the_delay(endpoint):
    arn = ensure_tg(endpoint)
    ok(
        endpoint,
        "ModifyTargetGroupAttributes",
        TargetGroupArn=arn,
        **{"Attributes.member.1.Key": "deregistration_delay.timeout_seconds", "Attributes.member.1.Value": "60"},
    )
    assert "<Value>60</Value>" in ok(endpoint, "DescribeTargetGroupAttributes", TargetGroupArn=arn)


# ---------------------------------------------------------------------------
# Listeners
# ---------------------------------------------------------------------------


def test_create_listener_is_read_back(endpoint):
    lb = new_lb(endpoint)
    tg = ensure_tg(endpoint)
    created = ok(
        endpoint,
        "CreateListener",
        LoadBalancerArn=lb,
        Protocol="HTTP",
        Port="80",
        **{"DefaultActions.member.1.Type": "forward", "DefaultActions.member.1.TargetGroupArn": tg},
    )
    arn = field(created, "ListenerArn")
    assert arn in ok(endpoint, "DescribeListeners", LoadBalancerArn=lb)


def test_describe_listeners_lists_the_listener(endpoint):
    _lb, _tg, listener = context(endpoint)
    assert listener in ok(endpoint, "DescribeListeners", LoadBalancerArn=ensure_lb(endpoint))


def test_modify_listener_changes_the_port(endpoint):
    _lb, _tg, listener = context(endpoint)
    ok(endpoint, "ModifyListener", ListenerArn=listener, Port="8080")
    assert "<Port>8080</Port>" in ok(endpoint, "DescribeListeners")
    ok(endpoint, "ModifyListener", ListenerArn=listener, Port="80")


def test_delete_listener_removes_the_listener_it_created(endpoint):
    lb = new_lb(endpoint)
    tg = ensure_tg(endpoint)
    created = ok(
        endpoint,
        "CreateListener",
        LoadBalancerArn=lb,
        Protocol="HTTP",
        Port="80",
        **{"DefaultActions.member.1.Type": "forward", "DefaultActions.member.1.TargetGroupArn": tg},
    )
    arn = field(created, "ListenerArn")
    ok(endpoint, "DeleteListener", ListenerArn=arn)
    assert arn not in ok(endpoint, "DescribeListeners", LoadBalancerArn=lb)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def test_create_rule_is_read_back(endpoint):
    _lb, _tg, listener = context(endpoint)
    arn = new_rule(endpoint, listener)
    assert arn in ok(endpoint, "DescribeRules", ListenerArn=listener)


def test_describe_rules_lists_the_rule(endpoint):
    _lb, _tg, listener = context(endpoint)
    arn = new_rule(endpoint, listener)
    assert arn in ok(endpoint, "DescribeRules", ListenerArn=listener)


def test_modify_rule_changes_the_conditions(endpoint):
    _lb, _tg, listener = context(endpoint)
    arn = new_rule(endpoint, listener)
    ok(
        endpoint,
        "ModifyRule",
        RuleArn=arn,
        **{"Conditions.member.1.Field": "path-pattern", "Conditions.member.1.Values.member.1": "/changed"},
    )
    assert "/changed" in ok(endpoint, "DescribeRules", ListenerArn=listener)


def test_delete_rule_removes_the_rule_it_created(endpoint):
    _lb, _tg, listener = context(endpoint)
    arn = new_rule(endpoint, listener)
    ok(endpoint, "DeleteRule", RuleArn=arn)
    assert arn not in ok(endpoint, "DescribeRules", ListenerArn=listener)


def test_set_rule_priorities_reorders_the_rule(endpoint):
    _lb, _tg, listener = context(endpoint)
    arn = new_rule(endpoint, listener)
    ok(endpoint, "SetRulePriorities", **{"RulePriorities.member.1.RuleArn": arn, "RulePriorities.member.1.Priority": "5"})
    assert "<Priority>5</Priority>" in ok(endpoint, "DescribeRules", ListenerArn=listener)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


def test_register_targets_is_read_back_by_health(endpoint):
    tg = ensure_tg(endpoint)
    ok(endpoint, "RegisterTargets", TargetGroupArn=tg, **{"Targets.member.1.Id": f"i-ops-{time.time_ns() % 100000}", "Targets.member.1.Port": "80"})
    assert "<TargetHealthDescriptions>" in ok(endpoint, "DescribeTargetHealth", TargetGroupArn=tg)


def test_deregister_targets_removes_the_target(endpoint):
    tg = ensure_tg(endpoint)
    target = f"i-dereg-{time.time_ns() % 100000}"
    ok(endpoint, "RegisterTargets", TargetGroupArn=tg, **{"Targets.member.1.Id": target, "Targets.member.1.Port": "80"})
    ok(endpoint, "DeregisterTargets", TargetGroupArn=tg, **{"Targets.member.1.Id": target})
    assert f"<Id>{target}</Id>" not in ok(endpoint, "DescribeTargetHealth", TargetGroupArn=tg)


def test_describe_target_health_reports_healthy(endpoint):
    tg = ensure_tg(endpoint)
    target = f"i-health-{time.time_ns() % 100000}"
    ok(endpoint, "RegisterTargets", TargetGroupArn=tg, **{"Targets.member.1.Id": target, "Targets.member.1.Port": "80"})
    text = ok(endpoint, "DescribeTargetHealth", TargetGroupArn=tg, **{"Targets.member.1.Id": target})
    assert f"<Id>{target}</Id>" in text
    assert "<State>healthy</State>" in text


# ---------------------------------------------------------------------------
# Listener certificates
# ---------------------------------------------------------------------------


def test_add_listener_certificates_is_read_back(endpoint):
    _lb, _tg, listener = context(endpoint)
    cert = ensure_certificate(endpoint)
    ok(endpoint, "AddListenerCertificates", ListenerArn=listener, **{"Certificates.member.1.CertificateArn": cert})
    assert cert in ok(endpoint, "DescribeListenerCertificates", ListenerArn=listener)


def test_describe_listener_certificates_lists_the_certificate(endpoint):
    _lb, _tg, listener = context(endpoint)
    cert = ensure_certificate(endpoint)
    ok(endpoint, "AddListenerCertificates", ListenerArn=listener, **{"Certificates.member.1.CertificateArn": cert})
    assert cert in ok(endpoint, "DescribeListenerCertificates", ListenerArn=listener)


def test_remove_listener_certificates_removes_the_certificate(endpoint):
    _lb, _tg, listener = context(endpoint)
    cert = ensure_certificate(endpoint)
    ok(endpoint, "AddListenerCertificates", ListenerArn=listener, **{"Certificates.member.1.CertificateArn": cert})
    ok(endpoint, "RemoveListenerCertificates", ListenerArn=listener, **{"Certificates.member.1.CertificateArn": cert})
    assert cert not in ok(endpoint, "DescribeListenerCertificates", ListenerArn=listener)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_add_tags_is_read_back_by_describe_tags(endpoint):
    arn = ensure_lb(endpoint)
    ok(endpoint, "AddTags", **{"ResourceArns.member.1": arn, "Tags.member.1.Key": "env", "Tags.member.1.Value": "ops"})
    assert "<Key>env</Key>" in ok(endpoint, "DescribeTags", **{"ResourceArns.member.1": arn})


def test_remove_tags_removes_the_key_it_names(endpoint):
    arn = ensure_lb(endpoint)
    ok(endpoint, "AddTags", **{"ResourceArns.member.1": arn, "Tags.member.1.Key": "doomed", "Tags.member.1.Value": "yes"})
    ok(endpoint, "RemoveTags", **{"ResourceArns.member.1": arn, "TagKeys.member.1": "doomed"})
    assert "<Key>doomed</Key>" not in ok(endpoint, "DescribeTags", **{"ResourceArns.member.1": arn})


def test_describe_tags_lists_the_tags(endpoint):
    arn = ensure_lb(endpoint)
    ok(endpoint, "AddTags", **{"ResourceArns.member.1": arn, "Tags.member.1.Key": "team", "Tags.member.1.Value": "platform"})
    assert "<Key>team</Key>" in ok(endpoint, "DescribeTags", **{"ResourceArns.member.1": arn})
