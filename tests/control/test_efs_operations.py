"""EFS on the wire: all 28 advertised operations, REST/JSON under `/2015-02-01`.

File systems are idempotent on `CreationToken`, so a stable token is how a sweep
meets the file system an earlier one created. Mount targets need a real EC2
subnet; the account's default subnet is used, and a mount target is a record.
Replication needs two file systems with the destination's overwrite protection
`DISABLED`, and the configuration is removed and re-made each sweep.
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
BASE = "/2015-02-01"
JSON = {"Content-Type": "application/json"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
EC2_VERSION = "2016-11-15"

MAIN = "ops-efs-main"
MOUNT = "ops-efs-mount"
ACCESS = "ops-efs-access"
REPL_SOURCE = "ops-efs-repl-source"
REPL_DEST = "ops-efs-repl-dest"

POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "elasticfilesystem:ClientMount",
            }
        ],
    }
)


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, method: str, path: str, body=""):
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return signed.request(
        endpoint, "elasticfilesystem", ACCOUNT, REGION, method, BASE + path, body,
        JSON if body else None,
    )


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = call(endpoint, method, path, body)
    assert status in (200, 201, 202, 204), f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text) if text.strip() else {}


def rejected(endpoint, method: str, path: str, expected: int, body="") -> str:
    status, text = call(endpoint, method, path, body)
    assert status == expected, f"{method} {path} answered {status}: {text[:400]}"
    return text


def ec2_ok(endpoint, action: str, **params) -> str:
    payload = urlencode({"Action": action, "Version": EC2_VERSION, **params})
    status, text = signed.request(endpoint, "ec2", ACCOUNT, REGION, "POST", "/", payload, FORM)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return text


def default_subnet(endpoint) -> str:
    text = ec2_ok(endpoint, "DescribeSubnets")
    found = __import__("re").findall(r"<subnetId>([^<]+)</subnetId>", text)
    assert found, f"no default subnet in {text[:400]}"
    return found[0]


# ---------------------------------------------------------------------------
# Find-or-create
# ---------------------------------------------------------------------------


def ensure_fs(endpoint, token: str, **body) -> str:
    status, text = call(
        endpoint, "POST", "/file-systems", {"CreationToken": token, **body}
    )
    payload = json.loads(text or "{}")
    assert status in (201, 409), f"CreateFileSystem answered {status}: {text[:400]}"
    return payload["FileSystemId"]


def mount_targets(endpoint, fs_id: str) -> list[dict]:
    return ok(endpoint, "GET", f"/mount-targets?FileSystemId={fs_id}")["MountTargets"]


def ensure_mount_target(endpoint, fs_id: str) -> str:
    existing = mount_targets(endpoint, fs_id)
    if existing:
        return existing[0]["MountTargetId"]
    return ok(
        endpoint,
        "POST",
        "/mount-targets",
        {"FileSystemId": fs_id, "SubnetId": default_subnet(endpoint)},
    )["MountTargetId"]


def access_points(endpoint, fs_id: str) -> list[dict]:
    return ok(endpoint, "GET", f"/access-points?FileSystemId={fs_id}")["AccessPoints"]


def ensure_access_point(endpoint, fs_id: str, name: str = "ops-efs-access-point") -> str:
    for ap in access_points(endpoint, fs_id):
        if ap.get("Name") == name:
            return ap["AccessPointId"]
    return ok(
        endpoint,
        "POST",
        "/access-points",
        {"FileSystemId": fs_id, "Tags": [{"Key": "Name", "Value": name}]},
    )["AccessPointId"]


def set_protection(endpoint, fs_id: str, value: str) -> None:
    ok(
        endpoint,
        "PUT",
        f"/file-systems/{fs_id}/protection",
        {"ReplicationOverwriteProtection": value},
    )


def ensure_replication(endpoint) -> str:
    source = ensure_fs(endpoint, REPL_SOURCE)
    dest = ensure_fs(endpoint, REPL_DEST)
    call(endpoint, "DELETE", f"/file-systems/{source}/replication-configuration")
    set_protection(endpoint, dest, "DISABLED")
    ok(
        endpoint,
        "POST",
        f"/file-systems/{source}/replication-configuration",
        {"Destinations": [{"FileSystemId": dest, "Region": REGION}]},
    )
    return source


# ---------------------------------------------------------------------------
# File systems
# ---------------------------------------------------------------------------


def test_create_file_system_answers_the_file_system(endpoint):
    token = f"ops-efs-created-{time.time_ns()}"
    created = ok(
        endpoint,
        "POST",
        "/file-systems",
        {"CreationToken": token, "Tags": [{"Key": "Name", "Value": token}]},
    )
    assert created["FileSystemId"].startswith("fs-")
    assert created["CreationToken"] == token
    assert created["LifeCycleState"] == "available"


def test_describe_file_systems_reads_the_file_system(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    answer = ok(endpoint, "GET", f"/file-systems?FileSystemId={fs_id}")
    assert [item["FileSystemId"] for item in answer["FileSystems"]] == [fs_id]


def test_delete_file_system_removes_the_file_system_it_created(endpoint):
    token = f"ops-efs-deleted-{time.time_ns()}"
    fs_id = ensure_fs(endpoint, token)
    ok(endpoint, "DELETE", f"/file-systems/{fs_id}")
    rejected(endpoint, "GET", f"/file-systems?FileSystemId={fs_id}", 404)


def test_update_file_system_changes_the_throughput_mode(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    updated = ok(
        endpoint, "PUT", f"/file-systems/{fs_id}", {"ThroughputMode": "elastic"}
    )
    assert updated["ThroughputMode"] == "elastic"


# ---------------------------------------------------------------------------
# Mount targets
# ---------------------------------------------------------------------------


def test_create_mount_target_answers_the_target(endpoint):
    fs_id = ensure_fs(endpoint, MOUNT)
    for target in mount_targets(endpoint, fs_id):
        ok(endpoint, "DELETE", f"/mount-targets/{target['MountTargetId']}")
    created = ok(
        endpoint,
        "POST",
        "/mount-targets",
        {"FileSystemId": fs_id, "SubnetId": default_subnet(endpoint)},
    )
    assert created["MountTargetId"].startswith("fsmt-")
    assert created["FileSystemId"] == fs_id
    assert created["IpAddress"]


def test_describe_mount_targets_lists_the_target(endpoint):
    fs_id = ensure_fs(endpoint, MOUNT)
    target = ensure_mount_target(endpoint, fs_id)
    assert target in [item["MountTargetId"] for item in mount_targets(endpoint, fs_id)]


def test_delete_mount_target_removes_the_target_it_created(endpoint):
    fs_id = ensure_fs(endpoint, f"ops-efs-mt-deleted-{time.time_ns()}")
    target = ensure_mount_target(endpoint, fs_id)
    ok(endpoint, "DELETE", f"/mount-targets/{target}")
    rejected(endpoint, "GET", f"/mount-targets?MountTargetId={target}", 404)


def test_describe_mount_target_security_groups_lists_the_groups(endpoint):
    fs_id = ensure_fs(endpoint, MOUNT)
    target = ensure_mount_target(endpoint, fs_id)
    answer = ok(endpoint, "GET", f"/mount-targets/{target}/security-groups")
    assert answer["SecurityGroups"]


def test_modify_mount_target_security_groups_sets_the_groups(endpoint):
    fs_id = ensure_fs(endpoint, MOUNT)
    target = ensure_mount_target(endpoint, fs_id)
    current = ok(endpoint, "GET", f"/mount-targets/{target}/security-groups")["SecurityGroups"]
    ok(
        endpoint,
        "PUT",
        f"/mount-targets/{target}/security-groups",
        {"SecurityGroups": current},
    )
    assert ok(endpoint, "GET", f"/mount-targets/{target}/security-groups")["SecurityGroups"] == current


# ---------------------------------------------------------------------------
# Access points
# ---------------------------------------------------------------------------


def test_create_access_point_answers_the_point(endpoint):
    fs_id = ensure_fs(endpoint, ACCESS)
    for ap in access_points(endpoint, fs_id):
        if ap.get("Name") == "ops-efs-access-created":
            ok(endpoint, "DELETE", f"/access-points/{ap['AccessPointId']}")
    created = ok(
        endpoint,
        "POST",
        "/access-points",
        {"FileSystemId": fs_id, "Tags": [{"Key": "Name", "Value": "ops-efs-access-created"}]},
    )
    assert created["AccessPointId"].startswith("fsap-")
    assert created["FileSystemId"] == fs_id


def test_describe_access_points_lists_the_point(endpoint):
    fs_id = ensure_fs(endpoint, ACCESS)
    point = ensure_access_point(endpoint, fs_id)
    assert point in [ap["AccessPointId"] for ap in access_points(endpoint, fs_id)]


def test_delete_access_point_removes_the_point_it_created(endpoint):
    fs_id = ensure_fs(endpoint, ACCESS)
    name = f"ops-efs-ap-deleted-{time.time_ns()}"
    point = ensure_access_point(endpoint, fs_id, name)
    ok(endpoint, "DELETE", f"/access-points/{point}")
    assert point not in [ap["AccessPointId"] for ap in access_points(endpoint, fs_id)]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_adds_a_tag_the_list_reads_back(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    ok(endpoint, "POST", f"/resource-tags/{fs_id}", {"Tags": [{"Key": "env", "Value": "ops"}]})
    tags = ok(endpoint, "GET", f"/resource-tags/{fs_id}")["Tags"]
    assert {"Key": "env", "Value": "ops"} in tags


def test_untag_resource_removes_the_key_it_names(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    ok(endpoint, "POST", f"/resource-tags/{fs_id}", {"Tags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "DELETE", f"/resource-tags/{fs_id}?tagKeys=doomed")
    assert "doomed" not in {tag["Key"] for tag in ok(endpoint, "GET", f"/resource-tags/{fs_id}")["Tags"]}


def test_list_tags_for_resource_shows_the_tags(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    ok(endpoint, "POST", f"/resource-tags/{fs_id}", {"Tags": [{"Key": "team", "Value": "platform"}]})
    tags = ok(endpoint, "GET", f"/resource-tags/{fs_id}")["Tags"]
    assert {"Key": "team", "Value": "platform"} in tags


# ---------------------------------------------------------------------------
# Lifecycle, backup policy, file system policy, protection
# ---------------------------------------------------------------------------


def test_put_lifecycle_configuration_is_read_back(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    policies = [{"TransitionToIA": "AFTER_30_DAYS"}]
    assert ok(
        endpoint, "PUT", f"/file-systems/{fs_id}/lifecycle-configuration", {"LifecyclePolicies": policies}
    )["LifecyclePolicies"] == policies


def test_describe_lifecycle_configuration_reads_the_policies(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    policies = [{"TransitionToIA": "AFTER_30_DAYS"}]
    ok(endpoint, "PUT", f"/file-systems/{fs_id}/lifecycle-configuration", {"LifecyclePolicies": policies})
    assert ok(endpoint, "GET", f"/file-systems/{fs_id}/lifecycle-configuration")["LifecyclePolicies"] == policies


def test_put_backup_policy_is_read_back(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    assert ok(
        endpoint, "PUT", f"/file-systems/{fs_id}/backup-policy", {"BackupPolicy": {"Status": "ENABLED"}}
    )["BackupPolicy"] == {"Status": "ENABLED"}


def test_describe_backup_policy_reads_the_status(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    ok(endpoint, "PUT", f"/file-systems/{fs_id}/backup-policy", {"BackupPolicy": {"Status": "ENABLED"}})
    assert ok(endpoint, "GET", f"/file-systems/{fs_id}/backup-policy")["BackupPolicy"] == {"Status": "ENABLED"}


def test_put_file_system_policy_is_accepted(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    answer = ok(endpoint, "PUT", f"/file-systems/{fs_id}/policy", {"Policy": POLICY})
    assert answer["FileSystemId"] == fs_id
    assert "ClientMount" in answer["Policy"]


def test_describe_file_system_policy_reads_the_policy(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    ok(endpoint, "PUT", f"/file-systems/{fs_id}/policy", {"Policy": POLICY})
    assert "ClientMount" in ok(endpoint, "GET", f"/file-systems/{fs_id}/policy")["Policy"]


def test_delete_file_system_policy_removes_it(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    ok(endpoint, "PUT", f"/file-systems/{fs_id}/policy", {"Policy": POLICY})
    ok(endpoint, "DELETE", f"/file-systems/{fs_id}/policy")
    rejected(endpoint, "GET", f"/file-systems/{fs_id}/policy", 404)


def test_update_file_system_protection_sets_the_overwrite_protection(endpoint):
    fs_id = ensure_fs(endpoint, MAIN)
    assert ok(
        endpoint,
        "PUT",
        f"/file-systems/{fs_id}/protection",
        {"ReplicationOverwriteProtection": "DISABLED"},
    )["ReplicationOverwriteProtection"] == "DISABLED"
    described = ok(endpoint, "GET", f"/file-systems?FileSystemId={fs_id}")["FileSystems"][0]
    assert described["FileSystemProtection"]["ReplicationOverwriteProtection"] == "DISABLED"
    # Restore the default for the next sweep.
    set_protection(endpoint, fs_id, "ENABLED")


# ---------------------------------------------------------------------------
# Replication
# ---------------------------------------------------------------------------


def test_create_replication_configuration_is_read_back(endpoint):
    source = ensure_replication(endpoint)
    config = ok(endpoint, "GET", f"/file-systems/replication-configurations?FileSystemId={source}")[
        "Replications"
    ][0]
    assert config["SourceFileSystemId"] == source
    assert config["Destinations"][0]["Region"] == REGION


def test_describe_replication_configurations_lists_the_configuration(endpoint):
    source = ensure_replication(endpoint)
    configs = ok(endpoint, "GET", f"/file-systems/replication-configurations?FileSystemId={source}")[
        "Replications"
    ]
    assert [item["SourceFileSystemId"] for item in configs] == [source]


def test_delete_replication_configuration_removes_it(endpoint):
    source = ensure_replication(endpoint)
    ok(endpoint, "DELETE", f"/file-systems/{source}/replication-configuration")
    rejected(
        endpoint,
        "GET",
        f"/file-systems/replication-configurations?FileSystemId={source}",
        404,
    )


# ---------------------------------------------------------------------------
# Account preferences
# ---------------------------------------------------------------------------


def test_describe_account_preferences_reports_the_id_type(endpoint):
    answer = ok(endpoint, "GET", "/account-preferences")
    assert answer["ResourceIdPreference"]["ResourceIdType"] in ("LONG_ID", "SHORT_ID")


def test_put_account_preferences_answers_the_preference(endpoint):
    answer = ok(endpoint, "PUT", "/account-preferences", {"ResourceIdType": "LONG_ID"})
    assert answer["ResourceIdPreference"]["ResourceIdType"] == "LONG_ID"
