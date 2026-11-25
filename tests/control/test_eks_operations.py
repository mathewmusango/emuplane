"""EKS on the wire: all 34 advertised operations, REST/JSON under `/clusters`.

A cluster is a record; without Docker the k3s container is skipped and the
cluster settles `ACTIVE`, so nothing here needs a daemon. Stable names carry
the read and modify tests; every delete test creates a resource of its own.
Two clusters exist because the API allows one encryption configuration and one
OIDC identity provider per cluster, so each of those lives on its own.
"""

from __future__ import annotations

import json
from urllib.parse import quote, urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
IAM_VERSION = "2010-05-08"
ROLE_NAME = "ops-eks-role"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"

CLUSTER = "ops-eks-cluster"
ENCRYPTION_CLUSTER = "ops-eks-encryption"
IDP_CLUSTER = "ops-eks-idp"

NODEGROUP = "ops-eks-nodegroup"
ADDON = "vpc-cni"
PRINCIPAL = f"arn:aws:iam::{ACCOUNT}:role/ops-eks-developer"
POLICY = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
VIEW_POLICY = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
IDP_NAME = "ops-eks-oidc"


def call(endpoint, method: str, path: str, body=None):
    payload = json.dumps(body) if body is not None else ""
    return signed.request(
        endpoint, "eks", ACCOUNT, REGION, method, path, payload, JSON if payload else None
    )


def ok(endpoint, method: str, path: str, body=None) -> dict:
    status, text = call(endpoint, method, path, body)
    assert status == 200, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def created(endpoint, method: str, path: str, body=None) -> tuple[int, str]:
    """A create is idempotent across sweeps: an existing record is not a failure."""
    status, text = call(endpoint, method, path, body)
    assert status == 200 or "ResourceInUseException" in text, (
        f"{method} {path} answered {status}: {text[:400]}"
    )
    return status, text


def ensure_role(endpoint) -> None:
    """A live emulator enforces the cluster role; in-process `AUTH` is off, and this is a no-op create."""
    trust = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "eks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )
    body = urlencode(
        {
            "Action": "CreateRole",
            "Version": IAM_VERSION,
            "RoleName": ROLE_NAME,
            "AssumeRolePolicyDocument": trust,
        }
    )
    status, text = signed.request(
        endpoint, "iam", ACCOUNT, REGION, "POST", "/", body, FORM
    )
    assert status == 200 or "EntityAlreadyExists" in text, text[:300]


def arn(name: str) -> str:
    return f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/{name}"


def ensure_cluster(endpoint, name: str = CLUSTER) -> dict:
    ensure_role(endpoint)
    status, text = created(
        endpoint,
        "POST",
        "/clusters",
        {"name": name, "roleArn": ROLE, "resourcesVpcConfig": {}},
    )
    return json.loads(text or "{}")["cluster"] if status == 200 else ok(
        endpoint, "GET", f"/clusters/{name}"
    )["cluster"]


def ensure_nodegroup(endpoint, cluster: str = CLUSTER, name: str = NODEGROUP) -> dict:
    ensure_cluster(endpoint, cluster)
    status, text = created(
        endpoint,
        "POST",
        f"/clusters/{cluster}/node-groups",
        {"nodegroupName": name, "nodeRole": ROLE, "subnets": ["subnet-00000001"]},
    )
    if status != 200:
        return ok(endpoint, "GET", f"/clusters/{cluster}/node-groups/{name}")["nodegroup"]
    return json.loads(text)["nodegroup"]


def ensure_addon(endpoint, cluster: str = CLUSTER, name: str = ADDON) -> dict:
    ensure_cluster(endpoint, cluster)
    status, text = created(
        endpoint, "POST", f"/clusters/{cluster}/addons", {"addonName": name}
    )
    if status != 200:
        return ok(endpoint, "GET", f"/clusters/{cluster}/addons/{name}")["addon"]
    return json.loads(text)["addon"]


def ensure_access_entry(endpoint, principal: str = PRINCIPAL) -> dict:
    ensure_cluster(endpoint)
    status, text = created(
        endpoint,
        "POST",
        f"/clusters/{CLUSTER}/access-entries",
        {"principalArn": principal, "kubernetesGroups": ["ops-developers"]},
    )
    if status != 200:
        return ok(
            endpoint, "GET", f"/clusters/{CLUSTER}/access-entries/{quote(principal, safe='')}"
        )["accessEntry"]
    return json.loads(text)["accessEntry"]


