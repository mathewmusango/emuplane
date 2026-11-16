---
sidebar_position: 1
title: Quickstart
---

Emuplane runs as one container: the gateway and the console are two servers in
the same image, and the state they own lives in the emulator's DynamoDB. The
emulator itself is yours to run — MiniStack, LocalStack, moto or anything that
speaks the same API.

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

`EP_BACKEND` picks the profile (`generic`, `ministack`, `floci`, `localstack`,
`moto`); `EP_BACKEND_URL` is the only value that has to be right.

## Start it

```bash
# the emulator first — Emuplane's first job reads it
services/ministack/scripts/up.sh

# then Emuplane: preflight, apply the DynamoDB tables, start the control
./scripts/up.sh
```

`./scripts/up.sh` runs the `bootstrap` service to completion before the control
starts. Bootstrap applies `bootstrap/template.yml` as the `emuplane` stack — the
DynamoDB tables Emuplane keeps its own accounts and sessions in — and is
idempotent. **The control refuses to serve if those tables are missing**, rather
than starting and failing on the first login.

By hand, the same thing:

```bash
docker compose run --rm bootstrap
docker compose up -d emuplane
```

Two ports are published on loopback only:

| Port | What it is |
| --- | --- |
| `4570` | Console and control API (`EP_PORT`, `8080` inside) |
| `4571` | Gateway for your tools (`EP_GATEWAY_PORT`, `8081` inside) |

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

## The deployment token (optional)

The console signs in with sessions, so nothing here needs a token. The control API
has a second caller — a script, or the deployment itself — and that one is a bearer
token:

```bash
./scripts/token.sh
```

It is printed once and stored hashed. You do not need one to use Emuplane from the
console; you need one when something other than a browser calls the control API.

## Where next

- [Accessing it: the console and the CLI](/docs/getting-started/access)
- [The console, page by page](/docs/getting-started/console)
- [Accounts, regions and keys](/docs/concepts/tenancy)
- [What the gateway enforces](/docs/concepts/architecture)
