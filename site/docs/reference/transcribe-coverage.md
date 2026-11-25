---
sidebar_position: 22
title: Transcribe coverage
---

Every Transcribe operation the emulator advertises, and what Emuplane does with
it. There is no console action: batch transcription jobs are started, read,
listed and deleted over the wire. Jobs run on a background worker, so the
in-process stand-in skips the completion assertions and the live sweep proves
them; the operations themselves are all covered.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **4**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **4**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **2**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **4** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `StartTranscriptionJob` | — | not yet | tests/control/test_transcribe_operations.py |
| `GetTranscriptionJob` | — | not yet | tests/control/test_transcribe_operations.py |
| `ListTranscriptionJobs` | — | not yet | tests/control/test_transcribe_operations.py |
| `DeleteTranscriptionJob` | — | not yet | tests/control/test_transcribe_operations.py |

<!-- coverage:end -->
