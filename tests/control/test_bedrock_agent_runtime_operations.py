"""Bedrock Agent Runtime on the wire: all 27 advertised operations, REST/JSON.

The whole Bedrock family signs with the `bedrock` credential scope, so the
in-process stand-in picks the plane by path exactly as the emulator's router
does. Model, agent, flow and session answers are deterministic mocks; the tests
assert wire shape and state transitions. `Retrieve` needs a knowledge base,
created through the Bedrock Agent control plane.
"""

from __future__ import annotations

import http.client
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"
JSON_TYPE = {"Content-Type": "application/json"}
KB_NAME = "ops-agent-runtime-kb"

AGENT = "ops-agent"
ALIAS = "ops-alias"
FLOW = "ops-flow"
FLOW_ALIAS = "ops-flow-alias"
INPUTS = [{"nodeName": "Input", "nodeOutputName": "question", "content": {"document": "hello"}}]


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "bedrock", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None, status: int = 200) -> dict:
    code, text = call(endpoint, method, path, payload)
    assert code == status, f"{method} {path} answered {code}: {text[:400]}"
    return json.loads(text or "{}")


def stream(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    code, headers, out = signed.request_bytes(
        endpoint, "bedrock", ACCOUNT, REGION, method, path, body, JSON_TYPE
    )
    return code, headers, out


def inline_agent_stream(endpoint: str, payload: dict):
    """`InvokeInlineAgent` shares `/agents/{id}` with `PrepareAgent`; the runtime host is the only tell."""
    url = urlsplit(endpoint)
    stamp = datetime.now(timezone.utc)
    data = json.dumps(payload).encode()
    headers = {
        "Host": f"bedrock-agent-runtime.{REGION}.amazonaws.com",
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={ACCOUNT}/{stamp:%Y%m%d}/{REGION}/bedrock"
            "/aws4_request, SignedHeaders=host, Signature=local"
        ),
        "x-amz-date": stamp.strftime("%Y%m%dT%H%M%SZ"),
        "Content-Type": "application/json",
        "Content-Length": str(len(data)),
    }
    connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=30)
    try:
        connection.request("POST", "/agents/ops-inline-session", body=data, headers=headers)
        response = connection.getresponse()
        return (
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            response.read(),
        )
    finally:
        connection.close()


def new_session(endpoint) -> str:
    created = ok(endpoint, "PUT", "/sessions/", {}, status=201)
    return created["sessionId"]


def ensure_knowledge_base(endpoint) -> str:
    listed = ok(endpoint, "POST", "/knowledgebases/", {})
    for item in listed.get("knowledgeBaseSummaries", []):
        if item.get("name") == KB_NAME:
            return item["knowledgeBaseId"]
    created = ok(
        endpoint,
        "PUT",
        "/knowledgebases/",
        {
            "name": KB_NAME,
            "roleArn": f"arn:aws:iam::{ACCOUNT}:role/ops-kb-role",
            "knowledgeBaseConfiguration": {
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": (
                        f"arn:aws:bedrock:{REGION}::foundation-model/"
                        "amazon.titan-embed-text-v1"
                    )
                },
            },
        },
        status=202,
    )
    return created["knowledgeBase"]["knowledgeBaseId"]


def start_flow_execution(endpoint) -> str:
    created = ok(
        endpoint,
        "POST",
        f"/flows/{FLOW}/aliases/{FLOW_ALIAS}/executions",
        {"inputs": INPUTS},
    )
    return created["executionArn"]


def execution_id(arn: str) -> str:
    return arn.rsplit("/", 1)[-1]


def test_invoke_agent_answers_an_eventstream(endpoint):
    code, headers, body = stream(
        endpoint,
        "POST",
        f"/agents/{AGENT}/agentAliases/{ALIAS}/sessions/ops-invoke-session/text",
        {"inputText": "hello"},
    )
    assert code == 200
    assert body
    assert headers.get("x-amz-bedrock-agent-session-id") == "ops-invoke-session"


def test_invoke_inline_agent_answers_an_eventstream(endpoint):
    code, headers, body = inline_agent_stream(
        endpoint,
        {"inputText": "hello", "foundationModel": MODEL},
    )
    assert code == 200
    assert body
    assert headers.get("x-amz-bedrock-agent-session-id") == "ops-inline-session"


