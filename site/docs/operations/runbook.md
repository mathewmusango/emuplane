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
./scripts/up.sh           # .env, apply the control stack, pull the image, start
./scripts/up.sh --dev     # the same, with the console and control source mounted
./scripts/up.sh --build   # rebuild the image first
```

The first run creates `.env` from `.env.example` (mode `0600`). No credential is
seeded: the API bearer token is minted on demand by `./scripts/token.sh` and
stored as a hash, so `.env` carries no secret at all.

## The bootstrap stack

Before the console starts, `up.sh` runs the `bootstrap` service
(`bootstrap/apply.py`), which applies `bootstrap/template.yml` as the
CloudFormation stack `emuplane`. That stack owns the eleven DynamoDB tables the
control keeps its own state in.

- The job is idempotent: an existing stack is left alone.
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
container, so a change costs no image build:

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
