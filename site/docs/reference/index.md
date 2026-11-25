---
sidebar_position: 1
title: Reference
---

What the console can do, operation by operation; the settings it reads; and what it
deliberately does not do. Every coverage page is generated from the emulator's own
operation list, so a service that answers APIs gets a page here rather than a promise.

**This index is the map.** One row per service, grouped the way the emulator groups
them, and one page behind each row. The sidebar does not list the services: a list
that grows a line per service is a list nobody reads at 90 entries, and a table with
counts answers the same question better. Jump to a group: [Core](#core) ·
[Extended](#extended) · [Infrastructure](#infrastructure) ·
[CloudFormation](#cloudformation).

Two rules shape the pages. A page counts only what the emulator **advertises**, and
every operation it counts names the test behind it — a service with an operation and
no test shows up as untested here rather than being quietly omitted. A new service is
a `coverage/<service>.json` ledger, a page with `coverage:begin`/`coverage:end`
markers, and the tests the ledger names.

This index is generated from `coverage/*.json` by the same script that renders the
pages, so adding a service never means editing it by hand.

```bash
npm run coverage   # regenerates the index and every service page
```

<!-- coverage-index:begin -->

**10 services** · 236 operations · 216 tested · 0 blocked. Each page names the test behind every operation it counts.

### Core {#core}

| Service | Operations | Tested | Blocked | Page |
| --- | ---: | ---: | ---: | --- |
| IAM | 98 | 98 | 0 | [iam-coverage](iam-coverage.md) |
| S3 | 84 | 84 | 0 | [s3-coverage](s3-coverage.md) |
| STS | 5 | 5 | 0 | [sts-coverage](sts-coverage.md) |

### Infrastructure {#infrastructure}

| Service | Operations | Tested | Blocked | Page |
| --- | ---: | ---: | ---: | --- |
| Account | 4 | 4 | 0 | [account-coverage](account-coverage.md) |
| S3 Files | 21 | 1 | 0 | [s3-files-coverage](s3-files-coverage.md) |

### CloudFormation {#cloudformation}

| Service | Operations | Tested | Blocked | Page |
| --- | ---: | ---: | ---: | --- |
| Change Sets | 5 | 5 | 0 | [change-sets-coverage](change-sets-coverage.md) |
| Drift Detection | 4 | 4 | 0 | [drift-detection-coverage](drift-detection-coverage.md) |
| Exports | 1 | 1 | 0 | [exports-coverage](exports-coverage.md) |
| Stack Operations | 12 | 12 | 0 | [stack-operations-coverage](stack-operations-coverage.md) |
| StackSets | 2 | 2 | 0 | [stacksets-coverage](stacksets-coverage.md) |

<!-- coverage-index:end -->

The control API's own route table is generated from its dispatcher and sits under
**API** rather than here: it is a reference for callers, not a description of the
console.
