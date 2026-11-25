"""API Gateway v1 on the wire: every advertised REST operation, driven through the control plane.

REST APIs are found-or-created behind a pinned ``ms-custom-id`` so a second sweep of the
same lab reuses the API it left behind instead of minting a duplicate. Everything nested
in the shared API (resources, methods, integrations, deployments, stages, authorizers,
models, parts, validators) is found before it is created for the same reason; a delete
action builds a resource of its own and removes only that.

Only one success path is out of reach: a domain-name access association that can be
*rejected* belongs to another account, and this control plane stamps every association
it creates with the caller's own account. That operation is pinned on the documented
owner response instead (404, association kept), and the gap is named in the report.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
EC2_VERSION = "2016-11-15"

# Stable names and ids, so a sweep that re-runs finds instead of conflicting.
SHARED = "ops-apigw-v1-shared"
SHARED_ID = "opsshared"
IMPORTED = "ops-apigw-v1-imported"
IMPORTED_ID = "opsimport"
DOOMED_API = "ops-apigw-v1-doomed"
DOOMED_API_ID = "opsdoomed"

STAGE = "ops"
DOOMED_STAGE = "ops-doomed"
DEPLOYMENT = "ops-apigw-v1-deployment"
UPDATE_DEPLOYMENT = "ops-apigw-v1-update"
DOOMED_DEPLOYMENT = "ops-apigw-v1-doomed-deployment"

DOMAIN = "ops-apigw-v1.example.com"
PRIVATE_DOMAIN = "ops-apigw-v1.internal.example.com"
DOOMED_DOMAIN = "ops-apigw-v1-deleted.example.com"
ASSOC_DOMAIN = "ops-apigw-v1-assoc-deleted.example.com"
CERTIFICATE_ARN = f"arn:aws:acm:{REGION}:{ACCOUNT}:certificate/00000000-0000-0000-0000-000000000000"

KEY = "ops-apigw-v1-key"
DOOMED_KEY = "ops-apigw-v1-key-doomed"
PLAN = "ops-apigw-v1-plan"
PLAN_KEY = "ops-apigw-v1-key-plan"
PLAN_KEY_DOOMED = "ops-apigw-v1-key-plan-doomed"
DOOMED_PLAN = "ops-apigw-v1-plan-doomed"

VALIDATOR = "ops-apigw-v1-validator"
VALIDATOR_UPDATED = "ops-apigw-v1-validator-updated"
VALIDATOR_DOOMED = "ops-apigw-v1-validator-doomed"
AUTHORIZER = "ops-apigw-v1-authorizer"
AUTHORIZER_DOOMED = "ops-apigw-v1-authorizer-doomed"
MODEL = "OpsApigwV1Model"
MODEL_DOOMED = "OpsApigwV1ModelDoomed"

CERTIFICATE = "ops-apigw-v1-certificate"
CERTIFICATE_DOOMED = "ops-apigw-v1-certificate-doomed"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, method: str, path: str, body=""):
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return signed.request(
        endpoint, "apigateway", ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = call(endpoint, method, path, body)
    assert status in (200, 201, 202, 204), f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text) if text.strip() else {}


def all_items(endpoint, path: str) -> list[dict]:
    """Every page of one paginated listing; a lab may hold more than one page."""
    found: list[dict] = []
    url = f"{path}{'&' if '?' in path else '?'}limit=500"
    while url:
        answer = ok(endpoint, "GET", url)
        found.extend(answer.get("item", []))
        position = answer.get("position")
        url = f"{path}{'&' if '?' in path else '?'}limit=500&position={position}" if position else ""
    return found


# ---------------------------------------------------------------------------
# REST APIs — CreateRestApi, GetRestApi, GetRestApis, UpdateRestApi, PutRestApi,
# DeleteRestApi
# ---------------------------------------------------------------------------


def ensure_api(endpoint, name: str, custom_id: str) -> dict:
    """Find-or-create behind the pinned id: the create is attempted every sweep and the
    pinned id makes a second attempt a ConflictException rather than a duplicate."""
    status, text = call(
        endpoint, "POST", "/restapis", {"name": name, "tags": {"ms-custom-id": custom_id}}
    )
    if status == 201:
        created = json.loads(text)
        assert created["id"] == custom_id
    else:
        assert status == 409 and "already in use" in text, (
            f"CreateRestApi answered {status}: {text[:400]}"
        )
        created = ok(endpoint, "GET", f"/restapis/{custom_id}")
    assert created["name"] == name
    return created


def shared(endpoint) -> dict:
    return ensure_api(endpoint, SHARED, SHARED_ID)


def test_create_rest_api_is_listed_by_get_rest_apis(s3_endpoint):
    api = shared(s3_endpoint)
    assert api["apiStatus"] == "AVAILABLE"
    assert api["rootResourceId"]
    assert api["endpointConfiguration"] == {"types": ["REGIONAL"]}

    listed = all_items(s3_endpoint, "/restapis")
    row = next(row for row in listed if row["id"] == SHARED_ID)
    assert row["name"] == SHARED
    assert row["rootResourceId"] == api["rootResourceId"]


def test_get_rest_api_returns_the_shared_api(s3_endpoint):
    answer = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}")
    assert answer["id"] == SHARED_ID
    assert answer["name"] == SHARED
    assert call(s3_endpoint, "GET", "/restapis/opsapigwmissing")[0] == 404


def test_update_rest_api_patches_the_description_read_back(s3_endpoint):
    shared(s3_endpoint)
    body = {"patchOperations": [{"op": "replace", "path": "/description", "value": "ops description"}]}
    answer = ok(s3_endpoint, "PATCH", f"/restapis/{SHARED_ID}", body)
    assert answer["description"] == "ops description"
    assert ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}")["description"] == "ops description"


def test_put_rest_api_imports_a_definition_into_its_own_api(s3_endpoint):
    ensure_api(s3_endpoint, IMPORTED, IMPORTED_ID)
    spec = {
        "swagger": "2.0",
        "info": {"title": IMPORTED, "version": "1.0"},
        "paths": {
            "/imported": {"get": {"responses": {"200": {"description": "ok"}}}},
        },
    }
    answer = ok(s3_endpoint, "PUT", f"/restapis/{IMPORTED_ID}?mode=merge", json.dumps(spec))
    assert answer["name"] == IMPORTED

    resources = all_items(s3_endpoint, f"/restapis/{IMPORTED_ID}/resources")
    imported = next(row for row in resources if row["path"] == "/imported")
    assert "GET" in ok(
        s3_endpoint, "GET", f"/restapis/{IMPORTED_ID}/resources/{imported['id']}"
    )["resourceMethods"]


def test_delete_rest_api_removes_the_api_it_created(s3_endpoint):
    api = ensure_api(s3_endpoint, DOOMED_API, DOOMED_API_ID)
    status, text = call(s3_endpoint, "DELETE", f"/restapis/{api['id']}")
    assert status == 202, f"DeleteRestApi answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"/restapis/{api['id']}")[0] == 404
    assert api["id"] not in [row["id"] for row in all_items(s3_endpoint, "/restapis")]


# ---------------------------------------------------------------------------
# Resources and methods — CreateResource, GetResource, GetResources,
# UpdateResource, DeleteResource, PutMethod, GetMethod, DeleteMethod, UpdateMethod
# ---------------------------------------------------------------------------


def tree(endpoint, api_id: str) -> list[dict]:
    return all_items(endpoint, f"/restapis/{api_id}/resources")


def sibling(endpoint, api_id: str, parent_id: str, path_part: str) -> dict | None:
    return next(
        (row for row in tree(endpoint, api_id)
         if row.get("parentId") == parent_id and row.get("pathPart") == path_part),
        None,
    )


def ensure_resource(endpoint, api_id: str, parent_id: str, path_part: str) -> dict:
    """Find-or-create by pathPart: the create is attempted every sweep, and the emulator's
    duplicate-name ConflictException is the answer a second sweep reads."""
    status, text = call(
        endpoint, "POST", f"/restapis/{api_id}/resources/{parent_id}", {"pathPart": path_part}
    )
    if status == 201:
        return json.loads(text)
    assert status == 409 and "already has this name" in text, (
        f"CreateResource answered {status}: {text[:400]}"
    )
    found = sibling(endpoint, api_id, parent_id, path_part)
    assert found, f"{path_part} is not under {parent_id}"
    return found


def ensure_method(endpoint, api_id: str, resource_id: str, verb: str) -> dict:
    body = {"authorizationType": "NONE", "operationName": "ops"}
    return ok(endpoint, "PUT", f"/restapis/{api_id}/resources/{resource_id}/methods/{verb}", body)


def ensure_integration(endpoint, api_id: str, resource_id: str, verb: str) -> dict:
    body = {"type": "MOCK", "httpMethod": "POST", "passthroughBehavior": "WHEN_NO_MATCH"}
    return ok(
        endpoint, "PUT", f"/restapis/{api_id}/resources/{resource_id}/methods/{verb}/integration", body
    )


def widgets(endpoint) -> tuple[str, str]:
    """The shared API's root id and its `/widgets` resource, which most CRUD hangs off."""
    api = shared(endpoint)
    root_id = api["rootResourceId"]
    resource = ensure_resource(endpoint, SHARED_ID, root_id, "widgets")
    assert resource["path"] == "/widgets"
    return root_id, resource["id"]


