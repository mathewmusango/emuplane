---
sidebar_position: 80
title: Glue coverage
---

Every Glue operation the emulator advertises, and what Emuplane does with it.
Requests are JSON with an `X-Amz-Target` naming the action, signed with the `glue`
credential scope; there is no console action.

The Data Catalog is the book of record: databases, tables, partitions, column
statistics and partition indexes. Crawlers, jobs, triggers, workflows,
connections, classifiers and security configurations are control-plane records — a
crawler finishes after five seconds, a Spark job without Docker succeeds at once,
and a shell job whose script resolves to a Python file really runs it, so the stop
test uploads a script that sleeps.

Table optimizers follow a real-AWS capture: creating one needs a storage location
and an Iceberg `metadata_location` parameter, and with `AUTH=true` the optimizer
role must allow `glue:GetTable` and the location's bucket, so the suite creates an
IAM role with that inline policy (the in-process stand-in skips the check). Delete
tests create their own resource; stable records are restored by their update tests.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **83**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **83**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **31**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **83** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateDatabase` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteDatabase` | — | not yet | tests/control/test_glue_operations.py |
| `GetDatabase` | — | not yet | tests/control/test_glue_operations.py |
| `GetDatabases` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateDatabase` | — | not yet | tests/control/test_glue_operations.py |
| `CreateTable` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteTable` | — | not yet | tests/control/test_glue_operations.py |
| `GetTable` | — | not yet | tests/control/test_glue_operations.py |
| `GetTables` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateTable` | — | not yet | tests/control/test_glue_operations.py |
| `BatchDeleteTable` | — | not yet | tests/control/test_glue_operations.py |
| `CreatePartition` | — | not yet | tests/control/test_glue_operations.py |
| `DeletePartition` | — | not yet | tests/control/test_glue_operations.py |
| `GetPartition` | — | not yet | tests/control/test_glue_operations.py |
| `GetPartitions` | — | not yet | tests/control/test_glue_operations.py |
| `BatchCreatePartition` | — | not yet | tests/control/test_glue_operations.py |
| `BatchGetPartition` | — | not yet | tests/control/test_glue_operations.py |
| `BatchDeletePartition` | — | not yet | tests/control/test_glue_operations.py |
| `CreatePartitionIndex` | — | not yet | tests/control/test_glue_operations.py |
| `GetPartitionIndexes` | — | not yet | tests/control/test_glue_operations.py |
| `GetColumnStatisticsForTable` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateColumnStatisticsForTable` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteColumnStatisticsForTable` | — | not yet | tests/control/test_glue_operations.py |
| `GetColumnStatisticsForPartition` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateColumnStatisticsForPartition` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteColumnStatisticsForPartition` | — | not yet | tests/control/test_glue_operations.py |
| `CreateConnection` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteConnection` | — | not yet | tests/control/test_glue_operations.py |
| `GetConnection` | — | not yet | tests/control/test_glue_operations.py |
| `GetConnections` | — | not yet | tests/control/test_glue_operations.py |
| `CreateCrawler` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteCrawler` | — | not yet | tests/control/test_glue_operations.py |
| `GetCrawler` | — | not yet | tests/control/test_glue_operations.py |
| `GetCrawlers` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateCrawler` | — | not yet | tests/control/test_glue_operations.py |
| `StartCrawler` | — | not yet | tests/control/test_glue_operations.py |
| `StopCrawler` | — | not yet | tests/control/test_glue_operations.py |
| `GetCrawlerMetrics` | — | not yet | tests/control/test_glue_operations.py |
| `CreateJob` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteJob` | — | not yet | tests/control/test_glue_operations.py |
| `GetJob` | — | not yet | tests/control/test_glue_operations.py |
| `GetJobs` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateJob` | — | not yet | tests/control/test_glue_operations.py |
| `StartJobRun` | — | not yet | tests/control/test_glue_operations.py |
| `GetJobRun` | — | not yet | tests/control/test_glue_operations.py |
| `GetJobRuns` | — | not yet | tests/control/test_glue_operations.py |
| `BatchStopJobRun` | — | not yet | tests/control/test_glue_operations.py |
| `CreateTrigger` | — | not yet | tests/control/test_glue_operations.py |
| `GetTrigger` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteTrigger` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateTrigger` | — | not yet | tests/control/test_glue_operations.py |
| `StartTrigger` | — | not yet | tests/control/test_glue_operations.py |
| `StopTrigger` | — | not yet | tests/control/test_glue_operations.py |
| `ListTriggers` | — | not yet | tests/control/test_glue_operations.py |
| `BatchGetTriggers` | — | not yet | tests/control/test_glue_operations.py |
| `GetTriggers` | — | not yet | tests/control/test_glue_operations.py |
| `CreateWorkflow` | — | not yet | tests/control/test_glue_operations.py |
| `GetWorkflow` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteWorkflow` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateWorkflow` | — | not yet | tests/control/test_glue_operations.py |
| `StartWorkflowRun` | — | not yet | tests/control/test_glue_operations.py |
| `CreateUserDefinedFunction` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateUserDefinedFunction` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteUserDefinedFunction` | — | not yet | tests/control/test_glue_operations.py |
| `GetUserDefinedFunction` | — | not yet | tests/control/test_glue_operations.py |
| `GetUserDefinedFunctions` | — | not yet | tests/control/test_glue_operations.py |
| `CreateSecurityConfiguration` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteSecurityConfiguration` | — | not yet | tests/control/test_glue_operations.py |
| `GetSecurityConfiguration` | — | not yet | tests/control/test_glue_operations.py |
| `GetSecurityConfigurations` | — | not yet | tests/control/test_glue_operations.py |
| `CreateClassifier` | — | not yet | tests/control/test_glue_operations.py |
| `GetClassifier` | — | not yet | tests/control/test_glue_operations.py |
| `GetClassifiers` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteClassifier` | — | not yet | tests/control/test_glue_operations.py |
| `CreateTableOptimizer` | — | not yet | tests/control/test_glue_operations.py |
| `GetTableOptimizer` | — | not yet | tests/control/test_glue_operations.py |
| `UpdateTableOptimizer` | — | not yet | tests/control/test_glue_operations.py |
| `DeleteTableOptimizer` | — | not yet | tests/control/test_glue_operations.py |
| `BatchGetTableOptimizer` | — | not yet | tests/control/test_glue_operations.py |
| `ListTableOptimizerRuns` | — | not yet | tests/control/test_glue_operations.py |
| `TagResource` | — | not yet | tests/control/test_glue_operations.py |
| `UntagResource` | — | not yet | tests/control/test_glue_operations.py |
| `GetTags` | — | not yet | tests/control/test_glue_operations.py |

<!-- coverage:end -->
