---
sidebar_position: 82
title: Amazon Bedrock coverage
---

Every Amazon Bedrock control-plane operation the emulator advertises, and what
Emuplane does with it. All four Bedrock planes sign with the `bedrock` credential
scope and the path picks the plane, so the control plane here is the one behind
`/foundation-models`, `/inference-profiles`, `/guardrails`, `/custom-models`,
`/imported-models`, `/provisioned-model-throughput`, the job families,
`/marketplace-model/endpoints`, `/prompt-routers`, `/logging/modelinvocations`,
`/use-case-for-model-access` and the three tag paths. There is no console
action: every operation is made over the wire.

The foundation-model catalog, inference profiles, guardrail versions, custom and
imported models, provisioned throughput, the five job families (customization,
import, copy, invocation and evaluation), marketplace model endpoints, prompt
routers, the per-region logging configuration and the model-access use case are
deterministic records. A create answers an id or an ARN, a read returns the
record, and a delete is proven by the `404` that follows it; no model is trained
or served, so a job settles `InProgress` and a stop moves it to `Stopped`.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **66**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **66**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **31**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **66** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `ListFoundationModels` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetFoundationModel` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetFoundationModelAvailability` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateFoundationModelAgreement` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteFoundationModelAgreement` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListFoundationModelAgreementOffers` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListInferenceProfiles` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateInferenceProfile` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetInferenceProfile` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteInferenceProfile` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListGuardrails` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateGuardrail` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetGuardrail` | — | not yet | tests/control/test_bedrock_operations.py |
| `UpdateGuardrail` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteGuardrail` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateGuardrailVersion` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListCustomModels` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateCustomModel` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetCustomModel` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteCustomModel` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListImportedModels` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetImportedModel` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteImportedModel` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateProvisionedModelThroughput` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListProvisionedModelThroughputs` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetProvisionedModelThroughput` | — | not yet | tests/control/test_bedrock_operations.py |
| `UpdateProvisionedModelThroughput` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteProvisionedModelThroughput` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateModelCustomizationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListModelCustomizationJobs` | — | not yet | tests/control/test_bedrock_operations.py |
| `StopModelCustomizationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetModelCustomizationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateModelImportJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListModelImportJobs` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetModelImportJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateModelCopyJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListModelCopyJobs` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetModelCopyJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateModelInvocationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListModelInvocationJobs` | — | not yet | tests/control/test_bedrock_operations.py |
| `StopModelInvocationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetModelInvocationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateEvaluationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListEvaluationJobs` | — | not yet | tests/control/test_bedrock_operations.py |
| `BatchDeleteEvaluationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `StopEvaluationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetEvaluationJob` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreateMarketplaceModelEndpoint` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListMarketplaceModelEndpoints` | — | not yet | tests/control/test_bedrock_operations.py |
| `RegisterMarketplaceModelEndpoint` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeregisterMarketplaceModelEndpoint` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetMarketplaceModelEndpoint` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteMarketplaceModelEndpoint` | — | not yet | tests/control/test_bedrock_operations.py |
| `UpdateMarketplaceModelEndpoint` | — | not yet | tests/control/test_bedrock_operations.py |
| `CreatePromptRouter` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListPromptRouters` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetPromptRouter` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeletePromptRouter` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetModelInvocationLoggingConfiguration` | — | not yet | tests/control/test_bedrock_operations.py |
| `PutModelInvocationLoggingConfiguration` | — | not yet | tests/control/test_bedrock_operations.py |
| `DeleteModelInvocationLoggingConfiguration` | — | not yet | tests/control/test_bedrock_operations.py |
| `GetUseCaseForModelAccess` | — | not yet | tests/control/test_bedrock_operations.py |
| `PutUseCaseForModelAccess` | — | not yet | tests/control/test_bedrock_operations.py |
| `TagResource` | — | not yet | tests/control/test_bedrock_operations.py |
| `UntagResource` | — | not yet | tests/control/test_bedrock_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_bedrock_operations.py |

<!-- coverage:end -->
