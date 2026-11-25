---
sidebar_position: 1
title: Reference
---

The settings the control reads, the limits it enforces, and the control API's own
route table. **Coverage has its own section**: [the coverage map](../coverage/index.md)
lists every service the emulator advertises, grouped the way the emulator groups
them, with the test behind each operation it counts.

| Page | What it answers |
| --- | --- |
| [Coverage](../coverage/index.md) | every service the emulator advertises, grouped, with its operation and test counts |
| [Configuration](configuration.md) | every `EP_` setting, its default, and what it does |
| [Limits](limits.md) | what is deliberately not done, and what each gap costs |

The control API's route table is generated from the control's dispatcher and sits
under **API** rather than here: it is a reference for callers, not a description of
the console.
