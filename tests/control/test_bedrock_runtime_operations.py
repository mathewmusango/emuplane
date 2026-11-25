"""Bedrock Runtime on the wire: all 8 advertised operations, REST/JSON.

Signed with `bedrock-runtime`. Model invocation falls back to a deterministic
mock reply when `MINISTACK_BEDROCK_PROXY_URL` is unset, so the tests assert the
wire shape rather than model output. `ApplyGuardrail` uses a guardrail created
through the Bedrock control plane.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"
JSON_TYPE = {"Content-Type": "application/json"}
GUARDRAIL = "ops-guardrail"


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "bedrock-runtime", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status == 200, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def stream(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    status, headers, out = signed.request_bytes(endpoint, "bedrock-runtime", ACCOUNT, REGION, method, path, body, JSON_TYPE)
    return status, headers, out


def ensure_guardrail(endpoint) -> str:
    create = {
        "name": GUARDRAIL,
        "blockedInputMessaging": "blocked input",
        "blockedOutputsMessaging": "blocked output",
    }
    body = json.dumps(create)
    status, text = signed.request(endpoint, "bedrock", ACCOUNT, REGION, "POST", "/guardrails", body, JSON_TYPE)
    if status in (200, 202):
        return json.loads(text)["guardrailId"]
    listed = signed.request(endpoint, "bedrock", ACCOUNT, REGION, "GET", "/guardrails", "", JSON_TYPE)
    status, text = listed
    assert status == 200, text[:300]
    for item in json.loads(text or "{}").get("guardrails", []):
        if item.get("name") == GUARDRAIL:
            return item["id"]
    raise AssertionError(f"guardrail {GUARDRAIL} not found")


CONVERSE = {"messages": [{"role": "user", "content": [{"text": "hello"}]}]}
INVOKE = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 16,
    "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
}


def test_converse_answers_a_message(endpoint):
    answer = ok(endpoint, "POST", f"/model/{MODEL}/converse", CONVERSE)
    assert answer["output"]["message"]["role"] == "assistant"
    assert answer["output"]["message"]["content"]


def test_converse_stream_answers_an_eventstream(endpoint):
    status, _headers, body = stream(endpoint, "POST", f"/model/{MODEL}/converse-stream", CONVERSE)
    assert status == 200
    assert body


def test_invoke_model_answers_a_body(endpoint):
    answer = ok(endpoint, "POST", f"/model/{MODEL}/invoke", INVOKE)
    assert isinstance(answer, dict)


def test_invoke_model_with_response_stream_answers_an_eventstream(endpoint):
    status, _headers, body = stream(endpoint, "POST", f"/model/{MODEL}/invoke-with-response-stream", INVOKE)
    assert status == 200
    assert body


def test_apply_guardrail_answers_an_assessment(endpoint):
    guardrail = ensure_guardrail(endpoint)
    answer = ok(
        endpoint,
        "POST",
        f"/guardrail/{guardrail}/version/DRAFT/apply",
        {"source": "INPUT", "content": [{"text": {"text": "hello"}}]},
    )
    assert "action" in answer


def test_start_async_invoke_answers_an_invocation_arn(endpoint):
    created = ok(
        endpoint,
        "POST",
        "/async-invoke",
        {
            "modelId": MODEL,
            "modelInput": {"prompt": "hello"},
            "outputDataConfig": {"s3OutputDataConfig": {"s3Uri": "s3://ops-bucket/out"}},
        },
    )
    assert created["invocationArn"]


def test_get_async_invoke_reads_the_invocation(endpoint):
    created = ok(
        endpoint,
        "POST",
        "/async-invoke",
        {
            "modelId": MODEL,
            "modelInput": {"prompt": "hello"},
            "outputDataConfig": {"s3OutputDataConfig": {"s3Uri": "s3://ops-bucket/out"}},
        },
    )
    got = ok(endpoint, "GET", f"/async-invoke/{created['invocationArn']}")
    assert got["invocationArn"] == created["invocationArn"]


def test_list_async_invokes_lists_the_invocation(endpoint):
    created = ok(
        endpoint,
        "POST",
        "/async-invoke",
        {
            "modelId": MODEL,
            "modelInput": {"prompt": "hello"},
            "outputDataConfig": {"s3OutputDataConfig": {"s3Uri": "s3://ops-bucket/out"}},
        },
    )
    listed = ok(endpoint, "GET", "/async-invoke")
    assert created["invocationArn"] in {item["invocationArn"] for item in listed["asyncInvokeSummaries"]}
