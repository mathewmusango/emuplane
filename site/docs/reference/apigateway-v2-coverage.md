---
sidebar_position: 20
title: API Gateway v2 coverage
---

Every API Gateway v2 operation the emulator advertises, and what Emuplane does
with it. There is no console action: HTTP and WebSocket APIs, routes,
integrations, responses, stages, deployments, authorizers, domain names and
mappings are driven over the wire. The `@connections` trio needs a real upgraded
socket for a connection id to exist at all, so its tests live in
`test_apigateway_ws_operations.py`, run against a lab and skip in the HTTP-only
in-process stand-in.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **55**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **55**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **22**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **55** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateApi` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetApi` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetApis` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateApi` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteApi` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateRoute` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetRoute` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetRoutes` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateRoute` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteRoute` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateIntegration` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetIntegration` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetIntegrations` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateIntegration` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteIntegration` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateRouteResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetRouteResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetRouteResponses` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateRouteResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteRouteResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateIntegrationResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetIntegrationResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetIntegrationResponses` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateIntegrationResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteIntegrationResponse` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateStage` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetStage` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetStages` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateStage` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteStage` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateDeployment` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetDeployment` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetDeployments` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteDeployment` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateAuthorizer` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetAuthorizer` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetAuthorizers` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateAuthorizer` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteAuthorizer` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateDomainName` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetDomainName` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetDomainNames` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateDomainName` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteDomainName` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `CreateApiMapping` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetApiMapping` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetApiMappings` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UpdateApiMapping` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `DeleteApiMapping` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `TagResource` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `UntagResource` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `GetTags` | — | not yet | tests/control/test_apigateway_v2_operations.py |
| `PostToConnection` | — | not yet | tests/control/test_apigateway_ws_operations.py |
| `GetConnection` | — | not yet | tests/control/test_apigateway_ws_operations.py |
| `DeleteConnection` | — | not yet | tests/control/test_apigateway_ws_operations.py |

<!-- coverage:end -->
