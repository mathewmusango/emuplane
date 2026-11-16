"""A page may only show an image the site can actually serve."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import qa_check  # noqa: E402


def _site(tmp_path: Path) -> Path:
    (tmp_path / "site" / "docs").mkdir(parents=True)
    (tmp_path / "site" / "static" / "img").mkdir(parents=True)
    return tmp_path


def test_a_reference_with_no_file_is_reported(tmp_path, monkeypatch):
    _site(tmp_path)
    (tmp_path / "site" / "docs" / "page.md").write_text("![x](/img/nope.png)\n", encoding="utf-8")
    monkeypatch.setattr(qa_check, "ROOT", tmp_path)

    problems = qa_check.docs_assets()

    assert any("nope.png" in problem for problem in problems)


def test_the_mark_itself_must_be_present(tmp_path, monkeypatch):
    _site(tmp_path)
    monkeypatch.setattr(qa_check, "ROOT", tmp_path)
    assert any("mark.png" in problem for problem in qa_check.docs_assets())


def test_a_resolvable_reference_passes(tmp_path, monkeypatch):
    _site(tmp_path)
    (tmp_path / "site" / "static" / "img" / "mark.png").write_bytes(b"x")
    (tmp_path / "site" / "static" / "img" / "shot.png").write_bytes(b"x")
    (tmp_path / "site" / "docs" / "page.md").write_text("![x](/img/shot.png)\n", encoding="utf-8")
    monkeypatch.setattr(qa_check, "ROOT", tmp_path)

    assert qa_check.docs_assets() == []


def test_a_remote_image_is_not_checked(tmp_path, monkeypatch):
    _site(tmp_path)
    (tmp_path / "site" / "static" / "img" / "mark.png").write_bytes(b"x")
    (tmp_path / "site" / "docs" / "page.md").write_text(
        "![x](https://example.com/a.png)\n", encoding="utf-8"
    )
    monkeypatch.setattr(qa_check, "ROOT", tmp_path)

    assert qa_check.docs_assets() == []
