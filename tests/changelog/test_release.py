"""What a merge means for a release: nothing, a patch that ships itself, or a pull request."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import release  # noqa: E402


def issue(number: int, title: str, labels=(), reason: str = "completed") -> dict:
    return {
        "number": number,
        "title": title,
        "body": "",
        "state_reason": reason,
        "html_url": f"https://github.com/o/r/issues/{number}",
        "labels": [{"name": name} for name in labels],
    }


@pytest.fixture
def config():
    return {
        "sections": [
            {"title": "Added", "labels": ["added"], "bump": "minor"},
            {"title": "Removed", "labels": ["removed"], "bump": "major"},
            {"title": "Fixed", "labels": ["bug"], "bump": "patch"},
        ],
        "exclude_labels": ["chore"],
        "unlabelled": "Added",
        "policy": {"auto": ["patch"]},
    }


def test_a_patch_ships_itself(config):
    decided = release.decide("v1.4.2", [issue(1, "A fix", ["bug"])], config)
    assert decided["action"] == release.RELEASE
    assert decided["version"] == "1.4.3"


def test_a_feature_waits_for_a_person(config):
    decided = release.decide("v1.4.2", [issue(1, "A feature", ["added"])], config)
    assert decided["action"] == release.PULL_REQUEST
    assert decided["version"] == "1.5.0"


def test_a_feature_beside_a_fix_is_not_shipped_by_the_patch_rule(config):
    decided = release.decide(
        "v1.4.2", [issue(1, "A fix", ["bug"]), issue(2, "A feature", ["added"])], config
    )
    assert decided["action"] == release.PULL_REQUEST
    assert decided["level"] == "minor"


def test_nothing_changelog_worthy_means_no_release(config):
    decided = release.decide("v1.4.2", [issue(1, "A chore", ["chore"])], config)
    assert decided["action"] == release.NOTHING
    assert decided["version"] == "v1.4.2"


def test_a_closed_as_not_planned_issue_is_not_a_release(config):
    decided = release.decide("v1.4.2", [issue(1, "A duplicate", ["bug"], reason="not_planned")], config)
    assert decided["action"] == release.NOTHING


def test_a_removal_is_never_a_patch_below_one_point_oh(config):
    decided = release.decide("v0.1.0", [issue(1, "Gone", ["removed"])], config)
    assert decided["action"] == release.PULL_REQUEST
    assert decided["version"] == "0.2.0"


def test_a_policy_can_allow_everything_through(config):
    config["policy"]["auto"] = ["patch", "minor", "major"]
    assert release.decide("v1.4.2", [issue(1, "A feature", ["added"])], config)["action"] == release.RELEASE


def test_a_policy_can_allow_nothing(config):
    config["policy"]["auto"] = []
    assert release.decide("v1.4.2", [issue(1, "A fix", ["bug"])], config)["action"] == release.PULL_REQUEST


def test_a_version_whose_tag_exists_is_not_planned_again(config):
    decided = release.decide("v1.4.2", [issue(1, "A fix", ["bug"])], config, {"v1.4.3"})
    assert decided["action"] == release.NOTHING


def test_a_version_without_its_tag_is_still_planned(config):
    decided = release.decide("v1.4.2", [issue(1, "A fix", ["bug"])], config, {"v1.4.2"})
    assert decided["action"] == release.RELEASE
    assert decided["version"] == "1.4.3"
