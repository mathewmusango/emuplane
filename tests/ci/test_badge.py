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
