"""AppSync on the wire: all 55 advertised control-plane operations, GraphQL and Event.

The 42 GraphQL API operations speak REST/JSON under ``/v1/apis`` and are signed with the
``appsync`` credential scope; the 13 Event API management operations speak ``/v2/apis``
and are signed ``appsync-events``. The three Event API key operations are the exception
on the wire: AWS files them under ``/v1/apis/{apiId}/apikeys`` even for an Event API, and
the emulator's ``appsync`` router delegates that path to the Event module when the id is
not a GraphQL API. They are therefore signed ``appsync`` here, which is what the
delegation reads; a request signed ``appsync-events`` to that path is refused, and the
Event key test pins that.

A GraphQL API is found by name before it is created, so a second sweep of the same lab
reuses the API and the children under it instead of minting duplicates: API keys by
description, data sources and types by name, resolvers by type and field, functions by
name, the cache by existence (an API holds at most one). An update action mutates its
own resource (``ops-appsync-source-updated`` beside ``ops-appsync-source``) so no create
assertion reads a field another test writes. A delete action builds a resource of its
own and removes only that; nothing else is deleted.

``StartSchemaCreation`` stores the SDL it is handed, ``GetIntrospectionSchema`` serves it
back as SDL or as the graphql-core introspection document, and ``EvaluateCode`` runs
APPSYNC_JS on the emulator's Node worker, so no resolver or data source has to be
deployed behind it.
"""

from __future__ import annotations

import base64
import json

import pytest

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}
# A fixed 2050 expiry, so a sweep that re-runs finds the key it left behind.
EXPIRES = 2524608000

GRAPHQL_API = "ops-appsync-graphql"
GRAPHQL_API_DOOMED = "ops-appsync-graphql-doomed"

CACHE_API = "ops-appsync-cache"
CACHE_API_UPDATED = "ops-appsync-cache-updated"
CACHE_API_DOOMED = "ops-appsync-cache-doomed"
MISSING_ID = "opsappsyncmissing"

TAG_CREATED = "ops-created"
TAG_KEPT = "ops-kept"
TAG_DOOMED = "ops-doomed"

API_KEY_CREATED = "ops-appsync-key-created"
API_KEY_UPDATED = "ops-appsync-key-updated"
API_KEY_DOOMED = "ops-appsync-key-doomed"

DATA_SOURCE = "ops_appsync_source"
DATA_SOURCE_UPDATED = "ops_appsync_source_updated"
DATA_SOURCE_DOOMED = "ops_appsync_source_doomed"

QUERY = "Query"
RESOLVER_FIELD = "getWidget"
RESOLVER_FIELD_UPDATED = "getWidgetNote"
RESOLVER_FIELD_DOOMED = "getWidgetDoomed"
REQUEST_TEMPLATE = '{"version": "2018-05-29", "payload": {}}'
REQUEST_TEMPLATE_UPDATED = '{"version": "2018-05-29", "payload": {"source": "ops"}}'
RESPONSE_TEMPLATE = "$util.toJson($ctx.result)"

FUNCTION = "ops-appsync-function"
FUNCTION_UPDATED = "ops-appsync-function-updated"
FUNCTION_DOOMED = "ops-appsync-function-doomed"

TYPE = "OpsWidget"
TYPE_DEFINITION = "type OpsWidget {\n  id: ID!\n  label: String\n}\n"
TYPE_UPDATED = "OpsWidgetNote"
TYPE_UPDATED_DEFINITION = "type OpsWidgetNote {\n  id: ID!\n  label: String\n  note: String\n}\n"
TYPE_UPDATED_DEFINITION_NEW = (
    "type OpsWidgetNote {\n  id: ID!\n  label: String\n  note: String\n  rank: Int\n}\n"
)

SCHEMA = """type Query {
  getWidget(id: ID!): OpsWidget
}

type OpsWidget {
  id: ID!
  label: String
}
"""

