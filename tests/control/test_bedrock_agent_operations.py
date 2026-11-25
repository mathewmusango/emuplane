"""Bedrock Agent control plane on the wire: all 72 advertised operations, REST/JSON.

Agents carry versions, aliases, action groups, collaborators and knowledge-base
associations, and `PrepareAgent` promotes the draft; knowledge bases carry data
sources, documents and ingestion jobs whose S3 source is read for real; flows carry
versions, aliases, `ValidateFlowDefinition` and `PrepareFlow`; prompts carry
versions; and one tag surface spans them all. Every create is found by name first,
so a sweep reuses what the last one left behind, and every delete action builds a
resource of its own and removes only that. One path needs explaining: the emulator
has no route that creates an agent version, so the three version operations read a
record seeded in-process (and skip on a lab, where in-process seeding cannot reach
the endpoint).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

import pytest

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}
MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/ops-bedrock-agent-role"
DRAFT = "DRAFT"

AGENT = "ops-ba-agent"
ALIAS = "ops-ba-alias"
ACTION_GROUP = "ops-ba-action-group"
COLLABORATOR = "ops-ba-collaborator"
KB = "ops-ba-kb"
OTHER_KB = "ops-ba-kb-collaborator"
UPDATED_KB = "ops-ba-kb-updated"
DS = "ops-ba-datasource"
FLOW = "ops-ba-flow"
FLOW_ALIAS = "ops-ba-flow-alias"
PROMPT = "ops-ba-prompt"

BUCKET = "ops-ba-ingestion"
DOCUMENT = "handbook.txt"


def call(endpoint, method: str, path: str, payload=None):
    body = json.dumps(payload) if payload is not None else ""
    return signed.request(
        endpoint, "bedrock", ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def ok(endpoint, method: str, path: str, payload=None, status: int = 200) -> dict:
    code, text = call(endpoint, method, path, payload)
    assert code == status, f"{method} {path} answered {code}: {text[:400]}"
    return json.loads(text or "{}")


def first(endpoint, method: str, path: str, key: str, field: str, value: str, payload=None):
    for item in ok(endpoint, method, path, payload).get(key, []):
        if item.get(field) == value:
            return item
    return None


def quoted(arn: str) -> str:
    return quote(arn, safe="")


# --- Found-or-created resources ---------------------------------------------


def ensure_agent(endpoint, name: str = AGENT) -> dict:
    summary = first(endpoint, "POST", "/agents/", "agentSummaries", "agentName", name, {})
    if summary is not None:
        return ok(endpoint, "GET", f"/agents/{summary['agentId']}")["agent"]
    return ok(
        endpoint,
        "PUT",
        "/agents/",
        {
            "agentName": name,
            "agentResourceRoleArn": ROLE,
            "foundationModel": MODEL,
            "instruction": "Ops agent used by the coverage suite.",
            "description": "Ops agent used by the coverage suite.",
        },
        status=202,
    )["agent"]


def ensure_alias(endpoint, agent_id: str, name: str = ALIAS) -> dict:
    path = f"/agents/{agent_id}/agentaliases/"
    summary = first(endpoint, "POST", path, "agentAliasSummaries", "agentAliasName", name, {})
    if summary is not None:
        return ok(endpoint, "GET", f"{path}{summary['agentAliasId']}")["agentAlias"]
    return ok(
        endpoint,
        "PUT",
        path,
        {"agentAliasName": name, "description": "Ops alias used by the coverage suite."},
        status=202,
    )["agentAlias"]


def ensure_action_group(endpoint, agent_id: str, name: str = ACTION_GROUP) -> dict:
    path = f"/agents/{agent_id}/agentversions/{DRAFT}/actiongroups/"
    summary = first(endpoint, "POST", path, "actionGroupSummaries", "actionGroupName", name, {})
    if summary is not None:
        return ok(endpoint, "GET", f"{path}{summary['actionGroupId']}")["agentActionGroup"]
    return ok(
        endpoint,
        "PUT",
        path,
        {
            "actionGroupName": name,
            "description": "Ops action group used by the coverage suite.",
            "actionGroupExecutor": {
                "lambda": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:ops-ba-action"
            },
            "functionSchema": {"functions": [{"name": "lookup", "description": "Look up an order."}]},
        },
    )["agentActionGroup"]


def ensure_collaborator(endpoint, agent_id: str, name: str = COLLABORATOR) -> dict:
    path = f"/agents/{agent_id}/agentversions/{DRAFT}/agentcollaborators/"
    summary = first(endpoint, "POST", path, "agentCollaboratorSummaries", "collaboratorName", name, {})
    if summary is not None:
        return ok(endpoint, "GET", f"{path}{summary['collaboratorId']}")["agentCollaborator"]
    return ok(
        endpoint,
        "PUT",
        path,
        {
            "collaboratorName": name,
            "agentDescriptor": {
                "aliasArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:agent-alias/AGENT00001/ALIAS00001"
            },
            "collaborationInstruction": "Collaborate on the request.",
        },
    )["agentCollaborator"]


def ensure_agent_kb(endpoint, agent_id: str, kb_id: str) -> dict:
    path = f"/agents/{agent_id}/agentversions/{DRAFT}/knowledgebases/"
    summary = first(endpoint, "POST", path, "agentKnowledgeBaseSummaries", "knowledgeBaseId", kb_id, {})
    if summary is not None:
        return ok(endpoint, "GET", f"{path}{kb_id}")["agentKnowledgeBase"]
    return ok(
        endpoint,
        "PUT",
        path,
        {"knowledgeBaseId": kb_id, "description": "Ops agent knowledge base association."},
    )["agentKnowledgeBase"]


def ensure_kb(endpoint, name: str = KB) -> dict:
    summary = first(endpoint, "POST", "/knowledgebases/", "knowledgeBaseSummaries", "name", name, {})
    if summary is not None:
        return ok(endpoint, "GET", f"/knowledgebases/{summary['knowledgeBaseId']}")["knowledgeBase"]
    return ok(
        endpoint,
        "PUT",
        "/knowledgebases/",
        {
            "name": name,
            "roleArn": ROLE,
            "description": "Ops knowledge base used by the coverage suite.",
            "knowledgeBaseConfiguration": {
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": (
                        f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v1"
                    )
                },
            },
        },
        status=202,
    )["knowledgeBase"]


def ensure_source(endpoint) -> str:
    """The S3 source an ingestion job reads: one bucket holding one UTF-8 document."""
    status, text = signed.request(endpoint, "s3", ACCOUNT, REGION, "PUT", f"/{BUCKET}")
    assert status in (200, 409), f"CreateBucket answered {status}: {text[:300]}"
    status, text = signed.request(
        endpoint,
        "s3",
        ACCOUNT,
        REGION,
        "PUT",
        f"/{BUCKET}/{DOCUMENT}",
        "Ops ingestion source document.\n",
        {"Content-Type": "text/plain"},
    )
    assert status == 200, f"PutObject answered {status}: {text[:300]}"
    return BUCKET


def ensure_ds(endpoint, kb_id: str, name: str = DS) -> dict:
    ensure_source(endpoint)
    path = f"/knowledgebases/{kb_id}/datasources/"
    summary = first(endpoint, "POST", path, "dataSourceSummaries", "name", name, {})
    if summary is not None:
        return ok(endpoint, "GET", f"{path}{summary['dataSourceId']}")["dataSource"]
    return ok(
        endpoint,
        "PUT",
        path,
        {
            "name": name,
            "description": "Ops data source used by the coverage suite.",
            "dataSourceConfiguration": {
                "type": "S3",
                "s3Configuration": {"bucketArn": f"arn:aws:s3:::{BUCKET}"},
            },
        },
    )["dataSource"]


def ensure_flow(endpoint, name: str = FLOW) -> dict:
    summary = first(endpoint, "GET", "/flows/", "flowSummaries", "name", name)
    if summary is not None:
        return ok(endpoint, "GET", f"/flows/{summary['id']}")
    return ok(
        endpoint,
        "POST",
        "/flows/",
        {
            "name": name,
            "executionRoleArn": ROLE,
            "description": "Ops flow used by the coverage suite.",
            "definition": {"nodes": [], "connections": []},
        },
        status=201,
    )


def ensure_flow_version(endpoint, flow_id: str) -> str:
    summaries = ok(endpoint, "GET", f"/flows/{flow_id}/versions").get("flowVersionSummaries", [])
    if summaries:
        return summaries[0]["version"]
    return ok(endpoint, "POST", f"/flows/{flow_id}/versions", {}, status=201)["version"]


def ensure_flow_alias(endpoint, flow_id: str, name: str = FLOW_ALIAS) -> dict:
    path = f"/flows/{flow_id}/aliases"
    summary = first(endpoint, "GET", path, "flowAliasSummaries", "name", name)
    if summary is not None:
        return ok(endpoint, "GET", f"{path}/{summary['id']}")
    return ok(
        endpoint,
        "POST",
        path,
        {
            "name": name,
            "description": "Ops flow alias used by the coverage suite.",
            "routingConfiguration": [{"flowVersion": ensure_flow_version(endpoint, flow_id)}],
        },
        status=201,
    )


def ensure_prompt(endpoint, name: str = PROMPT) -> dict:
    summary = first(endpoint, "GET", "/prompts/", "promptSummaries", "name", name)
    if summary is not None:
        return ok(endpoint, "GET", f"/prompts/{summary['id']}")
    return ok(
        endpoint,
        "POST",
        "/prompts/",
        {
            "name": name,
            "description": "Ops prompt used by the coverage suite.",
            "variants": [
                {
                    "name": "default",
                    "templateType": "TEXT",
                    "templateConfiguration": {"text": {"text": "Hello from ops."}},
                }
            ],
        },
        status=201,
    )


def ingest_document(endpoint, kb_id: str, ds_id: str, doc_id: str) -> dict:
    return ok(
        endpoint,
        "PUT",
        f"/knowledgebases/{kb_id}/datasources/{ds_id}/documents",
        {
            "documents": [
                {
                    "content": {
                        "custom": {
                            "customDocumentIdentifier": {"id": doc_id},
                            "inlineContent": {"textContent": {"data": "Ops document."}},
                        }
                    }
                }
            ]
        },
        status=202,
    )


def start_job(endpoint, kb_id: str, ds_id: str) -> dict:
    return ok(
        endpoint,
        "PUT",
        f"/knowledgebases/{kb_id}/datasources/{ds_id}/ingestionjobs/",
        {"description": "Ops ingestion run."},
        status=202,
    )["ingestionJob"]


def seed_agent_version(agent_id: str, name: str = AGENT, version: str = "1") -> dict:
    """A version record the emulator's own state restore would place; it exposes no create route."""
    if os.environ.get("EP_LAB_EMULATOR"):
        pytest.skip("no CreateAgentVersion route: an agent version is seeded in-process only")
    from ministack.services import bedrock_agent as emulator_agent  # noqa: PLC0415

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "AgentArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:agent/{agent_id}",
        "AgentId": agent_id,
        "AgentName": name,
        "AgentResourceRoleArn": ROLE,
        "AgentStatus": "PREPARED",
        "AgentVersion": version,
        "CreatedAt": now,
        "Description": "Seeded agent version.",
        "FoundationModel": MODEL,
        "Instruction": "Ops agent.",
        "UpdatedAt": now,
    }
    emulator_agent._agent_versions.set_scoped(ACCOUNT, REGION, f"{agent_id}/{version}", record)
    return record