def ensure_pod_identity(endpoint, cluster: str, namespace: str, service_account: str) -> dict:
    ensure_cluster(endpoint, cluster)
    status, text = created(
        endpoint,
        "POST",
        f"/clusters/{cluster}/pod-identity-associations",
        {"namespace": namespace, "serviceAccount": service_account, "roleArn": ROLE},
    )
    if status == 200:
        return json.loads(text)["association"]
    listed = ok(endpoint, "GET", f"/clusters/{cluster}/pod-identity-associations")
    for item in listed["associations"]:
        if item["namespace"] == namespace and item["serviceAccount"] == service_account:
            return ok(
                endpoint,
                "GET",
                f"/clusters/{cluster}/pod-identity-associations/{item['associationId']}",
            )["association"]
    raise AssertionError("association listed neither by create nor by list")


# --- Clusters ---------------------------------------------------------------


def test_create_cluster_is_read_back(endpoint):
    cluster = ensure_cluster(endpoint, "ops-eks-create")
    assert cluster["name"] == "ops-eks-create"
    assert cluster["status"] in ("CREATING", "ACTIVE")
    assert cluster["arn"] == arn("ops-eks-create")


def test_describe_cluster_reports_the_oidc_issuer(endpoint):
    ensure_cluster(endpoint)
    cluster = ok(endpoint, "GET", f"/clusters/{CLUSTER}")["cluster"]
    assert cluster["identity"]["oidc"]["issuer"]


def test_list_clusters_includes_the_cluster(endpoint):
    ensure_cluster(endpoint)
    assert CLUSTER in ok(endpoint, "GET", "/clusters")["clusters"]


def test_delete_cluster_removes_it(endpoint):
    name = "ops-eks-delete"
    ensure_cluster(endpoint, name)
    deleted = ok(endpoint, "DELETE", f"/clusters/{name}")["cluster"]
    assert deleted["status"] == "DELETING"
    status, text = call(endpoint, "GET", f"/clusters/{name}")
    assert status == 404, text[:300]


# --- Nodegroups -------------------------------------------------------------


def test_create_nodegroup_is_read_back(endpoint):
    nodegroup = ensure_nodegroup(endpoint)
    assert nodegroup["nodegroupName"] == NODEGROUP
    assert nodegroup["clusterName"] == CLUSTER
    assert nodegroup["status"] == "ACTIVE"


def test_describe_nodegroup_reports_its_scaling(endpoint):
    ensure_nodegroup(endpoint)
    nodegroup = ok(endpoint, "GET", f"/clusters/{CLUSTER}/node-groups/{NODEGROUP}")["nodegroup"]
    assert nodegroup["scalingConfig"]["desiredSize"] >= 1


def test_list_nodegroups_names_the_nodegroup(endpoint):
    ensure_nodegroup(endpoint)
    assert NODEGROUP in ok(endpoint, "GET", f"/clusters/{CLUSTER}/node-groups")["nodegroups"]


def test_delete_nodegroup_removes_it(endpoint):
    name = "ops-eks-ng-delete"
    ensure_nodegroup(endpoint, CLUSTER, name)
    ok(endpoint, "DELETE", f"/clusters/{CLUSTER}/node-groups/{name}")
    status, text = call(endpoint, "GET", f"/clusters/{CLUSTER}/node-groups/{name}")
    assert status == 404, text[:300]


# --- Addons -----------------------------------------------------------------


def test_create_addon_is_read_back(endpoint):
    addon = ensure_addon(endpoint)
    assert addon["addonName"] == ADDON
    assert addon["clusterName"] == CLUSTER
    assert addon["status"] == "ACTIVE"


def test_describe_addon_reports_its_arn(endpoint):
    ensure_addon(endpoint)
    addon = ok(endpoint, "GET", f"/clusters/{CLUSTER}/addons/{ADDON}")["addon"]
    assert f"addon/{CLUSTER}/{ADDON}" in addon["addonArn"]


def test_list_addons_names_the_addon(endpoint):
    ensure_addon(endpoint)
    assert ADDON in ok(endpoint, "GET", f"/clusters/{CLUSTER}/addons")["addons"]


def test_update_addon_sets_the_version(endpoint):
    ensure_addon(endpoint)
    ok(
        endpoint,
        "POST",
        f"/clusters/{CLUSTER}/addons/{ADDON}/update",
        {"addonVersion": "v1.19.0-eksbuild.1"},
    )
    addon = ok(endpoint, "GET", f"/clusters/{CLUSTER}/addons/{ADDON}")["addon"]
    assert addon["addonVersion"] == "v1.19.0-eksbuild.1"


def test_delete_addon_removes_it(endpoint):
    name = "ops-eks-addon-delete"
    ensure_addon(endpoint, CLUSTER, name)
    assert ok(endpoint, "DELETE", f"/clusters/{CLUSTER}/addons/{name}")["addon"]["status"] == "DELETING"
    status, text = call(endpoint, "GET", f"/clusters/{CLUSTER}/addons/{name}")
    assert status == 404, text[:300]


# --- Encryption -------------------------------------------------------------