EVENT_API = "ops-appsync-events"
EVENT_API_DOOMED = "ops-appsync-events-doomed"
NAMESPACE = "ops_namespace"
NAMESPACE_UPDATED = "ops_namespace_note"
NAMESPACE_DOOMED = "ops_namespace_doomed"
EVENT_KEY_CREATED = "ops-appsync-event-key-created"
EVENT_KEY_DOOMED = "ops-appsync-event-key-doomed"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def send(endpoint, service: str, method: str, path: str, body=""):
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return signed.request(
        endpoint, service, ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def call(endpoint, method: str, path: str, body=""):
    """One GraphQL-module call, signed with the ``appsync`` scope."""
    return send(endpoint, "appsync", method, path, body)


def event_call(endpoint, method: str, path: str, body=""):
    """One Event-module management call, signed with the ``appsync-events`` scope."""
    return send(endpoint, "appsync-events", method, path, body)


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = call(endpoint, method, path, body)
    assert status in (200, 201, 202, 204), (
        f"{method} {path} answered {status}: {text[:400]}"
    )
    return json.loads(text) if text.strip() else {}


def event_ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = event_call(endpoint, method, path, body)
    assert status in (200, 201, 202, 204), (
        f"{method} {path} answered {status}: {text[:400]}"
    )
    return json.loads(text) if text.strip() else {}


# ---------------------------------------------------------------------------
# GraphQL API fixtures
# ---------------------------------------------------------------------------


def graphql_apis(endpoint) -> list[dict]:
    return ok(endpoint, "GET", "/v1/apis")["graphqlApis"]


def graphql_api_named(endpoint, name: str) -> dict | None:
    return next(
        (row for row in graphql_apis(endpoint) if row.get("name") == name), None
    )


def ensure_graphql_api(endpoint, name: str = GRAPHQL_API) -> dict:
    """Find-or-create by name: the emulator does not refuse a duplicate name, so a
    second sweep must look before it creates."""
    found = graphql_api_named(endpoint, name)
    if found:
        return found
    return ok(
        endpoint,
        "POST",
        "/v1/apis",
        {"name": name, "authenticationType": "API_KEY"},
    )["graphqlApi"]


def shared_api(endpoint) -> dict:
    return ensure_graphql_api(endpoint, GRAPHQL_API)


def api_keys(endpoint, api_id: str) -> list[dict]:
    return ok(endpoint, "GET", f"/v1/apis/{api_id}/apikeys").get("apiKeys", [])


def ensure_api_key(endpoint, api_id: str, description: str) -> dict:
    found = next(
        (row for row in api_keys(endpoint, api_id) if row.get("description") == description),
        None,
    )
    if found:
        return found
    return ok(
        endpoint,
        "POST",
        f"/v1/apis/{api_id}/apikeys",
        {"description": description, "expires": EXPIRES},
    )["apiKey"]


def data_source(endpoint, api_id: str, name: str) -> dict | None:
    status, text = call(endpoint, "GET", f"/v1/apis/{api_id}/datasources/{name}")
    return json.loads(text)["dataSource"] if status == 200 else None


def ensure_data_source(endpoint, api_id: str, name: str) -> dict:
    found = data_source(endpoint, api_id, name)
    if found:
        return found
    return ok(
        endpoint,
        "POST",
        f"/v1/apis/{api_id}/datasources",
        {"name": name, "type": "NONE", "description": "ops fixture"},
    )["dataSource"]


def resolver(endpoint, api_id: str, type_name: str, field_name: str) -> dict | None:
    path = f"/v1/apis/{api_id}/types/{type_name}/resolvers/{field_name}"
    status, text = call(endpoint, "GET", path)
    return json.loads(text)["resolver"] if status == 200 else None


def ensure_resolver(endpoint, api_id: str, field_name: str) -> dict:
    found = resolver(endpoint, api_id, QUERY, field_name)
    if found:
        return found
    return ok(
        endpoint,
        "POST",
        f"/v1/apis/{api_id}/types/{QUERY}/resolvers",
        {
            "fieldName": field_name,
            "dataSourceName": DATA_SOURCE,
            "kind": "UNIT",
            "requestMappingTemplate": REQUEST_TEMPLATE,
            "responseMappingTemplate": RESPONSE_TEMPLATE,
        },
    )["resolver"]


def functions(endpoint, api_id: str) -> list[dict]:
    return ok(endpoint, "GET", f"/v1/apis/{api_id}/functions").get("functions", [])


def function_named(endpoint, api_id: str, name: str) -> dict | None:
    return next((row for row in functions(endpoint, api_id) if row.get("name") == name), None)


def ensure_function(endpoint, api_id: str, name: str) -> dict:
    found = function_named(endpoint, api_id, name)
    if found:
        return found
    return ok(
        endpoint,
        "POST",
        f"/v1/apis/{api_id}/functions",
        {
            "name": name,
            "dataSourceName": DATA_SOURCE,
            "description": "ops fixture",
            "functionVersion": "2018-05-29",
        },
    )["functionConfiguration"]


def type_named(endpoint, api_id: str, name: str) -> dict | None:
    status, text = call(endpoint, "GET", f"/v1/apis/{api_id}/types/{name}")
    return json.loads(text)["type"] if status == 200 else None


def ensure_type(endpoint, api_id: str, name: str, definition: str) -> dict:
    found = type_named(endpoint, api_id, name)
    if found:
        return found
    return ok(
        endpoint,
        "POST",
        f"/v1/apis/{api_id}/types",
        {"definition": definition, "format": "SDL", "description": "ops fixture"},
    )["type"]


def ensure_cache(endpoint, api_id: str) -> dict:
    """CreateApiCache refuses a second cache on the same API, so a re-run reads it."""
    status, text = call(endpoint, "GET", f"/v1/apis/{api_id}/ApiCaches")
    if status == 200:
        return json.loads(text)["apiCache"]
    return ok(
        endpoint,
        "POST",
        f"/v1/apis/{api_id}/ApiCaches",
        {"ttl": 600, "apiCachingBehavior": "FULL_REQUEST_CACHING", "type": "T2_SMALL"},
    )["apiCache"]


def tags_path(resource_arn: str) -> str:
    return f"/v1/tags/{resource_arn}"


# ---------------------------------------------------------------------------
# Event API fixtures
# ---------------------------------------------------------------------------


def event_apis(endpoint) -> list[dict]:
    """Every page of ListApis: a lab may hold more than one page of Event APIs."""
    found: list[dict] = []
    path = "/v2/apis?maxResults=100"
    while path:
        answer = event_ok(endpoint, "GET", path)
        found.extend(answer.get("apis", []))
        token = answer.get("nextToken")
        path = f"/v2/apis?maxResults=100&nextToken={token}" if token else ""
    return found


def event_api_named(endpoint, name: str) -> dict | None:
    return next((row for row in event_apis(endpoint) if row.get("name") == name), None)


def ensure_event_api(endpoint, name: str = EVENT_API) -> dict:
    found = event_api_named(endpoint, name)
    if found:
        return found
    return event_ok(
        endpoint, "POST", "/v2/apis", {"name": name, "tags": {"owner": "emuplane"}}
    )["api"]


def channel_namespaces(endpoint, api_id: str) -> list[dict]:
    found: list[dict] = []
    path = f"/v2/apis/{api_id}/channelNamespaces?maxResults=100"
    while path:
        answer = event_ok(endpoint, "GET", path)
        found.extend(answer.get("channelNamespaces", []))
        token = answer.get("nextToken")
        base = f"/v2/apis/{api_id}/channelNamespaces?maxResults=100"
        path = f"{base}&nextToken={token}" if token else ""
    return found


def ensure_namespace(endpoint, api_id: str, name: str) -> dict:
    found = next(
        (row for row in channel_namespaces(endpoint, api_id) if row.get("name") == name),
        None,
    )
    if found:
        return found
    return event_ok(
        endpoint, "POST", f"/v2/apis/{api_id}/channelNamespaces", {"name": name}
    )["channelNamespace"]


def event_keys(endpoint, api_id: str) -> list[dict]:
    """Event API keys live on the ``/v1`` path and, past the delegation, on this module."""
    return ok(endpoint, "GET", f"/v1/apis/{api_id}/apikeys").get("apiKeys", [])


def ensure_event_key(endpoint, api_id: str, description: str) -> dict:
    found = next(
        (row for row in event_keys(endpoint, api_id) if row.get("description") == description),
        None,
    )
    if found:
        return found
    return ok(
        endpoint,
        "POST",
        f"/v1/apis/{api_id}/apikeys",
        {"description": description, "expires": EXPIRES},
    )["apiKey"]


# ---------------------------------------------------------------------------
# GraphQL APIs — CreateGraphQLApi, GetGraphQLApi, ListGraphQLApis,
# UpdateGraphQLApi, DeleteGraphQLApi
# ---------------------------------------------------------------------------


def test_create_graphql_api_is_read_back_by_get_graphql_api(endpoint):
    api = ensure_graphql_api(endpoint)
    assert api["name"] == GRAPHQL_API
    assert api["authenticationType"] == "API_KEY"
    assert api["apiId"]
    assert api["arn"] == f"arn:aws:appsync:{REGION}:{ACCOUNT}:apis/{api['apiId']}"
    assert api["uris"]["GRAPHQL"].endswith("/graphql")

    read_back = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}")["graphqlApi"]
    assert read_back["apiId"] == api["apiId"]
    assert read_back["name"] == GRAPHQL_API

    status, text = call(endpoint, "GET", f"/v1/apis/{MISSING_ID}")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_list_graphql_apis_includes_the_shared_api(endpoint):
    shared = shared_api(endpoint)
    listed = graphql_apis(endpoint)
    row = next(row for row in listed if row["apiId"] == shared["apiId"])
    assert row["name"] == GRAPHQL_API
    assert row["arn"] == shared["arn"]
    assert row["uris"]["REALTIME"].startswith("wss://")