def prepare_agent(endpoint, agent_id: str) -> dict:
    return ok(endpoint, "POST", f"/agents/{agent_id}", status=202)


# --- Agents -----------------------------------------------------------------


def test_create_agent_is_read_back(endpoint):
    agent = ensure_agent(endpoint, "ops-ba-agent-create")
    assert agent["agentName"] == "ops-ba-agent-create"
    assert agent["agentStatus"] == "NOT_PREPARED"
    assert agent["agentVersion"] == DRAFT
    assert agent["agentArn"].endswith(f":agent/{agent['agentId']}")


def test_list_agents_includes_the_agent(endpoint):
    agent = ensure_agent(endpoint)
    listed = ok(endpoint, "POST", "/agents/", {})["agentSummaries"]
    assert agent["agentId"] in {item["agentId"] for item in listed}


def test_get_agent_reads_it(endpoint):
    agent = ensure_agent(endpoint)
    read = ok(endpoint, "GET", f"/agents/{agent['agentId']}")["agent"]
    assert read["agentName"] == AGENT
    assert read["agentArn"] == agent["agentArn"]


def test_update_agent_sets_the_description(endpoint):
    agent = ensure_agent(endpoint)
    updated = ok(
        endpoint,
        "PUT",
        f"/agents/{agent['agentId']}",
        {"description": "Ops agent updated.", "instruction": "Answer briefly."},
        status=202,
    )["agent"]
    assert updated["description"] == "Ops agent updated."
    assert ok(endpoint, "GET", f"/agents/{agent['agentId']}")["agent"]["instruction"] == "Answer briefly."


