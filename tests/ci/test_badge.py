"""The claims file is canonical, well-formed, and the URL carries every claim."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import badge  # noqa: E402


def test_the_claims_file_is_canonical():
    claims = badge.load_claims()
    assert badge.normalize(claims) == claims


def test_every_status_is_a_value_the_site_accepts():
    allowed = {"?", "N/A", "Unmet", "Met"}
    statuses = {k: v for k, v in badge.load_claims().items() if k.endswith("_status")}
    assert statuses, "the claims file should carry statuses"
    assert set(statuses.values()) <= allowed, set(statuses.values()) - allowed


def test_every_status_has_a_justification():
    claims = badge.load_claims()
    statuses = [k for k in claims if k.endswith("_status")]
    missing = [k for k in statuses if not claims.get(k.replace("_status", "_justification"))]
    assert not missing, missing


def test_the_url_carries_every_claim():
    claims = badge.load_claims()
    url = badge.automation_url(claims)
    assert url.startswith("https://www.bestpractices.dev/en/projects/16933/passing/edit?")
    for key in claims:
        assert f"{key}=" in url


def test_a_baseline_claim_reads_back_under_its_osps_id():
    assert badge.live_status("osps_ac_01_01_status") == "OSPS-AC-01.01_status"
    assert badge.live_status("floss_license_status") == "floss_license_status"


def test_an_older_release_in_a_justification_is_reported():
    latest = badge.newest_release()
    older = "v0.0.1" if latest != "0.0.1" else "v0.0.2"
    assert badge.stale_versions({"x_justification": f"released as {older}"})


def test_the_justifications_name_the_newest_release():
    assert badge.stale_versions(badge.load_claims()) == []


def test_an_entry_naming_an_older_release_is_reported():
    newest = f"v{badge.newest_release()}"
    entry = {"x_justification": "shipped in v0.0.1", "y_justification": f"shipped in {newest}"}
    assert badge.entry_stale(entry, newest) == ["x_justification"]


def test_the_write_uses_the_sites_own_form_fields():
    body = badge.form_body({"x_status": "Met"}, "TOKEN")
    assert "project%5Bx_status%5D=Met" in body
    assert "authentication_token=TOKEN" in body


def test_the_tokens_come_from_the_edit_page():
    html = '<meta name="csrf-token" content="CSRF"><input type="hidden" name="authenticity_token" value="AUTH"'
    assert badge.tokens(html) == ("AUTH", "CSRF")


def test_a_page_without_tokens_is_a_session_problem():
    try:
        badge.tokens("<html>not logged in</html>")
    except SystemExit as exit_:
        assert "not logged in" in str(exit_)
    else:
        raise AssertionError("a page with no tokens must not be written")


def test_the_session_cookie_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("BADGE_SESSION", "value")
    assert badge.session_cookie() == "value"
    monkeypatch.delenv("BADGE_SESSION")
    monkeypatch.delenv("_BadgeApp_session", raising=False)
    try:
        badge.session_cookie()
    except SystemExit as exit_:
        assert "no session cookie" in str(exit_)
    else:
        raise AssertionError("no cookie must not reach the network")
