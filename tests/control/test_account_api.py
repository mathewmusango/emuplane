"""The four account operations, driven through the catalogue's own path."""

from __future__ import annotations

import json

from conftest import ACCOUNT, api


def run(console, operation: str, params: dict | None = None, region: str = "us-east-1"):
    return api(
        console,
        "POST",
        "/api/exec",
        {
            "account": ACCOUNT,
            "region": region,
            "service": "account",
            "operation": operation,
            "params": params or {},
        },
    )


def answer(console, operation: str, params: dict | None = None) -> dict:
    status, body = run(console, operation, params)
    assert status == 200, body
    assert body["ok"], body
    return json.loads(body["body"])


def test_account_information_names_the_signed_in_account(console):
    data = answer(console, "get-account-information")
    assert data["AccountId"] == ACCOUNT
    assert data["AccountState"] == "ACTIVE"


def test_contact_information_is_the_emulators_own_answer(console):
    data = answer(console, "get-contact-information")
    assert data["ContactInformation"]["FullName"]


def test_list_regions_reports_a_status_for_every_region(console):
    data = answer(console, "list-regions")
    names = [row["RegionName"] for row in data["Regions"]]
    assert "us-east-1" in names
    assert all(
        row["RegionOptStatus"] in {"ENABLED", "ENABLED_BY_DEFAULT"}
        for row in data["Regions"]
    )


def test_region_opt_status_reads_one_region(console):
    data = answer(console, "get-region-opt-status", {"RegionName": "us-west-2"})
    assert data["RegionName"] == "us-west-2"
    assert data["RegionOptStatus"] == "ENABLED_BY_DEFAULT"