def test_create_resource_is_read_back_by_get_resource(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    answer = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/resources/{resource_id}")
    assert answer["id"] == resource_id
    assert answer["pathPart"] == "widgets"
    assert answer["path"] == "/widgets"
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/resources/opsapigwmissing")[0] == 404


def test_get_resources_lists_the_root_and_its_children(s3_endpoint):
    root_id, resource_id = widgets(s3_endpoint)
    paths = {row["path"]: row for row in tree(s3_endpoint, SHARED_ID)}
    assert "/" in paths
    assert paths["/"]["id"] == root_id
    assert paths["/widgets"]["id"] == resource_id


def test_update_resource_patches_the_path_part_read_back(s3_endpoint):
    api = shared(s3_endpoint)
    resource = ensure_resource(s3_endpoint, SHARED_ID, api["rootResourceId"], "ops-updated")
    body = {
        "patchOperations": [{"op": "replace", "path": "/pathPart", "value": "ops-updated"}]
    }
    answer = ok(
        s3_endpoint, "PATCH", f"/restapis/{SHARED_ID}/resources/{resource['id']}", body
    )
    assert answer["pathPart"] == "ops-updated"
    assert answer["path"] == "/ops-updated"
    read_back = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/resources/{resource['id']}")
    assert read_back["path"] == "/ops-updated"


def test_delete_resource_removes_the_resource_it_created(s3_endpoint):
    api = shared(s3_endpoint)
    resource = ensure_resource(s3_endpoint, SHARED_ID, api["rootResourceId"], "ops-resource-doomed")
    status, text = call(s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/resources/{resource['id']}")
    assert status == 202, f"DeleteResource answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/resources/{resource['id']}")[0] == 404
    )


def test_put_method_is_read_back_by_get_method(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    answer = ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    assert answer["httpMethod"] == "GET"
    assert answer["authorizationType"] == "NONE"

    read_back = ok(
        s3_endpoint, "GET", f"/restapis/{SHARED_ID}/resources/{resource_id}/methods/GET"
    )
    assert read_back["httpMethod"] == "GET"
    assert read_back["authorizationType"] == "NONE"


def test_delete_method_removes_the_method_it_created(s3_endpoint):
    api = shared(s3_endpoint)
    resource = ensure_resource(s3_endpoint, SHARED_ID, api["rootResourceId"], "ops-method-doomed")
    ensure_method(s3_endpoint, SHARED_ID, resource["id"], "GET")
    status, text = call(
        s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/resources/{resource['id']}/methods/GET"
    )
    assert status == 204, f"DeleteMethod answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/resources/{resource['id']}/methods/GET")[0]
        == 404
    )


def test_update_method_patches_the_operation_name(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/operationName", "value": "listWidgets"},
            {"op": "replace", "path": "/apiKeyRequired", "value": True},
        ]
    }
    answer = ok(
        s3_endpoint, "PATCH", f"/restapis/{SHARED_ID}/resources/{resource_id}/methods/GET", body
    )
    assert answer["operationName"] == "listWidgets"
    assert answer["apiKeyRequired"] is True
    read_back = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/resources/{resource_id}/methods/GET")
    assert read_back["operationName"] == "listWidgets"


# ---------------------------------------------------------------------------
# Method responses — PutMethodResponse, GetMethodResponse, DeleteMethodResponse
# ---------------------------------------------------------------------------


def method_path(resource_id: str, verb: str) -> str:
    return f"/restapis/{SHARED_ID}/resources/{resource_id}/methods/{verb}"


