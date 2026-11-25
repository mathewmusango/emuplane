---
sidebar_position: 2
title: Running Docker
---

```bash
cp .env.all.example .env.all
docker compose --env-file .env.all -f docker-compose.all.yml up -d
```

The console answers on `127.0.0.1:4570`, the gateway on `127.0.0.1:4571`.
`docker compose down` stops it; the named volumes keep the emulator's data.

## Services that start containers (optional)

Five things need the Docker API, because they run a sibling container rather than
a record:

| Service | The container |
| --- | --- |
| ECS | the task |
| EKS | the k3s node |
| DocumentDB | MongoDB |
| RDS | the database instance |
| RDS Data API | the same database, for `BatchExecuteStatement` and the three transaction calls |

Everything else works without this step. Save this overlay beside the compose
file:

```yaml
# compose.socket.yml
services:
  ministack:
    volumes:
      - "${DOCKER_SOCKET:-/var/run/docker.sock}:/var/run/docker.sock"
```

and bring the stack up with it:

```bash
docker compose --env-file .env.all \
  -f docker-compose.all.yml -f compose.socket.yml up -d
```

The overlay mounts the runtime's socket at `/var/run/docker.sock` inside the
emulator. On Docker that is where it already lives, so nothing else is needed —
and because it is the Docker client's default path, **no `DOCKER_HOST` is set**.
If your daemon listens somewhere else, name it:
`DOCKER_SOCKET=/run/docker.sock docker compose …`.

The daemon the emulator reaches is the host's, so it creates containers beside
the emulator rather than inside it. That has two consequences:

- **A bind mount into such a container must name a host path.** A path that exists
  only inside the emulator container fails. Keep data on named volumes; this is
  the same boundary [`act` documents][act-2393].
- **The socket is root on the host.** Mount it only into an image you trust, and
  not on a multi-user box.

EKS needs nothing extra on a rootful Docker daemon: the cpuset controller,
`/dev/kmsg` and the cgroups k3s's kubelet manages are already there. A rootless
Podman session is the harder case — see [Running Podman](podman.md).

[act-2393]: https://github.com/nektos/act/issues/2393