def test_update_graphql_api_patches_the_fields_it_is_given(endpoint):
    api = shared_api(endpoint)
    body = {
        "name": GRAPHQL_API,
        "xrayEnabled": True,
        "introspectionConfig": "DISABLED",
        "queryDepthLimit": 12,
    }
    answer = ok(endpoint, "POST", f"/v1/apis/{api['apiId']}", body)["graphqlApi"]
    assert answer["xrayEnabled"] is True
    assert answer["introspectionConfig"] == "DISABLED"
    assert answer["queryDepthLimit"] == 12

    read_back = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}")["graphqlApi"]
    assert read_back["introspectionConfig"] == "DISABLED"
    assert read_back["queryDepthLimit"] == 12

    status, text = call(endpoint, "POST", f"/v1/apis/{MISSING_ID}", body)
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_delete_graphql_api_removes_the_api_it_created(endpoint):
    # A sweep that stopped between its create and its delete left the doomed API behind.
    for row in graphql_apis(endpoint):
        if row.get("name") == GRAPHQL_API_DOOMED:
            call(endpoint, "DELETE", f"/v1/apis/{row['apiId']}")

    created = ok(
        endpoint,
        "POST",
        "/v1/apis",
        {"name": GRAPHQL_API_DOOMED, "authenticationType": "API_KEY"},
    )["graphqlApi"]
    status, text = call(endpoint, "DELETE", f"/v1/apis/{created['apiId']}")
    assert status == 200, f"DeleteGraphQLApi answered {status}: {text[:400]}"
    assert call(endpoint, "GET", f"/v1/apis/{created['apiId']}")[0] == 404
    assert GRAPHQL_API_DOOMED not in [row["name"] for row in graphql_apis(endpoint)]
    assert call(endpoint, "DELETE", f"/v1/apis/{created['apiId']}")[0] == 404


# ---------------------------------------------------------------------------
# API keys — CreateApiKey, UpdateApiKey, DeleteApiKey, ListApiKeys
# ---------------------------------------------------------------------------


def test_create_api_key_is_listed_by_list_api_keys(endpoint):
    api = shared_api(endpoint)
    key = ensure_api_key(endpoint, api["apiId"], API_KEY_CREATED)
    assert key["id"].startswith("da2-")
    assert key["description"] == API_KEY_CREATED
    assert key["expires"] == EXPIRES
    assert key["id"] in {row["id"] for row in api_keys(endpoint, api["apiId"])}

    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{MISSING_ID}/apikeys",
        {"description": API_KEY_DOOMED},
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_update_api_key_sets_the_expiry(endpoint):
    api = shared_api(endpoint)
    key = ensure_api_key(endpoint, api["apiId"], API_KEY_UPDATED)
    updated = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/apikeys/{key['id']}",
        {"expires": EXPIRES + 86400},
    )["apiKey"]
    assert updated["expires"] == EXPIRES + 86400
    assert updated["description"] == API_KEY_UPDATED

    listed = {row["id"]: row for row in api_keys(endpoint, api["apiId"])}
    assert listed[key["id"]]["expires"] == EXPIRES + 86400

    status, text = call(
        endpoint, "POST", f"/v1/apis/{api['apiId']}/apikeys/da2-missing", {"expires": EXPIRES}
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_delete_api_key_removes_only_the_key_it_created(endpoint):
    api = shared_api(endpoint)
    key = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/apikeys",
        {"description": API_KEY_DOOMED, "expires": EXPIRES},
    )["apiKey"]
    before = {row["id"] for row in api_keys(endpoint, api["apiId"])}
    assert key["id"] in before

    status, text = call(
        endpoint, "DELETE", f"/v1/apis/{api['apiId']}/apikeys/{key['id']}"
    )
    assert status == 200, f"DeleteApiKey answered {status}: {text[:400]}"
    after = {row["id"] for row in api_keys(endpoint, api["apiId"])}
    assert key["id"] not in after
    assert before - {key["id"]} <= after
    assert call(endpoint, "DELETE", f"/v1/apis/{api['apiId']}/apikeys/{key['id']}")[0] == 404