def test_delete_agent_removes_it(endpoint):
    agent = ensure_agent(endpoint, "ops-ba-agent-gone")
    deleted = ok(endpoint, "DELETE", f"/agents/{agent['agentId']}", status=202)
    assert deleted["agentStatus"] == "DELETING"
    code, text = call(endpoint, "GET", f"/agents/{agent['agentId']}")
    assert code == 404, text[:300]


def test_prepare_agent_reports_prepared(endpoint):
    agent = ensure_agent(endpoint)
    prepared = prepare_agent(endpoint, agent["agentId"])
    assert prepared["agentStatus"] == "PREPARED"
    assert prepared["agentVersion"] == DRAFT
    assert ok(endpoint, "GET", f"/agents/{agent['agentId']}")["agent"]["agentStatus"] == "PREPARED"


# --- Agent versions ---------------------------------------------------------


def test_list_agent_versions_names_the_version(endpoint):
    agent = ensure_agent(endpoint)
    seed_agent_version(agent["agentId"])
    versions = ok(endpoint, "POST", f"/agents/{agent['agentId']}/agentversions/", {})[
        "agentVersionSummaries"
    ]
    assert "1" in {item["agentVersion"] for item in versions}


def test_get_agent_version_reads_it(endpoint):
    agent = ensure_agent(endpoint)
    seeded = seed_agent_version(agent["agentId"])
    version = ok(endpoint, "GET", f"/agents/{agent['agentId']}/agentversions/1")["agentVersion"]
    assert version["agentVersion"] == "1"
    assert version["agentId"] == agent["agentId"]
    assert version["agentArn"] == seeded["AgentArn"]


def test_delete_agent_version_removes_it(endpoint):
    agent = ensure_agent(endpoint, "ops-ba-agent-versions")
    seed_agent_version(agent["agentId"], name="ops-ba-agent-versions", version="2")
    ok(endpoint, "DELETE", f"/agents/{agent['agentId']}/agentversions/2", status=202)
    code, text = call(endpoint, "GET", f"/agents/{agent['agentId']}/agentversions/2")
    assert code == 404, text[:300]


