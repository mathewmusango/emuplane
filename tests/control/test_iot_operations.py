"""IoT Core on the wire: all 75 callable operations the `IoT Core` row advertises.

The control plane is REST-style (verb + path), signed with the `iot` scope; `Publish`
and the retained-message reads are the `iot-data` plane. The row's own "76 operations"
counts `MQTT-over-WebSocket pub/sub`, a transport rather than a callable operation, so
the ledger names the 74 operations it lists plus `Publish` (written as `Publish (HTTP)`)
and excludes the transport.

Certificates are real X.509: the suite builds its own CA and a verification certificate
whose CN is the account's registration code, registers the CA, and issues leaves with it
for `RegisterCertificate`/`RegisterCertificateWithoutCA`; `CreateCertificateFromCsr`
uses a locally generated CSR and the emulator's local CA. Things, groups, policies,
rules, templates, domain configurations and tags keep one stable record each, and delete
tests create their own. A custom domain needs an ACM certificate, so the delete test
requests one. Rule actions carry a role ARN, which the live `AUTH=true` evaluator checks;
the in-process stand-in does not.
"""

from __future__ import annotations

import datetime
import json
import secrets
from urllib.parse import urlencode

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
JSON = {"Content-Type": "application/json"}

THING = "ops-iot-thing"
THING_TYPE = "ops-iot-type"
THING_GROUP = "ops-iot-group"
POLICY = "ops-iot-policy"
RULE = "ops_iot_rule"
TEMPLATE = "ops_iot_template"
DOMAIN = "ops-iot-domain"
ROLE_NAME = "ops-iot-rule-role"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"

RUN = secrets.token_hex(3)

_STATE: dict = {}

_RULE_SQL = "SELECT * FROM 'ops/iot/rules'"
_TRUST = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "iot.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)
_POLICY_DOC = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["iot:Connect", "iot:Publish"], "Resource": "*"}
        ],
    }
)
_TEMPLATE_BODY = {
    "Parameters": {"AWS::IoT::Certificate::Id": {"Type": "String"}},
    "Resources": {
        "certificate": {
            "Type": "AWS::IoT::Certificate",
            "Properties": {
                "CertificateId": {"Ref": "AWS::IoT::Certificate::Id"},
                "Status": "Active",
            },
        }
    },
}


def _request(endpoint, service, method, path, body=None, query=None, headers=None):
    if query:
        path = f"{path}?{urlencode(query)}"
    if body is None:
        payload = b""
        extra = dict(headers or {})
    elif isinstance(body, bytes):
        payload = body
        extra = {**JSON, **(headers or {})}
    else:
        payload = json.dumps(body).encode()
        extra = {**JSON, **(headers or {})}
    return signed.request(endpoint, service, ACCOUNT, REGION, method, path, payload, extra)


def call(endpoint, method, path, body=None, query=None, headers=None):
    return _request(endpoint, "iot", method, path, body, query, headers)


def data_call(endpoint, method, path, body=None, query=None):
    return _request(endpoint, "iot-data", method, path, body, query)


def ok(endpoint, method, path, body=None, query=None, headers=None) -> dict:
    status, text = call(endpoint, method, path, body, query, headers)
    assert status == 200, f"{method} {path} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def created(endpoint, method, path, body=None, query=None, headers=None) -> dict:
    status, text = call(endpoint, method, path, body, query, headers)
    assert status == 200 or "already exists" in text.lower(), (
        f"{method} {path} answered {status}: {text[:500]}"
    )
    return json.loads(text or "{}")


def status_of(endpoint, method, path, body=None, query=None, headers=None):
    return call(endpoint, method, path, body, query, headers)


def iam_call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": "2010-05-08", **params})
    return signed.request(endpoint, "iam", ACCOUNT, REGION, "POST", "/", body, FORM)


def ensure_role(endpoint) -> str:
    status, _text = iam_call(endpoint, "GetRole", RoleName=ROLE_NAME)
    if status != 200:
        status, text = iam_call(
            endpoint,
            "CreateRole",
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=_TRUST,
            Description="ops iot rule role",
        )
        assert status == 200 or "AlreadyExists" in text, f"CreateRole answered {status}: {text[:300]}"
    status, text = iam_call(
        endpoint,
        "PutRolePolicy",
        RoleName=ROLE_NAME,
        PolicyName="ops-iot-rule",
        PolicyDocument=_POLICY_DOC,
    )
    assert status == 200, f"PutRolePolicy answered {status}: {text[:300]}"
    return ROLE_ARN


# --- X.509 helpers ----------------------------------------------------------


