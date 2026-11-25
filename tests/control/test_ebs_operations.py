"""EBS on the wire: all 17 advertised operations, served by EC2's Query/XML API.

Volumes and snapshots have no unique name, so they carry a `Name` tag and the
helpers find them again through `DescribeVolumes` / `DescribeSnapshots`. A
create is proven by a read and left in place; a delete action creates a resource
of its own. The attach and detach tests restore the volume to `available`.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

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


def refused(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:400]}"
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


def tagged(resource_type: str, name: str, **params) -> dict:
    return {
        "TagSpecification.1.ResourceType": resource_type,
        "TagSpecification.1.Tag.1.Key": "Name",
        "TagSpecification.1.Tag.1.Value": name,
        **params,
    }


# ---------------------------------------------------------------------------
# Find-or-create
# ---------------------------------------------------------------------------


def ensure_volume(endpoint, name: str, **create) -> str:
    listing = ok(
        endpoint,
        "DescribeVolumes",
        **{"Filter.1.Name": "tag:Name", "Filter.1.Value.1": name},
    )
    found = ids(listing, "volumeId")
    if found:
        return found[0]
    text = ok(
        endpoint,
        "CreateVolume",
        AvailabilityZone=f"{REGION}a",
        Size="8",
        VolumeType="gp3",
        **tagged("volume", name, **create),
    )
    return first_id(text, "volumeId")


def ensure_instance(endpoint, name: str = "ops-ebs-instance") -> str:
    listing = ok(
        endpoint,
        "DescribeInstances",
        **{"Filter.1.Name": "tag:Name", "Filter.1.Value.1": name},
    )
    found = ids(listing, "instanceId")
    if found:
        return found[0]
    text = ok(
        endpoint,
        "RunInstances",
        ImageId=AMI,
        InstanceType="t3.micro",
        MinCount="1",
        MaxCount="1",
        **tagged("instance", name),
    )
    return first_id(text, "instanceId")


def ensure_snapshot(endpoint, name: str = "ops-ebs-snapshot") -> str:
    listing = ok(
        endpoint,
        "DescribeSnapshots",
        **{"Filter.1.Name": "tag:Name", "Filter.1.Value.1": name},
    )
    found = ids(listing, "snapshotId")
    if found:
        return found[0]
    volume = ensure_volume(endpoint, "ops-ebs-snapshot-volume")
    text = ok(
        endpoint,
        "CreateSnapshot",
        VolumeId=volume,
        Description=name,
        **tagged("snapshot", name),
    )
    return first_id(text, "snapshotId")


def attached(endpoint, volume_id: str) -> bool:
    listing = ok(endpoint, "DescribeVolumes", **{"VolumeId.1": volume_id})
    return field(listing, "status") == "in-use"


# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------


def test_create_volume_answers_an_available_volume(endpoint):
    name = f"ops-ebs-created-{time.time_ns()}"
    text = ok(
        endpoint,
        "CreateVolume",
        AvailabilityZone=f"{REGION}a",
        Size="8",
        VolumeType="gp3",
        **tagged("volume", name),
    )
    assert first_id(text, "volumeId").startswith("vol-")
    assert field(text, "size") == "8"
    assert field(text, "volumeType") == "gp3"
    assert field(text, "status") == "available"


def test_delete_volume_removes_the_volume_it_created(endpoint):
    text = ok(
        endpoint,
        "CreateVolume",
        AvailabilityZone=f"{REGION}a",
        Size="8",
        **tagged("volume", f"ops-ebs-deleted-{time.time_ns()}"),
    )
    volume = first_id(text, "volumeId")
    assert field(ok(endpoint, "DeleteVolume", VolumeId=volume), "return") == "true"
    text = refused(endpoint, "DescribeVolumes", **{"VolumeId.1": volume})
    assert "InvalidVolume.NotFound" in text


def test_describe_volumes_reads_the_volume_by_id(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-described")
    text = ok(endpoint, "DescribeVolumes", **{"VolumeId.1": volume})
    assert volume in ids(text, "volumeId")
    assert field(text, "status") == "available"


def test_describe_volume_status_reports_ok(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-status")
    text = ok(endpoint, "DescribeVolumeStatus", **{"VolumeId.1": volume})
    assert volume in ids(text, "volumeId")
    assert field(text, "status") == "ok"


def test_attach_volume_marks_it_in_use(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-attach")
    instance = ensure_instance(endpoint)
    text = ok(endpoint, "AttachVolume", VolumeId=volume, InstanceId=instance, Device="/dev/xvdf")
    assert field(text, "status") == "attached"
    assert attached(endpoint, volume)
    # Restore the volume for the next sweep.
    ok(endpoint, "DetachVolume", VolumeId=volume)


def test_detach_volume_returns_it_to_available(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-detach")
    instance = ensure_instance(endpoint)
    ok(endpoint, "AttachVolume", VolumeId=volume, InstanceId=instance, Device="/dev/xvdf")
    text = ok(endpoint, "DetachVolume", VolumeId=volume)
    assert field(text, "status") == "detached"
    assert not attached(endpoint, volume)


def test_modify_volume_is_read_back_by_describe(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-modify")
    text = ok(endpoint, "ModifyVolume", VolumeId=volume, Size="16", VolumeType="gp3")
    assert field(text, "modificationState") == "completed"
    assert field(text, "targetSize") == "16"
    assert field(ok(endpoint, "DescribeVolumes", **{"VolumeId.1": volume}), "size") == "16"


def test_describe_volumes_modifications_lists_the_volume(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-modifications")
    ok(endpoint, "ModifyVolume", VolumeId=volume, Size="16")
    text = ok(endpoint, "DescribeVolumesModifications", **{"VolumeId.1": volume})
    assert volume in ids(text, "volumeId")
    assert field(text, "modificationState") == "completed"


def test_enable_volume_io_answers_true(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-io")
    assert field(ok(endpoint, "EnableVolumeIO", VolumeId=volume), "return") == "true"


def test_modify_volume_attribute_sets_auto_enable_io(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-attr")
    ok(endpoint, "ModifyVolumeAttribute", VolumeId=volume, **{"AutoEnableIO.Value": "true"})
    text = ok(endpoint, "DescribeVolumeAttribute", VolumeId=volume)
    assert field(text, "value") == "true"


def test_describe_volume_attribute_reads_auto_enable_io(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-attr-read")
    text = ok(endpoint, "DescribeVolumeAttribute", VolumeId=volume)
    assert volume in ids(text, "volumeId")
    assert field(text, "value") in ("true", "false")


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def test_create_snapshot_is_completed_immediately(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-snapshot-volume")
    text = ok(
        endpoint,
        "CreateSnapshot",
        VolumeId=volume,
        Description=f"ops snapshot {time.time_ns()}",
        **tagged("snapshot", f"ops-ebs-created-snapshot-{time.time_ns()}"),
    )
    assert first_id(text, "snapshotId").startswith("snap-")
    assert field(text, "status") == "completed"
    assert field(text, "progress") == "100%"


def test_delete_snapshot_removes_the_snapshot_it_created(endpoint):
    volume = ensure_volume(endpoint, "ops-ebs-snapshot-volume")
    snapshot = first_id(
        ok(
            endpoint,
            "CreateSnapshot",
            VolumeId=volume,
            **tagged("snapshot", f"ops-ebs-deleted-snapshot-{time.time_ns()}"),
        ),
        "snapshotId",
    )
    assert field(ok(endpoint, "DeleteSnapshot", SnapshotId=snapshot), "return") == "true"
    text = refused(endpoint, "DescribeSnapshots", **{"SnapshotId.1": snapshot})
    assert "InvalidSnapshot.NotFound" in text


def test_describe_snapshots_reads_the_snapshot_by_id(endpoint):
    snapshot = ensure_snapshot(endpoint)
    text = ok(endpoint, "DescribeSnapshots", **{"SnapshotId.1": snapshot})
    assert snapshot in ids(text, "snapshotId")
    assert field(text, "status") == "completed"


def test_copy_snapshot_answers_a_new_snapshot(endpoint):
    source = ensure_snapshot(endpoint)
    name = "ops-ebs-copied-snapshot"
    listing = ok(
        endpoint,
        "DescribeSnapshots",
        **{"Filter.1.Name": "tag:Name", "Filter.1.Value.1": name},
    )
    found = ids(listing, "snapshotId")
    if found:
        copied = found[0]
    else:
        copied = first_id(
            ok(
                endpoint,
                "CopySnapshot",
                SourceSnapshotId=source,
                Description="ops copy",
                **tagged("snapshot", name),
            ),
            "snapshotId",
        )
    assert copied != source
    same = ok(endpoint, "DescribeSnapshots", **{"SnapshotId.1": copied})
    assert copied in ids(same, "snapshotId")
    assert field(same, "status") == "completed"


def test_modify_snapshot_attribute_adds_a_create_volume_permission(endpoint):
    snapshot = ensure_snapshot(endpoint)
    ok(
        endpoint,
        "ModifySnapshotAttribute",
        SnapshotId=snapshot,
        OperationType="add",
        **{"UserGroup.1": "all"},
    )
    text = ok(endpoint, "DescribeSnapshotAttribute", SnapshotId=snapshot, Attribute="createVolumePermission")
    assert "all" in ids(text, "group")
    # Restore the snapshot for the next sweep.
    ok(
        endpoint,
        "ModifySnapshotAttribute",
        SnapshotId=snapshot,
        OperationType="remove",
        **{"UserGroup.1": "all"},
    )


def test_describe_snapshot_attribute_lists_the_permissions(endpoint):
    snapshot = ensure_snapshot(endpoint)
    text = ok(endpoint, "DescribeSnapshotAttribute", SnapshotId=snapshot, Attribute="createVolumePermission")
    assert snapshot in ids(text, "snapshotId")
    assert "createVolumePermission" in text