def test_put_method_response_is_read_back_by_get_method_response(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    body = {"responseParameters": {"method.response.header.ops": True}}
    answer = ok(s3_endpoint, "PUT", f"{method_path(resource_id, 'GET')}/responses/200", body)
    assert answer["statusCode"] == "200"
    assert answer["responseParameters"] == {"method.response.header.ops": True}

    read_back = ok(s3_endpoint, "GET", f"{method_path(resource_id, 'GET')}/responses/200")
    assert read_back["statusCode"] == "200"
    assert read_back["responseParameters"] == {"method.response.header.ops": True}
    assert call(s3_endpoint, "GET", f"{method_path(resource_id, 'GET')}/responses/599")[0] == 404


def test_delete_method_response_removes_the_response_it_created(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    ok(s3_endpoint, "PUT", f"{method_path(resource_id, 'GET')}/responses/201", {})
    status, text = call(s3_endpoint, "DELETE", f"{method_path(resource_id, 'GET')}/responses/201")
    assert status == 204, f"DeleteMethodResponse answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"{method_path(resource_id, 'GET')}/responses/201")[0] == 404


# ---------------------------------------------------------------------------
# Integrations — PutIntegration, GetIntegration, DeleteIntegration,
# UpdateIntegration
# ---------------------------------------------------------------------------


def test_put_integration_is_read_back_by_get_integration(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    answer = ensure_integration(s3_endpoint, SHARED_ID, resource_id, "GET")
    assert answer["type"] == "MOCK"
    assert answer["httpMethod"] == "POST"

    read_back = ok(s3_endpoint, "GET", f"{method_path(resource_id, 'GET')}/integration")
    assert read_back["type"] == "MOCK"
    assert read_back["httpMethod"] == "POST"
    assert read_back["cacheNamespace"] == resource_id


def test_update_integration_patches_the_passthrough_behavior(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    ensure_integration(s3_endpoint, SHARED_ID, resource_id, "GET")
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/passthroughBehavior", "value": "NEVER"},
            {"op": "replace", "path": "/timeoutInMillis", "value": 29000},
        ]
    }
    answer = ok(s3_endpoint, "PATCH", f"{method_path(resource_id, 'GET')}/integration", body)
    assert answer["passthroughBehavior"] == "NEVER"
    assert answer["timeoutInMillis"] == 29000
    read_back = ok(s3_endpoint, "GET", f"{method_path(resource_id, 'GET')}/integration")
    assert read_back["passthroughBehavior"] == "NEVER"


def test_delete_integration_removes_the_integration_it_created(s3_endpoint):
    api = shared(s3_endpoint)
    resource = ensure_resource(
        s3_endpoint, SHARED_ID, api["rootResourceId"], "ops-integration-doomed"
    )
    ensure_method(s3_endpoint, SHARED_ID, resource["id"], "GET")
    ensure_integration(s3_endpoint, SHARED_ID, resource["id"], "GET")
    status, text = call(
        s3_endpoint, "DELETE", f"{method_path(resource['id'], 'GET')}/integration"
    )
    assert status == 204, f"DeleteIntegration answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"{method_path(resource['id'], 'GET')}/integration")[0] == 404


# ---------------------------------------------------------------------------
# Integration responses — PutIntegrationResponse, GetIntegrationResponse,
# DeleteIntegrationResponse
# ---------------------------------------------------------------------------


def test_put_integration_response_is_read_back_by_get(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    ensure_integration(s3_endpoint, SHARED_ID, resource_id, "GET")
    body = {
        "selectionPattern": "",
        "responseParameters": {},
        "responseTemplates": {"application/json": '{"ok":true}'},
    }
    answer = ok(
        s3_endpoint, "PUT", f"{method_path(resource_id, 'GET')}/integration/responses/200", body
    )
    assert answer["statusCode"] == "200"
    assert answer["responseTemplates"] == {"application/json": '{"ok":true}'}

    read_back = ok(
        s3_endpoint, "GET", f"{method_path(resource_id, 'GET')}/integration/responses/200"
    )
    assert read_back["responseTemplates"] == {"application/json": '{"ok":true}'}


def test_delete_integration_response_removes_the_response_it_created(s3_endpoint):
    _root_id, resource_id = widgets(s3_endpoint)
    ensure_method(s3_endpoint, SHARED_ID, resource_id, "GET")
    ensure_integration(s3_endpoint, SHARED_ID, resource_id, "GET")
    ok(
        s3_endpoint,
        "PUT",
        f"{method_path(resource_id, 'GET')}/integration/responses/201",
        {"selectionPattern": "5\\d{2}"},
    )
    status, text = call(
        s3_endpoint, "DELETE", f"{method_path(resource_id, 'GET')}/integration/responses/201"
    )
    assert status == 204, f"DeleteIntegrationResponse answered {status}: {text[:400]}"
    assert (
        call(
            s3_endpoint, "GET", f"{method_path(resource_id, 'GET')}/integration/responses/201"
        )[0]
        == 404
    )


# ---------------------------------------------------------------------------
# Deployments and stages — CreateDeployment, GetDeployment, GetDeployments,
# UpdateDeployment, DeleteDeployment, CreateStage, GetStage, GetStages,
# UpdateStage, DeleteStage
# ---------------------------------------------------------------------------


def ensure_deployment(endpoint, api_id: str, description: str) -> dict:
    """Find-or-create behind a description prefix: a deployment has no name, and the
    update action lengthens the description rather than replacing it."""
    found = next(
        (
            row
            for row in all_items(endpoint, f"/restapis/{api_id}/deployments")
            if row.get("description", "").startswith(description)
        ),
        None,
    )
    if found:
        return found
    return ok(endpoint, "POST", f"/restapis/{api_id}/deployments", {"description": description})


def ensure_stage(endpoint, api_id: str, name: str) -> dict:
    deployment = ensure_deployment(endpoint, api_id, DEPLOYMENT)
    body = {"stageName": name, "deploymentId": deployment["id"], "description": "ops stage"}
    return ok(endpoint, "POST", f"/restapis/{api_id}/stages", body)


def test_create_deployment_is_read_back_by_get_deployment(s3_endpoint):
    shared(s3_endpoint)
    deployment = ensure_deployment(s3_endpoint, SHARED_ID, DEPLOYMENT)
    read_back = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/deployments/{deployment['id']}")
    assert read_back["id"] == deployment["id"]
    assert read_back["description"].startswith(DEPLOYMENT)
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/deployments/opsapigwmissing")[0] == 404


def test_get_deployments_lists_the_deployment(s3_endpoint):
    shared(s3_endpoint)
    deployment = ensure_deployment(s3_endpoint, SHARED_ID, DEPLOYMENT)
    listed = all_items(s3_endpoint, f"/restapis/{SHARED_ID}/deployments")
    row = next(row for row in listed if row["id"] == deployment["id"])
    assert row["description"].startswith(DEPLOYMENT)


def test_update_deployment_patches_the_description(s3_endpoint):
    shared(s3_endpoint)
    deployment = ensure_deployment(s3_endpoint, SHARED_ID, UPDATE_DEPLOYMENT)
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/description", "value": f"{UPDATE_DEPLOYMENT}-done"}
        ]
    }
    answer = ok(
        s3_endpoint, "PATCH", f"/restapis/{SHARED_ID}/deployments/{deployment['id']}", body
    )
    assert answer["description"] == f"{UPDATE_DEPLOYMENT}-done"
    assert (
        ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/deployments/{deployment['id']}")["description"]
        == f"{UPDATE_DEPLOYMENT}-done"
    )


def test_delete_deployment_removes_the_deployment_it_created(s3_endpoint):
    shared(s3_endpoint)
    deployment = ensure_deployment(s3_endpoint, SHARED_ID, DOOMED_DEPLOYMENT)
    status, text = call(
        s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/deployments/{deployment['id']}"
    )
    assert status == 202, f"DeleteDeployment answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/deployments/{deployment['id']}")[0] == 404
    )


