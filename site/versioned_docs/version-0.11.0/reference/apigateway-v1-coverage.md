---
sidebar_position: 19
title: API Gateway v1 coverage
---

Every API Gateway v1 (REST API) operation the emulator advertises, and what
Emuplane does with it. There is no console action: REST APIs, resources, methods,
integrations, deployments, stages, authorizers, keys, plans, domains and validators
are driven over the wire, and every advertised operation is exercised by the API
tests.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **87**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **87**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **33**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **87** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateRestApi` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetRestApi` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetRestApis` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateRestApi` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteRestApi` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `PutRestApi` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateResource` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetResource` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetResources` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateResource` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteResource` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `PutMethod` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetMethod` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteMethod` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateMethod` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `PutMethodResponse` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetMethodResponse` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteMethodResponse` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `PutIntegration` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetIntegration` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteIntegration` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateIntegration` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `PutIntegrationResponse` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetIntegrationResponse` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteIntegrationResponse` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateDeployment` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetDeployment` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetDeployments` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateDeployment` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteDeployment` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateStage` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetStage` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetStages` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateStage` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteStage` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateAuthorizer` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetAuthorizer` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetAuthorizers` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateAuthorizer` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteAuthorizer` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateModel` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetModel` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetModels` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteModel` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateDocumentationPart` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetDocumentationPart` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetDocumentationParts` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateDocumentationPart` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteDocumentationPart` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateApiKey` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetApiKey` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetApiKeys` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateApiKey` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteApiKey` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateUsagePlan` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetUsagePlan` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetUsagePlans` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateUsagePlan` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteUsagePlan` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateUsagePlanKey` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetUsagePlanKeys` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteUsagePlanKey` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateDomainName` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetDomainName` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetDomainNames` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteDomainName` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateDomainNameAccessAssociation` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetDomainNameAccessAssociations` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteDomainNameAccessAssociation` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `RejectDomainNameAccessAssociation` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GenerateClientCertificate` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetClientCertificate` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetClientCertificates` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateClientCertificate` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteClientCertificate` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateBasePathMapping` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetBasePathMapping` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetBasePathMappings` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteBasePathMapping` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `TagResource` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UntagResource` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetTags` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `CreateRequestValidator` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetRequestValidators` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `GetRequestValidator` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `UpdateRequestValidator` | — | not yet | tests/control/test_apigateway_v1_operations.py |
| `DeleteRequestValidator` | — | not yet | tests/control/test_apigateway_v1_operations.py |

<!-- coverage:end -->
