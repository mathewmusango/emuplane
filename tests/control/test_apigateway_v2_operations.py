"""API Gateway v2 on the wire: every advertised control-plane operation, HTTP and WebSocket.

An API is found-or-created behind a pinned ``ms-custom-id`` tag, so a second sweep of the
same lab reuses the API it left behind instead of minting a duplicate. Everything nested
in an API (routes, integrations, responses, stages, deployments, authorizers) is found
before it is created — routes by route key, integrations and deployments by description,
responses by their key, authorizers by name, stages by stage name — and a delete action
builds a resource of its own and removes only that.

The shared HTTP API carries the API, stage, deployment, authorizer, domain and tag
surfaces; the shared WebSocket API carries routes, integrations and the two response
collections, because that is the protocol that has them. Every integration here is MOCK,
so no Lambda has to exist behind a route. A resource an update action mutates belongs to
that action (``ops-updated`` beside ``$default``), so no create assertion reads a field
another test writes.

``PostToConnection``, ``GetConnection`` and ``DeleteConnection`` are the three operations
that cannot be driven here: the emulator registers a connection id only inside
``handle_websocket`` after an ASGI ``websocket.connect``, and the test harness serves the
emulator through a plain HTTP stand-in that has no upgrade path. They live in
``test_apigateway_ws_operations.py``, which runs against a lab.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}

# Stable names and ids, so a sweep that re-runs finds instead of conflicting.
HTTP_API = "ops-apigw-v2-http"
HTTP_API_ID = "opsv2htt"
WS_API = "ops-apigw-v2-websocket"
WS_API_ID = "opsv2wsx"
DOOMED_API = "ops-apigw-v2-doomed"
DOOMED_API_ID = "opsv2del"

STAGE = "ops"
DOOMED_STAGE = "ops-doomed"
DEPLOYMENT = "ops-apigw-v2-deployment"
DOOMED_DEPLOYMENT = "ops-apigw-v2-doomed-deployment"

AUTHORIZER = "ops-apigw-v2-authorizer"
DOOMED_AUTHORIZER = "ops-apigw-v2-authorizer-doomed"
JWT_ISSUER = "https://ops-apigw-v2.example.com"
JWT_AUDIENCE = ["ops-client"]

DOMAIN = "ops-apigw-v2.example.com"
DOOMED_DOMAIN = "ops-apigw-v2-doomed.example.com"
MAPPING_KEY = "ops-v2"
DOOMED_MAPPING_KEY = "ops-v2-doomed"

WS_ROUTE = "$default"
WS_ROUTE_UPDATED = "ops-updated"
WS_ROUTE_DOOMED = "ops-doomed"
INTEGRATION = "ops-apigw-v2-mock-integration"
INTEGRATION_UPDATED = "ops-apigw-v2-mock-integration-updated"
INTEGRATION_DOOMED = "ops-apigw-v2-mock-integration-doomed"
ROUTE_RESPONSE_KEY = "$default"
ROUTE_RESPONSE_UPDATED = "ops-updated"
ROUTE_RESPONSE_DOOMED = "ops-doomed"
INTEGRATION_RESPONSE_KEY = "$default"
INTEGRATION_RESPONSE_UPDATED = "ops-updated"
INTEGRATION_RESPONSE_DOOMED = "ops-doomed"

TAG_CREATED = "ops-created"
TAG_KEPT = "ops-kept"
TAG_DOOMED = "ops-doomed"


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
    assert status in (200, 201, 202, 204), (
        f"{method} {path} answered {status}: {text[:400]}"
    )
    return json.loads(text) if text.strip() else {}


def all_items(endpoint, path: str) -> list[dict]:
    """Every page of one v2 listing: a lab may hold more than one page."""
    found: list[dict] = []
    separator = "&" if "?" in path else "?"
    url = f"{path}{separator}maxResults=100"
    while url:
        answer = ok(endpoint, "GET", url)
        found.extend(answer.get("items", []))
        token = answer.get("nextToken")
        url = f"{path}{separator}maxResults=100&nextToken={token}" if token else ""
    return found


def api_arn(api_id: str) -> str:
    return f"arn:aws:apigateway:{REGION}::/apis/{api_id}"


# ---------------------------------------------------------------------------
# APIs — CreateApi, GetApi, GetApis, UpdateApi, DeleteApi
# ---------------------------------------------------------------------------


def ensure_api(endpoint, name: str, api_id: str, protocol: str = "HTTP") -> dict:
    """Find-or-create behind the pinned id: the create is attempted every sweep and the
    pinned id makes a second attempt a ConflictException rather than a duplicate."""
    status, text = call(
        endpoint,
        "POST",
        "/v2/apis",
        {
            "name": name,
            "protocolType": protocol,
            "description": "ops fixture",
            "tags": {"ms-custom-id": api_id},
        },
    )
    if status == 201:
        created = json.loads(text)
        assert created["apiId"] == api_id
    else:
        assert status == 409 and "already in use" in text, (
            f"CreateApi answered {status}: {text[:400]}"
        )
        created = ok(endpoint, "GET", f"/v2/apis/{api_id}")
    assert created["name"] == name
    return created


def shared_http(endpoint) -> dict:
    return ensure_api(endpoint, HTTP_API, HTTP_API_ID, "HTTP")


def shared_websocket(endpoint) -> dict:
    return ensure_api(endpoint, WS_API, WS_API_ID, "WEBSOCKET")


def test_create_api_is_listed_by_get_apis(s3_endpoint):
    api = shared_http(s3_endpoint)
    assert api["apiId"] == HTTP_API_ID
    assert api["protocolType"] == "HTTP"
    assert f"{HTTP_API_ID}.execute-api." in api["apiEndpoint"]
    assert api["routeSelectionExpression"] == "$request.method $request.path"

    websocket = shared_websocket(s3_endpoint)
    assert websocket["protocolType"] == "WEBSOCKET"
    assert websocket["routeSelectionExpression"] == "$request.body.action"

    listed = {row["apiId"]: row for row in all_items(s3_endpoint, "/v2/apis")}
    assert listed[HTTP_API_ID]["name"] == HTTP_API
    assert listed[WS_API_ID]["name"] == WS_API


def test_get_api_returns_the_shared_api(s3_endpoint):
    shared_http(s3_endpoint)
    answer = ok(s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}")
    assert answer["apiId"] == HTTP_API_ID
    assert answer["name"] == HTTP_API
    assert answer["createdDate"]
    status, text = call(s3_endpoint, "GET", "/v2/apis/opsv2missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_update_api_patches_the_fields_it_is_given(s3_endpoint):
    shared_http(s3_endpoint)
    body = {
        "description": "ops description",
        "version": "2",
        "corsConfiguration": {
            "allowOrigins": ["https://ops.example.com"],
            "allowMethods": ["GET"],
            "allowHeaders": ["content-type"],
            "maxAge": 600,
        },
    }
    answer = ok(s3_endpoint, "PATCH", f"/v2/apis/{HTTP_API_ID}", body)
    assert answer["description"] == "ops description"
    assert answer["version"] == "2"
    assert answer["corsConfiguration"]["allowOrigins"] == ["https://ops.example.com"]

    read_back = ok(s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}")
    assert read_back["description"] == "ops description"
    assert read_back["corsConfiguration"]["maxAge"] == 600
    status, text = call(s3_endpoint, "PATCH", "/v2/apis/opsv2missing", {"description": "x"})
    assert status == 404, text[:400]


def test_delete_api_removes_the_api_it_created(s3_endpoint):
    api = ensure_api(s3_endpoint, DOOMED_API, DOOMED_API_ID)
    status, text = call(s3_endpoint, "DELETE", f"/v2/apis/{api['apiId']}")
    assert status == 204, f"DeleteApi answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"/v2/apis/{api['apiId']}")[0] == 404
    assert api["apiId"] not in [
        row["apiId"] for row in all_items(s3_endpoint, "/v2/apis")
    ]


# ---------------------------------------------------------------------------
# Integrations — CreateIntegration, GetIntegration, GetIntegrations,
# UpdateIntegration, DeleteIntegration
# ---------------------------------------------------------------------------


def integrations(endpoint, api_id: str) -> list[dict]:
    return all_items(endpoint, f"/v2/apis/{api_id}/integrations")


def find_integration(endpoint, api_id: str, description: str) -> dict | None:
    return next(
        (row for row in integrations(endpoint, api_id) if row.get("description") == description),
        None,
    )


def ensure_integration(endpoint, api_id: str, description: str = INTEGRATION) -> dict:
    """Find-or-create by description: a MOCK integration needs no Lambda behind it."""
    found = find_integration(endpoint, api_id, description)
    if found:
        return found
    answer = ok(
        endpoint,
        "POST",
        f"/v2/apis/{api_id}/integrations",
        {"integrationType": "MOCK", "description": description},
    )
    assert answer["description"] == description
    return answer


def test_create_integration_is_read_back_by_get_integration(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    assert integration["integrationType"] == "MOCK"
    assert integration["integrationMethod"] == "POST"
    # A WebSocket integration is payload format 1.0, and the emulator says so.
    assert integration["payloadFormatVersion"] == "1.0"
    assert integration["timeoutInMillis"] == 29000

    read_back = ok(
        s3_endpoint, "GET", f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
    )
    assert read_back["integrationId"] == integration["integrationId"]
    assert read_back["integrationType"] == "MOCK"


def test_get_integration_returns_the_shared_integration(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    answer = ok(
        s3_endpoint, "GET", f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
    )
    assert answer["description"] == INTEGRATION
    status, text = call(
        s3_endpoint, "GET", f"/v2/apis/{WS_API_ID}/integrations/opsv2missing"
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_integrations_lists_the_shared_integration(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    rows = {row["integrationId"]: row for row in integrations(s3_endpoint, WS_API_ID)}
    assert rows[integration["integrationId"]]["description"] == INTEGRATION


def test_update_integration_patches_the_fields_it_is_given(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID, INTEGRATION_UPDATED)
    body = {"timeoutInMillis": 5000, "contentHandlingStrategy": "CONVERT_TO_TEXT"}
    answer = ok(
        s3_endpoint,
        "PATCH",
        f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}",
        body,
    )
    assert answer["timeoutInMillis"] == 5000
    assert answer["contentHandlingStrategy"] == "CONVERT_TO_TEXT"
    read_back = ok(
        s3_endpoint, "GET", f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
    )
    assert read_back["timeoutInMillis"] == 5000
    # The description is the find marker, so the update leaves it alone.
    assert read_back["description"] == INTEGRATION_UPDATED


def test_delete_integration_removes_the_integration_it_created(s3_endpoint):
    shared_websocket(s3_endpoint)
    doomed = ensure_integration(s3_endpoint, WS_API_ID, INTEGRATION_DOOMED)
    path = f"/v2/apis/{WS_API_ID}/integrations/{doomed['integrationId']}"
    status, text = call(s3_endpoint, "DELETE", path)
    assert status == 204, f"DeleteIntegration answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", path)[0] == 404
    assert doomed["integrationId"] not in [
        row["integrationId"] for row in integrations(s3_endpoint, WS_API_ID)
    ]


# ---------------------------------------------------------------------------
# Routes — CreateRoute, GetRoute, GetRoutes, UpdateRoute, DeleteRoute
# ---------------------------------------------------------------------------


def routes(endpoint, api_id: str) -> list[dict]:
    return all_items(endpoint, f"/v2/apis/{api_id}/routes")


def find_route(endpoint, api_id: str, route_key: str) -> dict | None:
    return next(
        (row for row in routes(endpoint, api_id) if row.get("routeKey") == route_key),
        None,
    )


def route_target(endpoint, api_id: str) -> str:
    return f"integrations/{ensure_integration(endpoint, api_id)['integrationId']}"


def ensure_route(endpoint, api_id: str, route_key: str, target: str = "") -> dict:
    """Find-or-create by route key: the emulator does not keep them unique, so a
    second sweep reads the route the first one left rather than adding another."""
    found = find_route(endpoint, api_id, route_key)
    if found:
        return found
    body = {"routeKey": route_key}
    if target:
        body["target"] = target
    answer = ok(endpoint, "POST", f"/v2/apis/{api_id}/routes", body)
    assert answer["routeKey"] == route_key
    return answer


def test_create_route_targets_the_mock_integration(s3_endpoint):
    shared_websocket(s3_endpoint)
    target = route_target(s3_endpoint, WS_API_ID)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, target)
    assert route["routeId"]
    assert route["routeKey"] == WS_ROUTE
    assert route["target"] == target
    assert route["authorizationType"] == "NONE"
    assert route["apiKeyRequired"] is False


def test_get_route_returns_the_shared_route(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, route_target(s3_endpoint, WS_API_ID))
    answer = ok(s3_endpoint, "GET", f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}")
    assert answer["routeKey"] == WS_ROUTE
    assert answer["routeId"] == route["routeId"]
    status, text = call(s3_endpoint, "GET", f"/v2/apis/{WS_API_ID}/routes/opsv2missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_routes_lists_the_shared_route(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, route_target(s3_endpoint, WS_API_ID))
    rows = {row["routeId"]: row for row in routes(s3_endpoint, WS_API_ID)}
    assert rows[route["routeId"]]["routeKey"] == WS_ROUTE


def test_update_route_patches_the_fields_it_is_given(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE_UPDATED)
    body = {"operationName": "ops-updated", "apiKeyRequired": True}
    answer = ok(
        s3_endpoint, "PATCH", f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}", body
    )
    assert answer["operationName"] == "ops-updated"
    assert answer["apiKeyRequired"] is True
    read_back = ok(s3_endpoint, "GET", f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}")
    assert read_back["operationName"] == "ops-updated"
    # The route key is the find marker, so the update leaves it alone.
    assert read_back["routeKey"] == WS_ROUTE_UPDATED


def test_delete_route_removes_the_route_it_created(s3_endpoint):
    shared_websocket(s3_endpoint)
    doomed = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE_DOOMED)
    path = f"/v2/apis/{WS_API_ID}/routes/{doomed['routeId']}"
    status, text = call(s3_endpoint, "DELETE", path)
    assert status == 204, f"DeleteRoute answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", path)[0] == 404
    assert doomed["routeId"] not in [
        row["routeId"] for row in routes(s3_endpoint, WS_API_ID)
    ]


# ---------------------------------------------------------------------------
# Route responses — CreateRouteResponse, GetRouteResponse, GetRouteResponses,
# UpdateRouteResponse, DeleteRouteResponse
# ---------------------------------------------------------------------------


def route_responses(endpoint, api_id: str, route_id: str) -> list[dict]:
    return all_items(
        endpoint, f"/v2/apis/{api_id}/routes/{route_id}/routeresponses"
    )


def find_route_response(endpoint, api_id: str, route_id: str, key: str) -> dict | None:
    return next(
        (
            row
            for row in route_responses(endpoint, api_id, route_id)
            if row.get("routeResponseKey") == key
        ),
        None,
    )


def ensure_route_response(
    endpoint, api_id: str, route_id: str, key: str = ROUTE_RESPONSE_KEY
) -> dict:
    """Find-or-create by response key on the shared route."""
    found = find_route_response(endpoint, api_id, route_id, key)
    if found:
        return found
    answer = ok(
        endpoint,
        "POST",
        f"/v2/apis/{api_id}/routes/{route_id}/routeresponses",
        {"routeResponseKey": key, "responseParameters": {"method.response.header.x-ops": True}},
    )
    assert answer["routeResponseKey"] == key
    return answer


def test_create_route_response_is_read_back_by_get_route_response(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, route_target(s3_endpoint, WS_API_ID))
    response = ensure_route_response(s3_endpoint, WS_API_ID, route["routeId"])
    assert response["routeResponseId"]
    assert response["routeResponseKey"] == ROUTE_RESPONSE_KEY
    assert response["responseParameters"] == {"method.response.header.x-ops": True}

    read_back = ok(
        s3_endpoint,
        "GET",
        f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}"
        f"/routeresponses/{response['routeResponseId']}",
    )
    assert read_back["routeResponseId"] == response["routeResponseId"]


def test_get_route_response_returns_the_shared_response(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, route_target(s3_endpoint, WS_API_ID))
    response = ensure_route_response(s3_endpoint, WS_API_ID, route["routeId"])
    base = f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}/routeresponses"
    answer = ok(s3_endpoint, "GET", f"{base}/{response['routeResponseId']}")
    assert answer["routeResponseKey"] == ROUTE_RESPONSE_KEY
    status, text = call(s3_endpoint, "GET", f"{base}/opsv2missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_route_responses_lists_the_shared_response(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, route_target(s3_endpoint, WS_API_ID))
    response = ensure_route_response(s3_endpoint, WS_API_ID, route["routeId"])
    rows = {
        row["routeResponseId"]: row
        for row in route_responses(s3_endpoint, WS_API_ID, route["routeId"])
    }
    assert rows[response["routeResponseId"]]["routeResponseKey"] == ROUTE_RESPONSE_KEY


def test_update_route_response_patches_the_fields_it_is_given(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, route_target(s3_endpoint, WS_API_ID))
    response = ensure_route_response(
        s3_endpoint, WS_API_ID, route["routeId"], ROUTE_RESPONSE_UPDATED
    )
    body = {
        "responseParameters": {"method.response.header.x-ops-updated": True},
        "modelSelectionExpression": "$request.body.action",
    }
    answer = ok(
        s3_endpoint,
        "PATCH",
        f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}"
        f"/routeresponses/{response['routeResponseId']}",
        body,
    )
    assert answer["modelSelectionExpression"] == "$request.body.action"
    assert answer["responseParameters"] == {
        "method.response.header.x-ops-updated": True
    }
    read_back = ok(
        s3_endpoint,
        "GET",
        f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}"
        f"/routeresponses/{response['routeResponseId']}",
    )
    assert read_back["modelSelectionExpression"] == "$request.body.action"
    # The response key is the find marker, so the update leaves it alone.
    assert read_back["routeResponseKey"] == ROUTE_RESPONSE_UPDATED


def test_delete_route_response_removes_the_response_it_created(s3_endpoint):
    shared_websocket(s3_endpoint)
    route = ensure_route(s3_endpoint, WS_API_ID, WS_ROUTE, route_target(s3_endpoint, WS_API_ID))
    doomed = ensure_route_response(
        s3_endpoint, WS_API_ID, route["routeId"], ROUTE_RESPONSE_DOOMED
    )
    base = f"/v2/apis/{WS_API_ID}/routes/{route['routeId']}/routeresponses"
    status, text = call(s3_endpoint, "DELETE", f"{base}/{doomed['routeResponseId']}")
    assert status == 204, f"DeleteRouteResponse answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"{base}/{doomed['routeResponseId']}")[0] == 404
    assert doomed["routeResponseId"] not in [
        row["routeResponseId"]
        for row in route_responses(s3_endpoint, WS_API_ID, route["routeId"])
    ]


# ---------------------------------------------------------------------------
# Integration responses — CreateIntegrationResponse, GetIntegrationResponse,
# GetIntegrationResponses, UpdateIntegrationResponse, DeleteIntegrationResponse
# ---------------------------------------------------------------------------


def integration_responses(endpoint, api_id: str, integration_id: str) -> list[dict]:
    return all_items(
        endpoint, f"/v2/apis/{api_id}/integrations/{integration_id}/integrationresponses"
    )


def find_integration_response(
    endpoint, api_id: str, integration_id: str, key: str
) -> dict | None:
    return next(
        (
            row
            for row in integration_responses(endpoint, api_id, integration_id)
            if row.get("integrationResponseKey") == key
        ),
        None,
    )


def ensure_integration_response(
    endpoint, api_id: str, integration_id: str, key: str = INTEGRATION_RESPONSE_KEY
) -> dict:
    """Find-or-create by response key on the shared integration."""
    found = find_integration_response(endpoint, api_id, integration_id, key)
    if found:
        return found
    answer = ok(
        endpoint,
        "POST",
        f"/v2/apis/{api_id}/integrations/{integration_id}/integrationresponses",
        {
            "integrationResponseKey": key,
            "contentHandlingStrategy": "CONVERT_TO_TEXT",
            "responseTemplates": {"$default": '{"ok":true}'},
        },
    )
    assert answer["integrationResponseKey"] == key
    return answer


def test_create_integration_response_is_read_back(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    response = ensure_integration_response(
        s3_endpoint, WS_API_ID, integration["integrationId"]
    )
    assert response["integrationResponseId"]
    assert response["integrationResponseKey"] == INTEGRATION_RESPONSE_KEY
    assert response["responseTemplates"] == {"$default": '{"ok":true}'}

    read_back = ok(
        s3_endpoint,
        "GET",
        f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
        f"/integrationresponses/{response['integrationResponseId']}",
    )
    assert read_back["integrationResponseId"] == response["integrationResponseId"]


def test_get_integration_response_returns_the_shared_response(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    response = ensure_integration_response(
        s3_endpoint, WS_API_ID, integration["integrationId"]
    )
    base = (
        f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
        "/integrationresponses"
    )
    answer = ok(s3_endpoint, "GET", f"{base}/{response['integrationResponseId']}")
    assert answer["integrationResponseKey"] == INTEGRATION_RESPONSE_KEY
    status, text = call(s3_endpoint, "GET", f"{base}/opsv2missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_integration_responses_lists_the_shared_response(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    response = ensure_integration_response(
        s3_endpoint, WS_API_ID, integration["integrationId"]
    )
    rows = {
        row["integrationResponseId"]: row
        for row in integration_responses(
            s3_endpoint, WS_API_ID, integration["integrationId"]
        )
    }
    assert rows[response["integrationResponseId"]]["integrationResponseKey"] == (
        INTEGRATION_RESPONSE_KEY
    )


def test_update_integration_response_patches_the_fields_it_is_given(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    response = ensure_integration_response(
        s3_endpoint, WS_API_ID, integration["integrationId"], INTEGRATION_RESPONSE_UPDATED
    )
    body = {
        "contentHandlingStrategy": "CONVERT_TO_BINARY",
        "responseTemplates": {"$default": '{"ok":"updated"}'},
    }
    answer = ok(
        s3_endpoint,
        "PATCH",
        f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
        f"/integrationresponses/{response['integrationResponseId']}",
        body,
    )
    assert answer["contentHandlingStrategy"] == "CONVERT_TO_BINARY"
    assert answer["responseTemplates"] == {"$default": '{"ok":"updated"}'}
    read_back = ok(
        s3_endpoint,
        "GET",
        f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
        f"/integrationresponses/{response['integrationResponseId']}",
    )
    assert read_back["contentHandlingStrategy"] == "CONVERT_TO_BINARY"
    # The response key is the find marker, so the update leaves it alone.
    assert read_back["integrationResponseKey"] == INTEGRATION_RESPONSE_UPDATED


def test_delete_integration_response_removes_the_response_it_created(s3_endpoint):
    shared_websocket(s3_endpoint)
    integration = ensure_integration(s3_endpoint, WS_API_ID)
    doomed = ensure_integration_response(
        s3_endpoint, WS_API_ID, integration["integrationId"], INTEGRATION_RESPONSE_DOOMED
    )
    base = (
        f"/v2/apis/{WS_API_ID}/integrations/{integration['integrationId']}"
        "/integrationresponses"
    )
    status, text = call(
        s3_endpoint, "DELETE", f"{base}/{doomed['integrationResponseId']}"
    )
    assert status == 204, f"DeleteIntegrationResponse answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"{base}/{doomed['integrationResponseId']}")[0] == 404
    assert doomed["integrationResponseId"] not in [
        row["integrationResponseId"]
        for row in integration_responses(
            s3_endpoint, WS_API_ID, integration["integrationId"]
        )
    ]


# ---------------------------------------------------------------------------
# Stages — CreateStage, GetStage, GetStages, UpdateStage, DeleteStage
# ---------------------------------------------------------------------------

UPDATED_STAGE = "ops-updated"


def stages(endpoint, api_id: str) -> list[dict]:
    return all_items(endpoint, f"/v2/apis/{api_id}/stages")


def find_stage(endpoint, api_id: str, name: str) -> dict | None:
    return next((row for row in stages(endpoint, api_id) if row.get("stageName") == name), None)


def ensure_stage(
    endpoint,
    api_id: str,
    name: str = STAGE,
    description: str = "ops stage",
    stage_variables: dict | None = None,
) -> dict:
    """Find-or-create by stage name; the create carries the stage's own settings."""
    found = find_stage(endpoint, api_id, name)
    if found:
        return found
    answer = ok(
        endpoint,
        "POST",
        f"/v2/apis/{api_id}/stages",
        {
            "stageName": name,
            "autoDeploy": True,
            "description": description,
            "stageVariables": stage_variables or {"env": "ops"},
            "tags": {"owner": "emuplane"},
        },
    )
    assert answer["stageName"] == name
    return answer