def _pem_cert(cert) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _new_key():
    return ec.generate_private_key(ec.SECP256R1())


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def build_ca(common_name: str):
    key = _new_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(_name(common_name))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def issue_leaf(ca_key, ca_cert, common_name: str) -> str:
    key = _new_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )
    return _pem_cert(cert)


def ensure_ca(endpoint) -> dict:
    """A registered, ACTIVE CA of our own, and a leaf it signed."""
    if "ca" not in _STATE:
        code = ok(endpoint, "GET", "/registrationcode")["registrationCode"]
        ca_key, ca_cert = build_ca(f"ops iot ca {RUN}")
        ca_pem = _pem_cert(ca_cert)
        verification = issue_leaf(ca_key, ca_cert, code)
        answer = created(
            endpoint,
            "POST",
            "/cacertificate",
            {"caCertificate": ca_pem, "verificationCertificate": verification},
            query={"setAsActive": "true", "allowAutoRegistration": "true"},
        )
        _STATE["ca"] = {
            "id": answer["certificateId"],
            "pem": ca_pem,
            "key": ca_key,
            "cert": ca_cert,
            "leaf": issue_leaf(ca_key, ca_cert, f"ops iot leaf {RUN}"),
        }
    return _STATE["ca"]


def ensure_certificate(endpoint) -> dict:
    """A stable device certificate (INACTIVE) used for principals and policies."""
    if "certificate" not in _STATE:
        _STATE["certificate"] = ok(endpoint, "POST", "/keys-and-certificate")
    return _STATE["certificate"]


def ensure_thing(endpoint) -> str:
    if "thing" not in _STATE:
        created(
            endpoint,
            "POST",
            f"/things/{THING}",
            {"attributePayload": {"attributes": {"ops": "yes"}}},
        )
        _STATE["thing"] = THING
    return THING


def ensure_thing_type(endpoint) -> str:
    if "thing_type" not in _STATE:
        created(
            endpoint,
            "POST",
            f"/thing-types/{THING_TYPE}",
            {"thingTypeProperties": {"thingTypeDescription": "ops type"}},
        )
        _STATE["thing_type"] = THING_TYPE
    return THING_TYPE


def ensure_thing_group(endpoint) -> str:
    if "thing_group" not in _STATE:
        created(
            endpoint,
            "POST",
            f"/thing-groups/{THING_GROUP}",
            {"thingGroupProperties": {"thingGroupDescription": "ops group"}},
        )
        _STATE["thing_group"] = THING_GROUP
    return THING_GROUP


def ensure_policy(endpoint) -> str:
    if "policy" not in _STATE:
        created(endpoint, "POST", f"/policies/{POLICY}", {"policyDocument": _POLICY_DOC})
        _STATE["policy"] = POLICY
    return POLICY


def ensure_rule(endpoint) -> str:
    ensure_role(endpoint)
    if "rule" not in _STATE:
        created(
            endpoint,
            "POST",
            f"/rules/{RULE}",
            {
                "sql": _RULE_SQL,
                "description": "ops rule",
                "actions": [{"republish": {"topic": "ops/iot/out", "roleArn": ROLE_ARN}}],
            },
        )
        _STATE["rule"] = RULE
    return RULE


def ensure_template(endpoint) -> str:
    if "template" not in _STATE:
        created(
            endpoint,
            "POST",
            "/provisioning-templates",
            {
                "templateName": TEMPLATE,
                "templateBody": _TEMPLATE_BODY,
                "provisioningRoleArn": ROLE_ARN,
                "description": "ops template",
            },
        )
        _STATE["template"] = TEMPLATE
    return TEMPLATE


def ensure_domain(endpoint) -> str:
    if "domain" not in _STATE:
        status, text = status_of(endpoint, "GET", f"/domainConfigurations/{DOMAIN}")
        if status != 200:
            created(endpoint, "POST", f"/domainConfigurations/{DOMAIN}", {"serviceType": "DATA"})
        _STATE["domain"] = DOMAIN
    return DOMAIN


def ensure_index(endpoint) -> None:
    ok(
        endpoint,
        "POST",
        "/indexing/config",
        {"thingIndexingConfiguration": {"thingIndexingMode": "REGISTRY"}},
    )


# --- Things and groups ------------------------------------------------------


def test_create_thing_answers_it(endpoint):
    name = f"ops-iot-created-{RUN}"
    answer = ok(endpoint, "POST", f"/things/{name}", {"attributePayload": {"attributes": {"ops": "yes"}}})
    assert answer["thingName"] == name
    assert ok(endpoint, "GET", f"/things/{name}")["attributes"]["ops"] == "yes"


def test_describe_thing_reads_it(endpoint):
    ensure_thing(endpoint)
    answer = ok(endpoint, "GET", f"/things/{THING}")
    assert answer["thingName"] == THING
    assert answer["version"] >= 1


