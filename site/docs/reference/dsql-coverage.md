---
sidebar_position: 77
title: Aurora DSQL coverage
---

Every Aurora DSQL operation the emulator advertises, and what Emuplane does with it.
The API is REST-JSON routed on method + path and signed with the `dsql` credential
scope. There is no console action.

Unless `DSQL_STRICT=1` and Docker are available, a cluster is metadata-only and
`ACTIVE` at creation — nothing listens on its port — so the tests need no backend.
Cluster policies carry a version; a CDC stream targets a Kinesis stream, which the
test creates under the `kinesis` scope, and with `AUTH=true` the target role must
exist in IAM, so the test creates that too. Nothing is delivered to the stream.
Stable names carry the read and update rows; delete actions make their own cluster
or stream.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **16**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **16**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **7**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **16** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateCluster` | — | not yet | tests/control/test_dsql_operations.py |
| `GetCluster` | — | not yet | tests/control/test_dsql_operations.py |
| `UpdateCluster` | — | not yet | tests/control/test_dsql_operations.py |
| `DeleteCluster` | — | not yet | tests/control/test_dsql_operations.py |
| `ListClusters` | — | not yet | tests/control/test_dsql_operations.py |
| `PutClusterPolicy` | — | not yet | tests/control/test_dsql_operations.py |
| `GetClusterPolicy` | — | not yet | tests/control/test_dsql_operations.py |
| `DeleteClusterPolicy` | — | not yet | tests/control/test_dsql_operations.py |
| `CreateStream` | — | not yet | tests/control/test_dsql_operations.py |
| `GetStream` | — | not yet | tests/control/test_dsql_operations.py |
| `ListStreams` | — | not yet | tests/control/test_dsql_operations.py |
| `DeleteStream` | — | not yet | tests/control/test_dsql_operations.py |
| `GetVpcEndpointServiceName` | — | not yet | tests/control/test_dsql_operations.py |
| `TagResource` | — | not yet | tests/control/test_dsql_operations.py |
| `UntagResource` | — | not yet | tests/control/test_dsql_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_dsql_operations.py |

<!-- coverage:end -->
