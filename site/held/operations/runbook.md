---
sidebar_position: 1
title: Runbook
---

Day-to-day operation of an Emuplane deployment.

## Before anything: the emulator

Emuplane is the control plane, not the emulator. The emulator runs from its own
compose file in its own repository, and the control will not serve until it answers.

## Start

```bash
cp .env.example .env        # EP_BACKEND_URL, EP_CONSOLE_URL, EP_GATEWAY_URL
podman-compose up -d        # bootstrap first, then the control
```

No credential is seeded: the API bearer token is minted on demand (see [Tokens and
passwords](#tokens-and-passwords)) and stored as a hash, so `.env` carries no
secret at all.

`docker-compose.yml` is the product's own definition; a deployment adds a compose
override of its own for its image, names, routes and network, and
`docker-compose.all.yml` already does that for the bundled emulator.

## The image

The build is two stages: Node builds `web/dist`, then the Python stage copies it,
the control source and the first-setup job, so the image is self-contained —
nothing is bind-mounted from the host and nothing has to be built there.

- Base images are pinned by **index digest** — multi-arch, so a rebuild resolves
  to the same bytes. `renovate.json` is what moves them.
- npm's cache and Vite's transform cache are build mounts rather than layers, so
  unchanged modules are neither re-downloaded nor re-transformed, and nothing from
  either cache ships in the image.
- The healthcheck lives in `docker-compose.yml`, because podman's default OCI image
  format ignores `HEALTHCHECK`.
- The container runs as uid **10001** on a **read-only** root filesystem, with
  `/tmp` on a tmpfs, every capability dropped and `no-new-privileges`, plus
  `init: true` so signals are forwarded and children reaped. Nothing needs a
  writable layer: all state is in the emulator.
- The same image runs the first-setup job with another command
  (`/app/bootstrap/apply.py`): a job, not a service — no ports, no healthcheck,
  `restart: "no"`.
- `docker-compose.yml` names the published image and never builds it, so `up` on
  a fresh host pulls. A deployment's own overlay can add a `build:` block beside
  that name, which is how a checkout builds itself with `up` and `build`.

## The bootstrap stack

Before the console starts, the `bootstrap` service (`/app/bootstrap/apply.py`, the
same image with another command) applies `bootstrap/template.yml` as the
CloudFormation stack `emuplane`. That stack owns the eleven DynamoDB tables the
control keeps its own state in.

- Compose orders it: `emuplane` declares `depends_on: bootstrap:
  service_completed_successfully`, so a plain `up -d` is enough.
- Running it by hand (`docker compose run --rm bootstrap`) is idempotent too.
- **The control refuses to serve when a table is missing**, naming it and this
  command, rather than starting and failing on the first sign-in.
- Tables that predate the stack are reported, not adopted — CloudFormation cannot
  adopt one. Drop them on a fresh setup and re-run.
- Its exit status is 0 only when every table is present, so a failed job stops
  `up` before the control. `--drop-tables` deletes the stack and the control tables; `--delete` removes
  only the stack. `EP_STACK_NAME`, `EP_TABLE_PREFIX` and `MC_TEMPLATE` (the template
  path) let a smoke run use names of its own.

## Day to day

```bash
podman-compose -p emuplane -f docker-compose.yml ps
podman-compose -p emuplane -f docker-compose.yml logs -f
podman-compose -p emuplane -f docker-compose.yml down
```

This stops and starts the **control plane only**; these commands never touch the
emulator. Reset the emulator from the dashboard, or
`POST /api/nodes/<node>/reset`.

There is nothing to back up on the host: the console is stateless and the control
state lives in the emulator's DynamoDB.

### Removing it, and what survives

`down` removes the containers and nothing else. Emuplane keeps no volume, so it
holds no state to rescue — everything it knows belongs to the emulator:

| What | Where it lives |
| --- | --- |
| Accounts, users, keys, sessions, reset tokens, settings | the emulator's DynamoDB (`state`) |
| Buckets and objects | the emulator's S3 store (`s3`) |
| The deployment's own configuration | `.env` in this repository |

So removing Emuplane is reversible: start it again against the same emulator and
every account, key and bucket is still there. Removing the **emulator** is the
irreversible act. Back up its two data directories first — `/var/lib/ministack/state`
and `/var/lib/ministack/s3` inside the container, host bind mounts or a volume in
practice — or accept that the accounts and their buckets go with it. A fresh
emulator comes back empty, and the next `docker compose up -d` applies the control's
tables to it again.

## Working on the source

The image flattens `control/` into `/app/`, so mount the file you are changing
rather than the directory — a directory mount would hide `/app/static`:

```yaml title="compose.override.yml"
services:
  emuplane:
    volumes:
      - ./web/dist:/app/static:ro
      - ./control/app.py:/app/app.py:ro
```

Compose loads that file automatically, so `up -d` picks up the mounts:

| Change | What to do |
| --- | --- |
| `control/`, `scripts/` | restart the container |
| `web/` | `cd web && npm run build`, with the mount in place |
| `site/` (these pages) | `cd site && npm run build` |

Without the mounts the container runs the image's baked code — a restart then
silently serves the last built image.

## Tokens and passwords

```bash
docker compose exec emuplane python /app/api_token.py            # mint, printed once
docker compose exec emuplane python /app/api_token.py --status   # is there one?
docker compose exec emuplane python /app/api_token.py --rotate   # the old one stops working
docker compose exec emuplane python /app/password.py <user> --link   # a one-time /reset link
docker compose exec emuplane python /app/password.py <user>          # set it outright
```

Both password paths revoke that principal's sessions.

## Before you push

```bash
python3 scripts/qa_check.py --tests     # pytest, the task ledger, secrets, compile
cd web && npx tsc --noEmit && npm test  # the console
cd web && npx vite build                # dist/, which the container serves
cd site && npm run build                # these pages
```

The S3 and access-point tests import the emulator's own service modules rather than
a mock, so they need its source: set `EP_EMULATOR_SRC` to a checkout of the tag the
images carry (`v1.5.41`), which is what CI clones. Without it those tests skip and
the run proves less than it looks like it does.