# ---------------------------------------------------------------------------
# Data sources — CreateDataSource, GetDataSource, ListDataSources,
# UpdateDataSource, DeleteDataSource
# ---------------------------------------------------------------------------


def test_create_data_source_is_read_back_by_get_data_source(endpoint):
    api = shared_api(endpoint)
    created = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/datasources",
        {"name": DATA_SOURCE, "type": "NONE", "description": "ops fixture"},
    )["dataSource"]
    assert created["name"] == DATA_SOURCE
    assert created["type"] == "NONE"
    assert created["description"] == "ops fixture"
    assert created["dataSourceArn"].endswith(f"/datasources/{DATA_SOURCE}")

    read_back = data_source(endpoint, api["apiId"], DATA_SOURCE)
    assert read_back["dataSourceArn"] == created["dataSourceArn"]

    status, text = call(endpoint, "GET", f"/v1/apis/{api['apiId']}/datasources/ops_missing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_list_data_sources_includes_the_shared_source(endpoint):
    api = shared_api(endpoint)
    ensure_data_source(endpoint, api["apiId"], DATA_SOURCE)
    listed = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}/datasources")["dataSources"]
    row = next(row for row in listed if row["name"] == DATA_SOURCE)
    assert row["type"] == "NONE"
    assert row["dataSourceArn"].endswith(f"/datasources/{DATA_SOURCE}")


def test_update_data_source_changes_its_description(endpoint):
    api = shared_api(endpoint)
    ensure_data_source(endpoint, api["apiId"], DATA_SOURCE_UPDATED)
    updated = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/datasources/{DATA_SOURCE_UPDATED}",
        {"type": "NONE", "description": "ops updated"},
    )["dataSource"]
    assert updated["name"] == DATA_SOURCE_UPDATED
    assert updated["description"] == "ops updated"

    read_back = data_source(endpoint, api["apiId"], DATA_SOURCE_UPDATED)
    assert read_back["description"] == "ops updated"

    status, text = call(
        endpoint, "POST", f"/v1/apis/{api['apiId']}/datasources/ops_missing", {"type": "NONE"}
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_delete_data_source_removes_only_the_source_it_created(endpoint):
    api = shared_api(endpoint)
    ensure_data_source(endpoint, api["apiId"], DATA_SOURCE)
    ensure_data_source(endpoint, api["apiId"], DATA_SOURCE_DOOMED)

    status, text = call(
        endpoint, "DELETE", f"/v1/apis/{api['apiId']}/datasources/{DATA_SOURCE_DOOMED}"
    )
    assert status == 200, f"DeleteDataSource answered {status}: {text[:400]}"
    assert call(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/datasources/{DATA_SOURCE_DOOMED}"
    )[0] == 404

    names = {row["name"] for row in ok(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/datasources"
    )["dataSources"]}
    assert DATA_SOURCE_DOOMED not in names
    assert DATA_SOURCE in names
    assert call(
        endpoint, "DELETE", f"/v1/apis/{api['apiId']}/datasources/{DATA_SOURCE_DOOMED}"
    )[0] == 404


# ---------------------------------------------------------------------------
# Resolvers — CreateResolver, GetResolver, ListResolvers, UpdateResolver,
# DeleteResolver
# ---------------------------------------------------------------------------


def test_create_resolver_is_read_back_by_get_resolver(endpoint):
    api = shared_api(endpoint)
    ensure_data_source(endpoint, api["apiId"], DATA_SOURCE)
    created = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers",
        {
            "fieldName": RESOLVER_FIELD,
            "dataSourceName": DATA_SOURCE,
            "kind": "UNIT",
            "requestMappingTemplate": REQUEST_TEMPLATE,
            "responseMappingTemplate": RESPONSE_TEMPLATE,
        },
    )["resolver"]
    assert created["typeName"] == QUERY
    assert created["fieldName"] == RESOLVER_FIELD
    assert created["kind"] == "UNIT"
    assert created["dataSourceName"] == DATA_SOURCE
    assert created["resolverArn"].endswith(f"/types/{QUERY}/resolvers/{RESOLVER_FIELD}")

    read_back = resolver(endpoint, api["apiId"], QUERY, RESOLVER_FIELD)
    assert read_back["resolverArn"] == created["resolverArn"]
    assert read_back["requestMappingTemplate"] == REQUEST_TEMPLATE

    status, text = call(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers/ops_missing"
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_list_resolvers_lists_the_shared_resolver(endpoint):
    api = shared_api(endpoint)
    ensure_resolver(endpoint, api["apiId"], RESOLVER_FIELD)
    listed = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers")[
        "resolvers"
    ]
    assert RESOLVER_FIELD in {row["fieldName"] for row in listed}
    # A type with no resolvers is an empty list, not a 404.
    assert ok(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/types/OpsUnknown/resolvers"
    )["resolvers"] == []


def test_update_resolver_changes_its_request_template(endpoint):
    api = shared_api(endpoint)
    ensure_resolver(endpoint, api["apiId"], RESOLVER_FIELD_UPDATED)
    updated = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers/{RESOLVER_FIELD_UPDATED}",
        {
            "dataSourceName": DATA_SOURCE,
            "requestMappingTemplate": REQUEST_TEMPLATE_UPDATED,
        },
    )["resolver"]
    assert updated["fieldName"] == RESOLVER_FIELD_UPDATED
    assert updated["requestMappingTemplate"] == REQUEST_TEMPLATE_UPDATED

    read_back = resolver(endpoint, api["apiId"], QUERY, RESOLVER_FIELD_UPDATED)
    assert read_back["requestMappingTemplate"] == REQUEST_TEMPLATE_UPDATED

    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers/ops_missing",
        {"dataSourceName": DATA_SOURCE},
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_delete_resolver_removes_only_the_resolver_it_created(endpoint):
    api = shared_api(endpoint)
    ensure_resolver(endpoint, api["apiId"], RESOLVER_FIELD)
    ensure_resolver(endpoint, api["apiId"], RESOLVER_FIELD_DOOMED)

    status, text = call(
        endpoint,
        "DELETE",
        f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers/{RESOLVER_FIELD_DOOMED}",
    )
    assert status == 200, f"DeleteResolver answered {status}: {text[:400]}"
    assert resolver(endpoint, api["apiId"], QUERY, RESOLVER_FIELD_DOOMED) is None

    fields = {row["fieldName"] for row in ok(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers"
    )["resolvers"]}
    assert RESOLVER_FIELD_DOOMED not in fields
    assert RESOLVER_FIELD in fields
    assert call(
        endpoint,
        "DELETE",
        f"/v1/apis/{api['apiId']}/types/{QUERY}/resolvers/{RESOLVER_FIELD_DOOMED}",
    )[0] == 404


