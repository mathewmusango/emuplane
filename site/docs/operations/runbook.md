---
sidebar_position: 1
title: Runbook
---

Day-to-day operation of an Emuplane deployment.

## Before anything: the emulator

Emuplane is the control plane, not the emulator. The emulator runs from its own
compose file in its own repository, and `up.sh` refuses to start without it.

## Start

```bash
cp .env.example .env        # EP_BACKEND_URL, EP_CONSOLE_URL, EP_GATEWAY_URL
podman-compose up -d        # bootstrap first, then the control
```

`./scripts/up.sh` is the maintainer's wrapper over the same two compose files: it
derives `EP_BACKEND_URL` from `EP_BACKEND_CONTAINER` and `EP_BACKEND_PORT` when that
is empty, creates the lab network, pulls the image when it is missing, runs the
bootstrap job explicitly and waits for `/health`. The first run creates `.env` from
`.env.example` (mode `0600`) when it is missing. No credential is
seeded: the API bearer token is minted on demand by `./scripts/token.sh` and
stored as a hash, so `.env` carries no secret at all.

`docker-compose.yml` is the product's own definition; `up.sh` layers an untracked
`compose.lab.yml` over it for a deployment's image, names, routes and network.

## The image

Two stages: Node builds `web/dist`, then the Python stage copies it and the
control source, so the image is self-contained — nothing is bind-mounted from the
host and nothing has to be built there.

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
- `docker-compose.yml` names the published image and never builds it, so `up` on a
  fresh host pulls. A deployment's own overlay can add a `build:` block beside that
  name, which is how a checkout builds itself with `up` and `build`.

## The bootstrap stack

Before the console starts, the `bootstrap` service (`bootstrap/apply.py`) applies
`bootstrap/template.yml` as the CloudFormation stack `emuplane`. That stack owns the
eleven DynamoDB tables the control keeps its own state in.

- Compose orders it: `emuplane` declares `depends_on: bootstrap:
  service_completed_successfully`, so a plain `up -d` is enough.
- `up.sh` runs it explicitly first, and is idempotent either way.
- **The control refuses to serve when a table is missing**, naming it and this
  command, rather than starting and failing on the first sign-in.
- Tables that predate the stack are reported, not adopted — CloudFormation cannot
  adopt one. Drop them on a fresh setup and re-run.

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
emulator comes back empty, and the next `./scripts/up.sh` applies the control's
tables to it again.

## The dev loop

`./scripts/up.sh --dev` mounts the control source and the built console into the
container, so a change costs no image build. The overlay it applies
(`compose.dev.yml`) is generated on the spot from `control/*.py` and `web/dist`,
and ignored — the mounts cannot live in `docker-compose.yml`, which has to work for
someone who has the image and no source checkout.

| Change | What to do |
| --- | --- |
| `control/`, `scripts/` | restart the container |
| `web/` | `cd web && npm run build`, with the mount in place |
| `site/` (these pages) | `cd site && npm run build` |

Without `--dev` the container runs the image's baked code — a restart then
silently serves the last built image.

## Tokens and passwords

```bash
./scripts/token.sh            # mint the API bearer token, printed once
./scripts/token.sh --status   # is there one?
./scripts/token.sh --rotate   # replace it; the old one stops working immediately
./scripts/reset-link.sh <user>   # a one-time /reset link, handed over out of band
./scripts/password.sh <user>     # set the password outright
```

Both password paths revoke that principal's sessions.

## Before you push

```bash
python3 scripts/qa_check.py --tests     # pytest, the task ledger, secrets, compile
cd web && npx tsc --noEmit && npm test  # the console
cd web && npx vite build                # dist/, which the container serves
cd site && npm run build                # these pages
```
