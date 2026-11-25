"""S3 Files on the wire: every operation the emulator advertises, driven through its REST surface.

A file system created here is left in place; the delete actions each make their own
resource to remove. `ListFileSystems` is covered by `test_children.py`.
"""

from __future__ import annotations

import json
import os

import signed

ACCOUNT = os.environ.get("EP_LAB_ACCOUNT") or "344381301567"
REGION = "us-east-1"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/s3files"


def call(endpoint, method: str, path: str, body=None):
    payload = json.dumps(body) if body is not None else ""
    return signed.request(endpoint, "s3files", ACCOUNT, REGION, method, path, payload)


def ok(endpoint, method: str, path: str, body=None):
    status, text = call(endpoint, method, path, body)
    assert 200 <= status < 300, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text) if text else {}


def file_system(endpoint, bucket: str) -> str:
    created = ok(endpoint, "PUT", "/file-systems", {"bucket": bucket, "roleArn": ROLE})
    return created["fileSystemId"]


def test_create_file_system_is_read_back_by_get_and_list(s3_endpoint):
    fs_id = file_system(s3_endpoint, "ops-s3files-created")
    read = ok(s3_endpoint, "GET", f"/file-systems/{fs_id}")
    assert read["fileSystemId"] == fs_id
    assert read["bucket"] == "ops-s3files-created"
    listed = ok(s3_endpoint, "GET", "/file-systems?bucket=ops-s3files-created")
    assert fs_id in [system["fileSystemId"] for system in listed["fileSystems"]]


def test_file_system_policy_is_put_read_and_deleted(s3_endpoint):
    fs_id = file_system(s3_endpoint, "ops-s3files-policy")
    policy = json.dumps({"Version": "2012-10-17", "Statement": []})
    ok(s3_endpoint, "PUT", f"/file-systems/{fs_id}/policy", {"policy": policy})
    assert ok(s3_endpoint, "GET", f"/file-systems/{fs_id}/policy")["policy"] == policy

    ok(s3_endpoint, "DELETE", f"/file-systems/{fs_id}/policy")
    status, _text = call(s3_endpoint, "GET", f"/file-systems/{fs_id}/policy")
    assert status == 404


def test_synchronization_configuration_is_put_and_read(s3_endpoint):
    fs_id = file_system(s3_endpoint, "ops-s3files-sync")
    rules = {
        "expirationDataRules": [{"daysAfterLastAccess": 30}],
        "importDataRules": [{"trigger": "onFileCreated"}],
    }
    ok(s3_endpoint, "PUT", f"/file-systems/{fs_id}/synchronization-configuration", rules)
    read = ok(s3_endpoint, "GET", f"/file-systems/{fs_id}/synchronization-configuration")
    assert read["expirationDataRules"] == rules["expirationDataRules"]


def test_mount_target_lifecycle(s3_endpoint):
    fs_id = file_system(s3_endpoint, "ops-s3files-mounts")
    created = ok(
        s3_endpoint,
        "PUT",
        "/mount-targets",
        {"fileSystemId": fs_id, "subnetId": "subnet-0123456789abcdef0"},
    )
    mt_id = created["mountTargetId"]
    assert ok(s3_endpoint, "GET", f"/mount-targets/{mt_id}")["fileSystemId"] == fs_id
    listed = ok(s3_endpoint, "GET", f"/mount-targets?fileSystemId={fs_id}")
    assert mt_id in [item["mountTargetId"] for item in listed["mountTargets"]]

    updated = ok(
        s3_endpoint,
        "PUT",
        f"/mount-targets/{mt_id}",
        {"securityGroups": ["sg-0123456789abcdef0"]},
    )
    assert updated["securityGroups"] == ["sg-0123456789abcdef0"]

    ok(s3_endpoint, "DELETE", f"/mount-targets/{mt_id}")
    assert call(s3_endpoint, "GET", f"/mount-targets/{mt_id}")[0] == 404


def test_access_point_lifecycle(s3_endpoint):
    fs_id = file_system(s3_endpoint, "ops-s3files-points")
    created = ok(
        s3_endpoint,
        "PUT",
        "/access-points",
        {"fileSystemId": fs_id, "tags": [{"key": "Name", "value": "ops-point"}]},
    )
    ap_id = created["accessPointId"]
    assert ok(s3_endpoint, "GET", f"/access-points/{ap_id}")["fileSystemId"] == fs_id
    listed = ok(s3_endpoint, "GET", f"/access-points?fileSystemId={fs_id}")
    assert ap_id in [item["accessPointId"] for item in listed["accessPoints"]]

    ok(s3_endpoint, "DELETE", f"/access-points/{ap_id}")
    assert call(s3_endpoint, "GET", f"/access-points/{ap_id}")[0] == 404


def test_tags_are_tagged_listed_and_untagged(s3_endpoint):
    fs_id = file_system(s3_endpoint, "ops-s3files-tags")
    ok(s3_endpoint, "POST", f"/resource-tags/{fs_id}", {"tags": [{"key": "env", "value": "lab"}]})
    listed = ok(s3_endpoint, "GET", f"/resource-tags/{fs_id}")
    assert {"key": "env", "value": "lab"} in listed["tags"]

    ok(s3_endpoint, "DELETE", f"/resource-tags/{fs_id}?tagKeys=env")
    assert "env" not in [tag["key"] for tag in ok(s3_endpoint, "GET", f"/resource-tags/{fs_id}")["tags"]]


def test_delete_file_system_removes_the_file_system_it_created(s3_endpoint):
    fs_id = file_system(s3_endpoint, "ops-s3files-deleted")
    ok(s3_endpoint, "DELETE", f"/file-systems/{fs_id}")
    assert call(s3_endpoint, "GET", f"/file-systems/{fs_id}")[0] == 404