def test_create_stage_is_read_back_by_get_stage(s3_endpoint):
    shared(s3_endpoint)
    created = ensure_stage(s3_endpoint, SHARED_ID, STAGE)
    assert created["stageName"] == STAGE

    read_back = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/stages/{STAGE}")
    assert read_back["stageName"] == STAGE
    assert read_back["deploymentId"] == created["deploymentId"]
    assert read_back["tracingEnabled"] is False
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/stages/opsapigwmissing")[0] == 404


def test_get_stages_lists_the_shared_stage(s3_endpoint):
    shared(s3_endpoint)
    ensure_stage(s3_endpoint, SHARED_ID, STAGE)
    answer = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/stages")
    assert STAGE in [row["stageName"] for row in answer["item"]]


def test_update_stage_patches_a_variable_read_back(s3_endpoint):
    shared(s3_endpoint)
    ensure_stage(s3_endpoint, SHARED_ID, STAGE)
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/variables/ops", "value": "on"},
            {"op": "replace", "path": "/tracingEnabled", "value": "false"},
        ]
    }
    answer = ok(s3_endpoint, "PATCH", f"/restapis/{SHARED_ID}/stages/{STAGE}", body)
    assert answer["variables"] == {"ops": "on"}
    assert ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/stages/{STAGE}")["variables"] == {
        "ops": "on"
    }


def test_delete_stage_removes_the_stage_it_created(s3_endpoint):
    shared(s3_endpoint)
    ensure_stage(s3_endpoint, SHARED_ID, DOOMED_STAGE)
    status, text = call(s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/stages/{DOOMED_STAGE}")
    assert status == 202, f"DeleteStage answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/stages/{DOOMED_STAGE}")[0] == 404


# ---------------------------------------------------------------------------
# Authorizers — CreateAuthorizer, GetAuthorizer, GetAuthorizers,
# UpdateAuthorizer, DeleteAuthorizer
# ---------------------------------------------------------------------------


def ensure_authorizer(endpoint, api_id: str, name: str) -> dict:
    found = next(
        (row for row in all_items(endpoint, f"/restapis/{api_id}/authorizers") if row["name"] == name),
        None,
    )
    if found:
        return found
    body = {
        "name": name,
        "type": "TOKEN",
        "identitySource": "method.request.header.Authorization",
        "authorizerResultTtlInSeconds": 300,
    }
    return ok(endpoint, "POST", f"/restapis/{api_id}/authorizers", body)


def test_create_authorizer_is_read_back_by_get_authorizer(s3_endpoint):
    shared(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, SHARED_ID, AUTHORIZER)
    read_back = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/authorizers/{authorizer['id']}")
    assert read_back["name"] == AUTHORIZER
    assert read_back["type"] == "TOKEN"
    assert read_back["identitySource"] == "method.request.header.Authorization"
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/authorizers/opsapigwmissing")[0] == 404


def test_get_authorizers_lists_the_shared_authorizer(s3_endpoint):
    shared(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, SHARED_ID, AUTHORIZER)
    listed = all_items(s3_endpoint, f"/restapis/{SHARED_ID}/authorizers")
    assert authorizer["id"] in [row["id"] for row in listed]


def test_update_authorizer_patches_the_ttl_read_back(s3_endpoint):
    shared(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, SHARED_ID, AUTHORIZER)
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/authorizerResultTtlInSeconds", "value": 600}
        ]
    }
    answer = ok(
        s3_endpoint, "PATCH", f"/restapis/{SHARED_ID}/authorizers/{authorizer['id']}", body
    )
    assert answer["authorizerResultTtlInSeconds"] == 600
    assert (
        ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/authorizers/{authorizer['id']}")[
            "authorizerResultTtlInSeconds"
        ]
        == 600
    )


def test_delete_authorizer_removes_the_authorizer_it_created(s3_endpoint):
    shared(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, SHARED_ID, AUTHORIZER_DOOMED)
    status, text = call(
        s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/authorizers/{authorizer['id']}"
    )
    assert status == 202, f"DeleteAuthorizer answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/authorizers/{authorizer['id']}")[0] == 404
    )


# ---------------------------------------------------------------------------
# Models — CreateModel, GetModel, GetModels, DeleteModel
# ---------------------------------------------------------------------------


def test_create_model_is_read_back_by_get_model(s3_endpoint):
    shared(s3_endpoint)
    schema = json.dumps({"type": "object", "properties": {"id": {"type": "string"}}})
    body = {"name": MODEL, "description": "ops model", "schema": schema, "contentType": "application/json"}
    answer = ok(s3_endpoint, "POST", f"/restapis/{SHARED_ID}/models", body)
    assert answer["name"] == MODEL

    read_back = ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/models/{MODEL}")
    assert read_back["name"] == MODEL
    assert read_back["contentType"] == "application/json"
    assert json.loads(read_back["schema"])["type"] == "object"
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/models/OpsMissing")[0] == 404


def test_get_models_lists_the_model(s3_endpoint):
    shared(s3_endpoint)
    listed = all_items(s3_endpoint, f"/restapis/{SHARED_ID}/models")
    assert MODEL in [row["name"] for row in listed]


def test_delete_model_removes_the_model_it_created(s3_endpoint):
    shared(s3_endpoint)
    body = {"name": MODEL_DOOMED, "contentType": "application/json", "schema": "{}"}
    ok(s3_endpoint, "POST", f"/restapis/{SHARED_ID}/models", body)
    status, text = call(s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/models/{MODEL_DOOMED}")
    assert status == 202, f"DeleteModel answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/models/{MODEL_DOOMED}")[0] == 404