# ---------------------------------------------------------------------------
# Functions — CreateFunction, GetFunction, ListFunctions, UpdateFunction,
# DeleteFunction
# ---------------------------------------------------------------------------


def test_create_function_is_read_back_by_get_function(endpoint):
    api = shared_api(endpoint)
    ensure_data_source(endpoint, api["apiId"], DATA_SOURCE)
    function = ensure_function(endpoint, api["apiId"], FUNCTION)
    assert function["name"] == FUNCTION
    assert function["dataSourceName"] == DATA_SOURCE
    assert function["functionVersion"] == "2018-05-29"
    assert function["functionArn"].endswith(f"/functions/{function['functionId']}")

    read_back = ok(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/functions/{function['functionId']}"
    )["functionConfiguration"]
    assert read_back["functionId"] == function["functionId"]
    assert read_back["name"] == FUNCTION

    status, text = call(endpoint, "GET", f"/v1/apis/{api['apiId']}/functions/opsmissing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_list_functions_includes_the_shared_function(endpoint):
    api = shared_api(endpoint)
    ensure_function(endpoint, api["apiId"], FUNCTION)
    listed = functions(endpoint, api["apiId"])
    assert FUNCTION in {row["name"] for row in listed}


def test_update_function_changes_its_description(endpoint):
    api = shared_api(endpoint)
    function = ensure_function(endpoint, api["apiId"], FUNCTION_UPDATED)
    updated = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/functions/{function['functionId']}",
        {
            "name": FUNCTION_UPDATED,
            "dataSourceName": DATA_SOURCE,
            "description": "ops updated",
        },
    )["functionConfiguration"]
    assert updated["functionId"] == function["functionId"]
    assert updated["name"] == FUNCTION_UPDATED
    assert updated["description"] == "ops updated"

    read_back = ok(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/functions/{function['functionId']}"
    )["functionConfiguration"]
    assert read_back["description"] == "ops updated"

    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/functions/opsmissing",
        {"name": FUNCTION_UPDATED, "dataSourceName": DATA_SOURCE},
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_delete_function_removes_only_the_function_it_created(endpoint):
    api = shared_api(endpoint)
    ensure_function(endpoint, api["apiId"], FUNCTION)
    doomed = ensure_function(endpoint, api["apiId"], FUNCTION_DOOMED)

    status, text = call(
        endpoint, "DELETE", f"/v1/apis/{api['apiId']}/functions/{doomed['functionId']}"
    )
    assert status == 200, f"DeleteFunction answered {status}: {text[:400]}"
    assert call(
        endpoint, "GET", f"/v1/apis/{api['apiId']}/functions/{doomed['functionId']}"
    )[0] == 404

    names = {row["name"] for row in functions(endpoint, api["apiId"])}
    assert FUNCTION_DOOMED not in names
    assert FUNCTION in names
    assert call(
        endpoint, "DELETE", f"/v1/apis/{api['apiId']}/functions/{doomed['functionId']}"
    )[0] == 404


# ---------------------------------------------------------------------------
# Types — CreateType, GetType, ListTypes, UpdateType
# ---------------------------------------------------------------------------


def test_create_type_is_read_back_by_get_type(endpoint):
    api = shared_api(endpoint)
    created = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/types",
        {"definition": TYPE_DEFINITION, "format": "SDL", "description": "ops fixture"},
    )["type"]
    assert created["name"] == TYPE
    assert created["format"] == "SDL"
    assert created["description"] == "ops fixture"
    assert "label: String" in created["definition"]
    assert created["arn"].endswith(f"/types/{TYPE}")

    read_back = type_named(endpoint, api["apiId"], TYPE)
    assert read_back["definition"] == created["definition"]

    status, text = call(endpoint, "GET", f"/v1/apis/{api['apiId']}/types/OpsMissing")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_list_types_includes_the_created_type(endpoint):
    api = shared_api(endpoint)
    ensure_type(endpoint, api["apiId"], TYPE, TYPE_DEFINITION)
    listed = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}/types")["types"]
    assert TYPE in {row["name"] for row in listed}


def test_update_type_rewrites_the_definition(endpoint):
    api = shared_api(endpoint)
    ensure_type(endpoint, api["apiId"], TYPE_UPDATED, TYPE_UPDATED_DEFINITION)
    updated = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/types/{TYPE_UPDATED}",
        {"definition": TYPE_UPDATED_DEFINITION_NEW, "format": "SDL"},
    )["type"]
    assert updated["name"] == TYPE_UPDATED
    assert "rank: Int" in updated["definition"]

    read_back = type_named(endpoint, api["apiId"], TYPE_UPDATED)
    assert read_back["definition"] == updated["definition"]

    # format is required on an update, as on a create.
    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/types/{TYPE_UPDATED}",
        {"definition": TYPE_UPDATED_DEFINITION_NEW},
    )
    assert status == 400, text[:400]
    assert "format is required" in text

    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/types/OpsMissing",
        {"definition": TYPE_DEFINITION, "format": "SDL"},
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text


# ---------------------------------------------------------------------------
# Schema — StartSchemaCreation, GetSchemaCreationStatus, GetIntrospectionSchema
# ---------------------------------------------------------------------------


