"""The issue plan: every entry names a module and one changelog label, and the PR closes them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import issues  # noqa: E402


@pytest.fixture()
def spec():
    return issues.load("s3")


def test_every_plan_is_valid():
    for name in issues.plan_names():
        assert issues.problems(issues.load(name)) == [], name


def test_the_s3_plan_covers_code_docs_and_coverage(spec):
    modules = {issue["module"] for issue in spec["issues"]}
    assert {"s3", "docs", "ci"} <= modules
    # One release note per issue is the gate's rule, so every entry carries one.
    for issue in spec["issues"]:
        assert len(issues.labels_for(issue)) == 2
        assert issues.labels_for(issue)[0].startswith("module:")


def test_an_unknown_changelog_label_is_reported(spec):
    spec["issues"][0]["changelog"] = "nice-to-have"
    assert any("changelog label" in problem for problem in issues.problems(spec))


def test_an_unknown_module_is_reported(spec):
    spec["issues"][0]["module"] = "telepathy"
    assert any("module label" in problem for problem in issues.problems(spec))


def test_a_plan_without_issues_is_a_problem(spec):
    spec["issues"] = []
    assert any("no issues" in problem for problem in issues.problems(spec))


def test_the_pull_request_closes_every_issue(spec, tmp_path, capsys):
    cache = tmp_path / "issues.json"
    cache.write_text(
        json.dumps(
            {
                f"s3:{issue['key']}": number
                for number, issue in enumerate(spec["issues"], start=101)
            }
        ),
        encoding="utf-8",
    )
    assert issues.pull_request("s3", spec, cache) == 0
    printed = capsys.readouterr().out
    assert f"Closes #{101}" in printed
    assert f"#{100 + len(spec['issues'])}" in printed
    assert "## Documentation" in printed


def test_a_pull_request_waits_for_the_issues(spec, tmp_path, capsys):
    empty = tmp_path / "issues.json"
    assert issues.pull_request("s3", spec, empty) == 1
    assert "run --apply first" in capsys.readouterr().err
