# Architecture

What this control plane is trying to be, and the decisions that follow. The
reference design is AWS's substrate model: a control plane that owns accounts
and identity, data-plane **cells** that own tenant resources, and a router in
between so no tenant can see another's cell.

The emulator (`services/ministack`) stays emulator-only. This repo is the
control plane, the console and the AWS gateway.

## The five pieces

```
             +-----------------------------+
  console -> |  control plane (this repo)   |  accounts, principals, sessions,
             |  /api/v1/...                 |  cells, audit, policy
             +--------------+--------------+
                            |  cell router (account -> cell)
             +--------------+--------------+-------------+
             |                            |             |
        +----v----+                  +----v----+   +----v----+
        | cell 1a |                  | cell 1b |   |   ...   |   each cell: its own
        | storage |                  | storage |   |         |   state, own endpoint
        +---------+                  +---------+   +---------+
```

1. **Control plane** — accounts, principals (root / IAM user / substrate
   admin), sessions, cells, audit. Nothing here is tenant data.
2. **Cell router** — resolves `account_id -> cell`, refuses an offline or
   draining cell, and forwards with `X-Forwarded-Account-Id`,
   `X-Forwarded-Cell-Id` and `X-Elevated-Root`.
3. **Cells** — the data plane. Each holds its own state and refuses any request
   that did not come through the router.
4. **Bootstrap (Layer 0)** — idempotent, runs before the API serves: ensure the
   tables exist, seed the substrate admin, register the cells. No circular
   dependency on the API it is about to start.
5. **Console** — stateless Cloudscape SPA; every action is an API call, never a
   direct database read.

## Decision: the database lives in the emulator (DynamoDB)

The control plane stores nothing on the host filesystem. State lives in the
emulator's **DynamoDB**, which the fork implements
(`ministack/services/dynamodb.py`), reached at `MINISTACK_NODE_URL` with the
same SigV4 signer the gateway already uses.

- **No boto3.** The image is stdlib-only on purpose (`python:3.13-alpine` plus
  `control/*.py`). The gateway already signs AWS requests, so the store reuses
  that signer over `urllib` — one signing implementation, no new dependency, no
  requirements file.
- **DynamoDB, not RDS/MySQL.** The emulator implements both, but DynamoDB needs
  no connection pooling, no schema migration and no server-side credentials for
  a local service, and the substrate's access patterns are key lookups.
- **The trade-off, stated plainly:** the control plane now depends on the
  emulator being up. That is already true of the gateway (`up.sh` refuses to
  start without it), so the dependency is not new — it is only wider. Table
  creation is the first thing Layer 0 does, and every failure names the
  endpoint it could not reach.

### Tables

One table per store keeps the access patterns obvious and the migration from
`control.db` mechanical.

| Table | Key | Holds |
| --- | --- | --- |
| `ministack-principals` | `pk = PRINCIPAL#<id>` | root, IAM users, substrate admins; argon2 hash, account, type |
| `ministack-accounts` | `pk = ACCOUNT#<12-digit>` | alias, cell, status, `root_credentials_enabled`, users |
| `ministack-sessions` | `pk = SESSION#<sha256(token)>` | principal, account, `is_elevated`, `expires_at` |
| `ministack-cells` | `pk = CELL#<id>` | endpoint, status (`ACTIVE`/`DRAINING`/`OFFLINE`), weight |
| `ministack-audit` | `pk = ACTOR#<id>`, `sk = <ts>#<uuid>` | action, outcome, target account |

Sessions are stored **hashed**, never raw; the raw token exists only in the
response that created it. TTL is set on `expires_at` so expiry needs no sweeper.

## Identity and the three logins

Modeled on the five sign-in screens we are copying:

| Screen | Principal | Credential |
| --- | --- | --- |
| User type → Root user | `ROOT` | email + password |
| User type → IAM user | `IAM_USER` | account id/alias + username + password |
| MFA | either | one-time code, after a correct password |
| Substrate (console) | `SUBSTRATE_ADMIN` | email + password |

Rules:

- **Root login is disableable.** `DELETE /org/accounts/<id>/root-credentials`
  clears the principal's password hash, flips
  `root_credentials_enabled=false`, and purges that principal's sessions. A
  later root login is `403`, and the attempt is audited as `DENIED`.
- **Break-glass is 15 minutes and audited before it is issued.**
  `POST /sts/assume-root` records the justification, then returns a token whose
  session carries `is_elevated=true`. Only an elevated session may override a
  locked bucket policy, and the override is recorded on the delete.
- **No standing admin.** Substrate admin sessions are short-lived; the console
  re-authenticates rather than holding a long token.

## Slices

Ordered so each one is verifiable on its own.

1. **Store** — the stdlib DynamoDB client (signer + table ops) and the
   `ensure_tables()` Layer-0 call. Verify: tables exist after a cold start.
2. **Principals, accounts, sessions, audit** — the four document stores over the
   new backend, replacing the `control.db` write paths one store at a time.
3. **Login screens** — the five screens above, wired to the new auth endpoints;
   the console keeps its Cloudscape shell.
4. **Cells and the router** — cell records, account→cell assignment, the proxy
   with its forwarded headers, and per-account storage inside each cell.
5. **Break-glass and root lifecycle** — the two destructive paths, both audited.
6. **Bootstrap hardening** — Layer 0 ordering, idempotency, and a clear failure
   when the emulator is unreachable.

## Not in scope

- Real container provisioning inside a cell (the reference uses local
  directories; Firecracker/Podman is a later question).
- Anything that renames the product or its accounts — that stays a user
  decision.
- Reinstating OIDC, SMTP, audit-to-SIEM or OTel; those stay in the local
  roadmap with their return criteria.
