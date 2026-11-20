"""One release, several artefacts: the units that must agree before it ships."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import units  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "versions.json").write_text("[]", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _units(repo: Path, version: str = "v0.2.0") -> dict[str, bool]:
    return {row["unit"]: row["present"] for row in units.report(repo, version)}


def test_nothing_is_present_before_a_release(repo):
    assert _units(repo)["CHANGELOG.md"] is False
    assert _units(repo)["site/versions.json"] is False
    assert _units(repo)["versioned docs"] is False


def test_the_changelog_section_is_seen(repo):
    text = (repo / "CHANGELOG.md").read_text()
    (repo / "CHANGELOG.md").write_text(text + "\n## [v0.2.0] - 2026-11-16\n", encoding="utf-8")
    assert _units(repo)["CHANGELOG.md"] is True


def test_a_section_for_another_version_does_not_count(repo):
    text = (repo / "CHANGELOG.md").read_text()
    (repo / "CHANGELOG.md").write_text(text + "\n## [v0.1.0] - 2026-11-01\n", encoding="utf-8")
    assert _units(repo)["CHANGELOG.md"] is False


def test_the_docs_version_needs_both_the_list_and_the_pages(repo):
    (repo / "site" / "versions.json").write_text(json.dumps(["0.2.0"]), encoding="utf-8")
    assert _units(repo)["site/versions.json"] is True
    assert _units(repo)["versioned docs"] is False

    (repo / "site" / "docs").mkdir()
    (repo / "site" / "docs" / "intro.md").write_text("# Intro\n", encoding="utf-8")
    assert _units(repo)["versioned docs"] is False, "an empty version directory is not frozen docs"

    frozen = repo / "site" / "versioned_docs" / "version-0.2.0"
    frozen.mkdir(parents=True)
    (frozen / "intro.md").write_text("# Intro\n", encoding="utf-8")
    assert _units(repo)["versioned docs"] is True


def test_a_frozen_version_missing_a_page_is_not_a_release(repo):
    (repo / "site" / "docs" / "reference").mkdir(parents=True)
    (repo / "site" / "docs" / "intro.md").write_text("# Intro\n", encoding="utf-8")
    (repo / "site" / "docs" / "reference" / "limits.md").write_text("# Limits\n", encoding="utf-8")
    frozen = repo / "site" / "versioned_docs" / "version-0.2.0"
    frozen.mkdir(parents=True)
    (frozen / "intro.md").write_text("# Intro\n", encoding="utf-8")
    assert _units(repo)["versioned docs"] is False

    (frozen / "reference").mkdir()
    (frozen / "reference" / "limits.md").write_text("# Limits\n", encoding="utf-8")
    assert _units(repo)["versioned docs"] is True


def test_the_tag_is_read_from_git(repo):
    tags = subprocess.run(["git", "tag", "-l"], cwd=repo, capture_output=True, text=True)
    assert tags.stdout.strip() == ""
    assert _units(repo)["git tag"] is False


def test_check_reports_what_is_missing(repo, capsys):
    assert units.main.__module__ == "units"
    rows = units.report(repo, "v0.2.0")
    assert [row["unit"] for row in rows] == [
        "git tag",
        "CHANGELOG.md",
        "site/versions.json",
        "versioned docs",
        "compose image tags",
    ]


def test_every_compose_file_tracks_the_version(repo):
    for name in ("docker-compose.yml", "docker-compose.all.yml"):
        (repo / name).write_text(
            'image: "ghcr.io/mathewmusango/emuplane:0.2.0"\n', encoding="utf-8"
        )
    assert _units(repo)["compose image tags"] is True
    assert _units(repo, "v0.3.0")["compose image tags"] is False


def test_one_stack_left_behind_fails_the_release(repo):
    (repo / "docker-compose.yml").write_text(
        'image: "ghcr.io/mathewmusango/emuplane:0.2.0"\n', encoding="utf-8"
    )
    (repo / "docker-compose.all.yml").write_text(
        'image: "ghcr.io/mathewmusango/emuplane:0.1.0"\n', encoding="utf-8"
    )
    assert _units(repo)["compose image tags"] is False


def test_a_compose_default_of_latest_does_not_match(repo):
    (repo / "docker-compose.yml").write_text(
        'image: "ghcr.io/mathewmusango/emuplane:latest"\n', encoding="utf-8"
    )
    assert _units(repo)["compose image tags"] is False
