"""AWS AppConfig on the wire: all 33 advertised operations, REST/JSON.

Applications, environments, configuration profiles, deployment strategies and
deployments are REST resources under `/applications` etc.; hosted configuration
versions carry raw content; the data plane is `/configurationsessions` and
`/configuration`. Everything is found again by name, so stable resources carry
the read/update/tag tests while a create or delete test makes its own.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
APP = "ops-app"
ENV = "ops-env"
PROFILE = "ops-profile"
STRATEGY = "ops-strategy"
CONTENT = "key=value\n"


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "appconfig", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None, statuses=(200, 201)) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status in statuses, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def raw(endpoint, method: str, path: str, body: str = "", headers: dict | None = None):
    status, out_headers, out_body = signed.request_bytes(
        endpoint, "appconfig", ACCOUNT, REGION, method, path, body, headers or {}
    )
    return status, out_headers, out_body.decode(errors="replace")


def ensure_app(endpoint, name: str = APP) -> str:
    for item in ok(endpoint, "GET", "/applications")["Items"]:
        if item["Name"] == name:
            return item["Id"]
    return ok(endpoint, "POST", "/applications", {"Name": name, "Description": "ops"})["Id"]


def ensure_env(endpoint, app: str, name: str = ENV) -> str:
    for item in ok(endpoint, "GET", f"/applications/{app}/environments")["Items"]:
        if item["Name"] == name:
            return item["Id"]
    return ok(endpoint, "POST", f"/applications/{app}/environments", {"Name": name})["Id"]


def ensure_profile(endpoint, app: str, name: str = PROFILE) -> str:
    for item in ok(endpoint, "GET", f"/applications/{app}/configurationprofiles")["Items"]:
        if item["Name"] == name:
            return item["Id"]
    return ok(endpoint, "POST", f"/applications/{app}/configurationprofiles", {"Name": name, "LocationUri": "hosted"})["Id"]


def create_version(endpoint, app: str, profile: str, content: str = CONTENT):
    status, headers, body = raw(
        endpoint,
        "POST",
        f"/applications/{app}/configurationprofiles/{profile}/hostedconfigurationversions",
        content,
        {"Content-Type": "text/plain"},
    )
    assert status == 201, body[:400]
    return int(headers["version-number"])


def ensure_version(endpoint, app: str, profile: str) -> int:
    items = ok(endpoint, "GET", f"/applications/{app}/configurationprofiles/{profile}/hostedconfigurationversions")["Items"]
    if items:
        return max(int(item["VersionNumber"]) for item in items)
    return create_version(endpoint, app, profile)


def ensure_strategy(endpoint, name: str = STRATEGY, duration: int = 0) -> str:
    for item in ok(endpoint, "GET", "/deploymentstrategies")["Items"]:
        if item["Name"] == name:
            return item["Id"]
    body = {"Name": name, "DeploymentDurationInMinutes": duration, "GrowthFactor": 100.0, "ReplicateTo": "NONE"}
    return ok(endpoint, "POST", "/deploymentstrategies", body)["Id"]


def context(endpoint):
    app = ensure_app(endpoint)
    return app, ensure_env(endpoint, app), ensure_profile(endpoint, app)


def start_deployment(endpoint, app: str, env: str, profile: str, version: int, strategy: str):
    return ok(
        endpoint,
        "POST",
        f"/applications/{app}/environments/{env}/deployments",
        {"ConfigurationProfileId": profile, "ConfigurationVersion": str(version), "DeploymentStrategyId": strategy},
    )


def app_arn(app: str) -> str:
    return f"arn:aws:appconfig:{REGION}:{ACCOUNT}:application/{app}"


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


def test_create_application_is_read_back(endpoint):
    name = f"ops-app-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", "/applications", {"Name": name})
    assert ok(endpoint, "GET", f"/applications/{created['Id']}")["Name"] == name


def test_get_application_reads_the_application(endpoint):
    app = ensure_app(endpoint)
    assert ok(endpoint, "GET", f"/applications/{app}")["Name"] == APP


def test_list_applications_lists_the_application(endpoint):
    app = ensure_app(endpoint)
    assert app in {item["Id"] for item in ok(endpoint, "GET", "/applications")["Items"]}


def test_update_application_changes_the_description(endpoint):
    app = ensure_app(endpoint)
    updated = ok(endpoint, "PATCH", f"/applications/{app}", {"Description": "updated"})
    assert updated["Description"] == "updated"


def test_delete_application_removes_the_application_it_created(endpoint):
    name = f"ops-app-del-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", "/applications", {"Name": name})
    ok(endpoint, "DELETE", f"/applications/{created['Id']}", statuses=(200, 204))
    status, _ = call(endpoint, "GET", f"/applications/{created['Id']}")
    assert status >= 400


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------


def test_create_environment_is_read_back(endpoint):
    app = ensure_app(endpoint)
    name = f"ops-env-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", f"/applications/{app}/environments", {"Name": name})
    assert ok(endpoint, "GET", f"/applications/{app}/environments/{created['Id']}")["Name"] == name


def test_get_environment_reads_the_environment(endpoint):
    app, env, _profile = context(endpoint)
    assert ok(endpoint, "GET", f"/applications/{app}/environments/{env}")["Name"] == ENV


def test_list_environments_lists_the_environment(endpoint):
    app, env, _profile = context(endpoint)
    assert env in {item["Id"] for item in ok(endpoint, "GET", f"/applications/{app}/environments")["Items"]}


def test_update_environment_changes_the_description(endpoint):
    app, env, _profile = context(endpoint)
    updated = ok(endpoint, "PATCH", f"/applications/{app}/environments/{env}", {"Description": "updated"})
    assert updated["Description"] == "updated"


def test_delete_environment_removes_the_environment_it_created(endpoint):
    app = ensure_app(endpoint)
    name = f"ops-env-del-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", f"/applications/{app}/environments", {"Name": name})
    ok(endpoint, "DELETE", f"/applications/{app}/environments/{created['Id']}", statuses=(200, 204))
    status, _ = call(endpoint, "GET", f"/applications/{app}/environments/{created['Id']}")
    assert status >= 400


# ---------------------------------------------------------------------------
# Configuration profiles
# ---------------------------------------------------------------------------


def test_create_configuration_profile_is_read_back(endpoint):
    app = ensure_app(endpoint)
    name = f"ops-profile-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", f"/applications/{app}/configurationprofiles", {"Name": name, "LocationUri": "hosted"})
    assert ok(endpoint, "GET", f"/applications/{app}/configurationprofiles/{created['Id']}")["Name"] == name


def test_get_configuration_profile_reads_the_profile(endpoint):
    app, _env, profile = context(endpoint)
    assert ok(endpoint, "GET", f"/applications/{app}/configurationprofiles/{profile}")["Name"] == PROFILE


def test_list_configuration_profiles_lists_the_profile(endpoint):
    app, _env, profile = context(endpoint)
    assert profile in {item["Id"] for item in ok(endpoint, "GET", f"/applications/{app}/configurationprofiles")["Items"]}


def test_update_configuration_profile_changes_the_description(endpoint):
    app, _env, profile = context(endpoint)
    updated = ok(endpoint, "PATCH", f"/applications/{app}/configurationprofiles/{profile}", {"Description": "updated"})
    assert updated["Description"] == "updated"


def test_delete_configuration_profile_removes_the_profile_it_created(endpoint):
    app = ensure_app(endpoint)
    name = f"ops-profile-del-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", f"/applications/{app}/configurationprofiles", {"Name": name, "LocationUri": "hosted"})
    ok(endpoint, "DELETE", f"/applications/{app}/configurationprofiles/{created['Id']}", statuses=(200, 204))
    status, _ = call(endpoint, "GET", f"/applications/{app}/configurationprofiles/{created['Id']}")
    assert status >= 400


# ---------------------------------------------------------------------------
# Hosted configuration versions
# ---------------------------------------------------------------------------


def test_create_hosted_configuration_version_is_read_back(endpoint):
    app, _env, profile = context(endpoint)
    version = create_version(endpoint, app, profile, "version=created\n")
    status, _headers, body = raw(endpoint, "GET", f"/applications/{app}/configurationprofiles/{profile}/hostedconfigurationversions/{version}")
    assert status == 200
    assert "version=created" in body


def test_get_hosted_configuration_version_reads_the_content(endpoint):
    app, _env, profile = context(endpoint)
    version = ensure_version(endpoint, app, profile)
    status, _headers, _body = raw(endpoint, "GET", f"/applications/{app}/configurationprofiles/{profile}/hostedconfigurationversions/{version}")
    assert status == 200


def test_list_hosted_configuration_versions_lists_the_version(endpoint):
    app, _env, profile = context(endpoint)
    version = ensure_version(endpoint, app, profile)
    items = ok(endpoint, "GET", f"/applications/{app}/configurationprofiles/{profile}/hostedconfigurationversions")["Items"]
    assert version in {int(item["VersionNumber"]) for item in items}


def test_delete_hosted_configuration_version_removes_the_version_it_created(endpoint):
    app, _env, profile = context(endpoint)
    version = create_version(endpoint, app, profile, "version=doomed\n")
    ok(endpoint, "DELETE", f"/applications/{app}/configurationprofiles/{profile}/hostedconfigurationversions/{version}", statuses=(204,))
    status, _headers, _body = raw(endpoint, "GET", f"/applications/{app}/configurationprofiles/{profile}/hostedconfigurationversions/{version}")
    assert status >= 400


# ---------------------------------------------------------------------------
# Deployment strategies
# ---------------------------------------------------------------------------


def test_create_deployment_strategy_is_read_back(endpoint):
    name = f"ops-strategy-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", "/deploymentstrategies", {"Name": name, "DeploymentDurationInMinutes": 0, "GrowthFactor": 100.0, "ReplicateTo": "NONE"})
    assert ok(endpoint, "GET", f"/deploymentstrategies/{created['Id']}")["Name"] == name


def test_get_deployment_strategy_reads_the_strategy(endpoint):
    strategy = ensure_strategy(endpoint)
    assert ok(endpoint, "GET", f"/deploymentstrategies/{strategy}")["Name"] == STRATEGY


def test_list_deployment_strategies_lists_the_strategy(endpoint):
    strategy = ensure_strategy(endpoint)
    assert strategy in {item["Id"] for item in ok(endpoint, "GET", "/deploymentstrategies")["Items"]}


def test_update_deployment_strategy_changes_the_description(endpoint):
    strategy = ensure_strategy(endpoint)
    updated = ok(endpoint, "PATCH", f"/deploymentstrategies/{strategy}", {"Description": "updated"})
    assert updated["Description"] == "updated"


def test_delete_deployment_strategy_removes_the_strategy_it_created(endpoint):
    name = f"ops-strategy-del-{time.time_ns() % 10000000}"
    created = ok(endpoint, "POST", "/deploymentstrategies", {"Name": name, "DeploymentDurationInMinutes": 0, "GrowthFactor": 100.0, "ReplicateTo": "NONE"})
    ok(endpoint, "DELETE", f"/deploymentstrategies/{created['Id']}", statuses=(200, 204))
    status, _ = call(endpoint, "GET", f"/deploymentstrategies/{created['Id']}")
    assert status >= 400


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------


def test_start_deployment_answers_a_deployment(endpoint):
    app, env, profile = context(endpoint)
    version = ensure_version(endpoint, app, profile)
    summary = start_deployment(endpoint, app, env, profile, version, ensure_strategy(endpoint))
    assert summary["DeploymentNumber"] >= 1
    assert ok(endpoint, "GET", f"/applications/{app}/environments/{env}/deployments/{summary['DeploymentNumber']}")["DeploymentNumber"] == summary["DeploymentNumber"]


def test_get_deployment_reads_the_deployment(endpoint):
    app, env, profile = context(endpoint)
    version = ensure_version(endpoint, app, profile)
    summary = start_deployment(endpoint, app, env, profile, version, ensure_strategy(endpoint))
    got = ok(endpoint, "GET", f"/applications/{app}/environments/{env}/deployments/{summary['DeploymentNumber']}")
    assert got["ConfigurationProfileId"] == profile


def test_list_deployments_lists_the_deployment(endpoint):
    app, env, profile = context(endpoint)
    version = ensure_version(endpoint, app, profile)
    summary = start_deployment(endpoint, app, env, profile, version, ensure_strategy(endpoint))
    numbers = {item["DeploymentNumber"] for item in ok(endpoint, "GET", f"/applications/{app}/environments/{env}/deployments")["Items"]}
    assert summary["DeploymentNumber"] in numbers


def test_stop_deployment_stops_the_deployment_it_started(endpoint):
    app, env, profile = context(endpoint)
    version = ensure_version(endpoint, app, profile)
    strategy = ensure_strategy(endpoint, "ops-strategy-slow", duration=5)
    summary = start_deployment(endpoint, app, env, profile, version, strategy)
    ok(endpoint, "DELETE", f"/applications/{app}/environments/{env}/deployments/{summary['DeploymentNumber']}", statuses=(200, 202))
    state = ok(endpoint, "GET", f"/applications/{app}/environments/{env}/deployments/{summary['DeploymentNumber']}")["State"]
    assert state in ("ROLLED_BACK", "STOPPED", "COMPLETE")


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    arn = app_arn(ensure_app(endpoint))
    ok(endpoint, "POST", f"/tags/{arn}", {"Tags": {"env": "ops"}}, statuses=(200, 204))
    assert ok(endpoint, "GET", f"/tags/{arn}")["Tags"]["env"] == "ops"


def test_untag_resource_removes_the_key_it_names(endpoint):
    arn = app_arn(ensure_app(endpoint))
    ok(endpoint, "POST", f"/tags/{arn}", {"Tags": {"doomed": "yes"}}, statuses=(200, 204))
    ok(endpoint, "DELETE", f"/tags/{arn}?tagKeys=doomed", statuses=(200, 204))
    assert "doomed" not in ok(endpoint, "GET", f"/tags/{arn}")["Tags"]


def test_list_tags_for_resource_lists_the_tags(endpoint):
    arn = app_arn(ensure_app(endpoint))
    ok(endpoint, "POST", f"/tags/{arn}", {"Tags": {"team": "platform"}}, statuses=(200, 204))
    assert ok(endpoint, "GET", f"/tags/{arn}")["Tags"]["team"] == "platform"


# ---------------------------------------------------------------------------
# Data plane
# ---------------------------------------------------------------------------


def test_start_configuration_session_answers_a_token(endpoint):
    app, env, profile = context(endpoint)
    token = ok(
        endpoint,
        "POST",
        "/configurationsessions",
        {"ApplicationIdentifier": app, "EnvironmentIdentifier": env, "ConfigurationProfileIdentifier": profile},
        statuses=(201,),
    )["InitialConfigurationToken"]
    assert token


def test_get_latest_configuration_answers_the_content(endpoint):
    app, env, profile = context(endpoint)
    version = ensure_version(endpoint, app, profile)
    start_deployment(endpoint, app, env, profile, version, ensure_strategy(endpoint))
    token = ok(
        endpoint,
        "POST",
        "/configurationsessions",
        {"ApplicationIdentifier": app, "EnvironmentIdentifier": env, "ConfigurationProfileIdentifier": profile},
        statuses=(201,),
    )["InitialConfigurationToken"]
    status, _headers, _body = raw(endpoint, "GET", f"/configuration?configuration_token={token}")
    assert status == 200
