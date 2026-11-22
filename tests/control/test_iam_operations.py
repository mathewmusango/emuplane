"""IAM on the wire: every operation the emulator advertises, driven through its own query protocol."""

from __future__ import annotations

import base64
import html
import json
import re
from urllib.parse import unquote, urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2010-05-08"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

TRUST = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)
POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}
        ],
    }
)
# A self-signed test certificate, valid to 2036, so the emulator's x509 read has a real PEM to parse.
CERT = """-----BEGIN CERTIFICATE-----
MIIC8DCCAdigAwIBAgIUd8UCU0WOF8XNXjAhINYdphrFhdIwDQYJKoZIhvcNAQEL
BQAwGDEWMBQGA1UEAwwNZW11cGxhbmUtdGVzdDAeFw0yNjExMjIxNTMzMThaFw0z
NjExMTkxNTMzMThaMBgxFjAUBgNVBAMMDWVtdXBsYW5lLXRlc3QwggEiMA0GCSqG
SIb3DQEBAQUAA4IBDwAwggEKAoIBAQC/4GyhawLJ7jB/Up1Fiex5Yt6Ptz/mV5Ic
bdxjSFDdNmh/F7JxpcrZxJBVp77/IUuVwulnqtMDcxKMbxQL9cN3+/qMaCs9TAdT
7Q3BaYy44puAi2N1yQfGcs1bmdtvGym6sFcilBdmLMXkBEUv0lLK6kHa1LrjgkZT
tN7iF9UWfSlUdFmThWbJdc3k9BCmHh11izD1UK3e+DHeFn/TlDXIQS0wcEyamPoq
LL8tBRSIFPn4BQPF1cJvy7ymNAvqLJZ7AcUy5Zzlb+ZUJOolV3BUZkTDbGCNsykZ
j1dIyKuCjhCY3PSflakzyb7V0+Jp/gMKMNlDtEV/lGmZbFWOpzNHAgMBAAGjMjAw
MB0GA1UdDgQWBBQ2toh/Da2v3LY8sytCyHZsx/sydzAPBgNVHRMBAf8EBTADAQH/
MA0GCSqGSIb3DQEBCwUAA4IBAQCIfCkxmrl4Ve6yptaOoYwpC+e58yVRqQLvbcRu
4si0464leVDK6dkzLFUGUtlCSiRo4geBBgK5FRJOx61faG0GS1gK1CYBFBrxw457
TC1/fNKYk7+gjulLmkYWGkXCTe6QBAzIvWR31l8on2swRgqrnTkJkhU7/hXGji93
xe7ZNeqpo03+uBoAZk2tNRZ+4vnkN8JPjfEu4WSSXL74uUbK1tGR1G7SVwN7bu0j
2dBzrvXWUJ1a8P6EyURtqXgNmcz5qNBoWNwy6U71mdn7oergWcMGlGHtjeIk0nig
RXicob0k1ma0p6Tf80/zKRMWj/sUHhIxPBrvo1cQOmhL1Wic
-----END CERTIFICATE-----"""


def call(endpoint, action: str, **params):
    """One IAM query-protocol call, signed with the account credential the emulator resolves."""
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "iam", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:600]}"
    return text


