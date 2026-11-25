---
sidebar_position: 83
title: CloudFront KeyValueStore coverage
---

Every CloudFront KeyValueStore data-plane operation the emulator advertises, and what
Emuplane does with it. A separate `cloudfront-keyvaluestore` SDK service (REST/JSON,
signing name `cloudfront-keyvaluestore`); the store itself is created on the
management plane, and both planes share it by ARN.

Every mutating call sends `If-Match` with the `ETag` the previous read answered, and
the suite re-reads it before each write because one write invalidates it. `UpdateKeys`
is atomic: the whole batch is validated before anything is stored.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **6**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **6**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **3**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **6** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `DescribeKeyValueStore` | — | not yet | tests/control/test_cloudfront_kvs_operations.py |
| `ListKeys` | — | not yet | tests/control/test_cloudfront_kvs_operations.py |
| `GetKey` | — | not yet | tests/control/test_cloudfront_kvs_operations.py |
| `PutKey` | — | not yet | tests/control/test_cloudfront_kvs_operations.py |
| `DeleteKey` | — | not yet | tests/control/test_cloudfront_kvs_operations.py |
| `UpdateKeys` | — | not yet | tests/control/test_cloudfront_kvs_operations.py |

<!-- coverage:end -->
