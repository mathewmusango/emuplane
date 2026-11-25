---
sidebar_position: 3
title: Running Podman
---

```bash
cp .env.all.example .env.all
podman-compose --env-file .env.all -f docker-compose.all.yml up -d
```

Rootless Podman publishes the loopback ports exactly as Docker does, and the
image's healthcheck runs unprivileged. On an SELinux host a bind mount needs the
`:Z` label — the untracked dev overlay that mounts the console and control source
adds it for you.

## Services that start containers (optional)

The same five as on Docker — ECS tasks, EKS's k3s node, DocumentDB's MongoDB, an
RDS instance's database, and the database behind the RDS Data API's batch and
transactions. Everything else works without this step.

**1. Enable the user socket** — it exists only while the socket unit does:

```bash
systemctl --user enable --now podman.socket
ls -l /run/user/$(id -u)/podman/podman.sock
```

**2. Hand it to the emulator at the path the client looks for.** Inside the
container the socket belongs at `/var/run/docker.sock`, which is the Docker
client's default, so **no `DOCKER_HOST` is needed** and one compose overlay serves
both runtimes:

```bash
DOCKER_SOCKET=/run/user/$(id -u)/podman/podman.sock \
  podman-compose --env-file .env.all \
    -f docker-compose.all.yml -f docker-compose.socket.yml up -d
```

Standalone, the same thing:

```bash
podman run -d --name ministack \
  -p 4566:4566 \
  -v /run/user/$(id -u)/podman/podman.sock:/var/run/docker.sock \
  ministackorg/ministack:1.5.40
```

`DOCKER_HOST` earns its place only when something else already occupies
`/var/run/docker.sock` inside the image.

Podman's compatibility surface is not identical to Docker's in every corner;
[Podman Desktop documents which][compat]. The socket path, the API the client
speaks and the container it reaches are the parts this setup relies on.

Two boundaries come with the mount: a container the emulator starts cannot bind
mount a path that exists only inside the emulator container (keep data on named
volumes), and the socket is root on the host, so mount it only into an image you
trust.

## EKS needs the cpuset controller

k3s wants `cpuset`, and a rootless session does not delegate it to user units by
default: k3s exits with `failed to find cpuset cgroup (v2)` and the cluster stays
a control-plane record. Delegate the controllers once:

```ini
# /etc/systemd/system/user@.service.d/delegate.conf
[Service]
Delegate=cpu cpuset io memory pids
```

```bash
sudo systemctl daemon-reload
# log out and back in (or reboot) so user@$UID.service restarts
cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers
```

After a fresh session the emulator container sees `cpuset` in its own
`cgroup.controllers`, and `CreateCluster` starts a k3s container that stays up.
That is as far as rootless Podman goes on this kind of host: the in-container
kubelet then needs `KubeletInUserNamespace`, a nested overlay snapshotter, and a
`kubepods` cgroup it can own, so no API server comes up and `kubectl` through the
returned kubeconfig is not expected to work. A rootful Docker daemon has none of
these constraints. What is and is not real in the record is on the
[Limits](../reference/limits.md#eks-on-rootless-podman) page.

[compat]: https://podman-desktop.io/docs/migrating-from-docker/managing-docker-compatibility