def test_list_things_lists_it(endpoint):
    ensure_thing(endpoint)
    names = {thing["thingName"] for thing in ok(endpoint, "GET", "/things")["things"]}
    assert THING in names
    filtered = ok(endpoint, "GET", "/things", query={"thingName": "ops-iot-th"})["things"]
    assert THING in {thing["thingName"] for thing in filtered}


def test_update_thing_sets_an_attribute(endpoint):
    ensure_thing(endpoint)
    ok(
        endpoint,
        "PATCH",
        f"/things/{THING}",
        {"attributePayload": {"attributes": {"colour": "blue"}, "merge": True}},
    )
    read = ok(endpoint, "GET", f"/things/{THING}")
    assert read["attributes"]["colour"] == "blue"
    ok(
        endpoint,
        "PATCH",
        f"/things/{THING}",
        {"attributePayload": {"attributes": {"colour": ""}, "merge": True}},
    )


def test_delete_thing_removes_it(endpoint):
    name = f"ops-iot-deleted-{RUN}"
    ok(endpoint, "POST", f"/things/{name}")
    ok(endpoint, "DELETE", f"/things/{name}")
    status, _text = status_of(endpoint, "GET", f"/things/{name}")
    assert status == 404


def test_create_thing_type_answers_it(endpoint):
    name = f"ops-iot-type-created-{RUN}"
    answer = ok(
        endpoint,
        "POST",
        f"/thing-types/{name}",
        {"thingTypeProperties": {"thingTypeDescription": "created"}},
    )
    assert answer["thingTypeName"] == name
    assert ok(endpoint, "GET", f"/thing-types/{name}")["thingTypeProperties"][
        "thingTypeDescription"
    ] == "created"


def test_create_thing_group_answers_it(endpoint):
    name = f"ops-iot-group-created-{RUN}"
    answer = ok(
        endpoint,
        "POST",
        f"/thing-groups/{name}",
        {"thingGroupProperties": {"thingGroupDescription": "created"}},
    )
    assert answer["thingGroupName"] == name
    assert ok(endpoint, "GET", f"/thing-groups/{name}")["thingGroupProperties"][
        "thingGroupDescription"
    ] == "created"


def test_add_thing_to_thing_group(endpoint):
    ensure_thing(endpoint)
    ensure_thing_group(endpoint)
    ok(endpoint, "PUT", "/thing-groups/addThingToThingGroup", {"thingName": THING, "thingGroupName": THING_GROUP})
    listed = ok(endpoint, "GET", f"/thing-groups/{THING_GROUP}/things")["things"]
    assert THING in listed


def test_list_things_in_thing_group_lists_it(endpoint):
    ensure_thing(endpoint)
    ensure_thing_group(endpoint)
    ok(endpoint, "PUT", "/thing-groups/addThingToThingGroup", {"thingName": THING, "thingGroupName": THING_GROUP})
    listed = ok(endpoint, "GET", f"/thing-groups/{THING_GROUP}/things")["things"]
    assert THING in listed


def test_list_thing_groups_for_thing_lists_it(endpoint):
    ensure_thing(endpoint)
    ensure_thing_group(endpoint)
    ok(endpoint, "PUT", "/thing-groups/addThingToThingGroup", {"thingName": THING, "thingGroupName": THING_GROUP})
    groups = ok(endpoint, "GET", f"/things/{THING}/thing-groups")["thingGroups"]
    assert THING_GROUP in {group["groupName"] for group in groups}


# --- Certificates -----------------------------------------------------------


def test_create_keys_and_certificate_answers_it(endpoint):
    answer = ok(endpoint, "POST", "/keys-and-certificate", query={"setAsActive": "true"})
    assert answer["certificateId"]
    assert "BEGIN CERTIFICATE" in answer["certificatePem"]
    assert answer["keyPair"]["PrivateKey"]


def test_register_certificate_links_the_ca(endpoint):
    ca = ensure_ca(endpoint)
    answer = ok(endpoint, "POST", "/certificate/register", {"certificatePem": ca["leaf"]})
    assert answer["certificateId"]


def test_register_certificate_without_ca_answers_it(endpoint):
    ca = ensure_ca(endpoint)
    leaf = issue_leaf(ca["key"], ca["cert"], f"ops iot sni {RUN}")
    answer = ok(endpoint, "POST", "/certificate/register-no-ca", {"certificatePem": leaf})
    assert answer["certificateId"]


def test_create_certificate_from_csr_answers_it(endpoint):
    key = _new_key()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(_name(f"ops iot csr {RUN}"))
        .sign(key, hashes.SHA256())
    )
    answer = ok(
        endpoint,
        "POST",
        "/certificates",
        {"certificateSigningRequest": csr.public_bytes(serialization.Encoding.PEM).decode()},
    )
    assert answer["certificateId"]


