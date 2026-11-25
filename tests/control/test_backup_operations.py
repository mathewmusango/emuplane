"""AWS Backup on the wire: all 21 advertised operations, REST/JSON.

Vaults at `/backup-vaults/{name}`, plans at `/backup/plans`, selections under a
plan, jobs at `/backup-jobs`, and tags under `/tags/{arn}` and `/untag/{arn}`.
A vault and a plan are keyed by name, so stable ones carry the read/tag tests
while a create or delete test makes its own. Jobs complete immediately.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
VAULT = "ops-backup-vault"
PLAN = "ops-backup-plan"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/ops-backup-role"
RESOURCE = "arn:aws:s3:::ops-backup-bucket"


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "backup", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status in (200, 204), f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, method: str, path: str, payload: dict | None = None) -> str:
    status, text = call(endpoint, method, path, payload)
    assert status >= 400, f"{method} {path} unexpectedly answered {status}: {text[:400]}"
    return text


def plan_body(name: str = PLAN) -> dict:
    return {
        "BackupPlanName": name,
        "Rules": [
            {
                "RuleName": "daily",
                "TargetBackupVaultName": VAULT,
                "ScheduleExpression": "cron(0 5 ? * * *)",
            }
        ],
    }


def ensure_vault(endpoint, name: str = VAULT) -> dict:
    status, text = call(endpoint, "PUT", f"/backup-vaults/{name}", {})
    assert status in (200, 204) or "AlreadyExistsException" in text, text[:300]
    return ok(endpoint, "GET", f"/backup-vaults/{name}")


def create_plan(endpoint, name: str = PLAN) -> dict:
    return ok(endpoint, "PUT", "/backup/plans", {"BackupPlan": plan_body(name)})


def ensure_plan(endpoint, name: str = PLAN) -> str:
    listed = ok(endpoint, "GET", "/backup/plans").get("BackupPlansList", [])
    for item in listed:
        if item.get("BackupPlanName") == name:
            return item["BackupPlanId"]
    return create_plan(endpoint, name)["BackupPlanId"]


def create_selection(endpoint, plan_id: str) -> str:
    body = {
        "BackupSelection": {
            "SelectionName": "ops-selection",
            "IamRoleArn": ROLE,
            "Resources": [RESOURCE],
        }
    }
    return ok(endpoint, "PUT", f"/backup/plans/{plan_id}/selections", body)["SelectionId"]


def start_job(endpoint) -> dict:
    ensure_vault(endpoint)
    return ok(
        endpoint,
        "PUT",
        "/backup-jobs",
        {"BackupVaultName": VAULT, "ResourceArn": f"{RESOURCE}/{time.time_ns()}", "IamRoleArn": ROLE},
    )


# ---------------------------------------------------------------------------
# Vaults
# ---------------------------------------------------------------------------


def test_create_backup_vault_is_read_back(endpoint):
    name = f"ops-vault-{time.time_ns()}"
    ok(endpoint, "PUT", f"/backup-vaults/{name}", {})
    assert ok(endpoint, "GET", f"/backup-vaults/{name}")["BackupVaultName"] == name


def test_describe_backup_vault_reads_the_vault(endpoint):
    assert ensure_vault(endpoint)["BackupVaultName"] == VAULT


def test_delete_backup_vault_removes_the_vault_it_created(endpoint):
    name = f"ops-vault-deleted-{time.time_ns()}"
    ok(endpoint, "PUT", f"/backup-vaults/{name}", {})
    ok(endpoint, "DELETE", f"/backup-vaults/{name}")
    refused(endpoint, "GET", f"/backup-vaults/{name}")


def test_list_backup_vaults_lists_the_vault(endpoint):
    ensure_vault(endpoint)
    names = [item["BackupVaultName"] for item in ok(endpoint, "GET", "/backup-vaults")["BackupVaultList"]]
    assert VAULT in names


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def test_create_backup_plan_is_read_back(endpoint):
    created = create_plan(endpoint, f"ops-plan-{time.time_ns()}")
    got = ok(endpoint, "GET", f"/backup/plans/{created['BackupPlanId']}")
    assert got["BackupPlan"]["BackupPlanName"].startswith("ops-plan-")


def test_get_backup_plan_reads_the_plan(endpoint):
    plan_id = ensure_plan(endpoint)
    assert ok(endpoint, "GET", f"/backup/plans/{plan_id}")["BackupPlan"]["BackupPlanName"] == PLAN


def test_update_backup_plan_bumps_the_version(endpoint):
    plan_id = ensure_plan(endpoint)
    before = ok(endpoint, "GET", f"/backup/plans/{plan_id}")["VersionId"]
    ok(endpoint, "POST", f"/backup/plans/{plan_id}", {"BackupPlan": plan_body(PLAN)})
    assert ok(endpoint, "GET", f"/backup/plans/{plan_id}")["VersionId"] != before


def test_delete_backup_plan_removes_the_plan_it_created(endpoint):
    created = create_plan(endpoint, f"ops-plan-deleted-{time.time_ns()}")
    ok(endpoint, "DELETE", f"/backup/plans/{created['BackupPlanId']}")
    refused(endpoint, "GET", f"/backup/plans/{created['BackupPlanId']}")


def test_list_backup_plans_lists_the_plan(endpoint):
    plan_id = ensure_plan(endpoint)
    ids = [item["BackupPlanId"] for item in ok(endpoint, "GET", "/backup/plans")["BackupPlansList"]]
    assert plan_id in ids


def test_list_backup_plan_versions_lists_the_version(endpoint):
    plan_id = ensure_plan(endpoint)
    assert ok(endpoint, "GET", f"/backup/plans/{plan_id}/versions")["BackupPlanVersionsList"]


# ---------------------------------------------------------------------------
# Selections
# ---------------------------------------------------------------------------


def test_create_backup_selection_is_read_back(endpoint):
    plan_id = ensure_plan(endpoint)
    selection_id = create_selection(endpoint, plan_id)
    assert ok(endpoint, "GET", f"/backup/plans/{plan_id}/selections/{selection_id}")["SelectionId"] == selection_id


def test_get_backup_selection_reads_the_selection(endpoint):
    plan_id = ensure_plan(endpoint)
    selection_id = create_selection(endpoint, plan_id)
    got = ok(endpoint, "GET", f"/backup/plans/{plan_id}/selections/{selection_id}")
    assert got["BackupSelection"]["SelectionName"] == "ops-selection"


def test_delete_backup_selection_removes_the_selection_it_created(endpoint):
    plan_id = ensure_plan(endpoint)
    selection_id = create_selection(endpoint, plan_id)
    ok(endpoint, "DELETE", f"/backup/plans/{plan_id}/selections/{selection_id}")
    refused(endpoint, "GET", f"/backup/plans/{plan_id}/selections/{selection_id}")


def test_list_backup_selections_lists_the_selection(endpoint):
    plan_id = ensure_plan(endpoint)
    selection_id = create_selection(endpoint, plan_id)
    ids = [item["SelectionId"] for item in ok(endpoint, "GET", f"/backup/plans/{plan_id}/selections")["BackupSelectionsList"]]
    assert selection_id in ids


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def test_start_backup_job_answers_a_job(endpoint):
    created = start_job(endpoint)
    assert ok(endpoint, "GET", f"/backup-jobs/{created['BackupJobId']}")["BackupJobId"] == created["BackupJobId"]


def test_stop_backup_job_refuses_a_completed_job(endpoint):
    created = start_job(endpoint)
    refused(endpoint, "POST", f"/backup-jobs/{created['BackupJobId']}")


def test_describe_backup_job_reads_the_job(endpoint):
    created = start_job(endpoint)
    assert ok(endpoint, "GET", f"/backup-jobs/{created['BackupJobId']}")["State"] == "COMPLETED"


def test_list_backup_jobs_lists_the_job(endpoint):
    created = start_job(endpoint)
    ids = [item["BackupJobId"] for item in ok(endpoint, "GET", "/backup-jobs")["BackupJobs"]]
    assert created["BackupJobId"] in ids


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    arn = ensure_vault(endpoint)["BackupVaultArn"]
    ok(endpoint, "POST", f"/tags/{arn}", {"Tags": {"env": "ops"}})
    assert ok(endpoint, "GET", f"/tags/{arn}")["Tags"]["env"] == "ops"


def test_untag_resource_removes_the_key_it_names(endpoint):
    arn = ensure_vault(endpoint)["BackupVaultArn"]
    ok(endpoint, "POST", f"/tags/{arn}", {"Tags": {"doomed": "yes"}})
    ok(endpoint, "POST", f"/untag/{arn}", {"TagKeyList": ["doomed"]})
    assert "doomed" not in ok(endpoint, "GET", f"/tags/{arn}")["Tags"]


def test_list_tags_lists_the_tags(endpoint):
    arn = ensure_vault(endpoint)["BackupVaultArn"]
    ok(endpoint, "POST", f"/tags/{arn}", {"Tags": {"team": "platform"}})
    assert ok(endpoint, "GET", f"/tags/{arn}")["Tags"]["team"] == "platform"
