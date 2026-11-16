"""Two gates: a pull request names its issue, and an issue names its changelog label."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import triage  # noqa: E402


@pytest.fixture(scope="module")
def config():
    return triage.load_config()


@pytest.mark.parametrize(
    "text",
    [
        "Closes #12",
        "closes: #7",
        "Fixes #3",
        "fixed #4",
        "Resolves #9",
        "fix: the gateway\n\nResolved: #21",
    ],
)
def test_a_closing_reference_is_found(text):
    assert triage.closes_an_issue(text)


@pytest.mark.parametrize(
    "text",
    [
        "See #12 for context",
        "Closes the wrong thing",
        "#12",
        "",
        "Closes",
    ],
)
def test_a_bare_mention_is_not_a_link(text):
    assert not triage.closes_an_issue(text)


def test_either_the_title_or_the_body_may_carry_it():
    assert triage.closes_an_issue("Closes #5", "")
    assert triage.closes_an_issue("A title", "Fixes #5")


def test_a_section_label_passes(config):
    assert triage.labelled(["bug"], config)
    assert triage.labelled(["Feature"], config)


def test_an_exclusion_label_passes_because_it_is_a_decision(config):
    assert triage.labelled(["chore"], config)
    assert triage.labelled(["skip-changelog"], config)


def test_no_label_or_an_unknown_one_fails(config):
    assert not triage.labelled([], config)
    assert not triage.labelled(["needs-triage"], config)


def _event(tmp_path: Path, payload: dict) -> str:
    path = tmp_path / "event.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_a_pull_request_without_a_link_fails(tmp_path, config, capsys):
    path = _event(tmp_path, {"pull_request": {"title": "fix: a thing", "body": "no reference"}})
    assert triage.check_pull_request(json.loads(Path(path).read_text()), config) == 1
    assert "does not name the issue" in capsys.readouterr().err


def test_a_pull_request_with_a_link_passes(tmp_path, config):
    path = _event(tmp_path, {"pull_request": {"title": "fix: a thing", "body": "Closes #8"}})
    assert triage.check_pull_request(json.loads(Path(path).read_text()), config) == 0


def test_an_issue_without_a_label_fails(tmp_path, config, capsys):
    payload = {"issue": {"number": 2, "labels": [{"name": "needs-triage"}]}}
    path = _event(tmp_path, payload)
    assert triage.check_issue(json.loads(Path(path).read_text()), config) == 1
    assert "no changelog label" in capsys.readouterr().err


def test_an_issue_with_a_label_passes(tmp_path, config):
    payload = {"issue": {"number": 3, "labels": [{"name": "security"}]}}
    path = _event(tmp_path, payload)
    assert triage.check_issue(json.loads(Path(path).read_text()), config) == 0
