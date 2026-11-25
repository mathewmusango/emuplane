---
sidebar_position: 69
title: Bedrock Runtime coverage
---

Every Bedrock Runtime operation the emulator advertises, and what Emuplane does with
it. The service is REST/JSON on `/model/{modelId}`, `/guardrail/…` and
`/async-invoke`, signed with the `bedrock-runtime` credential scope. There is no
console action: conversations, invocations and guardrail assessments are made over
the wire.

Model calls answer a deterministic, family-aware mock reply unless
`MINISTACK_BEDROCK_PROXY_URL` points at an OpenAI-compatible endpoint such as Ollama
or vLLM, so the tests assert the wire shape rather than model output. Both streaming
operations answer a real eventstream. `ApplyGuardrail` needs a guardrail, created
through the Bedrock control plane; the async-invoke operations keep the invocation
readable after `StartAsyncInvoke` returns.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **8**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **8**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **2**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **8** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `Converse` | — | not yet | tests/control/test_bedrock_runtime_operations.py |
| `ConverseStream` | — | not yet | tests/control/test_bedrock_runtime_operations.py |
| `InvokeModel` | — | not yet | tests/control/test_bedrock_runtime_operations.py |
| `InvokeModelWithResponseStream` | — | not yet | tests/control/test_bedrock_runtime_operations.py |
| `ApplyGuardrail` | — | not yet | tests/control/test_bedrock_runtime_operations.py |
| `StartAsyncInvoke` | — | not yet | tests/control/test_bedrock_runtime_operations.py |
| `GetAsyncInvoke` | — | not yet | tests/control/test_bedrock_runtime_operations.py |
| `ListAsyncInvokes` | — | not yet | tests/control/test_bedrock_runtime_operations.py |

<!-- coverage:end -->
