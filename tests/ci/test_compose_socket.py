"""The socket compose file is the all-in-one stack plus exactly one mount."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
MOUNT = "${DOCKER_SOCKET:-/var/run/docker.sock}:/var/run/docker.sock"


def test_the_socket_file_is_the_all_file_plus_the_mount():
    """A second service, image tag or environment change in one file but not the other fails here."""
    everything = yaml.safe_load((ROOT / "docker-compose.all.yml").read_text(encoding="utf-8"))
    socket = yaml.safe_load((ROOT / "docker-compose.socket.yml").read_text(encoding="utf-8"))
    mounts = socket["services"]["ministack"]["volumes"]
    assert mounts[-1] == MOUNT
    mounts.pop()
    assert socket == everything