# ---------------------------------------------------------------------------
# Documentation parts — CreateDocumentationPart, GetDocumentationPart,
# GetDocumentationParts, UpdateDocumentationPart, DeleteDocumentationPart
# ---------------------------------------------------------------------------


def parts(endpoint, api_id: str) -> list[dict]:
    return all_items(endpoint, f"/restapis/{api_id}/documentation/parts")


def ensure_documentation_part(endpoint, api_id: str, location_type: str, properties: str) -> dict:
    """Find-or-create behind the location type: a part has no name of its own, and the
    shared API owns exactly one part per type."""
    found = next(
        (row for row in parts(endpoint, api_id) if row["location"]["type"] == location_type),
        None,
    )
    if found:
        return found
    body = {"location": {"type": location_type}, "properties": properties}
    return ok(endpoint, "POST", f"/restapis/{api_id}/documentation/parts", body)


def test_create_documentation_part_is_read_back_by_get_part(s3_endpoint):
    shared(s3_endpoint)
    part = ensure_documentation_part(s3_endpoint, SHARED_ID, "API", "the shared api")
    read_back = ok(
        s3_endpoint, "GET", f"/restapis/{SHARED_ID}/documentation/parts/{part['id']}"
    )
    assert read_back["id"] == part["id"]
    assert read_back["location"] == {"type": "API"}
    assert call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/documentation/parts/missing")[0] == 404


def test_get_documentation_parts_filters_by_type(s3_endpoint):
    shared(s3_endpoint)
    part = ensure_documentation_part(s3_endpoint, SHARED_ID, "API", "the shared api")
    listed = all_items(s3_endpoint, f"/restapis/{SHARED_ID}/documentation/parts?type=API")
    assert part["id"] in [row["id"] for row in listed]
    assert all(row["location"]["type"] == "API" for row in listed)


def test_update_documentation_part_patches_the_properties(s3_endpoint):
    shared(s3_endpoint)
    part = ensure_documentation_part(s3_endpoint, SHARED_ID, "API", "the shared api")
    body = {"patchOperations": [{"op": "replace", "path": "/properties", "value": "updated docs"}]}
    answer = ok(
        s3_endpoint, "PATCH", f"/restapis/{SHARED_ID}/documentation/parts/{part['id']}", body
    )
    assert answer["properties"] == "updated docs"
    assert (
        ok(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/documentation/parts/{part['id']}")["properties"]
        == "updated docs"
    )


def test_delete_documentation_part_removes_the_part_it_created(s3_endpoint):
    shared(s3_endpoint)
    body = {"location": {"type": "MODEL", "name": MODEL}, "properties": "doomed"}
    part = ok(s3_endpoint, "POST", f"/restapis/{SHARED_ID}/documentation/parts", body)
    status, text = call(
        s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/documentation/parts/{part['id']}"
    )
    assert status == 202, f"DeleteDocumentationPart answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/documentation/parts/{part['id']}")[0] == 404
    )


# ---------------------------------------------------------------------------
# API keys — CreateApiKey, GetApiKey, GetApiKeys, UpdateApiKey, DeleteApiKey
# ---------------------------------------------------------------------------


def ensure_api_key(endpoint, name: str) -> dict:
    found = next(
        (row for row in all_items(endpoint, f"/apikeys?name={name}") if row["name"] == name),
        None,
    )
    if found:
        return found
    return ok(endpoint, "POST", "/apikeys", {"name": name, "description": "ops key", "enabled": True})


def test_create_api_key_is_read_back_by_get_api_key(s3_endpoint):
    key = ensure_api_key(s3_endpoint, KEY)
    read_back = ok(s3_endpoint, "GET", f"/apikeys/{key['id']}")
    assert read_back["name"] == KEY
    assert read_back["enabled"] is True
    assert read_back["value"]
    assert call(s3_endpoint, "GET", "/apikeys/opsapigwmissing")[0] == 404


def test_get_api_keys_lists_the_key(s3_endpoint):
    key = ensure_api_key(s3_endpoint, KEY)
    listed = all_items(s3_endpoint, "/apikeys")
    assert key["id"] in [row["id"] for row in listed]


def test_update_api_key_patches_the_description(s3_endpoint):
    key = ensure_api_key(s3_endpoint, KEY)
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/description", "value": "ops key updated"},
            {"op": "replace", "path": "/enabled", "value": True},
        ]
    }
    answer = ok(s3_endpoint, "PATCH", f"/apikeys/{key['id']}", body)
    assert answer["description"] == "ops key updated"
    assert ok(s3_endpoint, "GET", f"/apikeys/{key['id']}")["description"] == "ops key updated"


def test_delete_api_key_removes_the_key_it_created(s3_endpoint):
    key = ensure_api_key(s3_endpoint, DOOMED_KEY)
    status, text = call(s3_endpoint, "DELETE", f"/apikeys/{key['id']}")
    assert status == 202, f"DeleteApiKey answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"/apikeys/{key['id']}")[0] == 404
    assert key["id"] not in [
        row["id"] for row in all_items(s3_endpoint, f"/apikeys?name={DOOMED_KEY}")
    ]


# ---------------------------------------------------------------------------
# Usage plans — CreateUsagePlan, GetUsagePlan, GetUsagePlans, UpdateUsagePlan,
# DeleteUsagePlan, CreateUsagePlanKey, GetUsagePlanKeys, DeleteUsagePlanKey
# ---------------------------------------------------------------------------


def ensure_usage_plan(endpoint, name: str) -> dict:
    found = next(
        (row for row in all_items(endpoint, "/usageplans") if row["name"] == name),
        None,
    )
    if found:
        return found
    body = {
        "name": name,
        "description": "ops plan",
        "throttle": {"burstLimit": 100, "rateLimit": 50.0},
        "quota": {"limit": 1000, "period": "DAY"},
    }
    return ok(endpoint, "POST", "/usageplans", body)


def test_create_usage_plan_is_read_back_by_get_usage_plan(s3_endpoint):
    plan = ensure_usage_plan(s3_endpoint, PLAN)
    read_back = ok(s3_endpoint, "GET", f"/usageplans/{plan['id']}")
    assert read_back["name"] == PLAN
    assert read_back["throttle"]["burstLimit"] == 100
    assert read_back["quota"]["period"] == "DAY"
    assert call(s3_endpoint, "GET", "/usageplans/opsapigwmissing")[0] == 404


def test_get_usage_plans_lists_the_plan(s3_endpoint):
    plan = ensure_usage_plan(s3_endpoint, PLAN)
    listed = all_items(s3_endpoint, "/usageplans")
    assert plan["id"] in [row["id"] for row in listed]


