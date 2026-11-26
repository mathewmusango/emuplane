---
title: Deployment
sidebar_position: 0
---

How Emuplane runs in production: the container, the compose file, the endpoints it
publishes, and how to move between releases without losing the emulator's data.

| Page | What it answers |
| --- | --- |
| [Running Docker](docker.md) | the compose file, the environment it reads, and the socket that lets the emulator start containers |
| [Running Podman](podman.md) | the same on a rootless host: the user socket, the SELinux label, and the cgroup delegation EKS needs |
| [Upgrading](upgrading.md) | moving a running instance to a new tag, and what a release changed |
