---
sidebar_position: 1
title: Reference
---

What the console can do, operation by operation; the settings it reads; and what it
deliberately does not do. **Not only S3** — every coverage page is generated from the
emulator's own operation list, so a service that answers APIs gets a page here rather
than a promise, and more are landing as the console grows pages for them.

| Page | What it answers |
| --- | --- |
| [S3 coverage](s3-coverage.md) | every S3 operation the emulator advertises, and whether the console can show or do it |
| [S3 Files coverage](s3-files-coverage.md) | the S3 Files API surface the console reads |
| [IAM coverage](iam-coverage.md) | the IAM operations, and which of them the console acts on |
| [Account coverage](account-coverage.md) | the account APIs the emulator answers |
| [Configuration](configuration.md) | every `EP_` setting, its default, and what it does |
| [Limits](limits.md) | what is deliberately not done, and what each gap costs |

The control API's own route table is generated from its dispatcher and sits under
**API** rather than here: it is a reference for callers, not a description of the
console.