def test_update_certificate_sets_its_status(endpoint):
    answer = ok(endpoint, "POST", "/keys-and-certificate")
    cert_id = answer["certificateId"]
    ok(endpoint, "PUT", f"/certificates/{cert_id}", {"newStatus": "ACTIVE"})
    listed = {cert["certificateId"]: cert for cert in ok(endpoint, "GET", "/certificates")["certificates"]}
    assert listed[cert_id]["status"] == "ACTIVE"
    ok(endpoint, "PUT", f"/certificates/{cert_id}", {"newStatus": "INACTIVE"})


def test_delete_certificate_removes_it(endpoint):
    answer = ok(endpoint, "POST", "/keys-and-certificate")
    cert_id = answer["certificateId"]
    ok(endpoint, "DELETE", f"/certificates/{cert_id}")
    listed = {cert["certificateId"] for cert in ok(endpoint, "GET", "/certificates")["certificates"]}
    assert cert_id not in listed


def test_get_and_delete_registration_code(endpoint):
    code = ok(endpoint, "GET", "/registrationcode")["registrationCode"]
    assert len(code) == 64
    ok(endpoint, "DELETE", "/registrationcode")
    assert ok(endpoint, "GET", "/registrationcode")["registrationCode"] != code


def test_register_ca_certificate_answers_it(endpoint):
    ca_key, ca_cert = build_ca(f"ops iot created ca {RUN}")
    code = ok(endpoint, "GET", "/registrationcode")["registrationCode"]
    verification = issue_leaf(ca_key, ca_cert, code)
    answer = ok(
        endpoint,
        "POST",
        "/cacertificate",
        {"caCertificate": _pem_cert(ca_cert), "verificationCertificate": verification},
        query={"setAsActive": "false"},
    )
    assert answer["certificateId"]


def test_describe_ca_certificate_reads_it(endpoint):
    ca = ensure_ca(endpoint)
    answer = ok(endpoint, "GET", f"/cacertificate/{ca['id']}")
    assert answer["certificateDescription"]["certificateId"] == ca["id"]


def test_update_ca_certificate_sets_its_status(endpoint):
    ca = ensure_ca(endpoint)
    ok(endpoint, "PUT", f"/cacertificate/{ca['id']}", {"newStatus": "INACTIVE"})
    read = ok(endpoint, "GET", f"/cacertificate/{ca['id']}")
    assert read["certificateDescription"]["status"] == "INACTIVE"
    ok(endpoint, "PUT", f"/cacertificate/{ca['id']}", {"newStatus": "ACTIVE"})


def test_list_ca_certificates_lists_it(endpoint):
    ca = ensure_ca(endpoint)
    ids = {cert["certificateId"] for cert in ok(endpoint, "GET", "/cacertificates")["certificates"]}
    assert ca["id"] in ids


def test_list_certificates_by_ca_lists_the_leaf(endpoint):
    ca = ensure_ca(endpoint)
    answer = created(endpoint, "POST", "/certificate/register", {"certificatePem": ca["leaf"]})
    cert_id = answer.get("certificateId") or answer.get("resourceId")
    listed = ok(endpoint, "GET", f"/certificates-by-ca/{ca['id']}")["certificates"]
    assert cert_id in {cert["certificateId"] for cert in listed}


def test_delete_ca_certificate_removes_it(endpoint):
    ca_key, ca_cert = build_ca(f"ops iot deleted ca {RUN}")
    code = ok(endpoint, "GET", "/registrationcode")["registrationCode"]
    verification = issue_leaf(ca_key, ca_cert, code)
    answer = ok(
        endpoint,
        "POST",
        "/cacertificate",
        {"caCertificate": _pem_cert(ca_cert), "verificationCertificate": verification},
        query={"setAsActive": "false"},
    )
    ca_id = answer["certificateId"]
    ok(endpoint, "DELETE", f"/cacertificate/{ca_id}")
    status, _text = status_of(endpoint, "GET", f"/cacertificate/{ca_id}")
    assert status == 404


# --- Thing principals -------------------------------------------------------


def test_attach_detach_and_list_thing_principals(endpoint):
    ensure_thing(endpoint)
    certificate = ensure_certificate(endpoint)
    principal = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/things/{THING}/principals", headers={"x-amzn-principal": principal})
    listed = ok(endpoint, "GET", f"/things/{THING}/principals")["principals"]
    assert principal in listed
    ok(endpoint, "DELETE", f"/things/{THING}/principals", headers={"x-amzn-principal": principal})
    listed = ok(endpoint, "GET", f"/things/{THING}/principals")["principals"]
    assert principal not in listed