# --- Agent aliases ----------------------------------------------------------


def test_create_agent_alias_is_read_back(endpoint):
    agent = ensure_agent(endpoint)
    alias = ensure_alias(endpoint, agent["agentId"])
    assert alias["agentAliasName"] == ALIAS
    assert alias["agentAliasStatus"] == "PREPARED"
    assert alias["agentId"] == agent["agentId"]


def test_list_agent_aliases_names_the_alias(endpoint):
    agent = ensure_agent(endpoint)
    alias = ensure_alias(endpoint, agent["agentId"])
    listed = ok(endpoint, "POST", f"/agents/{agent['agentId']}/agentaliases/", {})[
        "agentAliasSummaries"
    ]
    assert alias["agentAliasId"] in {item["agentAliasId"] for item in listed}


def test_get_agent_alias_reads_it(endpoint):
    agent = ensure_agent(endpoint)
    alias = ensure_alias(endpoint, agent["agentId"])
    read = ok(endpoint, "GET", f"/agents/{agent['agentId']}/agentaliases/{alias['agentAliasId']}")[
        "agentAlias"
    ]
    assert read["agentAliasName"] == ALIAS


def test_update_agent_alias_sets_the_description(endpoint):
    agent = ensure_agent(endpoint)
    alias = ensure_alias(endpoint, agent["agentId"])
    path = f"/agents/{agent['agentId']}/agentaliases/{alias['agentAliasId']}"
    updated = ok(endpoint, "PUT", path, {"description": "Ops alias updated."}, status=202)["agentAlias"]
    assert updated["description"] == "Ops alias updated."


def test_delete_agent_alias_removes_it(endpoint):
    agent = ensure_agent(endpoint)
    created = ok(
        endpoint,
        "PUT",
        f"/agents/{agent['agentId']}/agentaliases/",
        {"agentAliasName": "ops-ba-alias-gone"},
        status=202,
    )["agentAlias"]
    ok(endpoint, "DELETE", f"/agents/{agent['agentId']}/agentaliases/{created['agentAliasId']}", status=202)
    code, text = call(
        endpoint, "GET", f"/agents/{agent['agentId']}/agentaliases/{created['agentAliasId']}"
    )
    assert code == 404, text[:300]


# --- Agent action groups ----------------------------------------------------


def test_create_agent_action_group_is_read_back(endpoint):
    agent = ensure_agent(endpoint)
    group = ensure_action_group(endpoint, agent["agentId"])
    assert group["actionGroupName"] == ACTION_GROUP
    assert group["actionGroupState"] == "ENABLED"
    assert group["agentId"] == agent["agentId"]


def test_list_agent_action_groups_names_the_group(endpoint):
    agent = ensure_agent(endpoint)
    group = ensure_action_group(endpoint, agent["agentId"])
    listed = ok(
        endpoint, "POST", f"/agents/{agent['agentId']}/agentversions/{DRAFT}/actiongroups/", {}
    )["actionGroupSummaries"]
    assert group["actionGroupId"] in {item["actionGroupId"] for item in listed}


def test_get_agent_action_group_reads_it(endpoint):
    agent = ensure_agent(endpoint)
    group = ensure_action_group(endpoint, agent["agentId"])
    read = ok(
        endpoint,
        "GET",
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/actiongroups/{group['actionGroupId']}",
    )["agentActionGroup"]
    assert read["actionGroupName"] == ACTION_GROUP


def test_update_agent_action_group_disables_it(endpoint):
    agent = ensure_agent(endpoint)
    group = ensure_action_group(endpoint, agent["agentId"], "ops-ba-action-group-updated")
    path = (
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/actiongroups/{group['actionGroupId']}"
    )
    updated = ok(endpoint, "PUT", path, {"actionGroupState": "DISABLED"})["agentActionGroup"]
    assert updated["actionGroupState"] == "DISABLED"
    assert ok(endpoint, "GET", path)["agentActionGroup"]["actionGroupState"] == "DISABLED"


def test_delete_agent_action_group_removes_it(endpoint):
    agent = ensure_agent(endpoint)
    created = ok(
        endpoint,
        "PUT",
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/actiongroups/",
        {"actionGroupName": "ops-ba-action-group-gone"},
    )["agentActionGroup"]
    path = (
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/actiongroups/{created['actionGroupId']}"
    )
    ok(endpoint, "DELETE", path, status=204)
    code, text = call(endpoint, "GET", path)
    assert code == 404, text[:300]


# --- Agent collaborators ----------------------------------------------------


def test_associate_agent_collaborator_is_read_back(endpoint):
    agent = ensure_agent(endpoint)
    collaborator = ensure_collaborator(endpoint, agent["agentId"])
    assert collaborator["collaboratorName"] == COLLABORATOR
    assert collaborator["agentId"] == agent["agentId"]