def test_associate_encryption_config_is_recorded(endpoint):
    ensure_cluster(endpoint, ENCRYPTION_CLUSTER)
    config = [{"resources": ["secrets"], "provider": {"keyArn": f"arn:aws:kms:{REGION}:{ACCOUNT}:key/00000000-0000-0000-0000-000000000001"}}]
    status, text = call(
        endpoint,
        "POST",
        f"/clusters/{ENCRYPTION_CLUSTER}/encryption-config/associate",
        {"encryptionConfig": config},
    )
    assert status == 200 or "already has encryption configuration" in text, text[:300]
    described = ok(endpoint, "GET", f"/clusters/{ENCRYPTION_CLUSTER}")["cluster"]
    assert described["encryptionConfig"][0]["resources"] == ["secrets"]


# --- Access entries ---------------------------------------------------------


def test_create_access_entry_is_read_back(endpoint):
    entry = ensure_access_entry(endpoint)
    assert entry["principalArn"] == PRINCIPAL
    assert entry["kubernetesGroups"] == ["ops-developers"]


def test_describe_access_entry_reports_its_type(endpoint):
    ensure_access_entry(endpoint)
    entry = ok(
        endpoint, "GET", f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}"
    )["accessEntry"]
    assert entry["type"] == "STANDARD"


def test_list_access_entries_includes_the_principal(endpoint):
    ensure_access_entry(endpoint)
    listed = ok(endpoint, "GET", f"/clusters/{CLUSTER}/access-entries")["accessEntries"]
    assert PRINCIPAL in listed


def test_update_access_entry_sets_the_username(endpoint):
    ensure_access_entry(endpoint)
    entry = ok(
        endpoint,
        "POST",
        f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}",
        {"username": "ops-developer", "kubernetesGroups": ["ops-developers", "ops-admins"]},
    )["accessEntry"]
    assert entry["username"] == "ops-developer"
    assert "ops-admins" in entry["kubernetesGroups"]


def test_delete_access_entry_removes_it(endpoint):
    principal = f"arn:aws:iam::{ACCOUNT}:role/ops-eks-gone"
    ensure_access_entry(endpoint, principal)
    ok(endpoint, "DELETE", f"/clusters/{CLUSTER}/access-entries/{quote(principal, safe='')}")
    status, text = call(endpoint, "GET", f"/clusters/{CLUSTER}/access-entries/{quote(principal, safe='')}")
    assert status == 404, text[:300]


# --- Access policies --------------------------------------------------------


def test_associate_access_policy_is_listed(endpoint):
    ensure_access_entry(endpoint)
    ok(
        endpoint,
        "POST",
        f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}/access-policies",
        {"policyArn": POLICY, "accessScope": {"type": "cluster"}},
    )
    listed = ok(
        endpoint, "GET", f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}/access-policies"
    )["associatedAccessPolicies"]
    assert any(item["policyArn"] == POLICY for item in listed)


def test_list_associated_access_policies_names_the_scope(endpoint):
    ensure_access_entry(endpoint)
    ensure_policy(endpoint, POLICY)
    listed = ok(
        endpoint, "GET", f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}/access-policies"
    )["associatedAccessPolicies"]
    assert listed[0]["accessScope"]["type"] in ("cluster", "namespace")


def ensure_policy(endpoint, policy_arn: str, scope: str = "cluster") -> None:
    access_scope = {"type": scope}
    if scope == "namespace":
        access_scope["namespaces"] = ["ops"]
    ok(
        endpoint,
        "POST",
        f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}/access-policies",
        {"policyArn": policy_arn, "accessScope": access_scope},
    )


def test_disassociate_access_policy_removes_it(endpoint):
    ensure_access_entry(endpoint)
    ensure_policy(endpoint, VIEW_POLICY, "namespace")
    ok(
        endpoint,
        "DELETE",
        f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}"
        f"/access-policies/{quote(VIEW_POLICY, safe='')}",
    )
    listed = ok(
        endpoint, "GET", f"/clusters/{CLUSTER}/access-entries/{quote(PRINCIPAL, safe='')}/access-policies"
    )["associatedAccessPolicies"]
    assert all(item["policyArn"] != VIEW_POLICY for item in listed)


# --- Identity provider configs ----------------------------------------------


def ensure_idp(endpoint) -> str:
    ensure_cluster(endpoint, IDP_CLUSTER)
    status, text = call(
        endpoint,
        "POST",
        f"/clusters/{IDP_CLUSTER}/identity-provider-configs/associate",
        {
            "oidc": {
                "identityProviderConfigName": IDP_NAME,
                "issuerUrl": "https://oidc.example.com/ops",
                "clientId": "ops-client-id",
            }
        },
    )
    assert status == 200 or "already has an OIDC identity provider" in text, text[:300]
    if status == 200:
        return IDP_NAME
    listed = ok(endpoint, "GET", f"/clusters/{IDP_CLUSTER}/identity-provider-configs")[
        "identityProviderConfigs"
    ]
    return listed[0]["name"]