def test_update_usage_plan_patches_the_description(s3_endpoint):
    plan = ensure_usage_plan(s3_endpoint, PLAN)
    body = {"patchOperations": [{"op": "replace", "path": "/description", "value": "ops plan updated"}]}
    answer = ok(s3_endpoint, "PATCH", f"/usageplans/{plan['id']}", body)
    assert answer["description"] == "ops plan updated"
    assert ok(s3_endpoint, "GET", f"/usageplans/{plan['id']}")["description"] == "ops plan updated"


def ensure_plan_key(endpoint, plan_id: str, key_name: str) -> dict:
    key = ensure_api_key(endpoint, key_name)
    body = {"keyId": key["id"], "keyType": "API_KEY"}
    # CreateUsagePlanKey is keyed by key id, so re-adding the same key is idempotent.
    return ok(endpoint, "POST", f"/usageplans/{plan_id}/keys", body)


def test_create_usage_plan_key_is_read_back_by_get_usage_plan_keys(s3_endpoint):
    plan = ensure_usage_plan(s3_endpoint, PLAN)
    plan_key = ensure_plan_key(s3_endpoint, plan["id"], PLAN_KEY)
    listed = all_items(s3_endpoint, f"/usageplans/{plan['id']}/keys")
    row = next(row for row in listed if row["id"] == plan_key["id"])
    assert row["type"] == "API_KEY"
    assert row["name"] == PLAN_KEY


def test_delete_usage_plan_key_removes_the_key_it_added(s3_endpoint):
    plan = ensure_usage_plan(s3_endpoint, PLAN)
    plan_key = ensure_plan_key(s3_endpoint, plan["id"], PLAN_KEY_DOOMED)
    status, text = call(s3_endpoint, "DELETE", f"/usageplans/{plan['id']}/keys/{plan_key['id']}")
    assert status == 202, f"DeleteUsagePlanKey answered {status}: {text[:400]}"
    assert plan_key["id"] not in [
        row["id"] for row in all_items(s3_endpoint, f"/usageplans/{plan['id']}/keys")
    ]


def test_delete_usage_plan_removes_the_plan_it_created(s3_endpoint):
    plan = ensure_usage_plan(s3_endpoint, DOOMED_PLAN)
    status, text = call(s3_endpoint, "DELETE", f"/usageplans/{plan['id']}")
    assert status == 202, f"DeleteUsagePlan answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"/usageplans/{plan['id']}")[0] == 404


# ---------------------------------------------------------------------------
# Domain names and access associations — CreateDomainName, GetDomainName,
# GetDomainNames, DeleteDomainName, CreateDomainNameAccessAssociation,
# GetDomainNameAccessAssociations, DeleteDomainNameAccessAssociation,
# RejectDomainNameAccessAssociation
# ---------------------------------------------------------------------------


def ensure_domain(endpoint, name: str, endpoint_types: list[str], **extra) -> dict:
    """Find-or-create by name: re-creating a private domain mints a fresh
    ``domainNameId``, which would orphan every association pinned to the old ARN."""
    status, text = call(endpoint, "GET", f"/domainnames/{name}")
    if status == 200:
        return json.loads(text)
    assert status == 404, f"GetDomainName answered {status}: {text[:400]}"
    body = {
        "domainName": name,
        "endpointConfiguration": {"types": endpoint_types},
        "regionalCertificateArn": CERTIFICATE_ARN,
        **extra,
    }
    return ok(endpoint, "POST", "/domainnames", body)


def ec2_call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": EC2_VERSION, **params})
    return signed.request(endpoint, "ec2", ACCOUNT, REGION, "POST", "/", body, FORM)


def ensure_vpc_endpoint(endpoint) -> str:
    """The VPC endpoint an association must name. API Gateway only checks that the id
    exists in EC2, so this is the smallest dependant the association needs."""
    service_name = f"com.amazonaws.{REGION}.execute-api"
    status, text = ec2_call(endpoint, "DescribeVpcEndpoints")
    assert status == 200, f"DescribeVpcEndpoints answered {status}: {text[:400]}"
    for block in text.split("<item>")[1:]:
        if f"<serviceName>{service_name}</serviceName>" in block:
            match = re.search(r"<vpcEndpointId>([^<]+)</vpcEndpointId>", block)
            if match:
                return match.group(1)
    status, text = ec2_call(
        endpoint,
        "CreateVpcEndpoint",
        ServiceName=service_name,
        VpcEndpointType="Interface",
    )
    assert status == 200, f"CreateVpcEndpoint answered {status}: {text[:400]}"
    match = re.search(r"<vpcEndpointId>([^<]+)</vpcEndpointId>", text)
    assert match, f"no vpcEndpointId in {text[:400]}"
    return match.group(1)


def ensure_association(endpoint, domain_arn: str, vpce_id: str) -> dict:
    found = next(
        (
            row
            for row in all_items(endpoint, "/domainnameaccessassociations")
            if row["domainNameArn"] == domain_arn and row["accessAssociationSource"] == vpce_id
        ),
        None,
    )
    if found:
        return found
    body = {
        "domainNameArn": domain_arn,
        "accessAssociationSourceType": "VPCE",
        "accessAssociationSource": vpce_id,
    }
    return ok(endpoint, "POST", "/domainnameaccessassociations", body)


def test_create_domain_name_is_read_back_by_get_domain_name(s3_endpoint):
    domain = ensure_domain(s3_endpoint, DOMAIN, ["REGIONAL"])
    read_back = ok(s3_endpoint, "GET", f"/domainnames/{DOMAIN}")
    assert read_back["domainName"] == DOMAIN
    assert read_back["domainNameStatus"] == "AVAILABLE"
    assert read_back["endpointConfiguration"]["types"] == ["REGIONAL"]
    assert read_back["regionalDomainName"]
    assert read_back["securityPolicy"] == "TLS_1_2"
    assert call(s3_endpoint, "GET", "/domainnames/ops-apigw-v1-missing.example.com")[0] == 404
    assert domain["domainName"] == DOMAIN


def test_get_domain_names_lists_the_domain(s3_endpoint):
    ensure_domain(s3_endpoint, DOMAIN, ["REGIONAL"])
    listed = all_items(s3_endpoint, "/domainnames")
    assert DOMAIN in [row["domainName"] for row in listed]


def test_delete_domain_name_removes_the_domain_it_created(s3_endpoint):
    ensure_domain(s3_endpoint, DOOMED_DOMAIN, ["REGIONAL"])
    status, text = call(s3_endpoint, "DELETE", f"/domainnames/{DOOMED_DOMAIN}")
    assert status == 202, f"DeleteDomainName answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"/domainnames/{DOOMED_DOMAIN}")[0] == 404