def test_list_agent_collaborators_names_the_collaborator(endpoint):
    agent = ensure_agent(endpoint)
    collaborator = ensure_collaborator(endpoint, agent["agentId"])
    listed = ok(
        endpoint, "POST", f"/agents/{agent['agentId']}/agentversions/{DRAFT}/agentcollaborators/", {}
    )["agentCollaboratorSummaries"]
    assert collaborator["collaboratorId"] in {item["collaboratorId"] for item in listed}


def test_get_agent_collaborator_reads_it(endpoint):
    agent = ensure_agent(endpoint)
    collaborator = ensure_collaborator(endpoint, agent["agentId"])
    read = ok(
        endpoint,
        "GET",
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/agentcollaborators/"
        f"{collaborator['collaboratorId']}",
    )["agentCollaborator"]
    assert read["collaboratorName"] == COLLABORATOR


def test_update_agent_collaborator_sets_the_instruction(endpoint):
    agent = ensure_agent(endpoint)
    collaborator = ensure_collaborator(endpoint, agent["agentId"])
    path = (
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/agentcollaborators/"
        f"{collaborator['collaboratorId']}"
    )
    updated = ok(
        endpoint, "PUT", path, {"collaborationInstruction": "Relay the order id."}
    )["agentCollaborator"]
    assert updated["collaborationInstruction"] == "Relay the order id."


def test_disassociate_agent_collaborator_removes_it(endpoint):
    agent = ensure_agent(endpoint)
    created = ok(
        endpoint,
        "PUT",
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/agentcollaborators/",
        {"collaboratorName": "ops-ba-collaborator-gone"},
    )["agentCollaborator"]
    path = (
        f"/agents/{agent['agentId']}/agentversions/{DRAFT}/agentcollaborators/"
        f"{created['collaboratorId']}"
    )
    ok(endpoint, "DELETE", path, status=204)
    code, text = call(endpoint, "GET", path)
    assert code == 404, text[:300]


# --- Agent knowledge bases --------------------------------------------------


def test_associate_agent_knowledge_base_is_read_back(endpoint):
    agent = ensure_agent(endpoint)
    kb = ensure_kb(endpoint)
    association = ensure_agent_kb(endpoint, agent["agentId"], kb["knowledgeBaseId"])
    assert association["knowledgeBaseId"] == kb["knowledgeBaseId"]
    assert association["knowledgeBaseState"] == "ENABLED"


def test_list_agent_knowledge_bases_names_the_association(endpoint):
    agent = ensure_agent(endpoint)
    kb_id = ensure_kb(endpoint)["knowledgeBaseId"]
    ensure_agent_kb(endpoint, agent["agentId"], kb_id)
    listed = ok(
        endpoint, "POST", f"/agents/{agent['agentId']}/agentversions/{DRAFT}/knowledgebases/", {}
    )["agentKnowledgeBaseSummaries"]
    assert kb_id in {item["knowledgeBaseId"] for item in listed}


def test_get_agent_knowledge_base_reads_it(endpoint):
    agent = ensure_agent(endpoint)
    kb_id = ensure_kb(endpoint)["knowledgeBaseId"]
    ensure_agent_kb(endpoint, agent["agentId"], kb_id)
    read = ok(
        endpoint, "GET", f"/agents/{agent['agentId']}/agentversions/{DRAFT}/knowledgebases/{kb_id}"
    )["agentKnowledgeBase"]
    assert read["knowledgeBaseId"] == kb_id


def test_update_agent_knowledge_base_sets_the_state(endpoint):
    agent = ensure_agent(endpoint)
    kb_id = ensure_kb(endpoint, UPDATED_KB)["knowledgeBaseId"]
    ensure_agent_kb(endpoint, agent["agentId"], kb_id)
    path = f"/agents/{agent['agentId']}/agentversions/{DRAFT}/knowledgebases/{kb_id}"
    updated = ok(endpoint, "PUT", path, {"knowledgeBaseState": "DISABLED"})["agentKnowledgeBase"]
    assert updated["knowledgeBaseState"] == "DISABLED"


def test_disassociate_agent_knowledge_base_removes_it(endpoint):
    agent = ensure_agent(endpoint)
    kb_id = ensure_kb(endpoint, OTHER_KB)["knowledgeBaseId"]
    path = f"/agents/{agent['agentId']}/agentversions/{DRAFT}/knowledgebases/{kb_id}"
    ensure_agent_kb(endpoint, agent["agentId"], kb_id)
    ok(endpoint, "DELETE", path, status=204)
    code, text = call(endpoint, "GET", path)
    assert code == 404, text[:300]


# --- Knowledge bases --------------------------------------------------------


def test_create_knowledge_base_is_read_back(endpoint):
    kb = ensure_kb(endpoint, "ops-ba-kb-create")
    assert kb["name"] == "ops-ba-kb-create"
    assert kb["status"] == "ACTIVE"
    assert kb["knowledgeBaseArn"].endswith(f":knowledge-base/{kb['knowledgeBaseId']}")


