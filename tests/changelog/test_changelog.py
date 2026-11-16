"""The changelog is built from issues: the label picks the section, the title is the bullet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import changelog  # noqa: E402


def issue(number: int, title: str, labels=(), body: str = "", reason: str = "completed") -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "state_reason": reason,
        "html_url": f"https://github.com/o/r/issues/{number}",
        "labels": [{"name": name} for name in labels],
    }


@pytest.fixture(scope="module")
def config():
    return changelog.load_config()


def test_a_label_picks_the_section(config):
    assert changelog.section_for(issue(1, "A bucket page", ["feature"]), config) == "Added"
    assert changelog.section_for(issue(2, "A wrong region", ["bug"]), config) == "Fixed"


def test_a_changelog_line_replaces_the_title(config):
    written = issue(
        3,
        "fix: the gateway resolved the wrong account",
        ["bug"],
        body="Long explanation.\n\nChangelog: The gateway resolves the account from the key.\n",
    )
    assert changelog.summary(written, config) == "The gateway resolves the account from the key."
    assert changelog.summary(issue(4, "A plain title", ["bug"]), config) == "A plain title"


def test_an_excluded_label_is_left_out(config):
    assert changelog.section_for(issue(5, "Bump a dependency", ["chore"]), config) is None


def test_an_issue_with_no_matching_label_falls_back(config):
    assert changelog.section_for(issue(6, "Something notable"), config) == config["unlabelled"]


def test_the_section_lists_issues_in_order_with_links(config):
    section, dropped = changelog.render(
        "v0.2.0",
        "2026-11-16",
        [issue(12, "Second thing", ["feature"]), issue(7, "First thing", ["bug"])],
        config,
    )
    assert dropped == 0
    assert section.startswith("## [v0.2.0] - 2026-11-16\n")
    assert section.index("### Added") < section.index("### Fixed")
    assert "- First thing ([#7](https://github.com/o/r/issues/7))" in section
    assert "- Second thing ([#12](https://github.com/o/r/issues/12))" in section


def test_not_planned_and_excluded_issues_are_counted(config):
    section, dropped = changelog.render(
        "v0.2.0",
        "2026-11-16",
        [
            issue(8, "A duplicate", ["bug"], reason="not_planned"),
            issue(9, "A chore", ["chore"]),
            issue(10, "A real fix", ["bug"]),
        ],
        config,
    )
    assert dropped == 2
    assert "A real fix" in section
    assert "A duplicate" not in section


def test_an_empty_release_says_so(config):
    section, _dropped = changelog.render("v0.2.0", "2026-11-16", [], config)
    assert section.strip() == "## [v0.2.0] - 2026-11-16\n\nNothing was closed for this release."


def test_the_section_lands_between_unreleased_and_the_newest_release(config):
    text = (
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Pending work\n\n"
        "## [v0.1.0] - 2026-11-01\n\n- Shipped\n"
    )
    section, _dropped = changelog.render(
        "v0.2.0", "2026-11-16", [issue(1, "A thing", ["added"])], config
    )

    written = changelog.insert(text, section, "v0.2.0")

    assert written.index("## [Unreleased]") < written.index("## [v0.2.0]")
    assert written.index("## [v0.2.0]") < written.index("## [v0.1.0]")
    assert "- Pending work" in written and "- Shipped" in written


def test_a_version_cannot_be_written_twice(config):
    text = "## [Unreleased]\n\n## [v0.2.0] - 2026-11-16\n\n- Shipped\n"
    with pytest.raises(SystemExit):
        changelog.insert(text, "## [v0.2.0] - 2026-11-16\n", "v0.2.0")


def test_check_reports_the_missing_section(capsys):
    text = "## [Unreleased]\n\n- Pending\n"
    assert changelog.check(text, "v0.2.0") == 1
    assert "no section for v0.2.0" in capsys.readouterr().err

    assert changelog.check(text + "## [v0.2.0] - 2026-11-16\n", "v0.2.0") == 0
    assert "has a section for v0.2.0" in capsys.readouterr().out


def test_the_label_plan_covers_every_gate_label(config):
    plan = changelog.label_plan(config)
    named = {label["name"] for label in plan}
    assert {"added", "bug", "security", "chore", "skip-changelog"} <= named
    added = next(label for label in plan if label["name"] == "added")
    assert added["color"] == "0e8a16"
    assert added["description"] == "Changelog: Added"


def test_sync_creates_only_what_is_missing(config):
    calls = []

    def runner(arguments):
        calls.append(arguments)
        if arguments[:2] == ["label", "list"]:
            return json.dumps([{"name": "added"}, {"name": "bug"}])
        return ""

    created, present = changelog.sync_labels("o/r", changelog.label_plan(config), runner=runner)

    assert created == len(changelog.label_plan(config)) - 2
    assert present == 2
    assert not any("added" in call for call in calls if call[:2] == ["label", "create"])


def test_a_dry_run_creates_nothing(config):
    calls = []

    def runner(arguments):
        calls.append(arguments)
        return json.dumps([])

    created, present = changelog.sync_labels(
        "o/r", changelog.label_plan(config), dry_run=True, runner=runner
    )

    assert created == 0
    assert present == 0
    assert not any(call[:2] == ["label", "create"] for call in calls)