def test_associate_identity_provider_config_is_recorded(endpoint):
    name = ensure_idp(endpoint)
    assert name == IDP_NAME


def test_describe_identity_provider_config_reports_the_issuer(endpoint):
    name = ensure_idp(endpoint)
    described = ok(
        endpoint,
        "POST",
        f"/clusters/{IDP_CLUSTER}/identity-provider-configs/describe",
        {"identityProviderConfig": {"name": name, "type": "oidc"}},
    )["identityProviderConfig"]["oidc"]
    assert described["issuerUrl"] == "https://oidc.example.com/ops"


def test_list_identity_provider_configs_names_the_config(endpoint):
    name = ensure_idp(endpoint)
    listed = ok(endpoint, "GET", f"/clusters/{IDP_CLUSTER}/identity-provider-configs")[
        "identityProviderConfigs"
    ]
    assert {"name": name, "type": "oidc"} in listed


def test_disassociate_identity_provider_config_removes_it(endpoint):
    name = ensure_idp(endpoint)
    ok(
        endpoint,
        "POST",
        f"/clusters/{IDP_CLUSTER}/identity-provider-configs/disassociate",
        {"identityProviderConfig": {"name": name, "type": "oidc"}},
    )
    listed = ok(endpoint, "GET", f"/clusters/{IDP_CLUSTER}/identity-provider-configs")[
        "identityProviderConfigs"
    ]
    assert all(item["name"] != name for item in listed)


# --- Pod identity associations ----------------------------------------------


def test_create_pod_identity_association_is_read_back(endpoint):
    association = ensure_pod_identity(endpoint, CLUSTER, "ops-pods", "ops-worker")
    assert association["namespace"] == "ops-pods"
    assert association["serviceAccount"] == "ops-worker"
    assert association["associationId"].startswith("a-")


def test_describe_pod_identity_association_reports_its_role(endpoint):
    association = ensure_pod_identity(endpoint, CLUSTER, "ops-pods", "ops-worker")
    described = ok(
        endpoint,
        "GET",
        f"/clusters/{CLUSTER}/pod-identity-associations/{association['associationId']}",
    )["association"]
    assert described["roleArn"] == ROLE


def test_list_pod_identity_associations_filters_by_namespace(endpoint):
    ensure_pod_identity(endpoint, CLUSTER, "ops-pods", "ops-worker")
    listed = ok(
        endpoint, "GET", f"/clusters/{CLUSTER}/pod-identity-associations?namespace=ops-pods"
    )["associations"]
    assert any(item["serviceAccount"] == "ops-worker" for item in listed)


def test_update_pod_identity_association_sets_the_role(endpoint):
    association = ensure_pod_identity(endpoint, CLUSTER, "ops-pods", "ops-worker")
    updated = ok(
        endpoint,
        "POST",
        f"/clusters/{CLUSTER}/pod-identity-associations/{association['associationId']}",
        {"roleArn": f"arn:aws:iam::{ACCOUNT}:role/ops-eks-role-updated"},
    )["association"]
    assert updated["roleArn"].endswith("ops-eks-role-updated")


def test_delete_pod_identity_association_removes_it(endpoint):
    association = ensure_pod_identity(endpoint, CLUSTER, "ops-pods", "ops-delete")
    ok(
        endpoint,
        "DELETE",
        f"/clusters/{CLUSTER}/pod-identity-associations/{association['associationId']}",
    )
    status, text = call(
        endpoint, "GET", f"/clusters/{CLUSTER}/pod-identity-associations/{association['associationId']}"
    )
    assert status == 404, text[:300]


# --- Tags -------------------------------------------------------------------


def test_tag_resource_adds_a_tag(endpoint):
    ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/tags/{quote(arn(CLUSTER), safe='')}", {"tags": {"team": "ops"}})
    assert ok(endpoint, "GET", f"/tags/{quote(arn(CLUSTER), safe='')}")["tags"]["team"] == "ops"


def test_list_tags_for_resource_reports_the_cluster_arn(endpoint):
    ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/tags/{quote(arn(CLUSTER), safe='')}", {"tags": {"env": "test"}})
    tags = ok(endpoint, "GET", f"/tags/{quote(arn(CLUSTER), safe='')}")["tags"]
    assert tags["env"] == "test"


def test_untag_resource_removes_the_key(endpoint):
    ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/tags/{quote(arn(CLUSTER), safe='')}", {"tags": {"temporary": "yes"}})
    ok(endpoint, "DELETE", f"/tags/{quote(arn(CLUSTER), safe='')}?tagKeys=temporary")
    assert "temporary" not in ok(endpoint, "GET", f"/tags/{quote(arn(CLUSTER), safe='')}")["tags"]
