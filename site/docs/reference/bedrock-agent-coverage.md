---
sidebar_position: 83
title: Bedrock Agent coverage
---

Every Bedrock Agent control-plane operation the emulator advertises, and what
Emuplane does with it. The service is REST/JSON on `/agents`, `/knowledgebases`,
`/flows`, `/prompts` and `/tags`, signed with the `bedrock` credential scope that
all four Bedrock planes share — the path is what picks this plane. There is no
console action: agents, knowledge bases, flows and prompts are driven over the wire.

Agents carry versions, aliases, action groups, collaborators and knowledge-base
associations, and `PrepareAgent` promotes the draft to `PREPARED`. The emulator
exposes no route that creates an agent version, so the three version operations
read and remove a record its own state restore would place. Knowledge bases carry
data sources, documents and ingestion jobs: `StartIngestionJob` reads the data
source's S3 bucket for real, and the job reports the counts it actually scanned,
indexed and failed rather than a fabricated success. Flows carry versions and
aliases and answer `ValidateFlowDefinition` and `PrepareFlow`; prompts carry
versions; and one tag surface spans every resource that has an ARN.

Every create is found by name before it is created, so a sweep reuses what the
last one left behind, and every delete action builds a resource of its own and
removes only that. The table is generated from the emulator's own operation list;
every row names the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **72**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **72**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **29**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **72** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateAgent` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListAgents` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetAgent` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateAgent` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteAgent` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `PrepareAgent` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListAgentVersions` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetAgentVersion` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteAgentVersion` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreateAgentAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListAgentAliases` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetAgentAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateAgentAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteAgentAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreateAgentActionGroup` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListAgentActionGroups` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetAgentActionGroup` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateAgentActionGroup` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteAgentActionGroup` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `AssociateAgentCollaborator` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListAgentCollaborators` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetAgentCollaborator` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateAgentCollaborator` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DisassociateAgentCollaborator` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `AssociateAgentKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListAgentKnowledgeBases` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetAgentKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateAgentKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DisassociateAgentKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreateKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListKnowledgeBases` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteKnowledgeBase` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetKnowledgeBaseDocuments` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteKnowledgeBaseDocuments` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `IngestKnowledgeBaseDocuments` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListKnowledgeBaseDocuments` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `StopIngestionJob` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetIngestionJob` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `StartIngestionJob` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListIngestionJobs` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreateDataSource` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListDataSources` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetDataSource` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateDataSource` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteDataSource` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreateFlow` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListFlows` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ValidateFlowDefinition` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetFlowVersion` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteFlowVersion` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreateFlowVersion` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListFlowVersions` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetFlowAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateFlowAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteFlowAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreateFlowAlias` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListFlowAliases` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetFlow` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdateFlow` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeleteFlow` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `PrepareFlow` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreatePrompt` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListPrompts` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `CreatePromptVersion` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `GetPrompt` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UpdatePrompt` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `DeletePrompt` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `TagResource` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `UntagResource` | — | not yet | tests/control/test_bedrock_agent_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_bedrock_agent_operations.py |

<!-- coverage:end -->