def test_list_knowledge_bases_includes_the_knowledge_base(endpoint):
    kb = ensure_kb(endpoint)
    listed = ok(endpoint, "POST", "/knowledgebases/", {})["knowledgeBaseSummaries"]
    assert kb["knowledgeBaseId"] in {item["knowledgeBaseId"] for item in listed}


def test_get_knowledge_base_reads_it(endpoint):
    kb = ensure_kb(endpoint)
    read = ok(endpoint, "GET", f"/knowledgebases/{kb['knowledgeBaseId']}")["knowledgeBase"]
    assert read["name"] == KB
    assert read["roleArn"] == ROLE


def test_update_knowledge_base_sets_the_description(endpoint):
    kb = ensure_kb(endpoint)
    updated = ok(
        endpoint,
        "PUT",
        f"/knowledgebases/{kb['knowledgeBaseId']}",
        {"description": "Ops knowledge base updated."},
        status=202,
    )["knowledgeBase"]
    assert updated["description"] == "Ops knowledge base updated."


def test_delete_knowledge_base_removes_it(endpoint):
    kb = ensure_kb(endpoint, "ops-ba-kb-gone")
    deleted = ok(endpoint, "DELETE", f"/knowledgebases/{kb['knowledgeBaseId']}", status=202)
    assert deleted["status"] == "DELETING"
    code, text = call(endpoint, "GET", f"/knowledgebases/{kb['knowledgeBaseId']}")
    assert code == 404, text[:300]


# --- Data sources -----------------------------------------------------------