def test_create_domain_name_access_association_is_listed(s3_endpoint):
    domain = ensure_domain(s3_endpoint, PRIVATE_DOMAIN, ["PRIVATE"])
    assert domain["domainNameArn"].endswith(f"{PRIVATE_DOMAIN}+{domain['domainNameId']}")
    vpce_id = ensure_vpc_endpoint(s3_endpoint)
    association = ensure_association(s3_endpoint, domain["domainNameArn"], vpce_id)
    assert association["accessAssociationSourceType"] == "VPCE"
    assert association["accessAssociationSource"] == vpce_id

    listed = all_items(s3_endpoint, "/domainnameaccessassociations")
    assert association["domainNameAccessAssociationArn"] in [
        row["domainNameAccessAssociationArn"] for row in listed
    ]


def test_delete_domain_name_access_association_removes_the_one_it_created(s3_endpoint):
    domain = ensure_domain(s3_endpoint, ASSOC_DOMAIN, ["PRIVATE"])
    vpce_id = ensure_vpc_endpoint(s3_endpoint)
    association = ensure_association(s3_endpoint, domain["domainNameArn"], vpce_id)
    arn = association["domainNameAccessAssociationArn"]
    status, text = call(s3_endpoint, "DELETE", f"/domainnameaccessassociations/{arn}")
    assert status == 202, f"DeleteDomainNameAccessAssociation answered {status}: {text[:400]}"
    assert arn not in [
        row["domainNameAccessAssociationArn"]
        for row in all_items(s3_endpoint, "/domainnameaccessassociations")
    ]


def test_reject_domain_name_access_association_refuses_the_owners_own(s3_endpoint):
    """A rejectable association belongs to another account; this control plane stamps
    every association it creates with the caller's, so the owner's own is refused."""
    domain = ensure_domain(s3_endpoint, PRIVATE_DOMAIN, ["PRIVATE"])
    vpce_id = ensure_vpc_endpoint(s3_endpoint)
    association = ensure_association(s3_endpoint, domain["domainNameArn"], vpce_id)
    arn = association["domainNameAccessAssociationArn"]
    query = urlencode(
        {"domainNameAccessAssociationArn": arn, "domainNameArn": domain["domainNameArn"]}
    )
    status, text = call(s3_endpoint, "POST", f"/rejectdomainnameaccessassociations?{query}")
    assert status == 404, f"RejectDomainNameAccessAssociation answered {status}: {text[:400]}"
    assert arn in [
        row["domainNameAccessAssociationArn"]
        for row in all_items(s3_endpoint, "/domainnameaccessassociations")
    ]


# ---------------------------------------------------------------------------
# Client certificates — GenerateClientCertificate, GetClientCertificate,
# GetClientCertificates, UpdateClientCertificate, DeleteClientCertificate
# ---------------------------------------------------------------------------


def ensure_certificate(endpoint, description: str) -> dict:
    found = next(
        (
            row
            for row in all_items(endpoint, "/clientcertificates")
            if row.get("description", "").startswith(description)
        ),
        None,
    )
    if found:
        return found
    return ok(endpoint, "POST", "/clientcertificates", {"description": description})


def test_generate_client_certificate_is_read_back_by_get_client_certificate(s3_endpoint):
    certificate = ensure_certificate(s3_endpoint, CERTIFICATE)
    read_back = ok(s3_endpoint, "GET", f"/clientcertificates/{certificate['clientCertificateId']}")
    assert read_back["clientCertificateId"] == certificate["clientCertificateId"]
    assert read_back["description"].startswith(CERTIFICATE)
    assert read_back["expirationDate"] > read_back["createdDate"]
    if "pemEncodedCertificate" in read_back:
        assert read_back["pemEncodedCertificate"].startswith("-----BEGIN CERTIFICATE-----")
    assert call(s3_endpoint, "GET", "/clientcertificates/opsmissing")[0] == 404


def test_get_client_certificates_lists_the_certificate(s3_endpoint):
    certificate = ensure_certificate(s3_endpoint, CERTIFICATE)
    listed = all_items(s3_endpoint, "/clientcertificates")
    assert certificate["clientCertificateId"] in [
        row["clientCertificateId"] for row in listed
    ]


def test_update_client_certificate_patches_the_description(s3_endpoint):
    certificate = ensure_certificate(s3_endpoint, CERTIFICATE)
    cert_id = certificate["clientCertificateId"]
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/description", "value": f"{CERTIFICATE}-updated"}
        ]
    }
    answer = ok(s3_endpoint, "PATCH", f"/clientcertificates/{cert_id}", body)
    assert answer["description"] == f"{CERTIFICATE}-updated"
    assert ok(s3_endpoint, "GET", f"/clientcertificates/{cert_id}")["description"] == (
        f"{CERTIFICATE}-updated"
    )


def test_delete_client_certificate_removes_the_certificate_it_created(s3_endpoint):
    certificate = ok(
        s3_endpoint, "POST", "/clientcertificates", {"description": CERTIFICATE_DOOMED}
    )
    status, text = call(
        s3_endpoint, "DELETE", f"/clientcertificates/{certificate['clientCertificateId']}"
    )
    assert status == 202, f"DeleteClientCertificate answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/clientcertificates/{certificate['clientCertificateId']}")[0]
        == 404
    )


# ---------------------------------------------------------------------------
# Base path mappings — CreateBasePathMapping, GetBasePathMapping,
# GetBasePathMappings, DeleteBasePathMapping
# ---------------------------------------------------------------------------


def test_create_base_path_mapping_is_read_back_by_get_base_path_mapping(s3_endpoint):
    shared(s3_endpoint)
    ensure_domain(s3_endpoint, DOMAIN, ["REGIONAL"])
    ensure_stage(s3_endpoint, SHARED_ID, STAGE)
    body = {"basePath": "ops", "restApiId": SHARED_ID, "stage": STAGE}
    answer = ok(s3_endpoint, "POST", f"/domainnames/{DOMAIN}/basepathmappings", body)
    assert answer["basePath"] == "ops"

    read_back = ok(s3_endpoint, "GET", f"/domainnames/{DOMAIN}/basepathmappings/ops")
    assert read_back["basePath"] == "ops"
    assert read_back["restApiId"] == SHARED_ID
    assert read_back["stage"] == STAGE
    assert call(s3_endpoint, "GET", f"/domainnames/{DOMAIN}/basepathmappings/missing")[0] == 404


