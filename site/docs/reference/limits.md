---
sidebar_position: 4
title: Limits
---

What this control plane does not do, stated so it is not discovered at the worst
moment.

- **The gateway buffers request and response bodies** — no streaming. Fine for
  state files and API payloads, not for multi-gigabyte object transfers.
- **Responses that embed a node's own endpoint** (an API Gateway `execute-api`
  URL, for example) point at that node directly and bypass the gateway.
- **Account root keys are accepted with any secret, by design.** A 12-digit
  access key is that account's root; only issued `AKIA…` keys are verified by IAM.
  The control's own tokens authenticate the console, not AWS.
- **S3 buckets are region-scoped**: `ListBuckets` answers per region, and a request
  signed for the wrong region gets the `301` AWS returns.
- **The emulator is a local lab.** Nothing here is a substitute for a real AWS
  account, and no credential leaves the host.

Use **path-style** S3 addressing (`s3_use_path_style = true` in Terraform).
Virtual-hosted requests are parsed best-effort; presigned SigV4 credentials in the
query string are honoured.
