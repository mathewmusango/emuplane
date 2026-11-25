---
sidebar_position: 71
title: Bedrock AgentCore coverage
---

Every Bedrock AgentCore operation the emulator advertises, and what Emuplane does
with it. Two planes share the `bedrock-agentcore` credential scope and one module:
the control plane manages runtimes, runtime endpoints, resource policies and
memories, and the data plane invokes a runtime and drives memory events, actors,
sessions and records. There is no console action.

A runtime and its memory provision instantly and settle to `READY`/`ACTIVE`;
`InvokeAgentRuntime` answers a deterministic echo unless the runtime names a
container image and Docker is available. Memory retrieval is lexical — no
embeddings — and extraction never runs, so `StartMemoryExtractionJob` can only
answer `ResourceNotFound` for a job id that no extraction created. Delete tests
create a resource of their own.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **35**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **35**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **15**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **35** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateAgentRuntime` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `GetAgentRuntime` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListAgentRuntimes` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `UpdateAgentRuntime` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `DeleteAgentRuntime` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListAgentRuntimeVersions` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `CreateAgentRuntimeEndpoint` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `GetAgentRuntimeEndpoint` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListAgentRuntimeEndpoints` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `UpdateAgentRuntimeEndpoint` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `DeleteAgentRuntimeEndpoint` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `CreateMemory` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `GetMemory` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListMemories` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `UpdateMemory` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `DeleteMemory` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `PutResourcePolicy` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `GetResourcePolicy` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `DeleteResourcePolicy` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `InvokeAgentRuntime` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `CreateEvent` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `GetEvent` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListEvents` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `DeleteEvent` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListActors` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListSessions` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `BatchCreateMemoryRecords` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `BatchUpdateMemoryRecords` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `BatchDeleteMemoryRecords` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `GetMemoryRecord` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListMemoryRecords` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `DeleteMemoryRecord` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `RetrieveMemoryRecords` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `StartMemoryExtractionJob` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |
| `ListMemoryExtractionJobs` | — | not yet | tests/control/test_bedrock_agentcore_operations.py |

<!-- coverage:end -->