def test_start_schema_creation_is_reported_by_get_schema_creation_status(endpoint):
    api = shared_api(endpoint)
    definition = base64.b64encode(SCHEMA.encode()).decode()
    answer = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/schemacreation",
        {"definition": definition},
    )
    assert answer["status"] == "PROCESSING"

    status_answer = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}/schemacreation")
    assert status_answer["status"] == "SUCCESS"
    assert status_answer["details"]

    status, text = call(endpoint, "POST", f"/v1/apis/{api['apiId']}/schemacreation", {})
    assert status == 400, text[:400]
    assert "definition is required" in text


def test_get_introspection_schema_serves_sdl_and_json(endpoint):
    api = shared_api(endpoint)
    ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/schemacreation",
        {"definition": base64.b64encode(SCHEMA.encode()).decode()},
    )

    status, text = call(endpoint, "GET", f"/v1/apis/{api['apiId']}/schema?format=SDL")
    assert status == 200, text[:400]
    assert text.strip() == SCHEMA.strip()

    status, text = call(endpoint, "GET", f"/v1/apis/{api['apiId']}/schema?format=JSON")
    assert status == 200, text[:400]
    document = json.loads(text)["__schema"]
    assert document["queryType"]["name"] == "Query"
    assert TYPE in {row["name"] for row in document["types"]}

    status, text = call(endpoint, "GET", f"/v1/apis/{api['apiId']}/schema")
    assert status == 400, text[:400]
    assert "format is required" in text


# ---------------------------------------------------------------------------
# Environment variables — PutGraphqlApiEnvironmentVariables,
# GetGraphqlApiEnvironmentVariables
# ---------------------------------------------------------------------------


def test_put_graphql_api_environment_variables_is_read_back_by_get_graphql_api_environment_variables(endpoint):
    api = shared_api(endpoint)
    path = f"/v1/apis/{api['apiId']}/environmentVariables"
    answer = ok(
        endpoint,
        "PUT",
        path,
        {"environmentVariables": {"OPS_TOKEN": "one", "OPS_MODE": "lab"}},
    )
    assert answer["environmentVariables"] == {"OPS_TOKEN": "one", "OPS_MODE": "lab"}

    read_back = ok(endpoint, "GET", path)["environmentVariables"]
    assert read_back == {"OPS_TOKEN": "one", "OPS_MODE": "lab"}

    # A put replaces the whole map, as AWS does.
    ok(endpoint, "PUT", path, {"environmentVariables": {"OPS_TOKEN": "two"}})
    assert ok(endpoint, "GET", path)["environmentVariables"] == {"OPS_TOKEN": "two"}

    status, text = call(endpoint, "PUT", path, {})
    assert status == 400, text[:400]
    assert "environmentVariables is required" in text


# ---------------------------------------------------------------------------
# API cache — CreateApiCache, GetApiCache, UpdateApiCache, DeleteApiCache,
# FlushApiCache
# ---------------------------------------------------------------------------


def test_create_api_cache_is_read_back_by_get_api_cache(endpoint):
    api = ensure_graphql_api(endpoint, CACHE_API)
    cache = ensure_cache(endpoint, api["apiId"])
    assert cache["status"] == "AVAILABLE"
    assert cache["ttl"] == 600
    assert cache["apiCachingBehavior"] == "FULL_REQUEST_CACHING"
    assert cache["type"] == "T2_SMALL"

    read_back = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}/ApiCaches")["apiCache"]
    assert read_back["status"] == "AVAILABLE"
    assert read_back["type"] == "T2_SMALL"

    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/ApiCaches",
        {"ttl": 600, "apiCachingBehavior": "FULL_REQUEST_CACHING", "type": "T2_SMALL"},
    )
    assert status == 400, text[:400]
    assert "Cache already exists" in text

    status, text = call(endpoint, "GET", f"/v1/apis/{shared_api(endpoint)['apiId']}/ApiCaches")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_update_api_cache_changes_the_ttl(endpoint):
    api = ensure_graphql_api(endpoint, CACHE_API_UPDATED)
    ensure_cache(endpoint, api["apiId"])
    updated = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/ApiCaches/update",
        {"ttl": 1200, "apiCachingBehavior": "PER_RESOLVER_CACHING", "type": "T2_SMALL"},
    )["apiCache"]
    assert updated["ttl"] == 1200
    assert updated["apiCachingBehavior"] == "PER_RESOLVER_CACHING"

    read_back = ok(endpoint, "GET", f"/v1/apis/{api['apiId']}/ApiCaches")["apiCache"]
    assert read_back["ttl"] == 1200

    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/ApiCaches/update",
        {"apiCachingBehavior": "PER_RESOLVER_CACHING", "type": "T2_SMALL"},
    )
    assert status == 400, text[:400]
    assert "ttl is required" in text

    status, text = call(
        endpoint,
        "POST",
        f"/v1/apis/{shared_api(endpoint)['apiId']}/ApiCaches/update",
        {"ttl": 1200, "apiCachingBehavior": "PER_RESOLVER_CACHING", "type": "T2_SMALL"},
    )
    assert status == 404, text[:400]


def test_flush_api_cache_answers_ok(endpoint):
    api = ensure_graphql_api(endpoint, CACHE_API)
    ensure_cache(endpoint, api["apiId"])
    status, text = call(endpoint, "DELETE", f"/v1/apis/{api['apiId']}/FlushCache")
    assert status == 200, f"FlushApiCache answered {status}: {text[:400]}"
    # The cache's configuration survives a flush.
    assert ok(endpoint, "GET", f"/v1/apis/{api['apiId']}/ApiCaches")["apiCache"]["status"] == (
        "AVAILABLE"
    )
    assert call(
        endpoint, "DELETE", f"/v1/apis/{shared_api(endpoint)['apiId']}/FlushCache"
    )[0] == 404