def test_create_stage_is_read_back_by_get_stage(s3_endpoint):
    shared_http(s3_endpoint)
    stage = ensure_stage(s3_endpoint, HTTP_API_ID)
    assert stage["stageName"] == STAGE
    assert stage["autoDeploy"] is True
    assert stage["description"] == "ops stage"
    assert stage["stageVariables"] == {"env": "ops"}
    assert stage["tags"] == {"owner": "emuplane"}

    read_back = ok(s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/stages/{STAGE}")
    assert read_back["stageName"] == STAGE
    assert read_back["tags"] == {"owner": "emuplane"}


def test_get_stage_returns_the_shared_stage(s3_endpoint):
    shared_http(s3_endpoint)
    ensure_stage(s3_endpoint, HTTP_API_ID)
    answer = ok(s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/stages/{STAGE}")
    assert answer["stageName"] == STAGE
    assert answer["createdDate"]
    status, text = call(s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/stages/opsv2missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_stages_lists_the_shared_stage(s3_endpoint):
    shared_http(s3_endpoint)
    ensure_stage(s3_endpoint, HTTP_API_ID)
    names = [row["stageName"] for row in stages(s3_endpoint, HTTP_API_ID)]
    assert STAGE in names


def test_update_stage_patches_the_fields_it_is_given(s3_endpoint):
    shared_http(s3_endpoint)
    ensure_stage(s3_endpoint, HTTP_API_ID, UPDATED_STAGE, "ops stage before the update")
    body = {
        "description": "ops stage updated",
        "stageVariables": {"env": "ops-updated"},
        "autoDeploy": False,
    }
    answer = ok(s3_endpoint, "PATCH", f"/v2/apis/{HTTP_API_ID}/stages/{UPDATED_STAGE}", body)
    assert answer["description"] == "ops stage updated"
    assert answer["stageVariables"] == {"env": "ops-updated"}
    assert answer["autoDeploy"] is False
    read_back = ok(s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/stages/{UPDATED_STAGE}")
    assert read_back["description"] == "ops stage updated"
    assert read_back["stageVariables"] == {"env": "ops-updated"}


def test_delete_stage_removes_the_stage_it_created(s3_endpoint):
    shared_http(s3_endpoint)
    ensure_stage(s3_endpoint, HTTP_API_ID, DOOMED_STAGE, "ops stage doomed")
    path = f"/v2/apis/{HTTP_API_ID}/stages/{DOOMED_STAGE}"
    status, text = call(s3_endpoint, "DELETE", path)
    assert status == 204, f"DeleteStage answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", path)[0] == 404
    assert DOOMED_STAGE not in [row["stageName"] for row in stages(s3_endpoint, HTTP_API_ID)]


# ---------------------------------------------------------------------------
# Deployments — CreateDeployment, GetDeployment, GetDeployments, DeleteDeployment
# ---------------------------------------------------------------------------


def deployments(endpoint, api_id: str) -> list[dict]:
    return all_items(endpoint, f"/v2/apis/{api_id}/deployments")


def find_deployment(endpoint, api_id: str, description: str) -> dict | None:
    return next(
        (row for row in deployments(endpoint, api_id) if row.get("description") == description),
        None,
    )


def ensure_deployment(endpoint, api_id: str, description: str = DEPLOYMENT) -> dict:
    """Find-or-create by description: a deployment id is minted by the emulator."""
    found = find_deployment(endpoint, api_id, description)
    if found:
        return found
    answer = ok(
        endpoint,
        "POST",
        f"/v2/apis/{api_id}/deployments",
        {"description": description},
    )
    assert answer["description"] == description
    return answer


def test_create_deployment_is_read_back_by_get_deployment(s3_endpoint):
    shared_http(s3_endpoint)
    deployment = ensure_deployment(s3_endpoint, HTTP_API_ID)
    assert deployment["deploymentId"]
    assert deployment["deploymentStatus"] == "DEPLOYED"
    assert deployment["createdDate"]

    read_back = ok(
        s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/deployments/{deployment['deploymentId']}"
    )
    assert read_back["deploymentId"] == deployment["deploymentId"]
    assert read_back["deploymentStatus"] == "DEPLOYED"


def test_get_deployment_returns_the_shared_deployment(s3_endpoint):
    shared_http(s3_endpoint)
    deployment = ensure_deployment(s3_endpoint, HTTP_API_ID)
    answer = ok(
        s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/deployments/{deployment['deploymentId']}"
    )
    assert answer["description"] == DEPLOYMENT
    status, text = call(s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/deployments/opsv2missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_deployments_lists_the_shared_deployment(s3_endpoint):
    shared_http(s3_endpoint)
    deployment = ensure_deployment(s3_endpoint, HTTP_API_ID)
    rows = {row["deploymentId"]: row for row in deployments(s3_endpoint, HTTP_API_ID)}
    assert rows[deployment["deploymentId"]]["description"] == DEPLOYMENT


def test_delete_deployment_removes_the_deployment_it_created(s3_endpoint):
    shared_http(s3_endpoint)
    doomed = ensure_deployment(s3_endpoint, HTTP_API_ID, DOOMED_DEPLOYMENT)
    path = f"/v2/apis/{HTTP_API_ID}/deployments/{doomed['deploymentId']}"
    status, text = call(s3_endpoint, "DELETE", path)
    assert status == 204, f"DeleteDeployment answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", path)[0] == 404
    assert doomed["deploymentId"] not in [
        row["deploymentId"] for row in deployments(s3_endpoint, HTTP_API_ID)
    ]


# ---------------------------------------------------------------------------
# Authorizers — CreateAuthorizer, GetAuthorizer, GetAuthorizers,
# UpdateAuthorizer, DeleteAuthorizer
# ---------------------------------------------------------------------------

UPDATED_AUTHORIZER = "ops-apigw-v2-authorizer-updated"


def authorizers(endpoint, api_id: str) -> list[dict]:
    return all_items(endpoint, f"/v2/apis/{api_id}/authorizers")


def find_authorizer(endpoint, api_id: str, name: str) -> dict | None:
    return next((row for row in authorizers(endpoint, api_id) if row.get("name") == name), None)


def ensure_authorizer(endpoint, api_id: str, name: str = AUTHORIZER) -> dict:
    """Find-or-create by name, as a JWT authorizer on the HTTP API."""
    found = find_authorizer(endpoint, api_id, name)
    if found:
        return found
    answer = ok(
        endpoint,
        "POST",
        f"/v2/apis/{api_id}/authorizers",
        {
            "name": name,
            "authorizerType": "JWT",
            "identitySource": ["$request.header.Authorization"],
            "jwtConfiguration": {"Issuer": JWT_ISSUER, "Audience": JWT_AUDIENCE},
        },
    )
    assert answer["name"] == name
    return answer


def test_create_authorizer_is_read_back_by_get_authorizer(s3_endpoint):
    shared_http(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, HTTP_API_ID)
    assert authorizer["authorizerId"]
    assert authorizer["authorizerType"] == "JWT"
    assert authorizer["identitySource"] == ["$request.header.Authorization"]
    assert authorizer["jwtConfiguration"] == {
        "Issuer": JWT_ISSUER,
        "Audience": JWT_AUDIENCE,
    }
    assert authorizer["authorizerResultTtlInSeconds"] == 300

    read_back = ok(
        s3_endpoint,
        "GET",
        f"/v2/apis/{HTTP_API_ID}/authorizers/{authorizer['authorizerId']}",
    )
    assert read_back["authorizerId"] == authorizer["authorizerId"]

    # A WebSocket API only has REQUEST authorizers.
    status, text = call(
        s3_endpoint,
        "POST",
        f"/v2/apis/{WS_API_ID}/authorizers",
        {"name": "ops-apigw-v2-jwt-on-websocket", "authorizerType": "JWT"},
    )
    assert status == 400, text[:400]
    assert "Only REQUEST authorizer type is supported" in text


def test_get_authorizer_returns_the_shared_authorizer(s3_endpoint):
    shared_http(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, HTTP_API_ID)
    answer = ok(
        s3_endpoint,
        "GET",
        f"/v2/apis/{HTTP_API_ID}/authorizers/{authorizer['authorizerId']}",
    )
    assert answer["name"] == AUTHORIZER
    status, text = call(
        s3_endpoint, "GET", f"/v2/apis/{HTTP_API_ID}/authorizers/opsv2missing"
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_authorizers_lists_the_shared_authorizer(s3_endpoint):
    shared_http(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, HTTP_API_ID)
    rows = {row["authorizerId"]: row for row in authorizers(s3_endpoint, HTTP_API_ID)}
    assert rows[authorizer["authorizerId"]]["name"] == AUTHORIZER


def test_update_authorizer_patches_the_fields_it_is_given(s3_endpoint):
    shared_http(s3_endpoint)
    authorizer = ensure_authorizer(s3_endpoint, HTTP_API_ID, UPDATED_AUTHORIZER)
    body = {
        "authorizerResultTtlInSeconds": 60,
        "jwtConfiguration": {"Issuer": JWT_ISSUER, "Audience": ["ops-client", "ops-other"]},
    }
    answer = ok(
        s3_endpoint,
        "PATCH",
        f"/v2/apis/{HTTP_API_ID}/authorizers/{authorizer['authorizerId']}",
        body,
    )
    assert answer["authorizerResultTtlInSeconds"] == 60
    assert answer["jwtConfiguration"]["Audience"] == ["ops-client", "ops-other"]
    read_back = ok(
        s3_endpoint,
        "GET",
        f"/v2/apis/{HTTP_API_ID}/authorizers/{authorizer['authorizerId']}",
    )
    assert read_back["authorizerResultTtlInSeconds"] == 60
    # The name is the find marker, so the update leaves it alone.
    assert read_back["name"] == UPDATED_AUTHORIZER


def test_delete_authorizer_removes_the_authorizer_it_created(s3_endpoint):
    shared_http(s3_endpoint)
    doomed = ensure_authorizer(s3_endpoint, HTTP_API_ID, DOOMED_AUTHORIZER)
    path = f"/v2/apis/{HTTP_API_ID}/authorizers/{doomed['authorizerId']}"
    status, text = call(s3_endpoint, "DELETE", path)
    assert status == 204, f"DeleteAuthorizer answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", path)[0] == 404
    assert doomed["authorizerId"] not in [
        row["authorizerId"] for row in authorizers(s3_endpoint, HTTP_API_ID)
    ]


# ---------------------------------------------------------------------------
# Domain names — CreateDomainName, GetDomainName, GetDomainNames,
# UpdateDomainName, DeleteDomainName
# ---------------------------------------------------------------------------

# The update test renames its own mapping, so it needs a domain the read tests do not use.
UPDATE_DOMAIN = "ops-apigw-v2-update.example.com"
UPDATED_MAPPING_KEY = "ops-v2-map"
UPDATED_MAPPING_RENAMED = "ops-v2-map-renamed"


def domains(endpoint) -> list[dict]:
    return all_items(endpoint, "/v2/domainnames")


def find_domain(endpoint, name: str) -> dict | None:
    return next((row for row in domains(endpoint) if row.get("domainName") == name), None)


def ensure_domain(endpoint, name: str, endpoint_type: str = "REGIONAL") -> dict:
    """Find-or-create by name; a domain name is unique, so the create is the claim."""
    found = find_domain(endpoint, name)
    if found:
        return found
    status, text = call(
        endpoint,
        "POST",
        "/v2/domainnames",
        {
            "domainName": name,
            "domainNameConfigurations": [{"endpointType": endpoint_type}],
        },
    )
    if status == 201:
        created = json.loads(text)
        assert created["domainName"] == name
        return created
    # Another sweep won the race; the name is what it is found by.
    assert status == 409 and "already exists" in text, (
        f"CreateDomainName answered {status}: {text[:400]}"
    )
    found = find_domain(endpoint, name)
    assert found, f"{name} was refused as existing but is not in GetDomainNames"
    return found


def test_create_domain_name_is_read_back_by_get_domain_name(s3_endpoint):
    domain = ensure_domain(s3_endpoint, DOMAIN)
    assert domain["domainName"] == DOMAIN
    assert domain["apiMappingSelectionExpression"] == "$request.basepath"
    assert domain["domainNameArn"] == (
        f"arn:aws:apigateway:{REGION}::/domainnames/{DOMAIN}"
    )
    configuration = domain["domainNameConfigurations"][0]
    assert configuration["endpointType"] == "REGIONAL"
    assert configuration["domainNameStatus"] == "AVAILABLE"
    assert configuration["apiGatewayDomainName"]

    read_back = ok(s3_endpoint, "GET", f"/v2/domainnames/{DOMAIN}")
    assert read_back["domainName"] == DOMAIN


def test_get_domain_name_returns_the_shared_domain(s3_endpoint):
    ensure_domain(s3_endpoint, DOMAIN)
    answer = ok(s3_endpoint, "GET", f"/v2/domainnames/{DOMAIN}")
    assert answer["domainName"] == DOMAIN
    assert answer["domainNameConfigurations"][0]["domainNameStatus"] == "AVAILABLE"
    status, text = call(s3_endpoint, "GET", "/v2/domainnames/ops-apigw-v2-missing.example.com")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_domain_names_lists_the_shared_domain(s3_endpoint):
    ensure_domain(s3_endpoint, DOMAIN)
    names = [row["domainName"] for row in domains(s3_endpoint)]
    assert DOMAIN in names


def test_update_domain_name_patches_the_fields_it_is_given(s3_endpoint):
    ensure_domain(s3_endpoint, UPDATE_DOMAIN)
    body = {"routingMode": "ROUTING_RULE_THEN_API_MAPPING"}
    answer = ok(s3_endpoint, "PATCH", f"/v2/domainnames/{UPDATE_DOMAIN}", body)
    assert answer["routingMode"] == "ROUTING_RULE_THEN_API_MAPPING"
    read_back = ok(s3_endpoint, "GET", f"/v2/domainnames/{UPDATE_DOMAIN}")
    assert read_back["routingMode"] == "ROUTING_RULE_THEN_API_MAPPING"
    status, text = call(
        s3_endpoint,
        "PATCH",
        f"/v2/domainnames/{UPDATE_DOMAIN}",
        {"routingMode": "NOT_A_ROUTING_MODE"},
    )
    assert status == 400, text[:400]
    assert "Invalid routingMode" in text


def test_delete_domain_name_removes_the_domain_it_created(s3_endpoint):
    ensure_domain(s3_endpoint, DOOMED_DOMAIN)
    path = f"/v2/domainnames/{DOOMED_DOMAIN}"
    status, text = call(s3_endpoint, "DELETE", path)
    assert status == 204, f"DeleteDomainName answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", path)[0] == 404
    assert DOOMED_DOMAIN not in [row["domainName"] for row in domains(s3_endpoint)]


# ---------------------------------------------------------------------------
# API mappings — CreateApiMapping, GetApiMapping, GetApiMappings,
# UpdateApiMapping, DeleteApiMapping
# ---------------------------------------------------------------------------


def api_mappings(endpoint, domain: str) -> list[dict]:
    return all_items(endpoint, f"/v2/domainnames/{domain}/apimappings")


def find_mapping(endpoint, domain: str, *keys: str) -> dict | None:
    """A mapping is found by any of its keys, so a renamed one is still the same row."""
    return next(
        (row for row in api_mappings(endpoint, domain) if row.get("apiMappingKey") in keys),
        None,
    )


def ensure_mapping(endpoint, domain: str, api_id: str, stage: str, *keys: str) -> dict:
    found = find_mapping(endpoint, domain, *keys)
    if found:
        return found
    answer = ok(
        endpoint,
        "POST",
        f"/v2/domainnames/{domain}/apimappings",
        {"apiId": api_id, "stage": stage, "apiMappingKey": keys[0]},
    )
    assert answer["apiMappingKey"] == keys[0]
    return answer


def test_create_api_mapping_points_the_domain_at_the_stage(s3_endpoint):
    ensure_domain(s3_endpoint, DOMAIN)
    ensure_stage(s3_endpoint, HTTP_API_ID)
    mapping = ensure_mapping(s3_endpoint, DOMAIN, HTTP_API_ID, STAGE, MAPPING_KEY)
    assert mapping["apiMappingId"]
    assert mapping["apiId"] == HTTP_API_ID
    assert mapping["stage"] == STAGE
    assert mapping["apiMappingKey"] == MAPPING_KEY

    # A mapping must name a stage that exists on the target API.
    status, text = call(
        s3_endpoint,
        "POST",
        f"/v2/domainnames/{DOMAIN}/apimappings",
        {"apiId": HTTP_API_ID, "stage": "opsv2missing", "apiMappingKey": "ops-v2-bad"},
    )
    assert status == 400, text[:400]
    assert "Invalid stage identifier specified" in text


def test_get_api_mapping_returns_the_shared_mapping(s3_endpoint):
    ensure_domain(s3_endpoint, DOMAIN)
    ensure_stage(s3_endpoint, HTTP_API_ID)
    mapping = ensure_mapping(s3_endpoint, DOMAIN, HTTP_API_ID, STAGE, MAPPING_KEY)
    base = f"/v2/domainnames/{DOMAIN}/apimappings"
    answer = ok(s3_endpoint, "GET", f"{base}/{mapping['apiMappingId']}")
    assert answer["apiMappingKey"] == MAPPING_KEY
    assert answer["apiId"] == HTTP_API_ID
    status, text = call(s3_endpoint, "GET", f"{base}/opsv2missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_get_api_mappings_lists_the_shared_mapping(s3_endpoint):
    ensure_domain(s3_endpoint, DOMAIN)
    ensure_stage(s3_endpoint, HTTP_API_ID)
    mapping = ensure_mapping(s3_endpoint, DOMAIN, HTTP_API_ID, STAGE, MAPPING_KEY)
    rows = {
        row["apiMappingId"]: row for row in api_mappings(s3_endpoint, DOMAIN)
    }
    assert rows[mapping["apiMappingId"]]["apiMappingKey"] == MAPPING_KEY


def test_update_api_mapping_renames_the_mapping_it_created(s3_endpoint):
    ensure_domain(s3_endpoint, UPDATE_DOMAIN)
    ensure_stage(s3_endpoint, HTTP_API_ID)
    mapping = ensure_mapping(
        s3_endpoint,
        UPDATE_DOMAIN,
        HTTP_API_ID,
        STAGE,
        UPDATED_MAPPING_KEY,
        UPDATED_MAPPING_RENAMED,
    )
    base = f"/v2/domainnames/{UPDATE_DOMAIN}/apimappings"
    answer = ok(
        s3_endpoint,
        "PATCH",
        f"{base}/{mapping['apiMappingId']}",
        {"apiMappingKey": UPDATED_MAPPING_RENAMED},
    )
    assert answer["apiMappingId"] == mapping["apiMappingId"]
    assert answer["apiMappingKey"] == UPDATED_MAPPING_RENAMED
    read_back = ok(s3_endpoint, "GET", f"{base}/{mapping['apiMappingId']}")
    assert read_back["apiMappingKey"] == UPDATED_MAPPING_RENAMED
    assert read_back["apiId"] == HTTP_API_ID


def test_delete_api_mapping_removes_the_mapping_it_created(s3_endpoint):
    ensure_domain(s3_endpoint, DOMAIN)
    ensure_stage(s3_endpoint, HTTP_API_ID)
    doomed = ensure_mapping(
        s3_endpoint, DOMAIN, HTTP_API_ID, STAGE, DOOMED_MAPPING_KEY
    )
    base = f"/v2/domainnames/{DOMAIN}/apimappings"
    status, text = call(s3_endpoint, "DELETE", f"{base}/{doomed['apiMappingId']}")
    assert status == 204, f"DeleteApiMapping answered {status}: {text[:400]}"
    assert call(s3_endpoint, "GET", f"{base}/{doomed['apiMappingId']}")[0] == 404
    assert doomed["apiMappingId"] not in [
        row["apiMappingId"] for row in api_mappings(s3_endpoint, DOMAIN)
    ]


# ---------------------------------------------------------------------------
# Tags — TagResource, UntagResource, GetTags
# ---------------------------------------------------------------------------


def tags_path(resource_arn: str) -> str:
    return f"/v2/tags/{resource_arn}"


def test_tag_resource_is_read_back_by_get_tags(s3_endpoint):
    shared_http(s3_endpoint)
    path = tags_path(api_arn(HTTP_API_ID))
    status, text = call(
        s3_endpoint, "POST", path, {"tags": {TAG_CREATED: "yes"}}
    )
    assert status == 201, f"TagResource answered {status}: {text[:400]}"
    tags = ok(s3_endpoint, "GET", path)["tags"]
    assert tags[TAG_CREATED] == "yes"
    # CreateApi's own tags live on the same resource.
    assert tags["ms-custom-id"] == HTTP_API_ID

    status, text = call(
        s3_endpoint, "POST", tags_path(api_arn("opsv2missing")), {"tags": {"x": "y"}}
    )
    assert status == 404, text[:400]
    assert "resource not found" in text
    status, text = call(
        s3_endpoint,
        "POST",
        tags_path(f"arn:aws:apigateway:{REGION}::/apis"),
        {"tags": {"x": "y"}},
    )
    assert status == 400, text[:400]
    assert "Invalid API Gateway v2 ResourceArn" in text


def test_get_tags_returns_the_tags_the_resource_carries(s3_endpoint):
    shared_http(s3_endpoint)
    path = tags_path(api_arn(HTTP_API_ID))
    assert call(s3_endpoint, "POST", path, {"tags": {TAG_KEPT: "yes"}})[0] == 201
    tags = ok(s3_endpoint, "GET", path)["tags"]
    assert tags[TAG_KEPT] == "yes"

    # A stage is a taggable child resource of the API.
    ensure_stage(s3_endpoint, HTTP_API_ID)
    stage_path = tags_path(f"{api_arn(HTTP_API_ID)}/stages/{STAGE}")
    assert ok(s3_endpoint, "GET", stage_path)["tags"] == {"owner": "emuplane"}
    missing = tags_path(f"{api_arn(HTTP_API_ID)}/stages/opsv2missing")
    status, text = call(s3_endpoint, "GET", missing)
    assert status == 404, text[:400]


def test_untag_resource_removes_only_the_named_tag(s3_endpoint):
    shared_http(s3_endpoint)
    path = tags_path(api_arn(HTTP_API_ID))
    body = {"tags": {TAG_DOOMED: "yes", TAG_KEPT: "yes"}}
    assert call(s3_endpoint, "POST", path, body)[0] == 201
    status, text = call(s3_endpoint, "DELETE", f"{path}?tagKeys={TAG_DOOMED}")
    assert status == 204, f"UntagResource answered {status}: {text[:400]}"
    remaining = ok(s3_endpoint, "GET", path)["tags"]
    assert TAG_DOOMED not in remaining
    assert remaining[TAG_KEPT] == "yes"
    assert remaining["ms-custom-id"] == HTTP_API_ID


# ---------------------------------------------------------------------------
# WebSocket connections — PostToConnection, GetConnection, DeleteConnection
# ---------------------------------------------------------------------------
# They need an upgraded socket for a connection id to exist, so they live in
# `test_apigateway_ws_operations.py`, which runs against a lab and skips here.