def test_get_base_path_mappings_lists_the_mapping(s3_endpoint):
    shared(s3_endpoint)
    ensure_domain(s3_endpoint, DOMAIN, ["REGIONAL"])
    ensure_stage(s3_endpoint, SHARED_ID, STAGE)
    ok(
        s3_endpoint,
        "POST",
        f"/domainnames/{DOMAIN}/basepathmappings",
        {"basePath": "ops", "restApiId": SHARED_ID, "stage": STAGE},
    )
    listed = all_items(s3_endpoint, f"/domainnames/{DOMAIN}/basepathmappings")
    assert "ops" in [row["basePath"] for row in listed]


def test_delete_base_path_mapping_removes_the_mapping_it_created(s3_endpoint):
    shared(s3_endpoint)
    ensure_domain(s3_endpoint, DOMAIN, ["REGIONAL"])
    ensure_stage(s3_endpoint, SHARED_ID, STAGE)
    ok(
        s3_endpoint,
        "POST",
        f"/domainnames/{DOMAIN}/basepathmappings",
        {"basePath": "ops-doomed", "restApiId": SHARED_ID, "stage": STAGE},
    )
    status, text = call(s3_endpoint, "DELETE", f"/domainnames/{DOMAIN}/basepathmappings/ops-doomed")
    assert status == 202, f"DeleteBasePathMapping answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/domainnames/{DOMAIN}/basepathmappings/ops-doomed")[0] == 404
    )


# ---------------------------------------------------------------------------
# Request validators — CreateRequestValidator, GetRequestValidators,
# GetRequestValidator, UpdateRequestValidator, DeleteRequestValidator
# ---------------------------------------------------------------------------


def ensure_validator(endpoint, api_id: str, name: str, *, validate_parameters: bool = False) -> dict:
    """Find-or-create by name, and put the one flag a test asserts back to its initial
    value so a sweep that finds the validator still reads what the create set."""
    found = next(
        (
            row
            for row in all_items(endpoint, f"/restapis/{api_id}/requestvalidators")
            if row["name"] == name
        ),
        None,
    )
    if found:
        if found["validateRequestParameters"] is validate_parameters:
            return found
        body = {
            "patchOperations": [
                {
                    "op": "replace",
                    "path": "/validateRequestParameters",
                    "value": str(validate_parameters).lower(),
                }
            ]
        }
        return ok(
            endpoint, "PATCH", f"/restapis/{api_id}/requestvalidators/{found['id']}", body
        )
    body = {
        "name": name,
        "validateRequestBody": True,
        "validateRequestParameters": validate_parameters,
    }
    return ok(endpoint, "POST", f"/restapis/{api_id}/requestvalidators", body)


def test_create_request_validator_is_read_back_by_get_request_validator(s3_endpoint):
    shared(s3_endpoint)
    validator = ensure_validator(s3_endpoint, SHARED_ID, VALIDATOR)
    read_back = ok(
        s3_endpoint, "GET", f"/restapis/{SHARED_ID}/requestvalidators/{validator['id']}"
    )
    assert read_back["name"] == VALIDATOR
    assert read_back["validateRequestBody"] is True
    assert read_back["validateRequestParameters"] is False
    assert (
        call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/requestvalidators/opsmissing")[0] == 404
    )


def test_get_request_validators_lists_the_validator(s3_endpoint):
    shared(s3_endpoint)
    validator = ensure_validator(s3_endpoint, SHARED_ID, VALIDATOR)
    listed = all_items(s3_endpoint, f"/restapis/{SHARED_ID}/requestvalidators")
    assert validator["id"] in [row["id"] for row in listed]


def test_update_request_validator_patches_the_flags(s3_endpoint):
    shared(s3_endpoint)
    # Its own validator, so the shared one keeps the flags its create test asserts.
    validator = ensure_validator(
        s3_endpoint, SHARED_ID, VALIDATOR_UPDATED, validate_parameters=True
    )
    body = {
        "patchOperations": [
            {"op": "replace", "path": "/validateRequestParameters", "value": "true"}
        ]
    }
    answer = ok(
        s3_endpoint,
        "PATCH",
        f"/restapis/{SHARED_ID}/requestvalidators/{validator['id']}",
        body,
    )
    assert answer["validateRequestParameters"] is True
    assert (
        ok(
            s3_endpoint, "GET", f"/restapis/{SHARED_ID}/requestvalidators/{validator['id']}"
        )["validateRequestParameters"]
        is True
    )


def test_delete_request_validator_removes_the_validator_it_created(s3_endpoint):
    shared(s3_endpoint)
    validator = ensure_validator(s3_endpoint, SHARED_ID, VALIDATOR_DOOMED)
    status, text = call(
        s3_endpoint, "DELETE", f"/restapis/{SHARED_ID}/requestvalidators/{validator['id']}"
    )
    assert status == 204, f"DeleteRequestValidator answered {status}: {text[:400]}"
    assert (
        call(s3_endpoint, "GET", f"/restapis/{SHARED_ID}/requestvalidators/{validator['id']}")[0]
        == 404
    )


# ---------------------------------------------------------------------------
# Tags — TagResource, UntagResource, GetTags
# ---------------------------------------------------------------------------


def rest_api_arn(api_id: str) -> str:
    return f"arn:aws:apigateway:{REGION}::/restapis/{api_id}"


def test_tag_resource_is_read_back_by_get_tags(s3_endpoint):
    shared(s3_endpoint)
    arn = rest_api_arn(SHARED_ID)
    status, text = call(s3_endpoint, "PUT", f"/tags/{arn}", {"tags": {"ops": "on"}})
    assert status == 204, f"TagResource answered {status}: {text[:400]}"
    assert ok(s3_endpoint, "GET", f"/tags/{arn}")["tags"]["ops"] == "on"


def test_untag_resource_removes_only_the_key_it_names(s3_endpoint):
    shared(s3_endpoint)
    arn = rest_api_arn(SHARED_ID)
    body = {"tags": {"ops-doomed": "yes", "ops-kept": "yes"}}
    assert call(s3_endpoint, "PUT", f"/tags/{arn}", body)[0] == 204
    status, text = call(s3_endpoint, "DELETE", f"/tags/{arn}?tagKeys=ops-doomed")
    assert status == 204, f"UntagResource answered {status}: {text[:400]}"
    remaining = ok(s3_endpoint, "GET", f"/tags/{arn}")["tags"]
    assert "ops-doomed" not in remaining
    assert remaining["ops-kept"] == "yes"


def test_get_tags_returns_the_tags_the_api_carries(s3_endpoint):
    shared(s3_endpoint)
    arn = rest_api_arn(SHARED_ID)
    assert call(s3_endpoint, "PUT", f"/tags/{arn}", {"tags": {"owner": "emuplane"}})[0] == 204
    tags = ok(s3_endpoint, "GET", f"/tags/{arn}")["tags"]
    assert tags["owner"] == "emuplane"
