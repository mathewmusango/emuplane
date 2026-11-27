"""Cognito on the wire: all 101 advertised operations across both planes.

The emulator serves `cognito-idp` (`AWSCognitoIdentityProviderService.*`, user pools)
and `cognito-identity` (`AWSCognitoIdentityService.*`, identity pools) from one module.
The README row lists both under their labels, and its OAuth2 entry is a path rather
than an operation, so the ledger excludes that entry.

A stable pool, client and user carry the read paths; a delete creates its own resource.
Threat-protection audit events need a pool whose `AdvancedSecurityMode` is not `OFF`,
so the two auth-event operations use a second, `PLUS` pool. TOTP codes are computed
here with the RFC 6238 recipe the emulator checks. `UpdateAuthEventFeedback` has no
valid token to accept (the emulator sends no notification email), so its reachable
answer is the `NotAuthorizedException` refused below.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time

import signed
from conftest import ACCOUNT, requires

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
IDP = "AWSCognitoIdentityProviderService"
IDENTITY_SERVICE = "AWSCognitoIdentityService"

POOL_NAME = "ops-cognito-pool"
PLUS_POOL_NAME = "ops-cognito-plus"
CLIENT_NAME = "ops-cognito-client"
BRANDING_CLIENT_NAME = "ops-cognito-branding"
USERNAME = "ops-cognito-user"
PASSWORD = "OpsCognito-Pass1!"
NEW_PASSWORD = "OpsCognito-Pass2!"
EMAIL = "ops-cognito@example.com"
DOMAIN = "ops-cognito-domain"
GROUP = "ops-cognito-group"
RESOURCE_SERVER = "https://ops-cognito.example.com"
IDP_NAME = "ops-facebook"
IDP_IDENTIFIER = "ops-idp"
IDENTITY_POOL_NAME = "ops-cognito-identity"

RUN = secrets.token_hex(3)

_STATE: dict = {}


def _call(endpoint, service, target, action, payload):
    body = json.dumps(payload)
    headers = {"X-Amz-Target": f"{target}.{action}", **JSON_TYPE}
    return signed.request(endpoint, service, ACCOUNT, REGION, "POST", "/", body, headers)


def idp(endpoint, action: str, **payload) -> dict:
    status, text = _call(endpoint, "cognito-idp", IDP, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def idp_status(endpoint, action: str, **payload):
    return _call(endpoint, "cognito-idp", IDP, action, payload)


def idp_created(endpoint, action: str, **payload) -> dict:
    status, text = _call(endpoint, "cognito-idp", IDP, action, payload)
    assert status == 200 or "already exists" in text, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def identity(endpoint, action: str, **payload) -> dict:
    status, text = _call(endpoint, "cognito-identity", IDENTITY_SERVICE, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def identity_created(endpoint, action: str, **payload) -> dict:
    status, text = _call(endpoint, "cognito-identity", IDENTITY_SERVICE, action, payload)
    assert status == 200 or "already exists" in text, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def _all_pools(endpoint) -> list[dict]:
    pools: list[dict] = []
    token = None
    for _ in range(10):
        payload = {"MaxResults": 60}
        if token:
            payload["NextToken"] = token
        answer = idp(endpoint, "ListUserPools", **payload)
        pools.extend(answer.get("UserPools", []))
        token = answer.get("NextToken")
        if not token:
            break
    return pools


def _all_clients(endpoint, pool_id: str) -> list[dict]:
    clients: list[dict] = []
    token = None
    for _ in range(10):
        payload = {"UserPoolId": pool_id, "MaxResults": 60}
        if token:
            payload["NextToken"] = token
        answer = idp(endpoint, "ListUserPoolClients", **payload)
        clients.extend(answer.get("UserPoolClients", []))
        token = answer.get("NextToken")
        if not token:
            break
    return clients


def _all_identity_pools(endpoint) -> list[dict]:
    pools: list[dict] = []
    token = None
    for _ in range(10):
        payload = {"MaxResults": 60}
        if token:
            payload["NextToken"] = token
        answer = identity(endpoint, "ListIdentityPools", **payload)
        pools.extend(answer.get("IdentityPools", []))
        token = answer.get("NextToken")
        if not token:
            break
    return pools


def ensure_pool(endpoint, name: str = POOL_NAME, **extra) -> str:
    key = f"pool:{name}"
    if key not in _STATE:
        pool_id = next(
            (pool["Id"] for pool in _all_pools(endpoint) if pool["Name"] == name), ""
        )
        if not pool_id:
            pool_id = idp_created(endpoint, "CreateUserPool", PoolName=name, AutoVerifiedAttributes=["email"], **extra)[
                "UserPool"
            ]["Id"]
        # A pool that verifies email issues the sign-up code ConfirmSignUp checks under AUTH.
        read = idp(endpoint, "DescribeUserPool", UserPoolId=pool_id)["UserPool"]
        if "email" not in (read.get("AutoVerifiedAttributes") or []):
            idp(
                endpoint,
                "UpdateUserPool",
                UserPoolId=pool_id,
                AutoVerifiedAttributes=["email"],
            )
        _STATE[key] = pool_id
    return _STATE[key]


def ensure_plus_pool(endpoint) -> str:
    return ensure_pool(
        endpoint,
        PLUS_POOL_NAME,
        UserPoolTier="PLUS",
        UserPoolAddOns={"AdvancedSecurityMode": "ENFORCED"},
    )


def ensure_client(endpoint, name: str = CLIENT_NAME, pool_id: str = "") -> str:
    pool_id = pool_id or ensure_pool(endpoint)
    key = f"client:{pool_id}:{name}"
    if key not in _STATE:
        client_id = next(
            (
                client["ClientId"]
                for client in _all_clients(endpoint, pool_id)
                if client["ClientName"] == name
            ),
            "",
        )
        if not client_id:
            client_id = idp_created(
                endpoint,
                "CreateUserPoolClient",
                UserPoolId=pool_id,
                ClientName=name,
                ExplicitAuthFlows=[
                    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
                    "ALLOW_USER_PASSWORD_AUTH",
                    "ALLOW_REFRESH_TOKEN_AUTH",
                    "ALLOW_USER_SRP_AUTH",
                ],
            )["UserPoolClient"]["ClientId"]
        _STATE[key] = client_id
    return _STATE[key]


def _user_attributes(username: str, email: str = "") -> list[dict]:
    return [
        {"Name": "email", "Value": email or f"{username}@example.com"},
        {"Name": "email_verified", "Value": "true"},
    ]


def ensure_user(
    endpoint,
    username: str = USERNAME,
    password: str = PASSWORD,
    pool_id: str = "",
    email: str = "",
) -> str:
    pool_id = pool_id or ensure_pool(endpoint)
    key = f"user:{pool_id}:{username}"
    if key not in _STATE:
        status, _text = idp_status(
            endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username
        )
        if status != 200:
            idp_created(
                endpoint,
                "AdminCreateUser",
                UserPoolId=pool_id,
                Username=username,
                UserAttributes=_user_attributes(username, email or (EMAIL if username == USERNAME else "")),
                MessageAction="SUPPRESS",
                TemporaryPassword=password,
            )
            idp(
                endpoint,
                "AdminSetUserPassword",
                UserPoolId=pool_id,
                Username=username,
                Password=password,
                Permanent=True,
            )
        _STATE[key] = username
    return _STATE[key]


def fresh_user(
    endpoint, prefix: str, password: str = PASSWORD, pool_id: str = ""
) -> tuple[str, str]:
    pool_id = pool_id or ensure_pool(endpoint)
    username = f"ops-{prefix}-{RUN}"
    idp(
        endpoint,
        "AdminCreateUser",
        UserPoolId=pool_id,
        Username=username,
        UserAttributes=_user_attributes(username),
        MessageAction="SUPPRESS",
        TemporaryPassword=password,
    )
    idp(
        endpoint,
        "AdminSetUserPassword",
        UserPoolId=pool_id,
        Username=username,
        Password=password,
        Permanent=True,
    )
    return username, password


def sign_in(endpoint, username: str = USERNAME, password: str = PASSWORD, pool_id: str = "") -> dict:
    pool_id = pool_id or ensure_pool(endpoint)
    client_id = ensure_client(endpoint, pool_id=pool_id)
    answer = idp(
        endpoint,
        "AdminInitiateAuth",
        UserPoolId=pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": password},
    )
    assert "AuthenticationResult" in answer, answer
    return answer["AuthenticationResult"]


def ensure_group(endpoint, name: str = GROUP, pool_id: str = "") -> str:
    pool_id = pool_id or ensure_pool(endpoint)
    key = f"group:{pool_id}:{name}"
    if key not in _STATE:
        status, _text = idp_status(endpoint, "GetGroup", UserPoolId=pool_id, GroupName=name)
        if status != 200:
            idp_created(
                endpoint,
                "CreateGroup",
                UserPoolId=pool_id,
                GroupName=name,
                Description="ops cognito group",
            )
        _STATE[key] = name
    return _STATE[key]


def ensure_member(endpoint, group: str = GROUP, username: str = USERNAME, pool_id: str = "") -> None:
    pool_id = pool_id or ensure_pool(endpoint)
    ensure_group(endpoint, group, pool_id)
    ensure_user(endpoint, username, pool_id=pool_id)
    idp(
        endpoint,
        "AdminAddUserToGroup",
        UserPoolId=pool_id,
        Username=username,
        GroupName=group,
    )


def ensure_resource_server(endpoint, identifier: str = RESOURCE_SERVER, pool_id: str = "") -> None:
    pool_id = pool_id or ensure_pool(endpoint)
    key = f"resource:{pool_id}:{identifier}"
    if key not in _STATE:
        status, _text = idp_status(
            endpoint, "DescribeResourceServer", UserPoolId=pool_id, Identifier=identifier
        )
        if status != 200:
            idp_created(
                endpoint,
                "CreateResourceServer",
                UserPoolId=pool_id,
                Identifier=identifier,
                Name="ops cognito resource server",
                Scopes=[{"ScopeName": "read", "ScopeDescription": "read"}],
            )
        else:
            # A previous sweep's update test renames it; restore the reading state.
            idp(
                endpoint,
                "UpdateResourceServer",
                UserPoolId=pool_id,
                Identifier=identifier,
                Name="ops cognito resource server",
                Scopes=[{"ScopeName": "read", "ScopeDescription": "read"}],
            )
        _STATE[key] = identifier


def ensure_domain(endpoint, domain: str = DOMAIN, pool_id: str = "") -> str:
    pool_id = pool_id or ensure_pool(endpoint)
    answer = idp(endpoint, "DescribeUserPoolDomain", Domain=domain)["DomainDescription"]
    owner = answer.get("UserPoolId") or ""
    if owner != pool_id:
        if owner:
            idp(endpoint, "DeleteUserPoolDomain", UserPoolId=owner, Domain=domain)
        idp_created(endpoint, "CreateUserPoolDomain", UserPoolId=pool_id, Domain=domain)
    _STATE[f"domain:{domain}"] = pool_id
    return domain


def ensure_identity_provider(endpoint, pool_id: str = "") -> str:
    pool_id = pool_id or ensure_pool(endpoint)
    key = f"idp:{pool_id}"
    if key not in _STATE:
        providers = idp(endpoint, "ListIdentityProviders", UserPoolId=pool_id, MaxResults=60)[
            "Providers"
        ]
        if not any(provider["ProviderName"] == IDP_NAME for provider in providers):
            idp_created(
                endpoint,
                "CreateIdentityProvider",
                UserPoolId=pool_id,
                ProviderName=IDP_NAME,
                ProviderType="Facebook",
                ProviderDetails={"client_id": "ops-client-id", "client_secret": "ops-secret"},
                AttributeMapping={"email": "email"},
                IdpIdentifiers=[IDP_IDENTIFIER],
            )
        _STATE[key] = IDP_NAME
    return IDP_NAME


def ensure_branding(endpoint, client_name: str = BRANDING_CLIENT_NAME) -> tuple[str, str]:
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint, client_name, pool_id)
    key = f"branding:{client_id}"
    if key not in _STATE:
        status, text = idp_status(
            endpoint,
            "DescribeManagedLoginBrandingByClient",
            UserPoolId=pool_id,
            ClientId=client_id,
        )
        if status != 200:
            answer = idp_created(
                endpoint,
                "CreateManagedLoginBranding",
                UserPoolId=pool_id,
                ClientId=client_id,
                UseCognitoProvidedValues=True,
            )
            _STATE[key] = answer["ManagedLoginBranding"]["ManagedLoginBrandingId"]
        else:
            _STATE[key] = json.loads(text)["ManagedLoginBranding"]["ManagedLoginBrandingId"]
    return client_id, _STATE[key]


def ensure_identity_pool(endpoint) -> str:
    key = f"identity-pool:{IDENTITY_POOL_NAME}"
    if key not in _STATE:
        pool_id = next(
            (
                pool["IdentityPoolId"]
                for pool in _all_identity_pools(endpoint)
                if pool["IdentityPoolName"] == IDENTITY_POOL_NAME
            ),
            "",
        )
        if not pool_id:
            pool_id = identity_created(
                endpoint,
                "CreateIdentityPool",
                IdentityPoolName=IDENTITY_POOL_NAME,
                AllowUnauthenticatedIdentities=True,
            )["IdentityPoolId"]
        _STATE[key] = pool_id
    return _STATE[key]


def ensure_identity(endpoint, pool_id: str = "") -> str:
    pool_id = pool_id or ensure_identity_pool(endpoint)
    key = f"identity:{pool_id}"
    if key not in _STATE:
        _STATE[key] = identity(endpoint, "GetId", IdentityPoolId=pool_id)["IdentityId"]
    return _STATE[key]


def totp_code(secret_b32: str) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    return f"{(struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 10**6:06d}"


def _attribute(user: dict, name: str) -> str:
    for item in user.get("UserAttributes") or user.get("Attributes") or []:
        if item["Name"] == name:
            return item["Value"]
    return ""


# --- User pools -------------------------------------------------------------


def test_create_user_pool_answers_it(endpoint):
    name = f"ops-cognito-created-{RUN}"
    answer = idp(endpoint, "CreateUserPool", PoolName=name)
    pool_id = answer["UserPool"]["Id"]
    read = idp(endpoint, "DescribeUserPool", UserPoolId=pool_id)["UserPool"]
    assert read["Name"] == name


def test_describe_user_pool_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    answer = idp(endpoint, "DescribeUserPool", UserPoolId=pool_id)
    assert answer["UserPool"]["Id"] == pool_id
    assert answer["UserPool"]["Name"] == POOL_NAME


def test_list_user_pools_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    assert pool_id in {pool["Id"] for pool in _all_pools(endpoint)}


def test_update_user_pool_sets_the_email_subject(endpoint):
    pool_id = ensure_pool(endpoint)
    idp(
        endpoint,
        "UpdateUserPool",
        UserPoolId=pool_id,
        EmailVerificationSubject="Your ops verification code",
    )
    read = idp(endpoint, "DescribeUserPool", UserPoolId=pool_id)["UserPool"]
    assert read["EmailVerificationSubject"] == "Your ops verification code"


def test_delete_user_pool_removes_it(endpoint):
    pool_id = idp(endpoint, "CreateUserPool", PoolName=f"ops-cognito-delete-{RUN}")[
        "UserPool"
    ]["Id"]
    idp(endpoint, "DeleteUserPool", UserPoolId=pool_id)
    status, _text = idp_status(endpoint, "DescribeUserPool", UserPoolId=pool_id)
    assert status == 400


def test_tag_untag_list_tags_for_user_pool(endpoint):
    pool_id = ensure_pool(endpoint)
    arn = idp(endpoint, "DescribeUserPool", UserPoolId=pool_id)["UserPool"]["Arn"]
    idp(endpoint, "TagResource", ResourceArn=arn, Tags={"ops": "cognito", "keep": "yes"})
    assert idp(endpoint, "ListTagsForResource", ResourceArn=arn)["Tags"]["ops"] == "cognito"
    idp(endpoint, "UntagResource", ResourceArn=arn, TagKeys=["ops"])
    tags = idp(endpoint, "ListTagsForResource", ResourceArn=arn)["Tags"]
    assert "ops" not in tags and tags.get("keep") == "yes"


# --- User pool clients ------------------------------------------------------


def test_create_user_pool_client_answers_it(endpoint):
    pool_id = ensure_pool(endpoint)
    answer = idp(
        endpoint,
        "CreateUserPoolClient",
        UserPoolId=pool_id,
        ClientName=f"ops-cognito-new-client-{RUN}",
    )
    client_id = answer["UserPoolClient"]["ClientId"]
    read = idp(
        endpoint, "DescribeUserPoolClient", UserPoolId=pool_id, ClientId=client_id
    )["UserPoolClient"]
    assert read["ClientId"] == client_id


def test_describe_user_pool_client_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    answer = idp(
        endpoint, "DescribeUserPoolClient", UserPoolId=pool_id, ClientId=client_id
    )
    assert answer["UserPoolClient"]["ClientName"] == CLIENT_NAME


def test_list_user_pool_clients_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    assert client_id in {client["ClientId"] for client in _all_clients(endpoint, pool_id)}


def test_update_user_pool_client_sets_the_name(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    idp(
        endpoint,
        "UpdateUserPoolClient",
        UserPoolId=pool_id,
        ClientId=client_id,
        ClientName="ops-cognito-client-renamed",
    )
    read = idp(
        endpoint, "DescribeUserPoolClient", UserPoolId=pool_id, ClientId=client_id
    )["UserPoolClient"]
    assert read["ClientName"] == "ops-cognito-client-renamed"
    idp(
        endpoint,
        "UpdateUserPoolClient",
        UserPoolId=pool_id,
        ClientId=client_id,
        ClientName=CLIENT_NAME,
    )


def test_delete_user_pool_client_removes_it(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = idp(
        endpoint,
        "CreateUserPoolClient",
        UserPoolId=pool_id,
        ClientName=f"ops-cognito-delete-client-{RUN}",
    )["UserPoolClient"]["ClientId"]
    idp(endpoint, "DeleteUserPoolClient", UserPoolId=pool_id, ClientId=client_id)
    status, _text = idp_status(
        endpoint, "DescribeUserPoolClient", UserPoolId=pool_id, ClientId=client_id
    )
    assert status == 400


# --- Resource servers -------------------------------------------------------


def test_create_resource_server_answers_it(endpoint):
    pool_id = ensure_pool(endpoint)
    identifier = f"{RESOURCE_SERVER}/created-{RUN}"
    answer = idp(
        endpoint,
        "CreateResourceServer",
        UserPoolId=pool_id,
        Identifier=identifier,
        Name="ops created resource server",
        Scopes=[{"ScopeName": "read", "ScopeDescription": "read"}],
    )
    assert answer["ResourceServer"]["Identifier"] == identifier
    read = idp(
        endpoint, "DescribeResourceServer", UserPoolId=pool_id, Identifier=identifier
    )
    assert read["ResourceServer"]["Name"] == "ops created resource server"


def test_describe_resource_server_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_resource_server(endpoint)
    answer = idp(
        endpoint, "DescribeResourceServer", UserPoolId=pool_id, Identifier=RESOURCE_SERVER
    )
    assert answer["ResourceServer"]["Name"] == "ops cognito resource server"


def test_update_resource_server_sets_the_name(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_resource_server(endpoint)
    idp(
        endpoint,
        "UpdateResourceServer",
        UserPoolId=pool_id,
        Identifier=RESOURCE_SERVER,
        Name="ops renamed resource server",
    )
    read = idp(
        endpoint, "DescribeResourceServer", UserPoolId=pool_id, Identifier=RESOURCE_SERVER
    )["ResourceServer"]
    assert read["Name"] == "ops renamed resource server"
    idp(
        endpoint,
        "UpdateResourceServer",
        UserPoolId=pool_id,
        Identifier=RESOURCE_SERVER,
        Name="ops cognito resource server",
    )


def test_list_resource_servers_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_resource_server(endpoint)
    answer = idp(endpoint, "ListResourceServers", UserPoolId=pool_id)
    assert RESOURCE_SERVER in {
        server["Identifier"] for server in answer["ResourceServers"]
    }


def test_delete_resource_server_removes_it(endpoint):
    pool_id = ensure_pool(endpoint)
    identifier = f"{RESOURCE_SERVER}/delete-{RUN}"
    idp(
        endpoint,
        "CreateResourceServer",
        UserPoolId=pool_id,
        Identifier=identifier,
        Name="ops deleted resource server",
    )
    idp(endpoint, "DeleteResourceServer", UserPoolId=pool_id, Identifier=identifier)
    status, _text = idp_status(
        endpoint, "DescribeResourceServer", UserPoolId=pool_id, Identifier=identifier
    )
    assert status == 400


# --- Users ------------------------------------------------------------------


def test_admin_create_user_answers_it(endpoint):
    username, _password = fresh_user(endpoint, "created")
    read = idp(
        endpoint, "AdminGetUser", UserPoolId=ensure_pool(endpoint), Username=username
    )
    assert read["Username"] == username
    assert read["UserStatus"] == "CONFIRMED"


def test_admin_get_user_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_user(endpoint)
    answer = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=USERNAME)
    assert answer["Username"] == USERNAME
    assert answer["Enabled"] is True


def test_list_users_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_user(endpoint)
    answer = idp(endpoint, "ListUsers", UserPoolId=pool_id)
    assert USERNAME in {user["Username"] for user in answer["Users"]}


def test_admin_set_user_password_sets_it(endpoint):
    pool_id = ensure_pool(endpoint)
    username, _password = fresh_user(endpoint, "password")
    idp(
        endpoint,
        "AdminSetUserPassword",
        UserPoolId=pool_id,
        Username=username,
        Password=NEW_PASSWORD,
        Permanent=True,
    )
    assert sign_in(endpoint, username, NEW_PASSWORD)["AccessToken"]


def test_admin_update_user_attributes_sets_nickname(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_user(endpoint)
    idp(
        endpoint,
        "AdminUpdateUserAttributes",
        UserPoolId=pool_id,
        Username=USERNAME,
        UserAttributes=[{"Name": "nickname", "Value": "ops-nick"}],
    )
    read = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=USERNAME)
    assert _attribute(read, "nickname") == "ops-nick"


def test_admin_confirm_sign_up_confirms_it(endpoint):
    pool_id = ensure_pool(endpoint)
    username = f"ops-confirm-{RUN}"
    idp(
        endpoint,
        "AdminCreateUser",
        UserPoolId=pool_id,
        Username=username,
        MessageAction="SUPPRESS",
        TemporaryPassword=PASSWORD,
    )
    idp(endpoint, "AdminConfirmSignUp", UserPoolId=pool_id, Username=username)
    read = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)
    assert read["UserStatus"] == "CONFIRMED"


def test_admin_disable_and_enable_user(endpoint):
    pool_id = ensure_pool(endpoint)
    username, _password = fresh_user(endpoint, "toggled")
    idp(endpoint, "AdminDisableUser", UserPoolId=pool_id, Username=username)
    assert (
        idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)["Enabled"]
        is False
    )
    idp(endpoint, "AdminEnableUser", UserPoolId=pool_id, Username=username)
    assert (
        idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)["Enabled"]
        is True
    )


def test_admin_reset_user_password_is_accepted(endpoint):
    pool_id = ensure_pool(endpoint)
    username, _password = fresh_user(endpoint, "reset")
    assert idp(endpoint, "AdminResetUserPassword", UserPoolId=pool_id, Username=username) == {}
    assert (
        idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)["UserStatus"]
        == "RESET_REQUIRED"
    )


def test_admin_user_global_sign_out_is_accepted(endpoint):
    pool_id = ensure_pool(endpoint)
    username, password = fresh_user(endpoint, "admin-signout")
    sign_in(endpoint, username, password)
    assert idp(endpoint, "AdminUserGlobalSignOut", UserPoolId=pool_id, Username=username) == {}


def test_admin_add_remove_user_in_group(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_member(endpoint)
    members = idp(
        endpoint, "ListUsersInGroup", UserPoolId=pool_id, GroupName=GROUP
    )["Users"]
    assert USERNAME in {user["Username"] for user in members}
    idp(
        endpoint,
        "AdminRemoveUserFromGroup",
        UserPoolId=pool_id,
        Username=USERNAME,
        GroupName=GROUP,
    )
    members = idp(
        endpoint, "ListUsersInGroup", UserPoolId=pool_id, GroupName=GROUP
    )["Users"]
    assert USERNAME not in {user["Username"] for user in members}


def test_admin_list_groups_for_user_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_member(endpoint)
    answer = idp(endpoint, "AdminListGroupsForUser", UserPoolId=pool_id, Username=USERNAME)
    assert GROUP in {group["GroupName"] for group in answer["Groups"]}


def test_admin_list_user_auth_events_lists_them(endpoint):
    pool_id = ensure_plus_pool(endpoint)
    username, password = fresh_user(endpoint, "events", pool_id=pool_id)
    sign_in(endpoint, username, password, pool_id=pool_id)
    answer = idp(
        endpoint, "AdminListUserAuthEvents", UserPoolId=pool_id, Username=username
    )
    assert answer["AuthEvents"]
    assert answer["AuthEvents"][0]["EventType"] == "SignIn"


def test_admin_update_auth_event_feedback_records_it(endpoint):
    pool_id = ensure_plus_pool(endpoint)
    username, password = fresh_user(endpoint, "feedback", pool_id=pool_id)
    sign_in(endpoint, username, password, pool_id=pool_id)
    event = idp(
        endpoint, "AdminListUserAuthEvents", UserPoolId=pool_id, Username=username
    )["AuthEvents"][0]
    idp(
        endpoint,
        "AdminUpdateAuthEventFeedback",
        UserPoolId=pool_id,
        Username=username,
        EventId=event["EventId"],
        FeedbackValue="Valid",
    )
    events = idp(
        endpoint, "AdminListUserAuthEvents", UserPoolId=pool_id, Username=username
    )["AuthEvents"]
    assert events[0]["EventFeedback"]["FeedbackValue"] == "Valid"


def test_update_auth_event_feedback_refuses_without_a_session(endpoint):
    pool_id = ensure_plus_pool(endpoint)
    status, text = idp_status(
        endpoint,
        "UpdateAuthEventFeedback",
        UserPoolId=pool_id,
        Username=f"ops-nobody-{RUN}",
        EventId=f"event-{RUN}",
        FeedbackValue="Valid",
    )
    assert status == 400
    assert "Invalid session provided" in text


def test_get_user_attribute_verification_code_and_verify(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_user(endpoint)
    token = sign_in(endpoint)["AccessToken"]
    answer = idp(
        endpoint,
        "GetUserAttributeVerificationCode",
        AccessToken=token,
        AttributeName="email",
    )
    assert answer["CodeDeliveryDetails"]["AttributeName"] == "email"
    idp(
        endpoint,
        "VerifyUserAttribute",
        AccessToken=token,
        AttributeName="email",
        Code="123456",
    )
    read = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=USERNAME)
    assert _attribute(read, "email_verified") == "true"


# --- Auth flows and self-service --------------------------------------------


def test_admin_initiate_auth_answers_tokens(endpoint):
    ensure_user(endpoint)
    result = sign_in(endpoint)
    assert result["TokenType"] == "Bearer"
    assert result["AccessToken"] and result["RefreshToken"]


def test_admin_respond_to_auth_challenge_completes_the_change(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    username = f"ops-admin-challenge-{RUN}"
    idp(
        endpoint,
        "AdminCreateUser",
        UserPoolId=pool_id,
        Username=username,
        MessageAction="SUPPRESS",
        TemporaryPassword=PASSWORD,
    )
    answer = idp(
        endpoint,
        "AdminInitiateAuth",
        UserPoolId=pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": PASSWORD},
    )
    assert answer["ChallengeName"] == "NEW_PASSWORD_REQUIRED"
    result = idp(
        endpoint,
        "AdminRespondToAuthChallenge",
        UserPoolId=pool_id,
        ClientId=client_id,
        ChallengeName="NEW_PASSWORD_REQUIRED",
        Session=answer["Session"],
        ChallengeResponses={"USERNAME": username, "NEW_PASSWORD": NEW_PASSWORD},
    )
    assert result["AuthenticationResult"]["AccessToken"]


def test_initiate_auth_answers_tokens(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    ensure_user(endpoint)
    answer = idp(
        endpoint,
        "InitiateAuth",
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": USERNAME, "PASSWORD": PASSWORD},
    )
    assert answer["AuthenticationResult"]["AccessToken"]
    assert pool_id


def test_respond_to_auth_challenge_completes_the_change(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    username = f"ops-challenge-{RUN}"
    idp(
        endpoint,
        "AdminCreateUser",
        UserPoolId=pool_id,
        Username=username,
        MessageAction="SUPPRESS",
        TemporaryPassword=PASSWORD,
    )
    answer = idp(
        endpoint,
        "InitiateAuth",
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": PASSWORD},
    )
    assert answer["ChallengeName"] == "NEW_PASSWORD_REQUIRED"
    result = idp(
        endpoint,
        "RespondToAuthChallenge",
        ClientId=client_id,
        ChallengeName="NEW_PASSWORD_REQUIRED",
        Session=answer["Session"],
        ChallengeResponses={"USERNAME": username, "NEW_PASSWORD": NEW_PASSWORD},
    )
    assert result["AuthenticationResult"]["AccessToken"]


def test_global_sign_out_is_accepted(endpoint):
    username, password = fresh_user(endpoint, "signout")
    token = sign_in(endpoint, username, password)["AccessToken"]
    assert idp(endpoint, "GlobalSignOut", AccessToken=token) == {}


def test_revoke_token_is_accepted(endpoint):
    client_id = ensure_client(endpoint)
    username, password = fresh_user(endpoint, "revoke")
    refresh = sign_in(endpoint, username, password)["RefreshToken"]
    assert idp(endpoint, "RevokeToken", ClientId=client_id, Token=refresh) == {}


def test_sign_up_and_confirm(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    username = f"ops-signup-{RUN}"
    idp(
        endpoint,
        "SignUp",
        ClientId=client_id,
        Username=username,
        Password=PASSWORD,
        UserAttributes=[{"Name": "email", "Value": f"{username}@example.com"}],
    )
    idp(
        endpoint,
        "ConfirmSignUp",
        ClientId=client_id,
        Username=username,
        ConfirmationCode="123456",
    )
    read = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)
    assert read["UserStatus"] == "CONFIRMED"


def test_forgot_password_and_confirm(endpoint):
    client_id = ensure_client(endpoint)
    username, _password = fresh_user(endpoint, "forgot")
    answer = idp(endpoint, "ForgotPassword", ClientId=client_id, Username=username)
    assert answer["CodeDeliveryDetails"]["DeliveryMedium"] == "EMAIL"
    idp(
        endpoint,
        "ConfirmForgotPassword",
        ClientId=client_id,
        Username=username,
        ConfirmationCode="654321",
        Password=NEW_PASSWORD,
    )
    assert sign_in(endpoint, username, NEW_PASSWORD)["AccessToken"]


def test_change_password_changes_it(endpoint):
    username, password = fresh_user(endpoint, "change")
    token = sign_in(endpoint, username, password)["AccessToken"]
    idp(
        endpoint,
        "ChangePassword",
        AccessToken=token,
        PreviousPassword=password,
        ProposedPassword=NEW_PASSWORD,
    )
    assert sign_in(endpoint, username, NEW_PASSWORD)["AccessToken"]


def test_get_user_reads_it(endpoint):
    ensure_user(endpoint)
    token = sign_in(endpoint)["AccessToken"]
    answer = idp(endpoint, "GetUser", AccessToken=token)
    assert answer["Username"] == USERNAME
    assert _attribute(answer, "email") == EMAIL


def test_update_user_attributes_sets_given_name(endpoint):
    ensure_user(endpoint)
    token = sign_in(endpoint)["AccessToken"]
    idp(
        endpoint,
        "UpdateUserAttributes",
        AccessToken=token,
        UserAttributes=[{"Name": "given_name", "Value": "Ops"}],
    )
    answer = idp(endpoint, "GetUser", AccessToken=token)
    assert _attribute(answer, "given_name") == "Ops"


def test_delete_user_removes_it(endpoint):
    pool_id = ensure_pool(endpoint)
    username, password = fresh_user(endpoint, "self-delete")
    token = sign_in(endpoint, username, password)["AccessToken"]
    idp(endpoint, "DeleteUser", AccessToken=token)
    status, _text = idp_status(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)
    assert status == 400


def test_admin_delete_user_removes_it(endpoint):
    pool_id = ensure_pool(endpoint)
    username, _password = fresh_user(endpoint, "admin-delete")
    idp(endpoint, "AdminDeleteUser", UserPoolId=pool_id, Username=username)
    status, _text = idp_status(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)
    assert status == 400


# --- Groups -----------------------------------------------------------------


def test_create_group_answers_it(endpoint):
    pool_id = ensure_pool(endpoint)
    name = f"ops-created-group-{RUN}"
    answer = idp(
        endpoint, "CreateGroup", UserPoolId=pool_id, GroupName=name, Description="ops"
    )
    assert answer["Group"]["GroupName"] == name
    read = idp(endpoint, "GetGroup", UserPoolId=pool_id, GroupName=name)
    assert read["Group"]["Description"] == "ops"


def test_get_group_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_group(endpoint)
    answer = idp(endpoint, "GetGroup", UserPoolId=pool_id, GroupName=GROUP)
    assert answer["Group"]["GroupName"] == GROUP


def test_list_groups_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_group(endpoint)
    answer = idp(endpoint, "ListGroups", UserPoolId=pool_id)
    assert GROUP in {group["GroupName"] for group in answer["Groups"]}


def test_list_users_in_group_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_member(endpoint)
    answer = idp(endpoint, "ListUsersInGroup", UserPoolId=pool_id, GroupName=GROUP)
    assert USERNAME in {user["Username"] for user in answer["Users"]}


def test_delete_group_removes_it(endpoint):
    pool_id = ensure_pool(endpoint)
    name = f"ops-delete-group-{RUN}"
    idp(endpoint, "CreateGroup", UserPoolId=pool_id, GroupName=name)
    idp(endpoint, "DeleteGroup", UserPoolId=pool_id, GroupName=name)
    status, _text = idp_status(endpoint, "GetGroup", UserPoolId=pool_id, GroupName=name)
    assert status == 400


# --- Domain, UI customisation and managed login branding --------------------


def test_create_and_describe_user_pool_domain(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_domain(endpoint)
    answer = idp(endpoint, "DescribeUserPoolDomain", Domain=DOMAIN)["DomainDescription"]
    assert answer["UserPoolId"] == pool_id
    assert answer["Status"] == "ACTIVE"


def test_update_user_pool_domain_sets_the_version(endpoint):
    ensure_domain(endpoint)
    answer = idp(
        endpoint,
        "UpdateUserPoolDomain",
        UserPoolId=ensure_pool(endpoint),
        Domain=DOMAIN,
        ManagedLoginVersion=2,
    )
    assert answer["ManagedLoginVersion"] == 2
    read = idp(endpoint, "DescribeUserPoolDomain", Domain=DOMAIN)["DomainDescription"]
    assert read["ManagedLoginVersion"] == 2


def test_delete_user_pool_domain_removes_it(endpoint):
    pool_id = idp(endpoint, "CreateUserPool", PoolName=f"ops-cognito-domain-{RUN}")[
        "UserPool"
    ]["Id"]
    domain = f"ops-cognito-domain-{RUN}"
    idp(endpoint, "CreateUserPoolDomain", UserPoolId=pool_id, Domain=domain)
    idp(endpoint, "DeleteUserPoolDomain", UserPoolId=pool_id, Domain=domain)
    answer = idp(endpoint, "DescribeUserPoolDomain", Domain=domain)["DomainDescription"]
    assert answer == {}


def test_set_and_get_ui_customization(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint)
    ensure_domain(endpoint)
    idp(
        endpoint,
        "SetUICustomization",
        UserPoolId=pool_id,
        ClientId=client_id,
        CSS=".banner-customizable { background: #123456; }",
    )
    answer = idp(
        endpoint, "GetUICustomization", UserPoolId=pool_id, ClientId=client_id
    )["UICustomization"]
    assert "banner-customizable" in answer["CSS"]


def test_create_and_describe_managed_login_branding(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id, branding_id = ensure_branding(endpoint)
    read = idp(
        endpoint,
        "DescribeManagedLoginBranding",
        UserPoolId=pool_id,
        ManagedLoginBrandingId=branding_id,
    )["ManagedLoginBranding"]
    assert read["ManagedLoginBrandingId"] == branding_id
    by_client = idp(
        endpoint,
        "DescribeManagedLoginBrandingByClient",
        UserPoolId=pool_id,
        ClientId=client_id,
    )["ManagedLoginBranding"]
    assert by_client["ManagedLoginBrandingId"] == branding_id


def test_update_managed_login_branding_is_accepted(endpoint):
    pool_id = ensure_pool(endpoint)
    _client_id, branding_id = ensure_branding(endpoint)
    answer = idp(
        endpoint,
        "UpdateManagedLoginBranding",
        UserPoolId=pool_id,
        ManagedLoginBrandingId=branding_id,
        UseCognitoProvidedValues=True,
    )
    assert answer["ManagedLoginBranding"]["ManagedLoginBrandingId"] == branding_id


def test_delete_managed_login_branding_removes_it(endpoint):
    pool_id = ensure_pool(endpoint)
    client_id = ensure_client(endpoint, f"ops-cognito-branding-delete-{RUN}", pool_id)
    branding_id = idp(
        endpoint,
        "CreateManagedLoginBranding",
        UserPoolId=pool_id,
        ClientId=client_id,
        UseCognitoProvidedValues=True,
    )["ManagedLoginBranding"]["ManagedLoginBrandingId"]
    idp(
        endpoint,
        "DeleteManagedLoginBranding",
        UserPoolId=pool_id,
        ManagedLoginBrandingId=branding_id,
    )
    status, _text = idp_status(
        endpoint,
        "DescribeManagedLoginBranding",
        UserPoolId=pool_id,
        ManagedLoginBrandingId=branding_id,
    )
    assert status == 400


# --- MFA --------------------------------------------------------------------


def test_get_user_pool_mfa_config_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    answer = idp(endpoint, "GetUserPoolMfaConfig", UserPoolId=pool_id)
    assert answer["MfaConfiguration"] in ("OFF", "OPTIONAL", "ON")


def test_set_user_pool_mfa_config_sets_it(endpoint):
    pool_id = ensure_pool(endpoint)
    idp(
        endpoint,
        "SetUserPoolMfaConfig",
        UserPoolId=pool_id,
        MfaConfiguration="OPTIONAL",
        SoftwareTokenMfaConfiguration={"Enabled": True},
    )
    answer = idp(endpoint, "GetUserPoolMfaConfig", UserPoolId=pool_id)
    assert answer["MfaConfiguration"] == "OPTIONAL"
    assert answer["SoftwareTokenMfaConfiguration"]["Enabled"] is True
    idp(
        endpoint,
        "SetUserPoolMfaConfig",
        UserPoolId=pool_id,
        MfaConfiguration="OFF",
        SoftwareTokenMfaConfiguration={"Enabled": False},
    )


def test_associate_and_verify_software_token(endpoint):
    pool_id = ensure_pool(endpoint)
    username, password = fresh_user(endpoint, "totp")
    token = sign_in(endpoint, username, password)["AccessToken"]
    answer = idp(endpoint, "AssociateSoftwareToken", AccessToken=token)
    secret = answer["SecretCode"]
    idp(
        endpoint,
        "VerifySoftwareToken",
        AccessToken=token,
        Session=answer["Session"],
        UserCode=totp_code(secret),
    )
    read = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)
    assert "SOFTWARE_TOKEN_MFA" in read["UserMFASettingList"]


def test_admin_set_user_mfa_preference(endpoint):
    pool_id = ensure_pool(endpoint)
    username, _password = fresh_user(endpoint, "mfa-admin")
    idp(
        endpoint,
        "AdminSetUserMFAPreference",
        UserPoolId=pool_id,
        Username=username,
        SoftwareTokenMfaSettings={"Enabled": True, "PreferredMfa": True},
    )
    read = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)
    assert read["PreferredMfaSetting"] == "SOFTWARE_TOKEN_MFA"


def test_set_user_mfa_preference(endpoint):
    pool_id = ensure_pool(endpoint)
    username, password = fresh_user(endpoint, "mfa-self")
    token = sign_in(endpoint, username, password)["AccessToken"]
    idp(
        endpoint,
        "SetUserMFAPreference",
        AccessToken=token,
        SoftwareTokenMfaSettings={"Enabled": True},
    )
    read = idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)
    assert "SOFTWARE_TOKEN_MFA" in read["UserMFASettingList"]


# --- Identity providers -----------------------------------------------------


def test_create_identity_provider_answers_it(endpoint):
    pool_id = ensure_pool(endpoint)
    name = f"ops-google-{RUN}"
    answer = idp(
        endpoint,
        "CreateIdentityProvider",
        UserPoolId=pool_id,
        ProviderName=name,
        ProviderType="Google",
        ProviderDetails={"client_id": "ops-google-id", "client_secret": "ops-secret"},
    )
    assert answer["IdentityProvider"]["ProviderName"] == name
    read = idp(
        endpoint, "DescribeIdentityProvider", UserPoolId=pool_id, ProviderName=name
    )
    assert read["IdentityProvider"]["ProviderType"] == "Google"


def test_describe_identity_provider_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_identity_provider(endpoint)
    answer = idp(
        endpoint, "DescribeIdentityProvider", UserPoolId=pool_id, ProviderName=IDP_NAME
    )
    assert answer["IdentityProvider"]["ProviderType"] == "Facebook"


def test_update_identity_provider_sets_details(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_identity_provider(endpoint)
    idp(
        endpoint,
        "UpdateIdentityProvider",
        UserPoolId=pool_id,
        ProviderName=IDP_NAME,
        ProviderDetails={"client_id": "ops-client-id", "client_secret": "ops-new-secret"},
    )
    read = idp(
        endpoint, "DescribeIdentityProvider", UserPoolId=pool_id, ProviderName=IDP_NAME
    )["IdentityProvider"]
    assert read["ProviderDetails"]["client_secret"] == "ops-new-secret"


def test_list_identity_providers_lists_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_identity_provider(endpoint)
    answer = idp(endpoint, "ListIdentityProviders", UserPoolId=pool_id)
    assert IDP_NAME in {provider["ProviderName"] for provider in answer["Providers"]}


def test_get_identity_provider_by_identifier_reads_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_identity_provider(endpoint)
    answer = idp(
        endpoint,
        "GetIdentityProviderByIdentifier",
        UserPoolId=pool_id,
        IdpIdentifier=IDP_IDENTIFIER,
    )
    assert answer["IdentityProvider"]["ProviderName"] == IDP_NAME


def test_admin_link_provider_for_user_links_it(endpoint):
    pool_id = ensure_pool(endpoint)
    ensure_user(endpoint)
    # 1.5.43 checks SourceProviderName against the pool's configured providers.
    ensure_identity_provider(endpoint)
    assert idp(
        endpoint,
        "AdminLinkProviderForUser",
        UserPoolId=pool_id,
        DestinationUser={
            "ProviderName": "Cognito",
            "ProviderAttributeName": "Cognito_Subject",
            "ProviderAttributeValue": USERNAME,
        },
        SourceUser={
            "ProviderName": IDP_NAME,
            "ProviderAttributeName": "Cognito_Subject",
            "ProviderAttributeValue": f"facebook-{RUN}",
        },
    ) == {}


def test_admin_disable_provider_for_user_disables_it(endpoint):
    pool_id = ensure_pool(endpoint)
    username, _password = fresh_user(endpoint, "provider-disabled")
    assert idp(
        endpoint,
        "AdminDisableProviderForUser",
        UserPoolId=pool_id,
        User={
            "ProviderName": "Cognito",
            "ProviderAttributeName": "Cognito_Subject",
            "ProviderAttributeValue": username,
        },
    ) == {}
    assert (
        idp(endpoint, "AdminGetUser", UserPoolId=pool_id, Username=username)["Username"]
        == username
    )


def test_delete_identity_provider_removes_it(endpoint):
    pool_id = ensure_pool(endpoint)
    name = f"ops-delete-idp-{RUN}"
    idp(
        endpoint,
        "CreateIdentityProvider",
        UserPoolId=pool_id,
        ProviderName=name,
        ProviderType="Google",
    )
    idp(endpoint, "DeleteIdentityProvider", UserPoolId=pool_id, ProviderName=name)
    status, _text = idp_status(
        endpoint, "DescribeIdentityProvider", UserPoolId=pool_id, ProviderName=name
    )
    assert status == 400


# --- Identity pools ---------------------------------------------------------


def test_create_identity_pool_answers_it(endpoint):
    answer = identity(
        endpoint,
        "CreateIdentityPool",
        IdentityPoolName=f"ops-cognito-created-identity-{RUN}",
        AllowUnauthenticatedIdentities=True,
    )
    assert answer["IdentityPoolName"] == f"ops-cognito-created-identity-{RUN}"
    read = identity(
        endpoint, "DescribeIdentityPool", IdentityPoolId=answer["IdentityPoolId"]
    )
    assert read["IdentityPoolName"] == answer["IdentityPoolName"]


def test_describe_identity_pool_reads_it(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    answer = identity(endpoint, "DescribeIdentityPool", IdentityPoolId=pool_id)
    assert answer["IdentityPoolName"] == IDENTITY_POOL_NAME


def test_list_identity_pools_lists_it(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    assert pool_id in {pool["IdentityPoolId"] for pool in _all_identity_pools(endpoint)}


def test_update_identity_pool_sets_the_name(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    answer = identity(
        endpoint,
        "UpdateIdentityPool",
        IdentityPoolId=pool_id,
        IdentityPoolName=IDENTITY_POOL_NAME,
        AllowUnauthenticatedIdentities=True,
    )
    assert answer["IdentityPoolName"] == IDENTITY_POOL_NAME


def test_delete_identity_pool_removes_it(endpoint):
    pool_id = identity(
        endpoint,
        "CreateIdentityPool",
        IdentityPoolName=f"ops-cognito-delete-identity-{RUN}",
        AllowUnauthenticatedIdentities=True,
    )["IdentityPoolId"]
    identity(endpoint, "DeleteIdentityPool", IdentityPoolId=pool_id)
    status, _text = _call(
        endpoint,
        "cognito-identity",
        IDENTITY_SERVICE,
        "DescribeIdentityPool",
        {"IdentityPoolId": pool_id},
    )
    assert status == 400


def test_get_id_answers_an_identity(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    answer = identity(endpoint, "GetId", IdentityPoolId=pool_id)
    assert answer["IdentityId"].startswith(f"{REGION}:")


def test_get_credentials_for_identity_answers_credentials(endpoint):
    identity_id = ensure_identity(endpoint)
    answer = identity(endpoint, "GetCredentialsForIdentity", IdentityId=identity_id)
    assert answer["Credentials"]["AccessKeyId"].startswith("ASIA")


def test_get_open_id_token_answers_a_token(endpoint):
    identity_id = ensure_identity(endpoint)
    answer = identity(endpoint, "GetOpenIdToken", IdentityId=identity_id)
    assert answer["Token"]


def test_set_and_get_identity_pool_roles(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    role = f"arn:aws:iam::{ACCOUNT}:role/ops-cognito-identity-role"
    identity(endpoint, "SetIdentityPoolRoles", IdentityPoolId=pool_id, Roles={"unauthenticated": role})
    answer = identity(endpoint, "GetIdentityPoolRoles", IdentityPoolId=pool_id)
    assert answer["Roles"]["unauthenticated"] == role


def test_set_and_get_principal_tag_attribute_map(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    provider = f"graph.facebook.com-{RUN}"
    identity(
        endpoint,
        "SetPrincipalTagAttributeMap",
        IdentityPoolId=pool_id,
        IdentityProviderName=provider,
        UseDefaults=True,
        PrincipalTags={"department": "ops"},
    )
    answer = identity(
        endpoint,
        "GetPrincipalTagAttributeMap",
        IdentityPoolId=pool_id,
        IdentityProviderName=provider,
    )
    assert answer["PrincipalTags"]["department"] == "ops"
    status, _text = _call(
        endpoint,
        "cognito-identity",
        IDENTITY_SERVICE,
        "GetPrincipalTagAttributeMap",
        {"IdentityPoolId": pool_id, "IdentityProviderName": f"never-configured-{RUN}"},
    )
    assert status == 400


def test_list_and_describe_identities(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    identity_id = ensure_identity(endpoint, pool_id)
    listed = identity(endpoint, "ListIdentities", IdentityPoolId=pool_id)
    assert identity_id in {item["IdentityId"] for item in listed["Identities"]}
    described = identity(endpoint, "DescribeIdentity", IdentityId=identity_id)
    assert described["IdentityId"] == identity_id


def test_merge_and_unlink_developer_identities(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    merged = identity(
        endpoint,
        "MergeDeveloperIdentities",
        IdentityPoolId=pool_id,
        SourceUserIdentifier=f"source-{RUN}",
        DestinationUserIdentifier=f"destination-{RUN}",
        DeveloperProviderName="ops.developer",
    )
    assert merged["IdentityId"]
    assert identity(
        endpoint,
        "UnlinkDeveloperIdentity",
        IdentityId=merged["IdentityId"],
        IdentityPoolId=pool_id,
        IdentityProviderName="ops.developer",
        DeveloperProviderName="ops.developer",
        DeveloperUserIdentifier=f"source-{RUN}",
    ) == {}
    identity_id = ensure_identity(endpoint, pool_id)
    assert identity(
        endpoint, "UnlinkIdentity", IdentityId=identity_id, Logins={}
    ) == {}


def test_tag_untag_list_tags_for_identity_pool(endpoint):
    pool_id = ensure_identity_pool(endpoint)
    arn = f"arn:aws:cognito-identity:{REGION}:{ACCOUNT}:identitypool/{pool_id}"
    identity(endpoint, "TagResource", ResourceArn=arn, Tags={"ops": "identity", "keep": "yes"})
    assert identity(endpoint, "ListTagsForResource", ResourceArn=arn)["Tags"]["ops"] == "identity"
    identity(endpoint, "UntagResource", ResourceArn=arn, TagKeys=["ops"])
    tags = identity(endpoint, "ListTagsForResource", ResourceArn=arn)["Tags"]
    assert "ops" not in tags and tags.get("keep") == "yes"


# --- App client secret rotation (1.5.43) ------------------------------------


def secret_client(endpoint) -> tuple[str, str]:
    """A client that carries a secret, which AddUserPoolClientSecret requires."""
    pool_id = ensure_pool(endpoint)
    answer = idp(
        endpoint,
        "CreateUserPoolClient",
        UserPoolId=pool_id,
        ClientName=f"ops-secret-client-{RUN}",
        GenerateSecret=True,
    )
    return pool_id, answer["UserPoolClient"]["ClientId"]


def added_secret(endpoint, pool_id: str, client_id: str) -> dict:
    return idp(
        endpoint, "AddUserPoolClientSecret", UserPoolId=pool_id, ClientId=client_id
    )["ClientSecretDescriptor"]


def test_add_user_pool_client_secret_answers_a_descriptor(endpoint):
    requires("cognito", "AddUserPoolClientSecret")
    pool_id, client_id = secret_client(endpoint)
    descriptor = added_secret(endpoint, pool_id, client_id)
    assert descriptor["ClientSecretId"]
    assert descriptor["ClientSecretValue"]


def test_list_user_pool_client_secrets_lists_it(endpoint):
    requires("cognito", "ListUserPoolClientSecrets")
    pool_id, client_id = secret_client(endpoint)
    descriptor = added_secret(endpoint, pool_id, client_id)
    listed = idp(
        endpoint, "ListUserPoolClientSecrets", UserPoolId=pool_id, ClientId=client_id
    )["ClientSecrets"]
    assert descriptor["ClientSecretId"] in [item["ClientSecretId"] for item in listed]


def test_delete_user_pool_client_secret_removes_it(endpoint):
    requires("cognito", "DeleteUserPoolClientSecret")
    pool_id, client_id = secret_client(endpoint)
    descriptor = added_secret(endpoint, pool_id, client_id)
    idp(
        endpoint,
        "DeleteUserPoolClientSecret",
        UserPoolId=pool_id,
        ClientId=client_id,
        ClientSecretId=descriptor["ClientSecretId"],
    )
    listed = idp(
        endpoint, "ListUserPoolClientSecrets", UserPoolId=pool_id, ClientId=client_id
    )["ClientSecrets"]
    assert descriptor["ClientSecretId"] not in [
        item["ClientSecretId"] for item in listed
    ]
