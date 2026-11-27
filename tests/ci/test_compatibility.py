"""The compatibility chain: a version's position in the window, and the operations it can run."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "control"))

from compatibility import Compatibility, load  # noqa: E402

COMPAT = load()


def test_the_window_is_five_sorted_versions_ending_at_the_ceiling():
    assert COMPAT.window == 5
    assert COMPAT.versions == ["1.5.41", "1.5.42", "1.5.43", "1.5.44", "1.5.45"]
    assert COMPAT.floor == "1.5.41"
    assert COMPAT.ceiling == "1.5.45"
    assert COMPAT.supported == COMPAT.versions


def test_a_floor_operation_is_supported_by_every_version():
    for version in COMPAT.versions:
        assert COMPAT.supports("ec2", "DescribeInstances", version)


def test_an_operation_is_enabled_by_the_version_that_added_it():
    # EC2's Transit Gateway arrived in 1.5.44; ECR's cache rules in 1.5.42.
    assert not COMPAT.supports("ec2", "CreateTransitGateway", "1.5.41")
    assert not COMPAT.supports("ec2", "CreateTransitGateway", "1.5.43")
    assert COMPAT.supports("ec2", "CreateTransitGateway", "1.5.44")
    assert COMPAT.supports("ec2", "CreateTransitGateway", "1.5.45")
    assert not COMPAT.supports("ecr", "CreatePullThroughCacheRule", "1.5.41")
    assert COMPAT.supports("ecr", "CreatePullThroughCacheRule", "1.5.42")
    assert not COMPAT.supports("cognito", "AddUserPoolClientSecret", "1.5.42")
    assert COMPAT.supports("cognito", "AddUserPoolClientSecret", "1.5.43")


def test_a_deprecated_version_is_flagged_and_does_not_gain_new_operations():
    status = COMPAT.status("1.5.40")
    assert status["state"] == "deprecated"
    assert status["supported"] is False
    assert not COMPAT.supports("ec2", "CreateTransitGateway", "1.5.40")


def test_a_newer_untested_version_is_not_gated_by_the_chain():
    status = COMPAT.status("1.5.46")
    assert status["state"] == "untested"
    assert status["supported"] is True
    # The probe decides an untested release; the chain must not hide its operations.
    assert COMPAT.supports("ec2", "CreateTransitGateway", "1.5.46")


def test_an_unparsable_version_is_unknown_and_never_hides_an_action():
    assert COMPAT.status("")["state"] == "unknown"
    assert COMPAT.status("dev")["state"] == "unknown"
    assert COMPAT.supports("ec2", "CreateTransitGateway", "dev")


def test_since_names_the_adding_version_and_the_floor():
    assert COMPAT.since("ec2", "CreateTransitGateway") == "1.5.44"
    assert COMPAT.since("ec2", "DescribeInstances") == "1.5.41"


def test_advertised_since_names_the_first_version_that_lists_it():
    # The Lambda list operation arrived before the window; it is listed in 1.5.45.
    assert COMPAT.advertised_since("lambda", "ListFunctionEventInvokeConfigs") == "1.5.45"
    assert COMPAT.since("lambda", "ListFunctionEventInvokeConfigs") == "1.5.41"
    assert COMPAT.advertised_since("ec2", "CreateTransitGateway") == "1.5.44"


def test_a_removed_operation_is_disabled_from_the_version_that_removed_it():
    compat = Compatibility(
        {
            "window": 2,
            "ceiling": "1.5.2",
            "versions": ["1.5.1", "1.5.2"],
            "services": {"svc": {"name": "Svc"}},
            "deltas": {"1.5.2": {"removed": ["svc:OldOperation"]}},
        }
    )
    assert compat.supports("svc", "OldOperation", "1.5.1")
    assert not compat.supports("svc", "OldOperation", "1.5.2")


def test_the_checked_in_data_passes_its_own_check():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "compatibility.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1.5.45 ceiling" in result.stdout


def test_the_matrix_is_the_window_as_tags():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "compatibility.py"), "--matrix"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "v1.5.41",
        "v1.5.42",
        "v1.5.43",
        "v1.5.44",
        "v1.5.45",
    ]