def test_create_data_source_is_read_back(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    assert ds["name"] == DS
    assert ds["status"] == "AVAILABLE"
    assert ds["knowledgeBaseId"] == kb["knowledgeBaseId"]


def test_list_data_sources_names_the_data_source(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    listed = ok(endpoint, "POST", f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/", {})[
        "dataSourceSummaries"
    ]
    assert ds["dataSourceId"] in {item["dataSourceId"] for item in listed}


def test_get_data_source_reads_it(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    read = ok(
        endpoint, "GET", f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}"
    )["dataSource"]
    assert read["dataSourceConfiguration"]["s3Configuration"]["bucketArn"].endswith(BUCKET)


def test_update_data_source_sets_the_description(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    updated = ok(
        endpoint,
        "PUT",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}",
        {"description": "Ops data source updated."},
    )["dataSource"]
    assert updated["description"] == "Ops data source updated."


def test_delete_data_source_removes_it(endpoint):
    kb = ensure_kb(endpoint)
    created = ok(
        endpoint,
        "PUT",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/",
        {
            "name": "ops-ba-datasource-gone",
            "dataSourceConfiguration": {
                "type": "S3",
                "s3Configuration": {"bucketArn": f"arn:aws:s3:::{BUCKET}"},
            },
        },
    )["dataSource"]
    path = f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{created['dataSourceId']}"
    deleted = ok(endpoint, "DELETE", path, status=202)
    assert deleted["status"] == "DELETING"
    code, text = call(endpoint, "GET", path)
    assert code == 404, text[:300]


# --- Ingestion jobs ---------------------------------------------------------


def test_start_ingestion_job_reads_the_s3_source(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    job = start_job(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"])
    assert job["status"] == "STARTING"
    stats = job["statistics"]
    assert stats["numberOfDocumentsScanned"] >= 1
    assert stats["numberOfNewDocumentsIndexed"] + stats["numberOfModifiedDocumentsIndexed"] >= 1
    assert stats["numberOfDocumentsFailed"] == 0
    assert job["failureReasons"] == []


def test_get_ingestion_job_reports_the_statistics(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    started = start_job(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"])
    job = ok(
        endpoint,
        "GET",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}"
        f"/ingestionjobs/{started['ingestionJobId']}",
    )["ingestionJob"]
    assert job["status"] == "COMPLETE"
    assert job["statistics"]["numberOfDocumentsScanned"] >= 1


def test_list_ingestion_jobs_names_the_job(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    started = start_job(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"])
    listed = ok(
        endpoint,
        "POST",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}/ingestionjobs/",
        {},
    )["ingestionJobSummaries"]
    assert started["ingestionJobId"] in {item["ingestionJobId"] for item in listed}


def test_stop_ingestion_job_marks_it_stopped(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    started = start_job(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"])
    stopped = ok(
        endpoint,
        "POST",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}"
        f"/ingestionjobs/{started['ingestionJobId']}/stop",
        status=202,
    )["ingestionJob"]
    assert stopped["status"] == "STOPPED"


# --- Knowledge base documents -----------------------------------------------


def test_ingest_knowledge_base_documents_indexes_them(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    details = ingest_document(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"], "ops-ba-ingest")[
        "documentDetails"
    ]
    assert details[0]["status"] == "INDEXED"


def test_list_knowledge_base_documents_lists_the_document(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    ingest_document(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"], "ops-ba-list")
    details = ok(
        endpoint,
        "POST",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}/documents",
        {},
    )["documentDetails"]
    assert "ops-ba-list" in {
        (item.get("documentIdentifier") or {}).get("id") for item in details
    }


def test_get_knowledge_base_documents_reads_them(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"])
    ingest_document(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"], "ops-ba-read")
    details = ok(
        endpoint,
        "POST",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}"
        "/documents/getDocuments",
        {"documentIdentifiers": [{"custom": {"id": "ops-ba-read"}}]},
    )["documentDetails"]
    assert details[0]["status"] == "INDEXED"


def test_delete_knowledge_base_documents_removes_them(endpoint):
    kb = ensure_kb(endpoint)
    ds = ensure_ds(endpoint, kb["knowledgeBaseId"], "ops-ba-datasource-docs")
    ingest_document(endpoint, kb["knowledgeBaseId"], ds["dataSourceId"], "ops-ba-delete")
    path = (
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}"
        "/documents/deleteDocuments"
    )
    deleted = ok(
        endpoint, "POST", path, {"documentIdentifiers": [{"custom": {"id": "ops-ba-delete"}}]}, status=202
    )["documentDetails"]
    assert deleted[0]["status"] == "DELETING"
    remaining = ok(
        endpoint,
        "POST",
        f"/knowledgebases/{kb['knowledgeBaseId']}/datasources/{ds['dataSourceId']}" "/documents",
        {},
    )["documentDetails"]
    assert "ops-ba-delete" not in {
        (item.get("documentIdentifier") or {}).get("id") for item in remaining
    }


# --- Flows ------------------------------------------------------------------


def test_create_flow_is_read_back(endpoint):
    flow = ensure_flow(endpoint, "ops-ba-flow-create")
    assert flow["name"] == "ops-ba-flow-create"
    assert flow["status"] == "NotPrepared"
    assert flow["version"] == DRAFT
    assert flow["arn"].endswith(f":flow/{flow['id']}")


def test_list_flows_includes_the_flow(endpoint):
    flow = ensure_flow(endpoint)
    listed = ok(endpoint, "GET", "/flows/")["flowSummaries"]
    assert flow["id"] in {item["id"] for item in listed}


def test_validate_flow_definition_answers_validations(endpoint):
    answer = ok(
        endpoint,
        "POST",
        "/flows/validate-definition",
        {"definition": {"nodes": [{"name": "Input", "type": "Input"}], "connections": []}},
    )
    assert isinstance(answer["validations"], list)


def test_create_flow_version_is_read_back(endpoint):
    flow = ensure_flow(endpoint)
    created = ok(endpoint, "POST", f"/flows/{flow['id']}/versions", {}, status=201)
    assert created["version"].isdigit()
    assert created["id"] == flow["id"]


def test_get_flow_version_reads_it(endpoint):
    flow = ensure_flow(endpoint)
    version = ensure_flow_version(endpoint, flow["id"])
    read = ok(endpoint, "GET", f"/flows/{flow['id']}/versions/{version}")
    assert read["version"] == version
    assert read["id"] == flow["id"]


def test_list_flow_versions_names_the_version(endpoint):
    flow = ensure_flow(endpoint)
    version = ensure_flow_version(endpoint, flow["id"])
    listed = ok(endpoint, "GET", f"/flows/{flow['id']}/versions")["flowVersionSummaries"]
    assert version in {item["version"] for item in listed}


def test_delete_flow_version_removes_it(endpoint):
    flow = ensure_flow(endpoint)
    created = ok(endpoint, "POST", f"/flows/{flow['id']}/versions", {}, status=201)
    ok(endpoint, "DELETE", f"/flows/{flow['id']}/versions/{created['version']}")
    code, text = call(endpoint, "GET", f"/flows/{flow['id']}/versions/{created['version']}")
    assert code == 404, text[:300]


def test_create_flow_alias_is_read_back(endpoint):
    flow = ensure_flow(endpoint)
    alias = ensure_flow_alias(endpoint, flow["id"])
    assert alias["name"] == FLOW_ALIAS
    assert alias["flowId"] == flow["id"]
    assert alias["routingConfiguration"]


def test_list_flow_aliases_names_the_alias(endpoint):
    flow = ensure_flow(endpoint)
    alias = ensure_flow_alias(endpoint, flow["id"])
    listed = ok(endpoint, "GET", f"/flows/{flow['id']}/aliases")["flowAliasSummaries"]
    assert alias["id"] in {item["id"] for item in listed}


def test_get_flow_alias_reads_it(endpoint):
    flow = ensure_flow(endpoint)
    alias = ensure_flow_alias(endpoint, flow["id"])
    read = ok(endpoint, "GET", f"/flows/{flow['id']}/aliases/{alias['id']}")
    assert read["name"] == FLOW_ALIAS


def test_update_flow_alias_sets_the_description(endpoint):
    flow = ensure_flow(endpoint)
    alias = ensure_flow_alias(endpoint, flow["id"])
    updated = ok(
        endpoint,
        "PUT",
        f"/flows/{flow['id']}/aliases/{alias['id']}",
        {"description": "Ops flow alias updated."},
    )
    assert updated["description"] == "Ops flow alias updated."


def test_delete_flow_alias_removes_it(endpoint):
    flow = ensure_flow(endpoint)
    created = ok(
        endpoint,
        "POST",
        f"/flows/{flow['id']}/aliases",
        {
            "name": "ops-ba-flow-alias-gone",
            "routingConfiguration": [{"flowVersion": ensure_flow_version(endpoint, flow["id"])}],
        },
        status=201,
    )
    ok(endpoint, "DELETE", f"/flows/{flow['id']}/aliases/{created['id']}")
    code, text = call(endpoint, "GET", f"/flows/{flow['id']}/aliases/{created['id']}")
    assert code == 404, text[:300]


def test_get_flow_reads_it(endpoint):
    flow = ensure_flow(endpoint)
    read = ok(endpoint, "GET", f"/flows/{flow['id']}")
    assert read["name"] == FLOW
    assert read["arn"] == flow["arn"]


def test_update_flow_sets_the_description(endpoint):
    flow = ensure_flow(endpoint)
    updated = ok(
        endpoint, "PUT", f"/flows/{flow['id']}", {"description": "Ops flow updated."}
    )
    assert updated["description"] == "Ops flow updated."


def test_delete_flow_removes_it(endpoint):
    flow = ensure_flow(endpoint, "ops-ba-flow-gone")
    deleted = ok(endpoint, "DELETE", f"/flows/{flow['id']}")
    assert deleted["id"] == flow["id"]
    code, text = call(endpoint, "GET", f"/flows/{flow['id']}")
    assert code == 404, text[:300]


def test_prepare_flow_reports_prepared(endpoint):
    flow = ensure_flow(endpoint)
    prepared = ok(endpoint, "POST", f"/flows/{flow['id']}", status=202)
    assert prepared["status"] == "Prepared"
    assert ok(endpoint, "GET", f"/flows/{flow['id']}")["status"] == "Prepared"


# --- Prompts ----------------------------------------------------------------


def test_create_prompt_is_read_back(endpoint):
    prompt = ensure_prompt(endpoint, "ops-ba-prompt-create")
    assert prompt["name"] == "ops-ba-prompt-create"
    assert prompt["version"] == DRAFT
    assert prompt["arn"].endswith(f":prompt/{prompt['id']}")


def test_list_prompts_includes_the_prompt(endpoint):
    prompt = ensure_prompt(endpoint)
    listed = ok(endpoint, "GET", "/prompts/")["promptSummaries"]
    assert prompt["id"] in {item["id"] for item in listed}


def test_create_prompt_version_is_read_back(endpoint):
    prompt = ensure_prompt(endpoint)
    created = ok(endpoint, "POST", f"/prompts/{prompt['id']}/versions", {}, status=201)
    assert created["version"].isdigit()
    assert created["arn"].endswith(f":{created['version']}")


def test_get_prompt_reads_a_version(endpoint):
    prompt = ensure_prompt(endpoint)
    created = ok(endpoint, "POST", f"/prompts/{prompt['id']}/versions", {}, status=201)
    read = ok(endpoint, "GET", f"/prompts/{prompt['id']}?promptVersion={created['version']}")
    assert read["version"] == created["version"]
    assert read["id"] == prompt["id"]


def test_update_prompt_sets_the_description(endpoint):
    prompt = ensure_prompt(endpoint)
    updated = ok(
        endpoint, "PUT", f"/prompts/{prompt['id']}", {"description": "Ops prompt updated."}
    )
    assert updated["description"] == "Ops prompt updated."


def test_delete_prompt_removes_it(endpoint):
    prompt = ensure_prompt(endpoint, "ops-ba-prompt-gone")
    deleted = ok(endpoint, "DELETE", f"/prompts/{prompt['id']}")
    assert deleted["id"] == prompt["id"]
    code, text = call(endpoint, "GET", f"/prompts/{prompt['id']}")
    assert code == 404, text[:300]


# --- Tags -------------------------------------------------------------------


def test_tag_resource_adds_a_tag(endpoint):
    arn = ensure_agent(endpoint)["agentArn"]
    ok(endpoint, "POST", f"/tags/{quoted(arn)}", {"tags": {"team": "ops"}})
    assert ok(endpoint, "GET", f"/tags/{quoted(arn)}")["tags"]["team"] == "ops"


def test_list_tags_for_resource_reports_them(endpoint):
    arn = ensure_kb(endpoint)["knowledgeBaseArn"]
    ok(endpoint, "POST", f"/tags/{quoted(arn)}", {"tags": {"env": "test"}})
    tags = ok(endpoint, "GET", f"/tags/{quoted(arn)}")["tags"]
    assert tags["env"] == "test"


def test_untag_resource_removes_the_key(endpoint):
    arn = ensure_flow(endpoint)["arn"]
    ok(endpoint, "POST", f"/tags/{quoted(arn)}", {"tags": {"temporary": "yes"}})
    ok(endpoint, "DELETE", f"/tags/{quoted(arn)}?tagKeys=temporary")
    assert "temporary" not in ok(endpoint, "GET", f"/tags/{quoted(arn)}")["tags"]