def test_list_thing_principals_reads_them(endpoint):
    ensure_thing(endpoint)
    certificate = ensure_certificate(endpoint)
    principal = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/things/{THING}/principals", headers={"x-amzn-principal": principal})
    listed = ok(endpoint, "GET", f"/things/{THING}/principals")["principals"]
    assert principal in listed


def test_list_principal_things_lists_it(endpoint):
    ensure_thing(endpoint)
    certificate = ensure_certificate(endpoint)
    principal = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/things/{THING}/principals", headers={"x-amzn-principal": principal})
    things = ok(endpoint, "GET", "/principals/things", headers={"x-amzn-principal": principal})["things"]
    assert THING in things


# --- Policies ---------------------------------------------------------------


def test_create_policy_answers_it(endpoint):
    name = f"ops_iot_policy_created_{RUN}"
    answer = ok(endpoint, "POST", f"/policies/{name}", {"policyDocument": _POLICY_DOC})
    assert answer["policyName"] == name
    # ListTargetsForPolicy is the row's read of a policy: an unknown name is a 404 here.
    assert ok(endpoint, "GET", f"/policy-targets/{name}")["targets"] == []


def test_create_policy_version_answers_it(endpoint):
    ensure_policy(endpoint)
    answer = ok(endpoint, "POST", f"/policies/{POLICY}/version", {"policyDocument": _POLICY_DOC})
    assert int(answer["policyVersionId"]) >= 2


def test_set_default_policy_version_sets_it(endpoint):
    ensure_policy(endpoint)
    version = ok(endpoint, "POST", f"/policies/{POLICY}/version", {"policyDocument": _POLICY_DOC})[
        "policyVersionId"
    ]
    status, _text = status_of(endpoint, "PATCH", f"/policies/{POLICY}/version/{version}")
    assert status == 200
    # GetPolicy is not in the advertised row; it is the read that proves the default moved.
    assert ok(endpoint, "GET", f"/policies/{POLICY}")["defaultVersionId"] == version


def test_attach_and_detach_policy(endpoint):
    ensure_policy(endpoint)
    certificate = ensure_certificate(endpoint)
    target = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/target-policies/{POLICY}", {"target": target})
    assert target in ok(endpoint, "GET", f"/policy-targets/{POLICY}")["targets"]
    ok(endpoint, "POST", f"/target-policies/{POLICY}", {"target": target})
    assert target not in ok(endpoint, "GET", f"/policy-targets/{POLICY}")["targets"]


def test_list_targets_for_policy_lists_it(endpoint):
    ensure_policy(endpoint)
    certificate = ensure_certificate(endpoint)
    target = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/target-policies/{POLICY}", {"target": target})
    assert target in ok(endpoint, "GET", f"/policy-targets/{POLICY}")["targets"]


def test_list_attached_policies_lists_it(endpoint):
    ensure_policy(endpoint)
    certificate = ensure_certificate(endpoint)
    target = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/target-policies/{POLICY}", {"target": target})
    answer = ok(endpoint, "POST", f"/attached-policies/{target}")
    assert POLICY in {policy["policyName"] for policy in answer["policies"]}


def test_attach_and_detach_principal_policy(endpoint):
    ensure_policy(endpoint)
    certificate = ensure_certificate(endpoint)
    principal = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/principal-policies/{POLICY}", headers={"x-amzn-iot-principal": principal})
    assert principal in ok(endpoint, "GET", f"/policy-targets/{POLICY}")["targets"]
    ok(endpoint, "DELETE", f"/principal-policies/{POLICY}", headers={"x-amzn-iot-principal": principal})
    assert principal not in ok(endpoint, "GET", f"/policy-targets/{POLICY}")["targets"]


def test_list_principal_policies_lists_it(endpoint):
    ensure_policy(endpoint)
    certificate = ensure_certificate(endpoint)
    principal = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/principal-policies/{POLICY}", headers={"x-amzn-iot-principal": principal})
    answer = ok(endpoint, "GET", "/principal-policies", headers={"x-amzn-iot-principal": principal})
    assert POLICY in {policy["policyName"] for policy in answer["policies"]}


def test_list_policy_principals_lists_it(endpoint):
    ensure_policy(endpoint)
    certificate = ensure_certificate(endpoint)
    principal = certificate["certificateArn"]
    ok(endpoint, "PUT", f"/principal-policies/{POLICY}", headers={"x-amzn-iot-principal": principal})
    answer = ok(endpoint, "GET", "/policy-principals", headers={"x-amzn-iot-policy": POLICY})
    assert principal in answer["principals"]


# --- Topic rules ------------------------------------------------------------


