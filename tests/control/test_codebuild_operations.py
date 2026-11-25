"""CodeBuild on the wire: all 11 advertised operations, JSON 1.1.

The target prefix is `CodeBuild_20161006`. Projects are keyed by name (a stable
project carries the read/update tests; a create or delete test makes its own).
Builds are metadata-only unless `MINISTACK_CODEBUILD_EXECUTE=1`, so a build lands
`SUCCEEDED` synchronously and `StopBuild` moves it to `STOPPED`.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "CodeBuild_20161006"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
PROJECT = "ops-codebuild"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "codebuild", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def create_project(endpoint, name: str) -> str:
    ok(
        endpoint,
        "CreateProject",
        {"name": name, "source": {"type": "NO_SOURCE"}, "artifacts": {"type": "NO_ARTIFACTS"}},
    )
    return name


def ensure_project(endpoint, name: str = PROJECT) -> str:
    status, text = call(
        endpoint,
        "CreateProject",
        {"name": name, "source": {"type": "NO_SOURCE"}, "artifacts": {"type": "NO_ARTIFACTS"}},
    )
    assert status == 200 or "ResourceAlreadyExistsException" in text, text[:300]
    projects = ok(endpoint, "BatchGetProjects", {"names": [name]})["projects"]
    assert projects[0]["name"] == name
    return name


def fresh_project(endpoint) -> str:
    return create_project(endpoint, f"ops-codebuild-made-{time.time_ns()}")


def start_build(endpoint, project: str) -> str:
    return ok(endpoint, "StartBuild", {"projectName": project})["build"]["id"]


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def test_create_project_is_read_back(endpoint):
    name = fresh_project(endpoint)
    projects = ok(endpoint, "BatchGetProjects", {"names": [name]})["projects"]
    assert projects[0]["name"] == name
    assert projects[0]["arn"].endswith(f"project/{name}")


def test_batch_get_projects_answers_the_project(endpoint):
    ensure_project(endpoint)
    answer = ok(endpoint, "BatchGetProjects", {"names": [PROJECT]})
    assert PROJECT in {project["name"] for project in answer["projects"]}
    assert answer["projectsNotFound"] == []


def test_list_projects_lists_the_project(endpoint):
    ensure_project(endpoint)
    assert PROJECT in ok(endpoint, "ListProjects")["projects"]


def test_update_project_changes_the_description(endpoint):
    ensure_project(endpoint)
    updated = ok(endpoint, "UpdateProject", {"name": PROJECT, "description": "ops managed"})["project"]
    assert updated["description"] == "ops managed"
    projects = ok(endpoint, "BatchGetProjects", {"names": [PROJECT]})["projects"]
    assert projects[0]["description"] == "ops managed"


def test_delete_project_removes_the_project_it_created(endpoint):
    name = fresh_project(endpoint)
    ok(endpoint, "DeleteProject", {"name": name})
    answer = ok(endpoint, "BatchGetProjects", {"names": [name]})
    assert name in answer["projectsNotFound"]


# ---------------------------------------------------------------------------
# Builds
# ---------------------------------------------------------------------------


def test_start_build_answers_a_build(endpoint):
    ensure_project(endpoint)
    build_id = start_build(endpoint, PROJECT)
    assert build_id.startswith(f"{PROJECT}:")
    builds = ok(endpoint, "BatchGetBuilds", {"ids": [build_id]})["builds"]
    assert builds[0]["id"] == build_id
    assert builds[0]["buildStatus"] == "SUCCEEDED"


def test_batch_get_builds_answers_the_build(endpoint):
    ensure_project(endpoint)
    build_id = start_build(endpoint, PROJECT)
    answer = ok(endpoint, "BatchGetBuilds", {"ids": [build_id]})
    assert build_id in {build["id"] for build in answer["builds"]}
    assert answer["buildsNotFound"] == []


def test_stop_build_marks_it_stopped(endpoint):
    ensure_project(endpoint)
    build_id = start_build(endpoint, PROJECT)
    stopped = ok(endpoint, "StopBuild", {"id": build_id})["build"]
    assert stopped["buildStatus"] == "STOPPED"
    assert stopped["id"] == build_id


def test_list_builds_lists_the_build(endpoint):
    ensure_project(endpoint)
    build_id = start_build(endpoint, PROJECT)
    assert build_id in ok(endpoint, "ListBuilds")["ids"]


def test_list_builds_for_project_lists_the_build(endpoint):
    ensure_project(endpoint)
    build_id = start_build(endpoint, PROJECT)
    answer = ok(endpoint, "ListBuildsForProject", {"projectName": PROJECT})
    assert build_id in answer["ids"]


def test_batch_delete_builds_removes_the_build_it_created(endpoint):
    ensure_project(endpoint)
    build_id = start_build(endpoint, PROJECT)
    answer = ok(endpoint, "BatchDeleteBuilds", {"ids": [build_id]})
    assert build_id in answer["buildsDeleted"]
    assert ok(endpoint, "BatchGetBuilds", {"ids": [build_id]})["builds"] == []