def test_delete_api_cache_removes_only_the_cache_it_created(endpoint):
    api = ensure_graphql_api(endpoint, CACHE_API_DOOMED)
    ensure_cache(endpoint, api["apiId"])
    status, text = call(endpoint, "DELETE", f"/v1/apis/{api['apiId']}/ApiCaches")
    assert status == 200, f"DeleteApiCache answered {status}: {text[:400]}"
    assert call(endpoint, "GET", f"/v1/apis/{api['apiId']}/ApiCaches")[0] == 404
    assert call(endpoint, "DELETE", f"/v1/apis/{api['apiId']}/ApiCaches")[0] == 404


# ---------------------------------------------------------------------------
# EvaluateCode
# ---------------------------------------------------------------------------


def test_evaluate_code_runs_appsync_js(endpoint):
    body = {
        "runtime": {"name": "APPSYNC_JS", "runtimeVersion": "1.0.0"},
        "code": "export function request(ctx) { return { payload: ctx.arguments.id }; }",
        "context": json.dumps({"arguments": {"id": "ops-42"}}),
        "function": "request",
    }
    status, text = call(endpoint, "POST", "/v1/dataplane-evaluatecode", body)
    if status == 500 and "Node" in text:
        pytest.skip(f"EvaluateCode needs Node on the emulator host: {text[:200]}")
    assert status == 200, text[:400]
    answer = json.loads(text)
    assert json.loads(answer["evaluationResult"]) == {"payload": "ops-42"}
    assert answer["logs"] == []

    status, text = call(
        endpoint,
        "POST",
        "/v1/dataplane-evaluatecode",
        {"runtime": {"name": "VTL"}, "code": "x"},
    )
    assert status == 400, text[:400]
    assert "only APPSYNC_JS is evaluated" in text


# ---------------------------------------------------------------------------
# Tags — TagResource, UntagResource, ListTagsForResource
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags_for_resource(endpoint):
    api = shared_api(endpoint)
    path = tags_path(api["arn"])
    status, text = call(endpoint, "POST", path, {"tags": {TAG_CREATED: "yes"}})
    assert status == 200, f"TagResource answered {status}: {text[:400]}"
    assert ok(endpoint, "GET", path)["tags"][TAG_CREATED] == "yes"

    missing = tags_path(f"arn:aws:appsync:{REGION}:{ACCOUNT}:apis/{MISSING_ID}")
    status, text = call(endpoint, "POST", missing, {"tags": {"x": "y"}})
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_list_tags_for_resource_returns_the_tags_the_api_carries(endpoint):
    api = shared_api(endpoint)
    path = tags_path(api["arn"])
    body = {"tags": {TAG_CREATED: "yes", TAG_KEPT: "yes"}}
    assert call(endpoint, "POST", path, body)[0] == 200
    tags = ok(endpoint, "GET", path)["tags"]
    assert tags[TAG_CREATED] == "yes"
    assert tags[TAG_KEPT] == "yes"


def test_untag_resource_removes_only_the_named_tag(endpoint):
    api = shared_api(endpoint)
    path = tags_path(api["arn"])
    assert call(
        endpoint, "POST", path, {"tags": {TAG_DOOMED: "yes", TAG_KEPT: "yes"}}
    )[0] == 200
    status, text = call(endpoint, "DELETE", f"{path}?tagKeys={TAG_DOOMED}")
    assert status == 200, f"UntagResource answered {status}: {text[:400]}"
    remaining = ok(endpoint, "GET", path)["tags"]
    assert TAG_DOOMED not in remaining
    assert remaining[TAG_KEPT] == "yes"


# ---------------------------------------------------------------------------
# Event APIs — CreateApi, GetApi, ListApis, UpdateApi, DeleteApi
# ---------------------------------------------------------------------------


def test_create_api_is_listed_by_list_apis(endpoint):
    api = ensure_event_api(endpoint)
    assert api["name"] == EVENT_API
    assert api["apiId"]
    assert api["apiArn"] == f"arn:aws:appsync:{REGION}:{ACCOUNT}:apis/{api['apiId']}"
    assert api["apiId"] in api["dns"]["HTTP"]
    assert api["eventConfig"]["authProviders"] == [{"authType": "API_KEY"}]
    assert api["apiId"] in {row["apiId"] for row in event_apis(endpoint)}


def test_get_api_returns_the_shared_event_api(endpoint):
    api = ensure_event_api(endpoint)
    answer = event_ok(endpoint, "GET", f"/v2/apis/{api['apiId']}")["api"]
    assert answer["apiId"] == api["apiId"]
    assert answer["name"] == EVENT_API
    assert answer["apiArn"] == api["apiArn"]

    status, text = event_call(endpoint, "GET", f"/v2/apis/{MISSING_ID}")
    assert status == 404, text[:400]
    assert "NotFoundException" in text


def test_update_api_patches_the_fields_it_is_given(endpoint):
    api = ensure_event_api(endpoint)
    updated = event_ok(
        endpoint,
        "POST",
        f"/v2/apis/{api['apiId']}",
        {"name": EVENT_API, "ownerContact": "ops@example.com", "xrayEnabled": True},
    )["api"]
    assert updated["ownerContact"] == "ops@example.com"
    assert updated["xrayEnabled"] is True

    read_back = event_ok(endpoint, "GET", f"/v2/apis/{api['apiId']}")["api"]
    assert read_back["ownerContact"] == "ops@example.com"
    assert read_back["xrayEnabled"] is True

    status, text = event_call(endpoint, "POST", f"/v2/apis/{MISSING_ID}", {"name": "ops"})
    assert status == 404, text[:400]


def test_delete_api_removes_the_api_it_created(endpoint):
    for row in event_apis(endpoint):
        if row.get("name") == EVENT_API_DOOMED:
            event_call(endpoint, "DELETE", f"/v2/apis/{row['apiId']}")

    created = event_ok(endpoint, "POST", "/v2/apis", {"name": EVENT_API_DOOMED})["api"]
    status, text = event_call(endpoint, "DELETE", f"/v2/apis/{created['apiId']}")
    assert status == 200, f"DeleteApi answered {status}: {text[:400]}"
    assert event_call(endpoint, "GET", f"/v2/apis/{created['apiId']}")[0] == 404
    assert EVENT_API_DOOMED not in [row["name"] for row in event_apis(endpoint)]
    assert event_call(endpoint, "DELETE", f"/v2/apis/{created['apiId']}")[0] == 404


