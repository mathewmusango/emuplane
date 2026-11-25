"""ECS Task Metadata V4 on the wire: the four routes a task's own container calls.

The routes are keyed by a per-container token that a real ECS task receives in
`ECS_CONTAINER_METADATA_URI_V4`; the emulator registers it from `services/ecs.py`
when the container starts. A test process is not inside that container, so the
suite registers a token through the emulator's own `register_container` — the
same call, with the same payloads — and then asks over HTTP. On a live lab the
token belongs to the emulator's process, so these tests skip there.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest
from conftest import ACCOUNT

REGION = "us-east-1"
TOKEN = "opsmetadata0token"
TASK = f"arn:aws:ecs:{REGION}:{ACCOUNT}:task/ops-metadata-cluster/ops-metadata-task"
_CLUSTER = f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/ops-metadata-cluster"
_seeded = False


def seed() -> None:
    """Register the token the container runtime would have injected, once per process."""
    global _seeded
    if _seeded:
        return
    from ministack.services import ecs_metadata  # noqa: PLC0415 - the emulator's own registration call

    ecs_metadata.register_container(
        TOKEN,
        TASK,
        task_payload={
            "Cluster": _CLUSTER,
            "TaskARN": TASK,
            "Family": "ops-metadata",
            "Revision": "1",
            "DesiredStatus": "RUNNING",
            "KnownStatus": "RUNNING",
            "AvailabilityZone": f"{REGION}a",
            "LaunchType": "EC2",
        },
        container_payload={
            "DockerId": "0123456789ab",
            "Name": "ops-metadata",
            "Image": "public.ecr.aws/docker/library/busybox:latest",
            "Labels": {"com.amazonaws.ecs.container-name": "ops-metadata"},
            "DesiredStatus": "RUNNING",
            "KnownStatus": "RUNNING",
            "Limits": {"CPU": 2, "Memory": 512},
            "Ports": [],
        },
    )
    _seeded = True


def get(endpoint, path: str) -> dict:
    with urllib.request.urlopen(endpoint + path, timeout=30) as response:
        assert response.status == 200
        return json.loads(response.read())


@pytest.fixture
def metadata(endpoint):
    if os.environ.get("EP_LAB_EMULATOR"):
        pytest.skip("the token is registered inside the emulator's process, not over HTTP")
    seed()
    return endpoint


def test_container_metadata_reads_the_container(metadata):
    payload = get(metadata, f"/v4/{TOKEN}")
    assert payload["Name"] == "ops-metadata"
    assert payload["DockerId"] == "0123456789ab"
    assert payload["Labels"]["com.amazonaws.ecs.container-name"] == "ops-metadata"
    assert payload["KnownStatus"] == "RUNNING"


def test_task_metadata_lists_the_task_and_its_containers(metadata):
    payload = get(metadata, f"/v4/{TOKEN}/task")
    assert payload["TaskARN"] == TASK
    assert payload["Cluster"] == _CLUSTER
    assert [container["Name"] for container in payload["Containers"]] == ["ops-metadata"]


def test_container_stats_answers_an_object(metadata):
    assert get(metadata, f"/v4/{TOKEN}/stats") == {}


def test_task_stats_answers_an_object(metadata):
    assert get(metadata, f"/v4/{TOKEN}/task/stats") == {}


def test_an_unknown_token_is_not_found(metadata):
    status = None
    try:
        urllib.request.urlopen(metadata + "/v4/unknowntoken123", timeout=30)
    except urllib.error.HTTPError as error:
        status = error.code
    assert status == 404
