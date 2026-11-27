---
sidebar_position: 2
title: Upgrading
---

An upgrade replaces one image tag. Everything that matters is written down
somewhere else, so the procedure is short and the failure modes are few — but
they are not zero, and this page names them.

## What an upgrade touches, and what it does not

| Piece | Where it lives | An upgrade touches it? |
| --- | --- | --- |
| The console, control API and gateway | the image | **yes** — that is the upgrade |
| The `emuplane` CloudFormation stack | the emulator, reconciled on every start | **yes**, if the template changed |
| Accounts, users, sessions, access keys, region enablement, registries, settings | the emulator's `emuplane-*` DynamoDB tables | **no** |
| The objects and buckets you created | the emulator | **no** |
| Your `.env` and compose overlays | your host | **no** |

The control is stateless by design: there is no database container, no data
volume and nothing on the host. **Replacing the container costs nothing**, which
is also why rolling back costs nothing. See
[Architecture](../concepts/architecture.md#the-control-plane-owns-the-rest).

## The procedure

The compose files pin a released image tag, so the upgrade is the pin moving:

```bash
git pull
docker compose --env-file .env.all -f docker-compose.all.yml up -d
```

That is the whole of it, because `up` does the two real steps in order:

1. **`bootstrap` runs again** and brings the `emuplane` stack to the template
   that ships with the new image. It is an `UpdateStack`, and a template that did
   not change is success too: `No updates are to be performed` is treated as
   "already current", not as an error.
2. **The control starts** — and only if the job completed, because compose orders
   the two with `depends_on: … service_completed_successfully`.

A deployment that pins the tag in its own overlay instead can point at a version
directly, without waiting for a repository change:

```yaml title="docker-compose.override.yml"
services:
  emuplane:
    image: ghcr.io/mathewmusango/emuplane:0.12.0
```

Both the bare tag and the `v`-prefixed one are pushed to the same digest, so a tag
copied from the release page works as written. `latest`
exists for a quick look at the newest release; a deployment should pin, or the
image changes under it at the next pull.

## Verify it took

Three checks, in increasing cost:

- **`/health` answers `200`.** This proves the process is up and nothing more —
  it is liveness only, and it answers `200` while the emulator is down.
- **The Backend health widget says `reachable`, with a version beside it.** That
  is the first honest sign that the control and the emulator agree.
- **`aws s3 ls` through the gateway (`:4571`) lists your buckets.** That
  exercises the account lookup and the region rule, so it covers what the widget
  does not.

If any of the three fails, [Troubleshooting](../guides/troubleshooting.md) is
indexed by the messages a failed upgrade produces.

## Rolling back

Put the previous tag back and `up -d`. The data does not move in either
direction: no version in this repository migrates, rewrites or copies table
contents — `bootstrap` only reconciles the stack's *definition* — so the older
image reads the same tables the newer one wrote.

One caveat, and it is the only real one. The newer image may have **updated the
stack** to its own template. Rolling the image back makes the older `bootstrap`
try to bring that stack back to the older template, and an emulator that refuses
is a job that fails — and because the control waits for that job, compose will not
start it. Read the answer by hand first:

```bash
docker compose run --rm bootstrap
```

If the tables are all present and only the *stack* is the problem, delete the
stack and keep the tables: the next run finds them and exits successfully with a
warning that they exist without a stack owning them, which is enough for the
control to start.

```bash
docker compose run --rm bootstrap python /app/bootstrap/apply.py --delete
docker compose up -d
```

The stack itself can only be recreated by dropping the tables first — CloudFormation
will not adopt tables it does not own — so `--drop-tables`, which deletes the
stack *and* every control table and returns you to a first setup, is the
destructive fallback and not the routine one.

## Upgrading across versions

There is no ordering constraint and no intermediate step: the state is a set of
tables, not a schema version, and the template is applied as one update. Upgrading
from `0.2.x` to the current release is the same command as upgrading by one
patch.

The documentation is the part that is versioned differently. Each release gets a
frozen copy of these pages, and the version menu lists **released versions only**
— the working docs are unversioned and read as **Next**. After an upgrade, the
version you pick from that menu should match the image tag in your compose file;
when the two disagree, the freeze and the release are out of step, which is worth
a report rather than a workaround.
