---
sidebar_position: 21
title: AppSync coverage
---

Every AppSync control-plane operation the emulator advertises, and what Emuplane
does with it: GraphQL APIs, API keys, data sources, resolvers, functions, types,
schema, environment variables, caching, code evaluation and tags, plus the Event
API and channel-namespace management calls. There is no console action.

The row also names `HTTP Publish` and `WebSocket subscribe/publish`; those are
data-plane behaviours, not callable operations, so they are not counted here.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **55**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **55**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **21**
- Operations with no emuplane test: **0**

- Group: **Extended** · operations: **55** · Console actions: **0**





## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateGraphQLApi` | — | not yet | tests/control/test_appsync_operations.py |
| `GetGraphQLApi` | — | not yet | tests/control/test_appsync_operations.py |
| `ListGraphQLApis` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateGraphQLApi` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteGraphQLApi` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateApiKey` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateApiKey` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteApiKey` | — | not yet | tests/control/test_appsync_operations.py |
| `ListApiKeys` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateDataSource` | — | not yet | tests/control/test_appsync_operations.py |
| `GetDataSource` | — | not yet | tests/control/test_appsync_operations.py |
| `ListDataSources` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateDataSource` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteDataSource` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateResolver` | — | not yet | tests/control/test_appsync_operations.py |
| `GetResolver` | — | not yet | tests/control/test_appsync_operations.py |
| `ListResolvers` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateResolver` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteResolver` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateFunction` | — | not yet | tests/control/test_appsync_operations.py |
| `GetFunction` | — | not yet | tests/control/test_appsync_operations.py |
| `ListFunctions` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateFunction` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteFunction` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateType` | — | not yet | tests/control/test_appsync_operations.py |
| `GetType` | — | not yet | tests/control/test_appsync_operations.py |
| `ListTypes` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateType` | — | not yet | tests/control/test_appsync_operations.py |
| `StartSchemaCreation` | — | not yet | tests/control/test_appsync_operations.py |
| `GetSchemaCreationStatus` | — | not yet | tests/control/test_appsync_operations.py |
| `GetIntrospectionSchema` | — | not yet | tests/control/test_appsync_operations.py |
| `PutGraphqlApiEnvironmentVariables` | — | not yet | tests/control/test_appsync_operations.py |
| `GetGraphqlApiEnvironmentVariables` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateApiCache` | — | not yet | tests/control/test_appsync_operations.py |
| `GetApiCache` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateApiCache` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteApiCache` | — | not yet | tests/control/test_appsync_operations.py |
| `FlushApiCache` | — | not yet | tests/control/test_appsync_operations.py |
| `EvaluateCode` | — | not yet | tests/control/test_appsync_operations.py |
| `TagResource` | — | not yet | tests/control/test_appsync_operations.py |
| `UntagResource` | — | not yet | tests/control/test_appsync_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateApi` | — | not yet | tests/control/test_appsync_operations.py |
| `GetApi` | — | not yet | tests/control/test_appsync_operations.py |
| `ListApis` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateApi` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteApi` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateChannelNamespace` | — | not yet | tests/control/test_appsync_operations.py |
| `GetChannelNamespace` | — | not yet | tests/control/test_appsync_operations.py |
| `ListChannelNamespaces` | — | not yet | tests/control/test_appsync_operations.py |
| `UpdateChannelNamespace` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteChannelNamespace` | — | not yet | tests/control/test_appsync_operations.py |
| `CreateApiKey` | — | not yet | tests/control/test_appsync_operations.py |
| `ListApiKeys` | — | not yet | tests/control/test_appsync_operations.py |
| `DeleteApiKey` | — | not yet | tests/control/test_appsync_operations.py |

<!-- coverage:end -->