def test_create_topic_rule_answers_it(endpoint):
    ensure_role(endpoint)
    name = f"ops_iot_rule_created_{RUN}"
    ok(
        endpoint,
        "POST",
        f"/rules/{name}",
        {
            "sql": _RULE_SQL,
            "actions": [{"republish": {"topic": "ops/iot/out", "roleArn": ROLE_ARN}}],
        },
    )
    assert ok(endpoint, "GET", f"/rules/{name}")["rule"]["ruleName"] == name


def test_get_topic_rule_reads_it(endpoint):
    ensure_rule(endpoint)
    answer = ok(endpoint, "GET", f"/rules/{RULE}")
    assert answer["rule"]["sql"] == _RULE_SQL


def test_replace_topic_rule_sets_the_description(endpoint):
    ensure_rule(endpoint)
    ok(
        endpoint,
        "PATCH",
        f"/rules/{RULE}",
        {
            "sql": _RULE_SQL,
            "description": "replaced rule",
            "actions": [{"republish": {"topic": "ops/iot/out", "roleArn": ROLE_ARN}}],
        },
    )
    assert ok(endpoint, "GET", f"/rules/{RULE}")["rule"]["description"] == "replaced rule"
    ok(
        endpoint,
        "PATCH",
        f"/rules/{RULE}",
        {
            "sql": _RULE_SQL,
            "description": "ops rule",
            "actions": [{"republish": {"topic": "ops/iot/out", "roleArn": ROLE_ARN}}],
        },
    )


def test_enable_and_disable_topic_rule(endpoint):
    ensure_rule(endpoint)
    ok(endpoint, "POST", f"/rules/{RULE}/disable")
    assert ok(endpoint, "GET", f"/rules/{RULE}")["rule"]["ruleDisabled"] is True
    ok(endpoint, "POST", f"/rules/{RULE}/enable")
    assert ok(endpoint, "GET", f"/rules/{RULE}")["rule"]["ruleDisabled"] is False


def test_list_topic_rules_lists_it(endpoint):
    ensure_rule(endpoint)
    names = {rule["ruleName"] for rule in ok(endpoint, "GET", "/rules")["rules"]}
    assert RULE in names


def test_delete_topic_rule_removes_it(endpoint):
    ensure_role(endpoint)
    name = f"ops_iot_rule_deleted_{RUN}"
    ok(
        endpoint,
        "POST",
        f"/rules/{name}",
        {"sql": _RULE_SQL, "actions": [{"republish": {"topic": "ops/iot/out", "roleArn": ROLE_ARN}}]},
    )
    ok(endpoint, "DELETE", f"/rules/{name}")
    status, _text = status_of(endpoint, "GET", f"/rules/{name}")
    assert status in (401, 404)


# --- Provisioning templates -------------------------------------------------


def test_create_provisioning_template_answers_it(endpoint):
    name = f"ops_iot_created_{RUN}"
    answer = ok(
        endpoint,
        "POST",
        "/provisioning-templates",
        {
            "templateName": name,
            "templateBody": _TEMPLATE_BODY,
            "provisioningRoleArn": ROLE_ARN,
        },
    )
    assert answer["templateName"] == name
    assert ok(endpoint, "GET", f"/provisioning-templates/{name}")["templateName"] == name


def test_describe_provisioning_template_reads_it(endpoint):
    ensure_template(endpoint)
    answer = ok(endpoint, "GET", f"/provisioning-templates/{TEMPLATE}")
    assert answer["templateName"] == TEMPLATE
    assert answer["templateBody"]["Resources"]["certificate"]["Type"] == "AWS::IoT::Certificate"


def test_list_provisioning_templates_lists_it(endpoint):
    ensure_template(endpoint)
    names = {
        template["templateName"]
        for template in ok(endpoint, "GET", "/provisioning-templates")["templates"]
    }
    assert TEMPLATE in names


def test_update_provisioning_template_sets_the_description(endpoint):
    ensure_template(endpoint)
    status, _text = status_of(
        endpoint, "PATCH", f"/provisioning-templates/{TEMPLATE}", {"description": "updated template"}
    )
    assert status == 200
    assert ok(endpoint, "GET", f"/provisioning-templates/{TEMPLATE}")["description"] == "updated template"
    status, _text = status_of(
        endpoint, "PATCH", f"/provisioning-templates/{TEMPLATE}", {"description": "ops template"}
    )
    assert status == 200


def test_create_provisioning_template_version_answers_it(endpoint):
    ensure_template(endpoint)
    answer = ok(
        endpoint,
        "POST",
        f"/provisioning-templates/{TEMPLATE}/versions",
        {"templateBody": _TEMPLATE_BODY},
    )
    assert answer["versionId"] >= 2


