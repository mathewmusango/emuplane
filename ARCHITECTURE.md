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
4. **Bootstrap (Layer 0)** — the substrate is *provisioned, not conjured*:
   `bootstrap/template.yml` defines the control's ten DynamoDB tables as a
   CloudFormation stack and `bootstrap/apply.py` applies it as a first-setup init
   job before the control starts. Layer 0 only verifies the tables and refuses to
   serve when one is missing, naming it. No account is seeded — the first sign-up
   becomes the platform owner. No circular dependency on the API it is about to
   start.
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
  start without it), so the dependency is not new — it is only wider. The tables
  are created by the bootstrap stack (`bootstrap/template.yml`, applied by the
  first-setup init job); Layer 0 verifies them and refuses to serve when one is
  missing, naming it. A failure to reach the endpoint is reported the same way.

### Tables

One table per store keeps the access patterns obvious and the migration from
`control.db` mechanical. The set is owned by `bootstrap/template.yml`: adding a
store means adding a resource there *and* a name in `control/store.py`, which is
the point — the schema is a reviewable artifact, not a side effect of startup.

| Table | Key | Holds |
| --- | --- | --- |
| `emuplane-principals` | `pk = PRINCIPAL#<id>` | root, IAM users, substrate admins; argon2 hash, account, type |
| `emuplane-accounts` | `pk = ACCOUNT#<12-digit>` | alias, cell, status, `root_credentials_enabled`, users |
| `emuplane-sessions` | `pk = SESSION#<sha256(token)>` | principal, account, `is_elevated`, `expires_at` |
| `emuplane-cells` | `pk = CELL#<id>` | endpoint, status (`ACTIVE`/`DRAINING`/`OFFLINE`), weight |
| `emuplane-audit` | `pk = ACTOR#<id>`, `sk = <ts>#<uuid>` | action, outcome, target account |

Sessions are stored **hashed**, never raw: `save_sessions()` keys the
`emuplane-sessions` rows by the token's SHA-256 (`session_key()`), so a copy of
the table cannot replay a live session. The raw token exists only in the cookie
that created it. Rows written before that change were keyed by the raw token;
`load_sessions()` re-keys them on start-up and drops the raw copy. Expiry is kept
in the payload (`expires`) and enforced on read, extended on activity.

**Password recovery is local, because there is no mail transport.** A locked-out
principal is reset by someone who can reach the deployment: an administrator
over `POST /api/users/<username>/password` (bearer token, or a signed-in
platform admin), or the platform owner from the host with
`./scripts/password.sh <username>`. Either path revokes every session that
principal holds. `/forgot` is the public page that explains this. The user store
reads through to DynamoDB on every lookup (`UserStore._reload()`) precisely so an
out-of-process reset takes effect immediately instead of at the next restart —
and so a login cannot write a stale cached hash back over a reset.

## Identity and the three logins

Modeled on the five sign-in screens we are copying:

| Screen | Principal | Credential |
| --- | --- | --- |
| User type → Root user | `ROOT` | email + password |
| User type → IAM user | `IAM_USER` | account id/alias + username + password |
| MFA | either | one-time code, after a correct password |
| Substrate (console) | `SUBSTRATE_ADMIN` | email + password |

Rules:

- **Root login is disableable (designed, slice 5 — only the read side exists).**
  `DELETE /org/accounts/<id>/root-credentials` is meant to clear the principal's
  password hash, flip `root_credentials_enabled=false` and purge that principal's
  sessions; `POST /api/auth/login` already refuses a root whose flag is false, but
  nothing sets the flag today, and no audit rows are written (`emuplane-audit` is
  provisioned and unused).
- **Break-glass is 15 minutes and audited before it is issued.**
  `POST /sts/assume-root` records the justification, then returns a token whose
  session carries `is_elevated=true`. Only an elevated session may override a
  locked bucket policy, and the override is recorded on the delete.
- **No standing admin.** Substrate admin sessions are short-lived; the console
  re-authenticates rather than holding a long token.

## Email and events — SES and SNS, not SMTP

> Nothing here is implemented yet. A first pass used SES for a sign-up one-time
> password; that flow and its mailbox page were removed on request, so this
> section is the design that remains for slice 7.

The emulator implements SES (`ses.py`, `ses_v2.py`) and SNS (`sns.py`), so the
control plane never speaks SMTP: it calls the same emulator it fronts, signed
exactly like any other control call.

- **Transactional mail** — address verification, password reset, "your root
  credentials were deleted" — goes through **SES `SendEmail`**. The emulator
  keeps sent mail per account/region and exposes it at
  `GET /_ministack/ses/messages`, so the console gets a **Mailbox** view with no
  mail service, no relay and no deliverability to arrange.
- **Events** — account created or closed, root credentials deleted, break-glass
  assumed — publish to an SNS topic (`emuplane-events`). Mail is for
  people, a topic is for machines: local consumers subscribe over HTTP or SQS
  and nothing leaves the host.
- **Tokens** — verification and reset tokens are single-use, hashed at rest and
  TTL'd, the same contract as sessions. The reset link carries the raw token
  once, in the mail; the SES record is the audit copy.
- **Why not SMTP** — an SMTP client would add a dependency, a relay and a
  deliverability problem to reproduce what the emulator already stores. It
  comes back only if mail must actually leave the host.

## Slices

Ordered so each one is verifiable on its own.

1. **Store** — the stdlib DynamoDB client (signer + table ops) and the
   `ensure_tables()` Layer-0 call. Verify: tables exist after a cold start.
2. **Principals, accounts, sessions, audit** — the four document stores over the
   new backend, replacing the `control.db` write paths one store at a time.
3. **Login screens** — done for password auth: the console's five screens are
   `/login`, and `POST /api/auth/login` mints the session. Left: MFA enrolment
   (`mfa_required` is always false, `POST /api/auth/mfa` answers 501), and the
   sign-up screen is still server-rendered.
4. **Cells and the router** — cell records, account→cell assignment, the proxy
   with its forwarded headers, and per-account storage inside each cell.
5. **Break-glass and root lifecycle** — the two destructive paths, both audited.
6. **Bootstrap hardening** — the provisioning half is done: the tables come from
   the CloudFormation init job and Layer 0 fails loudly when one is absent. Left:
   Layer 0 ordering for cells, and the same treatment for the SES identity and SNS
   topic when slice 7 lands.
7. **Email and events** — SES send for verification and reset, the console's
   Mailbox view over `/_ministack/ses/messages`, and the SNS topic for account
   and root-lifecycle events.

## Not in scope

- Real container provisioning inside a cell (the reference uses local
  directories; Firecracker/Podman is a later question).
- Anything that renames the product or its accounts — that stays a user
  decision.
- Reinstating OIDC, SMTP, audit-to-SIEM or OTel; those stay in the local
  roadmap with their return criteria.
