---
title: Coverage
sidebar_position: 1
---

Every operation the emulator advertises, service by service, with the test behind each
one. A page counts only what the emulator's own operation list carries, so a service
that answers APIs gets a page here rather than a promise.

The map is grouped the way the emulator groups its services. Open a group for the
services and their counts, and a service for its operations, the console actions and
the test behind every row. This page and the group pages are generated from
`coverage/*.json` by the same script that renders the service pages, so a new service
never means editing a list by hand.

```bash
npm run coverage   # regenerates this map and every service page
```

<!-- coverage-index:begin -->

**87 services** · 2552 operations · 2550 tested · 2 blocked. Each page names the test behind every operation it counts.

| Group | Services | Operations | Tested | Blocked |
| --- | ---: | ---: | ---: | ---: |
| [Core](core/index.md) | 44 | 1282 | 1282 | 0 |
| [Extended](extended/index.md) | 4 | 166 | 166 | 0 |
| [Infrastructure](infrastructure/index.md) | 34 | 1080 | 1078 | 2 |
| [CloudFormation](cloudformation/index.md) | 5 | 24 | 24 | 0 |

<!-- coverage-index:end -->
