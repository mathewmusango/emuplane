---
sidebar_position: 78
title: Athena coverage
---

Every Athena operation the emulator advertises, and what Emuplane does with it.
Requests are JSON with an `X-Amz-Target` naming the action, signed with the
`athena` credential scope. There is no console action.

A query needs a result location, so the suite creates an S3 bucket and points
`ResultConfiguration.OutputLocation` at it; the emulator runs the statement with
DuckDB when it is installed and answers deterministic mock results otherwise, then
writes the CSV to S3. Databases and table metadata come from the Glue Data Catalog,
which the suite creates under the `glue` scope. A stable workgroup carries the read,
update and tag rows; delete actions make their own workgroup, named query, data
catalog or prepared statement.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **32**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **32**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **16**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **32** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `StartQueryExecution` | — | not yet | tests/control/test_athena_operations.py |
| `GetQueryExecution` | — | not yet | tests/control/test_athena_operations.py |
| `GetQueryResults` | — | not yet | tests/control/test_athena_operations.py |
| `StopQueryExecution` | — | not yet | tests/control/test_athena_operations.py |
| `ListQueryExecutions` | — | not yet | tests/control/test_athena_operations.py |
| `BatchGetQueryExecution` | — | not yet | tests/control/test_athena_operations.py |
| `CreateWorkGroup` | — | not yet | tests/control/test_athena_operations.py |
| `DeleteWorkGroup` | — | not yet | tests/control/test_athena_operations.py |
| `GetWorkGroup` | — | not yet | tests/control/test_athena_operations.py |
| `ListWorkGroups` | — | not yet | tests/control/test_athena_operations.py |
| `UpdateWorkGroup` | — | not yet | tests/control/test_athena_operations.py |
| `CreateNamedQuery` | — | not yet | tests/control/test_athena_operations.py |
| `DeleteNamedQuery` | — | not yet | tests/control/test_athena_operations.py |
| `GetNamedQuery` | — | not yet | tests/control/test_athena_operations.py |
| `ListNamedQueries` | — | not yet | tests/control/test_athena_operations.py |
| `BatchGetNamedQuery` | — | not yet | tests/control/test_athena_operations.py |
| `CreateDataCatalog` | — | not yet | tests/control/test_athena_operations.py |
| `GetDataCatalog` | — | not yet | tests/control/test_athena_operations.py |
| `ListDataCatalogs` | — | not yet | tests/control/test_athena_operations.py |
| `DeleteDataCatalog` | — | not yet | tests/control/test_athena_operations.py |
| `UpdateDataCatalog` | — | not yet | tests/control/test_athena_operations.py |
| `CreatePreparedStatement` | — | not yet | tests/control/test_athena_operations.py |
| `GetPreparedStatement` | — | not yet | tests/control/test_athena_operations.py |
| `DeletePreparedStatement` | — | not yet | tests/control/test_athena_operations.py |
| `ListPreparedStatements` | — | not yet | tests/control/test_athena_operations.py |
| `GetDatabase` | — | not yet | tests/control/test_athena_operations.py |
| `ListDatabases` | — | not yet | tests/control/test_athena_operations.py |
| `GetTableMetadata` | — | not yet | tests/control/test_athena_operations.py |
| `ListTableMetadata` | — | not yet | tests/control/test_athena_operations.py |
| `TagResource` | — | not yet | tests/control/test_athena_operations.py |
| `UntagResource` | — | not yet | tests/control/test_athena_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_athena_operations.py |

<!-- coverage:end -->