def test_list_provisioning_template_versions_lists_them(endpoint):
    ensure_template(endpoint)
    versions = ok(endpoint, "GET", f"/provisioning-templates/{TEMPLATE}/versions")["versions"]
    assert 1 in {version["versionId"] for version in versions}


def test_describe_provisioning_template_version_reads_it(endpoint):
    ensure_template(endpoint)
    answer = ok(endpoint, "GET", f"/provisioning-templates/{TEMPLATE}/versions/1")
    assert answer["versionId"] == 1
    assert answer["isDefaultVersion"] is True


def test_delete_provisioning_template_version_removes_it(endpoint):
    ensure_template(endpoint)
    version = ok(
        endpoint,
        "POST",
        f"/provisioning-templates/{TEMPLATE}/versions",
        {"templateBody": _TEMPLATE_BODY},
    )["versionId"]
    ok(endpoint, "DELETE", f"/provisioning-templates/{TEMPLATE}/versions/{version}")
    status, _text = status_of(endpoint, "GET", f"/provisioning-templates/{TEMPLATE}/versions/{version}")
    assert status == 404


def test_create_provisioning_claim_answers_it(endpoint):
    ensure_template(endpoint)
    answer = ok(endpoint, "POST", f"/provisioning-templates/{TEMPLATE}/provisioning-claim")
    assert answer["certificateId"]
    assert "BEGIN CERTIFICATE" in answer["certificatePem"]


def test_delete_provisioning_template_removes_it(endpoint):
    name = f"ops_iot_deleted_{RUN}"
    ok(
        endpoint,
        "POST",
        "/provisioning-templates",
        {"templateName": name, "templateBody": _TEMPLATE_BODY, "provisioningRoleArn": ROLE_ARN},
    )
    ok(endpoint, "DELETE", f"/provisioning-templates/{name}")
    status, _text = status_of(endpoint, "GET", f"/provisioning-templates/{name}")
    assert status == 404


# --- Fleet indexing ---------------------------------------------------------


def test_update_indexing_configuration_turns_it_on(endpoint):
    ok(
        endpoint,
        "POST",
        "/indexing/config",
        {"thingIndexingConfiguration": {"thingIndexingMode": "REGISTRY"}},
    )
    read = ok(endpoint, "GET", "/indexing/config")
    assert read["thingIndexingConfiguration"]["thingIndexingMode"] == "REGISTRY"


def test_get_indexing_configuration_reads_it(endpoint):
    ensure_index(endpoint)
    read = ok(endpoint, "GET", "/indexing/config")
    assert read["thingIndexingConfiguration"]["thingIndexingMode"] == "REGISTRY"


def test_describe_index_reads_it(endpoint):
    ensure_index(endpoint)
    answer = ok(endpoint, "GET", "/indices/AWS_Things")
    assert answer["indexName"] == "AWS_Things"
    assert answer["indexStatus"] == "ACTIVE"


def test_list_indices_lists_it(endpoint):
    ensure_index(endpoint)
    assert "AWS_Things" in ok(endpoint, "GET", "/indices")["indexNames"]


def test_search_index_finds_the_thing(endpoint):
    ensure_index(endpoint)
    ensure_thing(endpoint)
    answer = ok(
        endpoint,
        "POST",
        "/indices/search",
        {"indexName": "AWS_Things", "queryString": f"thingName:{THING}"},
    )
    assert THING in {thing["thingName"] for thing in answer["things"]}


# --- Endpoint, publish and retained messages --------------------------------


def test_describe_endpoint_answers_a_host(endpoint):
    answer = ok(endpoint, "GET", "/endpoint")
    assert "-ats.iot." in answer["endpointAddress"]


def test_publish_is_accepted(endpoint):
    status, text = data_call(
        endpoint, "POST", f"/topics/ops/iot/publish/{RUN}", b"hello", query={"qos": "0"}
    )
    assert status == 200, f"Publish answered {status}: {text[:300]}"


def test_get_retained_message_reads_it(endpoint):
    topic = f"ops/iot/retained/{RUN}"
    status, text = data_call(endpoint, "POST", f"/topics/{topic}", b"hello", query={"retain": "1"})
    assert status == 200, f"Publish answered {status}: {text[:300]}"
    status, text = data_call(endpoint, "GET", f"/retainedMessage/{topic}")
    assert status == 200, f"GetRetainedMessage answered {status}: {text[:300]}"
    assert json.loads(text)["topic"] == topic