def refused(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status >= 400, f"{action} unexpectedly succeeded: {text[:300]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def tags(**values) -> dict[str, str]:
    params = {}
    for index, (key, value) in enumerate(values.items(), 1):
        params[f"Tags.member.{index}.Key"] = key
        params[f"Tags.member.{index}.Value"] = value
    return params


def tag_keys(*values) -> dict[str, str]:
    return {f"TagKeys.member.{index}": value for index, value in enumerate(values, 1)}


def arn(resource: str) -> str:
    return f"arn:aws:iam::{ACCOUNT}:{resource}"


# ------------------------------------------------------------------ users


def test_users_round_trip(endpoint):
    """CreateUser → GetUser → ListUsers, the path every identity starts on."""
    ok(endpoint, "CreateUser", UserName="iam-user", Path="/team/", **tags(team="platform"))

    text = ok(endpoint, "GetUser", UserName="iam-user")
    assert field(text, "Arn") == arn("user/team/iam-user")
    assert field(text, "Path") == "/team/"
    assert "<Key>team</Key>" in text

    listing = ok(endpoint, "ListUsers", PathPrefix="/team/")
    assert "<UserName>iam-user</UserName>" in listing

    root = ok(endpoint, "GetUser")
    assert field(root, "Arn") == arn("root")


def test_users_are_tagged_and_untagged(endpoint):
    """TagUser and UntagUser change what the next read reports."""
    ok(endpoint, "CreateUser", UserName="iam-tagged")

    ok(endpoint, "TagUser", UserName="iam-tagged", **tags(cost="42"))
    assert "<Key>cost</Key>" in ok(endpoint, "GetUser", UserName="iam-tagged")

    ok(endpoint, "UntagUser", UserName="iam-tagged", **tag_keys("cost"))
    assert "<Key>cost</Key>" not in ok(endpoint, "GetUser", UserName="iam-tagged")


def test_permissions_boundaries_on_a_user(endpoint):
    """Put and DeleteUserPermissionsBoundary, with the ARN read back by GetUser."""
    ok(endpoint, "CreateUser", UserName="iam-bounded")
    policy = arn("policy/iam-boundary")
    ok(
        endpoint,
        "CreatePolicy",
        PolicyName="iam-boundary",
        PolicyDocument=POLICY,
    )

    ok(endpoint, "PutUserPermissionsBoundary", UserName="iam-bounded", PermissionsBoundary=policy)
    assert field(ok(endpoint, "GetUser", UserName="iam-bounded"), "PermissionsBoundaryArn") == policy

    ok(endpoint, "DeleteUserPermissionsBoundary", UserName="iam-bounded")
    assert "PermissionsBoundaryArn" not in ok(endpoint, "GetUser", UserName="iam-bounded")
    ok(endpoint, "DeletePolicy", PolicyArn=policy)


def test_delete_user_refuses_while_it_carries_state(endpoint):
    """DeleteUser is a 409 while a policy is attached, then succeeds once the user is clean."""
    ok(endpoint, "CreateUser", UserName="iam-busy")
    policy = arn("policy/iam-busy")
    ok(endpoint, "CreatePolicy", PolicyName="iam-busy", PolicyDocument=POLICY)
    ok(endpoint, "AttachUserPolicy", UserName="iam-busy", PolicyArn=policy)

    assert "DeleteConflict" in refused(endpoint, "DeleteUser", UserName="iam-busy")

    ok(endpoint, "DetachUserPolicy", UserName="iam-busy", PolicyArn=policy)
    ok(endpoint, "DeleteUser", UserName="iam-busy")
    assert "NoSuchEntity" in refused(endpoint, "GetUser", UserName="iam-busy")
    ok(endpoint, "DeletePolicy", PolicyArn=policy)


# ------------------------------------------------------------- access keys


def test_access_keys_are_created_listed_updated_and_deleted(endpoint):
    """The whole key lifecycle, including the Active → Inactive switch."""
    ok(endpoint, "CreateUser", UserName="iam-keyed")

    created = ok(endpoint, "CreateAccessKey", UserName="iam-keyed")
    key_id = field(created, "AccessKeyId")
    assert key_id.startswith("AKIA")
    assert field(created, "Status") == "Active"

    assert key_id in ok(endpoint, "ListAccessKeys", UserName="iam-keyed")

    ok(endpoint, "UpdateAccessKey", UserName="iam-keyed", AccessKeyId=key_id, Status="Inactive")
    assert "<Status>Inactive</Status>" in ok(endpoint, "ListAccessKeys", UserName="iam-keyed")

    last_used = ok(endpoint, "GetAccessKeyLastUsed", AccessKeyId=key_id)
    assert field(last_used, "ServiceName") == "N/A"

    ok(endpoint, "DeleteAccessKey", UserName="iam-keyed", AccessKeyId=key_id)
    assert key_id not in ok(endpoint, "ListAccessKeys", UserName="iam-keyed")
    ok(endpoint, "DeleteUser", UserName="iam-keyed")


# ------------------------------------------------------------------ roles


def test_roles_round_trip(endpoint):
    """CreateRole, GetRole, ListRoles and DeleteRole over one trust policy."""
    ok(
        endpoint,
        "CreateRole",
        RoleName="iam-role",
        AssumeRolePolicyDocument=TRUST,
        Path="/svc/",
        **tags(team="platform"),
    )

    text = ok(endpoint, "GetRole", RoleName="iam-role")
    assert field(text, "Arn") == arn("role/svc/iam-role")
    assert field(text, "MaxSessionDuration") == "3600"
    assert "<Key>team</Key>" in text
    assert "iam-role" in ok(endpoint, "ListRoles", PathPrefix="/svc/")

    ok(endpoint, "DeleteRole", RoleName="iam-role")
    assert "NoSuchEntity" in refused(endpoint, "GetRole", RoleName="iam-role")


def test_role_description_and_boundary_are_updated(endpoint):
    """UpdateRoleDescription and the role-side permissions boundary round trip."""
    ok(endpoint, "CreateRole", RoleName="iam-described", AssumeRolePolicyDocument=TRUST)
    ok(endpoint, "UpdateRoleDescription", RoleName="iam-described", Description="runs the pipeline")
    assert field(ok(endpoint, "GetRole", RoleName="iam-described"), "Description") == (
        "runs the pipeline"
    )

    policy = arn("policy/iam-role-boundary")
    ok(endpoint, "CreatePolicy", PolicyName="iam-role-boundary", PolicyDocument=POLICY)
    ok(
        endpoint,
        "PutRolePermissionsBoundary",
        RoleName="iam-described",
        PermissionsBoundary=policy,
    )
    assert field(ok(endpoint, "GetRole", RoleName="iam-described"), "PermissionsBoundaryArn") == policy

    ok(endpoint, "DeleteRolePermissionsBoundary", RoleName="iam-described")
    assert "PermissionsBoundaryArn" not in ok(endpoint, "GetRole", RoleName="iam-described")
    ok(endpoint, "DeletePolicy", PolicyArn=policy)


def test_role_tags(endpoint):
    """TagRole and UntagRole, read back through GetRole."""
    ok(endpoint, "CreateRole", RoleName="iam-tagged-role", AssumeRolePolicyDocument=TRUST)
    ok(endpoint, "TagRole", RoleName="iam-tagged-role", **tags(env="test"))
    assert "<Key>env</Key>" in ok(endpoint, "GetRole", RoleName="iam-tagged-role")
    ok(endpoint, "UntagRole", RoleName="iam-tagged-role", **tag_keys("env"))
    assert "<Key>env</Key>" not in ok(endpoint, "GetRole", RoleName="iam-tagged-role")


def test_role_inline_policies(endpoint):
    """PutRolePolicy, GetRolePolicy, ListRolePolicies and DeleteRolePolicy."""
    ok(endpoint, "CreateRole", RoleName="iam-inline", AssumeRolePolicyDocument=TRUST)

    ok(endpoint, "PutRolePolicy", RoleName="iam-inline", PolicyName="read", PolicyDocument=POLICY)
    read = ok(endpoint, "GetRolePolicy", RoleName="iam-inline", PolicyName="read")
    assert json.loads(unquote(field(read, "PolicyDocument")))["Statement"][0]["Action"] == "s3:GetObject"
    assert "read" in ok(endpoint, "ListRolePolicies", RoleName="iam-inline")

    ok(endpoint, "DeleteRolePolicy", RoleName="iam-inline", PolicyName="read")
    assert "<PolicyNames></PolicyNames>" in ok(endpoint, "ListRolePolicies", RoleName="iam-inline")
    ok(endpoint, "DeleteRole", RoleName="iam-inline")


def test_managed_policies_attach_and_detach_on_a_role(endpoint):
    """AttachRolePolicy, ListAttachedRolePolicies and DetachRolePolicy stay in step."""
    ok(endpoint, "CreateRole", RoleName="iam-attached", AssumeRolePolicyDocument=TRUST)
    policy = arn("policy/iam-attached")
    ok(endpoint, "CreatePolicy", PolicyName="iam-attached", PolicyDocument=POLICY)

    ok(endpoint, "AttachRolePolicy", RoleName="iam-attached", PolicyArn=policy)
    listing = ok(endpoint, "ListAttachedRolePolicies", RoleName="iam-attached")
    assert f"<PolicyArn>{policy}</PolicyArn>" in listing
    assert field(ok(endpoint, "GetPolicy", PolicyArn=policy), "AttachmentCount") == "1"

    ok(endpoint, "DetachRolePolicy", RoleName="iam-attached", PolicyArn=policy)
    assert policy not in ok(endpoint, "ListAttachedRolePolicies", RoleName="iam-attached")
    ok(endpoint, "DeletePolicy", PolicyArn=policy)
    ok(endpoint, "DeleteRole", RoleName="iam-attached")


# --------------------------------------------------------- managed policies


def test_managed_policies_round_trip(endpoint):
    """CreatePolicy, GetPolicy and DeletePolicy, with the document's shape checked by the emulator."""
    created = ok(
        endpoint,
        "CreatePolicy",
        PolicyName="iam-policy",
        PolicyDocument=POLICY,
        Description="reads objects",
    )
    policy = field(created, "Arn")
    assert policy == arn("policy/iam-policy")

    text = ok(endpoint, "GetPolicy", PolicyArn=policy)
    assert field(text, "PolicyName") == "iam-policy"
    assert field(text, "DefaultVersionId") == "v1"
    assert field(text, "Description") == "reads objects"

    ok(endpoint, "DeletePolicy", PolicyArn=policy)
    assert "NoSuchEntity" in refused(endpoint, "GetPolicy", PolicyArn=policy)


def test_policy_tags(endpoint):
    """TagPolicy and UntagPolicy, read back on GetPolicy."""
    policy = arn("policy/iam-policy-tags")
    ok(endpoint, "CreatePolicy", PolicyName="iam-policy-tags", PolicyDocument=POLICY)
    ok(endpoint, "TagPolicy", PolicyArn=policy, **tags(owner="security"))
    assert "<Key>owner</Key>" in ok(endpoint, "GetPolicy", PolicyArn=policy)
    ok(endpoint, "UntagPolicy", PolicyArn=policy, **tag_keys("owner"))
    assert "<Key>owner</Key>" not in ok(endpoint, "GetPolicy", PolicyArn=policy)
    ok(endpoint, "DeletePolicy", PolicyArn=policy)


# -------------------------------------------------------- instance profiles


def test_instance_profiles_round_trip(endpoint):
    """The profile, its one role, and the listing that shows the pairing."""
    ok(endpoint, "CreateRole", RoleName="iam-ec2-role", AssumeRolePolicyDocument=TRUST)
    created = ok(endpoint, "CreateInstanceProfile", InstanceProfileName="iam-profile", Path="/ec2/")
    assert field(created, "Arn") == arn("instance-profile/ec2/iam-profile")

    ok(endpoint, "AddRoleToInstanceProfile", InstanceProfileName="iam-profile", RoleName="iam-ec2-role")
    text = ok(endpoint, "GetInstanceProfile", InstanceProfileName="iam-profile")
    assert "<RoleName>iam-ec2-role</RoleName>" in text
    assert "iam-profile" in ok(endpoint, "ListInstanceProfiles", PathPrefix="/ec2/")

    ok(endpoint, "RemoveRoleFromInstanceProfile", InstanceProfileName="iam-profile", RoleName="iam-ec2-role")
    assert "<RoleName>" not in ok(endpoint, "GetInstanceProfile", InstanceProfileName="iam-profile")

    ok(endpoint, "DeleteInstanceProfile", InstanceProfileName="iam-profile")
    assert "NoSuchEntity" in refused(endpoint, "GetInstanceProfile", InstanceProfileName="iam-profile")
    ok(endpoint, "DeleteRole", RoleName="iam-ec2-role")


def test_instance_profile_tags(endpoint):
    """TagInstanceProfile, UntagInstanceProfile and ListInstanceProfileTags."""
    ok(endpoint, "CreateInstanceProfile", InstanceProfileName="iam-tagged-profile")
    ok(endpoint, "TagInstanceProfile", InstanceProfileName="iam-tagged-profile", **tags(env="lab"))
    assert "<Key>env</Key>" in ok(endpoint, "ListInstanceProfileTags", InstanceProfileName="iam-tagged-profile")

    ok(endpoint, "UntagInstanceProfile", InstanceProfileName="iam-tagged-profile", **tag_keys("env"))
    assert "<Key>env</Key>" not in ok(endpoint, "ListInstanceProfileTags", InstanceProfileName="iam-tagged-profile")
    ok(endpoint, "DeleteInstanceProfile", InstanceProfileName="iam-tagged-profile")


# ----------------------------------------------------------------- groups


def test_groups_and_membership(endpoint):
    """CreateGroup, GetGroup, ListGroups, AddUserToGroup, RemoveUserFromGroup, DeleteGroup."""
    ok(endpoint, "CreateUser", UserName="iam-member")
    ok(endpoint, "CreateGroup", GroupName="iam-group", Path="/teams/")
    assert field(ok(endpoint, "GetGroup", GroupName="iam-group"), "Arn") == arn("group/teams/iam-group")

    ok(endpoint, "AddUserToGroup", GroupName="iam-group", UserName="iam-member")
    assert "<UserName>iam-member</UserName>" in ok(endpoint, "GetGroup", GroupName="iam-group")
    assert "iam-group" in ok(endpoint, "ListGroups", PathPrefix="/teams/")

    ok(endpoint, "RemoveUserFromGroup", GroupName="iam-group", UserName="iam-member")
    assert "<UserName>" not in ok(endpoint, "GetGroup", GroupName="iam-group")

    ok(endpoint, "DeleteGroup", GroupName="iam-group")
    ok(endpoint, "DeleteUser", UserName="iam-member")


def test_group_inline_policies(endpoint):
    """PutGroupPolicy, GetGroupPolicy, ListGroupPolicies and DeleteGroupPolicy."""
    ok(endpoint, "CreateGroup", GroupName="iam-inline-group")
    ok(endpoint, "PutGroupPolicy", GroupName="iam-inline-group", PolicyName="write", PolicyDocument=POLICY)
    read = ok(endpoint, "GetGroupPolicy", GroupName="iam-inline-group", PolicyName="write")
    assert json.loads(unquote(field(read, "PolicyDocument")))["Statement"][0]["Effect"] == "Allow"
    assert "write" in ok(endpoint, "ListGroupPolicies", GroupName="iam-inline-group")

    ok(endpoint, "DeleteGroupPolicy", GroupName="iam-inline-group", PolicyName="write")
    assert "<PolicyNames></PolicyNames>" in ok(endpoint, "ListGroupPolicies", GroupName="iam-inline-group")
    ok(endpoint, "DeleteGroup", GroupName="iam-inline-group")


def test_group_managed_policies(endpoint):
    """AttachGroupPolicy, ListAttachedGroupPolicies and DetachGroupPolicy."""
    ok(endpoint, "CreateGroup", GroupName="iam-attached-group")
    policy = arn("policy/iam-group")
    ok(endpoint, "CreatePolicy", PolicyName="iam-group", PolicyDocument=POLICY)

    ok(endpoint, "AttachGroupPolicy", GroupName="iam-attached-group", PolicyArn=policy)
    assert policy in ok(endpoint, "ListAttachedGroupPolicies", GroupName="iam-attached-group")

    ok(endpoint, "DetachGroupPolicy", GroupName="iam-attached-group", PolicyArn=policy)
    assert policy not in ok(endpoint, "ListAttachedGroupPolicies", GroupName="iam-attached-group")
    ok(endpoint, "DeletePolicy", PolicyArn=policy)
    ok(endpoint, "DeleteGroup", GroupName="iam-attached-group")


# --------------------------------------------------- service-linked roles


def test_service_linked_role_lifecycle(endpoint):
    """CreateServiceLinkedRole names the role after the service; delete reports a task."""
    created = ok(endpoint, "CreateServiceLinkedRole", AWSServiceName="autoscaling.amazonaws.com")
    role_name = field(created, "RoleName")
    assert role_name == "AWSServiceRoleForAutoscaling"
    assert field(created, "Path") == "/aws-service-role/autoscaling.amazonaws.com/"

    task = field(ok(endpoint, "DeleteServiceLinkedRole", RoleName=role_name), "DeletionTaskId")
    status = ok(endpoint, "GetServiceLinkedRoleDeletionStatus", DeletionTaskId=task)
    assert field(status, "Status") == "SUCCEEDED"


# ------------------------------------------------------- identity providers


def test_oidc_provider_is_created_and_listed(endpoint):
    """CreateOpenIDConnectProvider, and the ARN ListOpenIDConnectProviders reports."""
    provider = ok(
        endpoint,
        "CreateOpenIDConnectProvider",
        Url="https://oidc.example.test",
        **{"ClientIDList.member.1": "emuplane-console"},
        **{"ThumbprintList.member.1": "a" * 40},
    )
    provider_arn = field(provider, "OpenIDConnectProviderArn")
    assert provider_arn == arn("oidc-provider/oidc.example.test")
    assert provider_arn in ok(endpoint, "ListOpenIDConnectProviders")


def test_saml_provider_round_trip(endpoint):
    """Create, read, list, update and delete one SAML metadata document."""
    metadata = "<EntityDescriptor entityID='https://saml.example.test'/>"
    provider = field(
        ok(endpoint, "CreateSAMLProvider", Name="iam-saml", SAMLMetadataDocument=metadata),
        "SAMLProviderArn",
    )
    assert html.unescape(field(ok(endpoint, "GetSAMLProvider", SAMLProviderArn=provider), "SAMLMetadataDocument")) == metadata
    assert provider in ok(endpoint, "ListSAMLProviders")

    updated = "<EntityDescriptor entityID='https://saml2.example.test'/>"
    ok(endpoint, "UpdateSAMLProvider", SAMLProviderArn=provider, SAMLMetadataDocument=updated)
    assert html.unescape(field(ok(endpoint, "GetSAMLProvider", SAMLProviderArn=provider), "SAMLMetadataDocument")) == updated

    ok(endpoint, "DeleteSAMLProvider", SAMLProviderArn=provider)
    assert "NoSuchEntity" in refused(endpoint, "GetSAMLProvider", SAMLProviderArn=provider)


# ------------------------------------------------------------ login and MFA


def test_login_profile_lifecycle(endpoint):
    """CreateLoginProfile, GetLoginProfile, UpdateLoginProfile and DeleteLoginProfile."""
    ok(endpoint, "CreateUser", UserName="iam-console")
    ok(endpoint, "CreateLoginProfile", UserName="iam-console", PasswordResetRequired="true")
    assert field(ok(endpoint, "GetLoginProfile", UserName="iam-console"), "PasswordResetRequired") == "true"

    ok(endpoint, "UpdateLoginProfile", UserName="iam-console", PasswordResetRequired="false")
    assert field(ok(endpoint, "GetLoginProfile", UserName="iam-console"), "PasswordResetRequired") == "false"

    ok(endpoint, "DeleteLoginProfile", UserName="iam-console")
    assert "NoSuchEntity" in refused(endpoint, "GetLoginProfile", UserName="iam-console")
    ok(endpoint, "DeleteUser", UserName="iam-console")


def test_virtual_mfa_devices(endpoint):
    """The device is created unassigned, enabled on a user, resynced, deactivated and deleted."""
    ok(endpoint, "CreateUser", UserName="iam-mfa")
    serial = field(
        ok(endpoint, "CreateVirtualMFADevice", VirtualMFADeviceName="iam-mfa-device"),
        "SerialNumber",
    )
    assert serial == arn("mfa/iam-mfa-device")
    assert serial in ok(endpoint, "ListVirtualMFADevices", AssignmentStatus="Unassigned")

    ok(endpoint, "EnableMFADevice", UserName="iam-mfa", SerialNumber=serial)
    assert serial in ok(endpoint, "ListMFADevices", UserName="iam-mfa")
    assert serial in ok(endpoint, "ListVirtualMFADevices")

    ok(endpoint, "ResyncMFADevice", UserName="iam-mfa", SerialNumber=serial)
    ok(endpoint, "DeactivateMFADevice", UserName="iam-mfa", SerialNumber=serial)
    assert serial not in ok(endpoint, "ListMFADevices", UserName="iam-mfa")

    ok(endpoint, "DeleteVirtualMFADevice", SerialNumber=serial)
    assert serial not in ok(endpoint, "ListVirtualMFADevices", AssignmentStatus="Unassigned")
    ok(endpoint, "DeleteUser", UserName="iam-mfa")


# ------------------------------------------------------- account reporting


def test_service_last_accessed_details(endpoint):
    """GenerateServiceLastAccessedDetails hands back a job, and the job reads back COMPLETED."""
    role = arn("role/iam-sla")
    job = field(ok(endpoint, "GenerateServiceLastAccessedDetails", Arn=role), "JobId")
    text = ok(endpoint, "GetServiceLastAccessedDetails", JobId=job)
    assert field(text, "JobStatus") == "COMPLETED"
    assert field(text, "IsTruncated") == "false"


def test_credential_report_lists_the_account_and_its_users(endpoint):
    """GenerateCredentialReport is a state machine of one step; GetCredentialReport returns CSV."""
    ok(endpoint, "CreateUser", UserName="iam-reported")
    assert field(ok(endpoint, "GenerateCredentialReport"), "State") == "COMPLETE"

    text = ok(endpoint, "GetCredentialReport")
    report = base64.b64decode(field(text, "Content")).decode()
    assert report.startswith("user,arn,user_creation_time")
    assert "<root_account>" in report
    assert "iam-reported" in report
    assert field(text, "ReportFormat") == "text/csv"


def test_account_summary_reports_counts(endpoint):
    """GetAccountSummary is the account's census; the keys are the contract."""
    text = ok(endpoint, "GetAccountSummary")
    assert "<key>Users</key>" in text
    assert "<key>Groups</key>" in text
    assert "<key>MFADevicesInUse</key>" in text
    assert "<key>VersionsPerPolicyQuota</key>" in text


def test_account_password_policy_is_read_updated_and_deleted(endpoint):
    """Get, Update and DeleteAccountPasswordPolicy; a deleted policy is a 404."""
    ok(
        endpoint,
        "UpdateAccountPasswordPolicy",
        MinimumPasswordLength="14",
        RequireSymbols="true",
        PasswordReusePrevention="5",
    )
    text = ok(endpoint, "GetAccountPasswordPolicy")
    assert field(text, "MinimumPasswordLength") == "14"
    assert field(text, "RequireSymbols") == "true"
    assert field(text, "PasswordReusePrevention") == "5"

    ok(endpoint, "DeleteAccountPasswordPolicy")
    assert "NoSuchEntity" in refused(endpoint, "GetAccountPasswordPolicy")


def test_account_aliases(endpoint):
    """CreateAccountAlias replaces the alias; List reports it and Delete removes it."""
    ok(endpoint, "CreateAccountAlias", AccountAlias="emuplane-iam")
    assert "<member>emuplane-iam</member>" in ok(endpoint, "ListAccountAliases")
    ok(endpoint, "DeleteAccountAlias", AccountAlias="emuplane-iam")
    assert "emuplane-iam" not in ok(endpoint, "ListAccountAliases")


# ------------------------------------------------ service-specific creds


def test_service_specific_credentials(endpoint):
    """The five-operation family for a CodeCommit credential, secret only on create and reset."""
    ok(endpoint, "CreateUser", UserName="iam-service")
    created = ok(
        endpoint,
        "CreateServiceSpecificCredential",
        UserName="iam-service",
        ServiceName="codecommit.amazonaws.com",
    )
    credential = field(created, "ServiceSpecificCredentialId")
    assert field(created, "ServiceUserName").startswith("iam-service-at-")
    assert "<ServicePassword>" in created

    listed = ok(endpoint, "ListServiceSpecificCredentials", UserName="iam-service")
    assert credential in listed
    assert "<ServicePassword>" not in listed

    ok(endpoint, "UpdateServiceSpecificCredential", UserName="iam-service",
       ServiceSpecificCredentialId=credential, Status="Inactive")
    assert "<Status>Inactive</Status>" in ok(
        endpoint, "ListServiceSpecificCredentials", UserName="iam-service"
    )

    assert "<ServicePassword>" in ok(
        endpoint, "ResetServiceSpecificCredential",
        UserName="iam-service", ServiceSpecificCredentialId=credential,
    )
    ok(endpoint, "DeleteServiceSpecificCredential", UserName="iam-service",
       ServiceSpecificCredentialId=credential)
    assert credential not in ok(endpoint, "ListServiceSpecificCredentials", UserName="iam-service")
    ok(endpoint, "DeleteUser", UserName="iam-service")


# ------------------------------------------------------ server certificates


def test_server_certificates_round_trip(endpoint):
    """Upload, list, read, rename and delete a certificate; the upload parses the PEM."""
    created = ok(
        endpoint,
        "UploadServerCertificate",
        ServerCertificateName="iam-cert",
        CertificateBody=CERT,
        PrivateKey="emuplane-test-private-key",
        Path="/certs/",
        **tags(env="lab"),
    )
    assert field(created, "Path") == "/certs/"
    assert field(created, "ServerCertificateName") == "iam-cert"

    assert "iam-cert" in ok(endpoint, "ListServerCertificates", PathPrefix="/certs/")
    text = ok(endpoint, "GetServerCertificate", ServerCertificateName="iam-cert")
    assert "BEGIN CERTIFICATE" in text

    ok(endpoint, "UpdateServerCertificate", ServerCertificateName="iam-cert",
       NewServerCertificateName="iam-cert-renamed")
    assert "iam-cert-renamed" in ok(endpoint, "GetServerCertificate", ServerCertificateName="iam-cert-renamed")

    ok(endpoint, "DeleteServerCertificate", ServerCertificateName="iam-cert-renamed")
    assert "NoSuchEntity" in refused(
        endpoint, "GetServerCertificate", ServerCertificateName="iam-cert-renamed"
    )


def test_server_certificate_tags(endpoint):
    """ListServerCertificateTags reads the tags the upload carried, and paging stops cleanly."""
    ok(
        endpoint,
        "UploadServerCertificate",
        ServerCertificateName="iam-cert-tags",
        CertificateBody=CERT,
        PrivateKey="key",
        **tags(env="lab", owner="security"),
    )
    text = ok(endpoint, "ListServerCertificateTags", ServerCertificateName="iam-cert-tags")
    assert "<Key>env</Key>" in text
    assert "<Key>owner</Key>" in text
    assert field(text, "IsTruncated") == "false"


# ---------------------------------------------------------- authorization


def test_account_authorization_details_reports_every_entity(endpoint):
    """GetAccountAuthorizationDetails returns the four lists a reviewer reads."""
    ok(endpoint, "CreateUser", UserName="iam-detail-user")
    ok(endpoint, "CreateRole", RoleName="iam-detail-role", AssumeRolePolicyDocument=TRUST)
    ok(endpoint, "CreateGroup", GroupName="iam-detail-group")

    text = ok(endpoint, "GetAccountAuthorizationDetails")
    assert "<UserDetailList>" in text and "iam-detail-user" in text
    assert "<RoleDetailList>" in text and "iam-detail-role" in text
    assert "<GroupDetailList>" in text and "iam-detail-group" in text

    users_only = ok(endpoint, "GetAccountAuthorizationDetails", **{"Filter.member.1": "User"})
    assert "iam-detail-user" in users_only
    assert "iam-detail-role" not in users_only


# ------------------------------------------------------------- protocol


def test_unknown_action_is_refused(endpoint):
    """Unknown IAM actions are a 400 InvalidAction, not a silent success."""
    assert "InvalidAction" in refused(endpoint, "CreateNothing")


def test_listings_page_on_max_items(endpoint):
    """A listing that exceeds MaxItems truncates and hands back a Marker, as AWS does."""
    for name in ("iam-page-a", "iam-page-b"):
        ok(endpoint, "CreateUser", UserName=name)

    first = ok(endpoint, "ListUsers", MaxItems="1")
    assert field(first, "IsTruncated") == "true"
    marker = field(first, "Marker")

    second = ok(endpoint, "ListUsers", MaxItems="50", Marker=marker)
    assert "<UserName>" in second
    assert field(second, "IsTruncated") == "false"