# ---------------------------------------------------------------------------
# Channel namespaces — CreateChannelNamespace, GetChannelNamespace,
# ListChannelNamespaces, UpdateChannelNamespace, DeleteChannelNamespace
# ---------------------------------------------------------------------------


def test_create_channel_namespace_is_read_back_by_get_channel_namespace(endpoint):
    api = ensure_event_api(endpoint)
    namespace = ensure_namespace(endpoint, api["apiId"], NAMESPACE)
    assert namespace["name"] == NAMESPACE
    assert namespace["apiId"] == api["apiId"]
    assert namespace["channelNamespaceArn"].endswith(f"/channelNamespace/{NAMESPACE}")
    assert namespace["publishAuthModes"] == [{"authType": "API_KEY"}]

    read_back = event_ok(
        endpoint, "GET", f"/v2/apis/{api['apiId']}/channelNamespaces/{NAMESPACE}"
    )["channelNamespace"]
    assert read_back["channelNamespaceArn"] == namespace["channelNamespaceArn"]

    status, text = event_call(
        endpoint, "GET", f"/v2/apis/{api['apiId']}/channelNamespaces/ops_missing"
    )
    assert status == 404, text[:400]
    assert "NotFoundException" in text

    status, text = event_call(
        endpoint, "POST", f"/v2/apis/{api['apiId']}/channelNamespaces", {"name": NAMESPACE}
    )
    assert status == 409, text[:400]
    assert "already exists" in text


def test_list_channel_namespaces_includes_the_shared_namespace(endpoint):
    api = ensure_event_api(endpoint)
    ensure_namespace(endpoint, api["apiId"], NAMESPACE)
    names = {row["name"] for row in channel_namespaces(endpoint, api["apiId"])}
    assert NAMESPACE in names


def test_update_channel_namespace_changes_its_auth_modes(endpoint):
    api = ensure_event_api(endpoint)
    ensure_namespace(endpoint, api["apiId"], NAMESPACE_UPDATED)
    modes = [{"authType": "API_KEY"}, {"authType": "AWS_IAM"}]
    updated = event_ok(
        endpoint,
        "POST",
        f"/v2/apis/{api['apiId']}/channelNamespaces/{NAMESPACE_UPDATED}",
        {"publishAuthModes": modes},
    )["channelNamespace"]
    assert updated["publishAuthModes"] == modes
    assert updated["name"] == NAMESPACE_UPDATED

    read_back = event_ok(
        endpoint, "GET", f"/v2/apis/{api['apiId']}/channelNamespaces/{NAMESPACE_UPDATED}"
    )["channelNamespace"]
    assert read_back["publishAuthModes"] == modes

    status, text = event_call(
        endpoint,
        "POST",
        f"/v2/apis/{api['apiId']}/channelNamespaces/ops_missing",
        {"publishAuthModes": modes},
    )
    assert status == 404, text[:400]


def test_delete_channel_namespace_removes_only_the_namespace_it_created(endpoint):
    api = ensure_event_api(endpoint)
    ensure_namespace(endpoint, api["apiId"], NAMESPACE)
    ensure_namespace(endpoint, api["apiId"], NAMESPACE_DOOMED)

    status, text = event_call(
        endpoint, "DELETE", f"/v2/apis/{api['apiId']}/channelNamespaces/{NAMESPACE_DOOMED}"
    )
    assert status == 200, f"DeleteChannelNamespace answered {status}: {text[:400]}"
    assert event_call(
        endpoint, "GET", f"/v2/apis/{api['apiId']}/channelNamespaces/{NAMESPACE_DOOMED}"
    )[0] == 404

    names = {row["name"] for row in channel_namespaces(endpoint, api["apiId"])}
    assert NAMESPACE_DOOMED not in names
    assert NAMESPACE in names
    assert event_call(
        endpoint, "DELETE", f"/v2/apis/{api['apiId']}/channelNamespaces/{NAMESPACE_DOOMED}"
    )[0] == 404


# ---------------------------------------------------------------------------
# Event API keys — CreateApiKey, ListApiKeys, DeleteApiKey
# ---------------------------------------------------------------------------


def test_create_api_key_is_listed_by_list_api_keys_for_the_event_api(endpoint):
    api = ensure_event_api(endpoint)
    key = ensure_event_key(endpoint, api["apiId"], EVENT_KEY_CREATED)
    assert key["id"].startswith("da2-")
    assert key["description"] == EVENT_KEY_CREATED
    assert key["expires"] == EXPIRES
    assert key["id"] in {row["id"] for row in event_keys(endpoint, api["apiId"])}

    # The key path belongs to the `appsync` scope: the Event module itself does not
    # serve /v1/apis, which is why these three operations are signed `appsync`.
    status, text = event_call(endpoint, "GET", f"/v1/apis/{api['apiId']}/apikeys")
    assert status == 400, text[:400]
    assert "Unsupported AppSync Events path" in text


def test_delete_api_key_removes_only_the_event_key_it_created(endpoint):
    api = ensure_event_api(endpoint)
    key = ok(
        endpoint,
        "POST",
        f"/v1/apis/{api['apiId']}/apikeys",
        {"description": EVENT_KEY_DOOMED, "expires": EXPIRES},
    )["apiKey"]
    before = {row["id"] for row in event_keys(endpoint, api["apiId"])}
    assert key["id"] in before

    status, text = call(
        endpoint, "DELETE", f"/v1/apis/{api['apiId']}/apikeys/{key['id']}"
    )
    assert status == 200, f"DeleteApiKey answered {status}: {text[:400]}"
    after = {row["id"] for row in event_keys(endpoint, api["apiId"])}
    assert key["id"] not in after
    assert before - {key["id"]} <= after
    assert call(endpoint, "DELETE", f"/v1/apis/{api['apiId']}/apikeys/{key['id']}")[0] == 404
