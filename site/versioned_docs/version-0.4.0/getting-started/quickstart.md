---
sidebar_position: 1
title: Quickstart
---

Emuplane runs as one container: the gateway and the console are two servers in
the same image, and the state they own lives in the emulator's DynamoDB. The
emulator itself is yours to run — MiniStack is the reference, but anything that
speaks the same API works.

## What you need

- **An emulator** reachable from the Emuplane container. MiniStack on port
  `4566` is the reference setup.
- **A container runtime** with compose: podman or docker.
- **Three settings** — everything else has a default:

```bash title=".env"
EP_BACKEND=ministack
EP_BACKEND_URL=http://ministack:4566
EP_CONSOLE_URL=http://localhost:4570
EP_GATEWAY_URL=http://localhost:4571
```

`EP_BACKEND` picks the backend profile and defaults to `ministack`, the tested
one; `EP_BACKEND_URL` is the only value that has to be right.

## Pull it

The image is published to the GitHub Container Registry: [ghcr.io/mathewmusango/emuplane](https://github.com/mathewmusango/emuplane/pkgs/container/emuplane). Every release tags its version and moves `latest` to the same digest.

```bash
docker pull ghcr.io/mathewmusango/emuplane:0.2.2      # the version this page documents
docker pull ghcr.io/mathewmusango/emuplane:latest     # the newest release
```

The compose files pin the current version, so bringing the stack up never changes
the image under you; `latest` is there for a quick look at the newest release.

## Start it

The whole stack — MiniStack, its first-setup job and the control — fits in one
file:

```bash
cp .env.all.example .env.all
docker compose --env-file .env.all -f docker-compose.all.yml up -d
```

The emulator is internal to that network and never published; the console answers
on `http://localhost:4570` and the gateway on `http://localhost:4571`.

Already running an emulator? The container has to be able to **reach** it, and
`EP_BACKEND_URL` names it the way the container sees it:

- **It runs as a container.** Put it on a network this stack joins and name it:
  `EP_BACKEND_URL=http://ministack:4566`.
- **It runs on the host.** It must listen on more than loopback — publishing
  `127.0.0.1:4566` is not reachable from a container. Then use
  `http://host.containers.internal:4566` on Podman, or
  `http://host.docker.internal:4566` on Docker Desktop (Docker on Linux needs an
  `extra_hosts` entry of your own).

```bash
cp .env.example .env      # set EP_BACKEND_URL
docker compose up -d
```

Either way, the compose `depends_on` runs the `bootstrap` service to completion
before the control starts. Bootstrap applies
`bootstrap/template.yml` as the `emuplane` stack — the DynamoDB tables Emuplane
keeps its own accounts and sessions in — and is idempotent. **The control refuses
to serve if those tables are missing**, rather than starting and failing on the
first login.

By hand, the same thing:

```bash
docker compose run --rm bootstrap
docker compose up -d emuplane
```

Two ports are published on loopback only:

| Port | What it is |
| --- | --- |
| `4570` | Console and control API |
| `4571` | Gateway for your tools |

## The first account

Nothing is seeded, so open [localhost:4570/signup](http://localhost:4570/signup) and
create the first root user. That account owns everything until you add more.

![The sign-in screen: root user or IAM user](/img/sign-in.png)

<figure>
  <figcaption>The sign-in screens mirror the AWS ones: user type, credentials,
  then MFA.</figcaption>
</figure>

## Your first bucket

1. **Sign in** at `/login` with the root user you just made.
2. The **region menu** at the top picks the region every page acts in. A region
   an account has not used yet is enabled on first use.
3. **S3 → Create bucket**. Give it a name and leave the defaults.
4. Open the bucket. Its **Objects** tab is empty because the bucket is.

## Prove it from outside the console

Mint an access key for the account in the console (**Account → Access keys**),
then point the AWS CLI at the gateway:

```bash
export AWS_ENDPOINT_URL=http://localhost:4571
export AWS_ACCESS_KEY_ID=<the key id from the console>
export AWS_SECRET_ACCESS_KEY=<the secret, shown once>

aws s3 ls
aws s3 cp ./README.md s3://<your-bucket>/README.md
```

The gateway resolves the account from the key, checks that the request's signing
region is enabled for that account, and forwards it. The object you uploaded is
now in the console's Objects tab.

## Where next

- [Accessing it: the console and the CLI](/docs/getting-started/access)
- [Deployment: Docker and Podman](/docs/deployment/docker-podman)
- [The console, page by page](/docs/getting-started/console)
- [Accounts, regions and keys](/docs/concepts/tenancy)
- [What the gateway enforces](/docs/concepts/architecture)
