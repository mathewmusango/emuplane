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

**10 services** · 236 operations · 216 tested · 0 blocked. Each page names the test behind every operation it counts.

| Group | Services | Operations | Tested | Blocked |
| --- | ---: | ---: | ---: | ---: |
| [Core](core/index.md) | 3 | 187 | 187 | 0 |
| [Infrastructure](infrastructure/index.md) | 2 | 25 | 5 | 0 |
| [CloudFormation](cloudformation/index.md) | 5 | 24 | 24 | 0 |

<!-- coverage-index:end -->
