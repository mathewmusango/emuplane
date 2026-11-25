---
sidebar_position: 70
title: Bedrock Agent Runtime coverage
---

Every Bedrock Agent Runtime operation the emulator advertises, and what Emuplane does
with it. The service is REST/JSON on `/agents`, `/knowledgebases`, `/sessions`,
`/flows` and the query, rerank and prompt routes. There is no console action:
agents, sessions and flows are driven over the wire.

All four Bedrock planes sign with the `bedrock` credential scope, so the caller is
identified by path — the same disambiguation the emulator's router performs.
Agent, inline-agent, retrieval-and-generate-stream and prompt-optimization calls
answer real eventstreams; the replies themselves are deterministic mocks.
`Retrieve` searches the documents a knowledge base holds, and needs a knowledge
base created through the Bedrock Agent control plane. Sessions, invocations,
invocation steps and flow executions are records that keep their identifiers.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **27**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **27**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **10**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **27** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `InvokeAgent` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `InvokeInlineAgent` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `GetAgentMemory` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `DeleteAgentMemory` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `Retrieve` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `RetrieveAndGenerate` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `RetrieveAndGenerateStream` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `Rerank` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `CreateSession` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `GetSession` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `UpdateSession` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `DeleteSession` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `EndSession` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `ListSessions` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `CreateInvocation` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `ListInvocations` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `PutInvocationStep` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `GetInvocationStep` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `ListInvocationSteps` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `InvokeFlow` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `StartFlowExecution` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `StopFlowExecution` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `GetFlowExecution` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `ListFlowExecutions` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `ListFlowExecutionEvents` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `GetExecutionFlowSnapshot` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |
| `OptimizePrompt` | — | not yet | tests/control/test_bedrock_agent_runtime_operations.py |

<!-- coverage:end -->