def test_get_agent_memory_answers_a_memory_list(endpoint):
    answer = ok(
        endpoint,
        "GET",
        f"/agents/{AGENT}/agentAliases/{ALIAS}/memories?type=SESSION_SUMMARY",
    )
    assert isinstance(answer["memoryContents"], list)


def test_delete_agent_memory_answers_accepted(endpoint):
    code, _text = call(
        endpoint,
        "DELETE",
        f"/agents/{AGENT}/agentAliases/{ALIAS}/memories?type=SESSION_SUMMARY",
    )
    assert code == 202


def test_retrieve_searches_a_knowledge_base(endpoint):
    knowledge_base = ensure_knowledge_base(endpoint)
    answer = ok(
        endpoint,
        "POST",
        f"/knowledgebases/{knowledge_base}/retrieve",
        {"retrievalQuery": {"type": "TEXT", "text": "hello"}},
    )
    assert isinstance(answer["retrievalResults"], list)


def test_retrieve_and_generate_answers_text(endpoint):
    answer = ok(
        endpoint,
        "POST",
        "/retrieveAndGenerate",
        {"input": {"type": "TEXT", "text": "hello"}},
    )
    assert answer["output"]["text"]
    assert answer["sessionId"]


def test_retrieve_and_generate_stream_answers_an_eventstream(endpoint):
    code, _headers, body = stream(
        endpoint,
        "POST",
        "/retrieveAndGenerateStream",
        {"input": {"type": "TEXT", "text": "hello"}},
    )
    assert code == 200
    assert body


def test_rerank_scores_the_sources(endpoint):
    answer = ok(
        endpoint,
        "POST",
        "/rerank",
        {
            "queries": [{"type": "TEXT", "textQuery": {"text": "hello"}}],
            "sources": [
                {
                    "type": "INLINE",
                    "inlineDocumentSource": {
                        "type": "TEXT",
                        "textDocument": {"text": "hello"},
                    },
                }
            ],
        },
    )
    assert len(answer["results"]) == 1
    assert answer["results"][0]["relevanceScore"] is not None


def test_optimize_prompt_answers_an_eventstream(endpoint):
    code, _headers, body = stream(
        endpoint,
        "POST",
        "/optimize-prompt",
        {
            "input": {"textPrompt": {"text": "hello"}},
            "targetModelId": MODEL,
        },
    )
    assert code == 200
    assert body


def test_create_session_answers_an_arn(endpoint):
    created = ok(endpoint, "PUT", "/sessions/", {}, status=201)
    assert created["sessionId"]
    assert created["sessionArn"]
    assert created["sessionStatus"] == "ACTIVE"


def test_get_session_reads_it(endpoint):
    session = new_session(endpoint)
    answer = ok(endpoint, "GET", f"/sessions/{session}")
    assert answer["sessionId"] == session
    assert answer["sessionStatus"] == "ACTIVE"


def test_list_sessions_lists_them(endpoint):
    session = new_session(endpoint)
    answer = ok(endpoint, "POST", "/sessions/", {})
    assert session in {item["sessionId"] for item in answer["sessionSummaries"]}


def test_update_session_sets_metadata(endpoint):
    session = new_session(endpoint)
    ok(endpoint, "PUT", f"/sessions/{session}", {"sessionMetadata": {"stage": "ops"}})
    answer = ok(endpoint, "GET", f"/sessions/{session}")
    assert answer["sessionMetadata"] == {"stage": "ops"}


def test_end_session_marks_it_ended(endpoint):
    session = new_session(endpoint)
    answer = ok(endpoint, "PATCH", f"/sessions/{session}")
    assert answer["sessionStatus"] == "ENDED"


def test_delete_session_removes_it(endpoint):
    session = new_session(endpoint)
    ok(endpoint, "DELETE", f"/sessions/{session}")
    code, _text = call(endpoint, "GET", f"/sessions/{session}")
    assert code == 404


def test_create_invocation_answers_an_id(endpoint):
    session = new_session(endpoint)
    created = ok(
        endpoint,
        "PUT",
        f"/sessions/{session}/invocations",
        {"description": "ops invocation"},
        status=201,
    )
    assert created["invocationId"]


def test_list_invocations_lists_it(endpoint):
    session = new_session(endpoint)
    created = ok(
        endpoint,
        "PUT",
        f"/sessions/{session}/invocations",
        {"description": "ops invocation"},
        status=201,
    )
    answer = ok(endpoint, "POST", f"/sessions/{session}/invocations", {})
    assert created["invocationId"] in {
        item["invocationId"] for item in answer["invocationSummaries"]
    }


