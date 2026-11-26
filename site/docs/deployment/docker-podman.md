---
sidebar_position: 1
title: Docker and Podman
---

The [Quickstart](../getting-started/quickstart.md) covers the two ways to deploy
Emuplane. This page is the same two methods with the detail behind them: which
file, which environment, what the first-setup job does, and what Podman needs
that Docker does not.

Docker and Podman read the same files; every command works with either
(`docker compose` or `podman-compose`).

## Method 1 — the whole stack

MiniStack, its first-setup job and the control in one file:

```bash
cp .env.all.example .env.all
docker compose --env-file .env.all -f docker-compose.all.yml up -d
```

The emulator is internal to that network and never published; the console answers
on `127.0.0.1:4570` and the gateway on `127.0.0.1:4571`.

## Method 2 — an emulator you already run

```bash
cp .env.example .env      # set EP_BACKEND_URL
docker compose up -d
```

Two things have to be true: the container must **reach** the emulator, and
`EP_BACKEND_URL` names it the way the container sees it.

- **The emulator is a container.** Put it on a network this stack joins, and name
  it: `EP_BACKEND_URL=http://ministack:4566`.
- **The emulator is on the host.** It has to listen on more than loopback —
  publishing `127.0.0.1:4566` is not reachable from inside a container. Then name
  the host: `http://host.containers.internal:4566` on Podman, or
  `http://host.docker.internal:4566` on Docker Desktop (Docker on Linux needs
  `extra_hosts: ["host.docker.internal:host-gateway"]` in your own overlay).

`EP_BACKEND_URL` has a default of `http://localhost:4566`, which is right for a bare
`python app.py` beside a local emulator and wrong inside a container, where
`localhost` is the container itself. The compose file passes the value through, so
an empty one takes that default rather than stopping the control.

## Which environment file

The compose files sit at the repository root, so their `.env` does too.
`.env.example` carries the container's whole environment; `.env.all.example`
carries the bundled emulator's image tag as well. Every `EP_` setting, its default
and what it does is on the [configuration](../reference/configuration.md) page.

## What the files hold

| File | Brings up |
| --- | --- |
| [`docker-compose.yml`](https://github.com/mathewmusango/emuplane/blob/main/docker-compose.yml) | the control only |
| [`docker-compose.all.yml`](https://github.com/mathewmusango/emuplane/blob/main/docker-compose.all.yml) | MiniStack, its first-setup job and the control, on one network |
| [`docker-compose.socket.yml`](https://github.com/mathewmusango/emuplane/blob/main/docker-compose.socket.yml) | the same stack with the runtime's socket mounted into the emulator — see [Running Docker](docker.md) or [Running Podman](podman.md) |

Both pin a released image tag, so bringing one up never changes the image under
you; `latest` is there for a quick look instead.

An optional third file, `docker-compose.socket.yml`, is the all-in-one stack with
the runtime's socket mounted, so the emulator can start sibling containers; it is
shown on [Running Docker](docker.md) and [Running Podman](podman.md).

## The first-setup job

`bootstrap` applies `bootstrap/template.yml` as the `emuplane` CloudFormation
stack: the DynamoDB tables the control keeps its accounts and sessions in. It is
idempotent, and the control **refuses to start** without those tables rather than
starting and failing at the first sign-in. Compose's `depends_on` runs it to
completion before the console is allowed to start.

By hand, the same thing:

```bash
docker compose run --rm bootstrap
docker compose up -d emuplane
```

## Ports

| Port | What it is |
| --- | --- |
| `4570` | console and control API |
| `4571` | gateway for your tools |

Both are published on loopback only.

## Runtime guides

The parts that differ are on their own pages:

- [Running Docker](docker.md) — the default socket, and the opt-in compose overlay
  that gives it to the emulator.
- [Running Podman](podman.md) — the rootless user socket, the SELinux label, and the
  cgroup delegation EKS needs.

Both mount the runtime's socket at `/var/run/docker.sock`, which is where the Docker
client looks by default — so **no `DOCKER_HOST` is set**, and the same overlay
serves both, and `docker-compose.socket.yml` is that file with the mount.

This section will grow to cover Kubernetes, Helm, Argo CD and other deployment
shapes as they are built; nothing here claims them today.