def test_list_retained_messages_lists_it(endpoint):
    topic = f"ops/iot/retained-list/{RUN}"
    status, text = data_call(endpoint, "POST", f"/topics/{topic}", b"hello", query={"retain": "1"})
    assert status == 200, f"Publish answered {status}: {text[:300]}"
    listed = json.loads(data_call(endpoint, "GET", "/retainedMessage")[1])["retainedTopics"]
    assert topic in {entry["topic"] for entry in listed}


# --- Event configurations ---------------------------------------------------


def test_update_event_configurations_enables_thing(endpoint):
    ok(endpoint, "PATCH", "/event-configurations", {"eventConfigurations": {"THING": {"Enabled": True}}})
    read = ok(endpoint, "GET", "/event-configurations")
    assert read["eventConfigurations"]["THING"]["Enabled"] is True


def test_describe_event_configurations_reads_them(endpoint):
    read = ok(endpoint, "GET", "/event-configurations")
    assert set(read["eventConfigurations"]) >= {"THING", "CERTIFICATE", "POLICY"}


# --- Domain configurations --------------------------------------------------


def test_create_domain_configuration_answers_it(endpoint):
    name = f"ops-iot-domain-created-{RUN}"
    answer = ok(endpoint, "POST", f"/domainConfigurations/{name}", {"serviceType": "DATA"})
    assert answer["domainConfigurationName"] == name
    read = ok(endpoint, "GET", f"/domainConfigurations/{name}")
    assert read["domainType"] == "AWS_MANAGED"


def test_describe_domain_configuration_reads_it(endpoint):
    ensure_domain(endpoint)
    read = ok(endpoint, "GET", f"/domainConfigurations/{DOMAIN}")
    assert read["domainConfigurationName"] == DOMAIN


def test_list_domain_configurations_lists_it(endpoint):
    ensure_domain(endpoint)
    names = {
        entry["domainConfigurationName"]
        for entry in ok(endpoint, "GET", "/domainConfigurations")["domainConfigurations"]
    }
    assert DOMAIN in names


def test_update_domain_configuration_sets_the_status(endpoint):
    ensure_domain(endpoint)
    ok(
        endpoint,
        "PUT",
        f"/domainConfigurations/{DOMAIN}",
        {"domainConfigurationStatus": "DISABLED"},
    )
    assert ok(endpoint, "GET", f"/domainConfigurations/{DOMAIN}")[
        "domainConfigurationStatus"
    ] == "DISABLED"
    ok(
        endpoint,
        "PUT",
        f"/domainConfigurations/{DOMAIN}",
        {"domainConfigurationStatus": "ENABLED"},
    )


def test_delete_domain_configuration_removes_it(endpoint):
    certificate = _acm_certificate(endpoint, f"ops-{RUN}.iot.example.com")
    name = f"ops-iot-domain-deleted-{RUN}"
    ok(
        endpoint,
        "POST",
        f"/domainConfigurations/{name}",
        {
            "serviceType": "DATA",
            "domainName": f"ops-{RUN}.iot.example.com",
            "serverCertificateArns": [certificate],
        },
    )
    ok(endpoint, "PUT", f"/domainConfigurations/{name}", {"domainConfigurationStatus": "DISABLED"})
    ok(endpoint, "DELETE", f"/domainConfigurations/{name}")
    status, _text = status_of(endpoint, "GET", f"/domainConfigurations/{name}")
    assert status == 404


# --- Tags -------------------------------------------------------------------


def test_tag_untag_and_list_tags_for_resource(endpoint):
    ensure_thing_type(endpoint)
    arn = ok(endpoint, "GET", f"/thing-types/{THING_TYPE}")["thingTypeArn"]
    ok(endpoint, "POST", "/tags", {"resourceArn": arn, "tags": [{"Key": "ops", "Value": "iot"}, {"Key": "keep", "Value": "yes"}]})
    tags = {tag["Key"]: tag["Value"] for tag in ok(endpoint, "GET", "/tags", query={"resourceArn": arn})["tags"]}
    assert tags["ops"] == "iot"
    ok(endpoint, "POST", "/untag", {"resourceArn": arn, "tagKeys": ["ops"]})
    tags = {tag["Key"]: tag["Value"] for tag in ok(endpoint, "GET", "/tags", query={"resourceArn": arn})["tags"]}
    assert "ops" not in tags and tags.get("keep") == "yes"


# --- ACM (a dependant of the custom domain) ---------------------------------


def _acm_certificate(endpoint, domain_name: str) -> str:
    status, text = signed.request(
        endpoint,
        "acm",
        ACCOUNT,
        REGION,
        "POST",
        "/",
        json.dumps({"DomainName": domain_name}),
        {"X-Amz-Target": "CertificateManager.RequestCertificate", **JSON},
    )
    assert status == 200, f"RequestCertificate answered {status}: {text[:300]}"
    return json.loads(text)["CertificateArn"]