def test_put_invocation_step_answers_an_id(endpoint):
    session = new_session(endpoint)
    invocation = ok(
        endpoint, "PUT", f"/sessions/{session}/invocations", {"description": "ops"}, status=201
    )["invocationId"]
    created = ok(
        endpoint,
        "PUT",
        f"/sessions/{session}/invocationSteps",
        {
            "invocationIdentifier": invocation,
            "payload": {"contentBlocks": [{"text": "hello"}]},
        },
        status=201,
    )
    assert created["invocationStepId"]


def test_get_invocation_step_reads_it(endpoint):
    session = new_session(endpoint)
    invocation = ok(
        endpoint, "PUT", f"/sessions/{session}/invocations", {"description": "ops"}, status=201
    )["invocationId"]
    step = ok(
        endpoint,
        "PUT",
        f"/sessions/{session}/invocationSteps",
        {"invocationIdentifier": invocation},
        status=201,
    )["invocationStepId"]
    answer = ok(
        endpoint,
        "POST",
        f"/sessions/{session}/invocationSteps/{step}",
        {"invocationIdentifier": invocation},
    )
    assert answer["invocationStep"]["invocationStepId"] == step


def test_list_invocation_steps_lists_it(endpoint):
    session = new_session(endpoint)
    invocation = ok(
        endpoint, "PUT", f"/sessions/{session}/invocations", {"description": "ops"}, status=201
    )["invocationId"]
    step = ok(
        endpoint,
        "PUT",
        f"/sessions/{session}/invocationSteps",
        {"invocationIdentifier": invocation},
        status=201,
    )["invocationStepId"]
    answer = ok(
        endpoint,
        "POST",
        f"/sessions/{session}/invocationSteps",
        {"invocationIdentifier": invocation},
    )
    assert step in {
        item["invocationStepId"] for item in answer["invocationStepSummaries"]
    }


def test_invoke_flow_answers_an_eventstream(endpoint):
    code, headers, body = stream(
        endpoint,
        "POST",
        f"/flows/{FLOW}/aliases/{FLOW_ALIAS}",
        {"inputs": INPUTS},
    )
    assert code == 200
    assert body
    assert headers.get("x-amz-bedrock-flow-execution-id")


def test_start_flow_execution_answers_an_arn(endpoint):
    created = ok(
        endpoint,
        "POST",
        f"/flows/{FLOW}/aliases/{FLOW_ALIAS}/executions",
        {"inputs": INPUTS},
    )
    assert created["executionArn"]


def test_get_flow_execution_reads_it(endpoint):
    execution = start_flow_execution(endpoint)
    answer = ok(
        endpoint,
        "GET",
        f"/flows/{FLOW}/aliases/{FLOW_ALIAS}/executions/{execution_id(execution)}",
    )
    assert answer["executionArn"] == execution


def test_list_flow_executions_lists_it(endpoint):
    execution = start_flow_execution(endpoint)
    answer = ok(endpoint, "GET", f"/flows/{FLOW}/executions")
    assert execution in {
        item["executionArn"] for item in answer["flowExecutionSummaries"]
    }


def test_list_flow_execution_events_answers_a_list(endpoint):
    execution = start_flow_execution(endpoint)
    answer = ok(
        endpoint,
        "GET",
        f"/flows/{FLOW}/aliases/{FLOW_ALIAS}/executions/{execution_id(execution)}/events",
    )
    assert isinstance(answer["flowExecutionEvents"], list)


def test_get_execution_flow_snapshot_answers_a_definition(endpoint):
    execution = start_flow_execution(endpoint)
    answer = ok(
        endpoint,
        "GET",
        f"/flows/{FLOW}/aliases/{FLOW_ALIAS}/executions/{execution_id(execution)}/flowsnapshot",
    )
    assert answer["definition"]
    assert answer["flowIdentifier"] == FLOW


def test_stop_flow_execution_aborts_it(endpoint):
    execution = start_flow_execution(endpoint)
    answer = ok(
        endpoint,
        "POST",
        f"/flows/{FLOW}/aliases/{FLOW_ALIAS}/executions/{execution_id(execution)}/stop",
    )
    assert answer["status"] == "Aborted"
