<h1 align="center">Ministack Control</h1>
<p align="center"><strong>The control plane for the MiniStack AWS emulator.</strong></p>
<p align="center">Emulator gateway · Accounts, logins and access keys · Console and control API</p>

<p align="center">
  <a href="https://github.com/mathewmusango/ministack-control/actions/workflows/release.yml"><img src="https://github.com/mathewmusango/ministack-control/actions/workflows/release.yml/badge.svg" alt="Release"></a>
  <a href="https://github.com/mathewmusango/ministack-control/actions/workflows/semgrep.yml"><img src="https://github.com/mathewmusango/ministack-control/actions/workflows/semgrep.yml/badge.svg" alt="Semgrep"></a>
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
  <img src="https://img.shields.io/badge/python-3.13-blue" alt="Python">
  <a href="https://github.com/users/mathewmusango/packages/container/package/ministack-control"><img src="https://img.shields.io/badge/ghcr.io-ministack--control-blue?logo=github" alt="ghcr.io"></a>
</p>

<!--
  Badges to add later, with what each needs:
  - GitHub release: a tag or release; the repo has neither yet.
  - Docker pulls: GitHub Packages (ghcr.io) exposes **no pull counts**, so there is
    no equivalent of Docker Hub's pulls badge. The ghcr.io badge above is a registry
    label, not a statistic; it starts resolving when the package is published.
-->

---

## Why Ministack Control?

Ministack Control is the control plane for the MiniStack emulator. Short version:

- It holds the accounts, and the logins inside them.
- It issues the access keys clients sign with. The secret is shown once.
- It is the endpoint AWS clients and Terraform point at.
- It serves the console, the control API and the resource browser.

The emulator it fronts is our fork of MiniStack,
[`mathewmusango/ministack-upstream`](https://github.com/mathewmusango/ministack-upstream),
on branch
[`feat/s3-region-scoped-state`](https://github.com/mathewmusango/ministack-upstream/tree/feat/s3-region-scoped-state).
It is upstream [`ministackorg/ministack`](https://github.com/ministackorg/ministack)
`v1.5.40` plus S3 region isolation, which upstream does not have yet, published as
`ghcr.io/mathewmusango/ministack-upstream:1.5.40-fork.2-full`.

## Multi-tenancy and regions

MiniStack already partitions state per account and per region, and its own
[README](https://github.com/ministackorg/ministack#readme) covers the mechanics —
the 12-digit access key and the SigV4 scope. This service adds the policy on top:

- **Regions are opt-in per account.** A region the instance does not serve is
  refused; one it serves is enabled on first use. The console lists only the enabled
  regions.
- **Logins belong to accounts.** A person signs in as a principal inside one
  account, with its own IAM user and keys — never as a second account.
- **Neither is a container.** A second account or a new region is one record, not a
  second emulator.

## Plain MiniStack or this fork?

Plain [MiniStack](https://github.com/ministackorg/ministack) already isolates state
per account and per region, for every service except S3. The fork closes that gap:

| S3 behaviour | Plain MiniStack | This fork |
| --- | --- | --- |
| A bucket belongs to | the account, in every region | exactly one account and region |
| `ListBuckets` | every bucket in the account | the signing region's buckets |
| Wrong-region request | reaches the bucket | `301 PermanentRedirect` with `x-amz-bucket-region` |
| State | shared namespace, unique names advised | one record under `(account, region, name)` |

## Compatibility with MiniStack

The fork is upstream `v1.5.40` plus one patch, so everything a client sees stays the
same:

- **Same API and ports.** Every service, operation and wire shape is upstream's;
  nothing is renamed and no endpoint moves.
- **Same configuration.** The `MINISTACK_*` variables keep their names and meanings
  — `AUTH`, `PERSIST_STATE`, `S3_PERSIST`, `MINISTACK_REGION` and the rest.
- **Same image shape.** Built from upstream's `Dockerfile.full`, and the `-full`
  suffix keeps the pin a drop-in for `ministackorg/ministack:<version>-full`.
- **Same duplicate-name behaviour.** AWS's rule for an owner re-create is untouched:
  `200` in us-east-1 with the ACLs reset, `BucketAlreadyOwnedByYou` elsewhere.
- **One visible difference.** S3 state is region-scoped, as the table above shows. A
  client that stays in one region sees no change at all.

| Field | Value |
| --- | --- |
| Runs | `ministack-control`: the console, the control API and the AWS gateway |
| Depends on | the MiniStack emulator, a separate service on port `4566` |
| Endpoints | `http://localhost:4570` (console/API) · `http://localhost:4571` (emulator gateway), loopback only |
| Data | `${MC_DATA_DIR}` — one SQLite database: accounts, users, sessions, registry, ownership, settings |
| Restart | `"no"` — on demand, not in the always-on set |

## Versioning and the image

The image is `ghcr.io/mathewmusango/ministack-control:<version>`, built and pushed
by [`.github/workflows/release.yml`](.github/workflows/release.yml) on every `v*`
tag, together with the GitHub Release.

| Bump | When | Example |
| --- | --- | --- |
| minor | a feature | `0.1.0` → `0.2.0`, up to `0.10.0` |
| patch | a Dependabot or Renovate PR | `0.1.0` → `0.1.10` |
| major | by hand | `0.1.0` → `1.0.0` |

The git tag carries a `v` (`v0.1.0`); the image tag does not (`0.1.0`). `latest`
follows the newest tag. Nothing is tagged yet — `0.1.0` is the first.

## Topology

```mermaid
flowchart LR
    client[AWS client / terraform] -->|4571 gateway| control[ministack-control]
    control -->|"every region, every account"| node[ministack<br/>the emulator]
    browser[browser] -->|"4570 console + API"| control
```

**There is exactly one emulator, and that is the whole point.** MiniStack is a
single process in which each request carries a region (from the SigV4 credential
scope) and an account (from a 12-digit access key), with state partitioned by
both. Regions and accounts are *configuration*, not containers: adding a region
or a second account is a console action plus a client credential.

| What | Where it comes from | Configured by |
| --- | --- | --- |
| Region | the SigV4 scope (`.../us-west-1/s3/aws4_request`), else `MINISTACK_REGION` | the per-account opt-in, chosen from the supported set |
| Account | a 12-digit access key, else `MINISTACK_ACCOUNT_ID` | this control's account store |
| State | partitioned per account; per region for every service, S3 included on the fork image; Aurora DSQL stays account-scoped | the emulator image |

S3 is region-isolated on the fork image: a bucket lives in one region,
`ListBuckets` answers with the signing region's buckets, and a request signed for
another region gets the `301 PermanentRedirect` AWS returns. Aurora DSQL remains
**account-scoped but not region-isolated** (an upstream limitation): two regions
within one account see the same state.

The emulator is not published on the host; the control reaches it at
`MINISTACK_NODE_URL` (`http://ministack:4566` on a shared compose network).

### Credentials

There are no pre-baked AWS profiles. Credentials come from the console: sign
in, and **Settings → Access keys** lists this account's **IAM access keys** by
name, each with a masked ID and a masked secret. Create one to get the pair once
(secret shown a single time, with **Download .csv**), delete one to revoke it.
An account holds **at most two** keys, so a rotation can overlap: create the
new key, switch the client, then delete the old one. Point any client at
`https://ministack.example.com` (a reverse proxy in front of the published
port, with `aws.example.com` kept as a deprecated alias), or at
`http://127.0.0.1:4571` directly.

A 12-digit access key is that account's **root** and accepts any secret; an
`AKIA…` key is verified by IAM. The region a request uses is the one the client
signs with, and the gateway only accepts it once the account has enabled that
region.

## One emulator, not a federation

The first cut ran one emulator and one ledger agent **per region** and federated
them (gossip, per-node ledgers, quorum). MiniStack already isolates state per
region and account, so that layer was redundant: the emulator is one process and
the control takes its address from `MINISTACK_NODE_URL` — no join, heartbeat,
expiry, mode or peer gossip. The registration endpoints,
`MINISTACK_CONTROL_MODE`, `MINISTACK_JOIN_TOKEN`, `MINISTACK_MESH_TOKEN` and
`NODE_TTL_SECONDS` are removed with `control/agent.py`.

## Gateway (`https://ministack.example.com`)

The single AWS entrypoint. It reads the **SigV4 signing region** (or
`X-Ministack-Region` for unsigned callers) and the access key, then forwards to
the one emulator, which does the region/account partitioning itself.

A request is refused (`403 AccessDenied`) when the account that owns the signing
key has not enabled the region it signed for — **except** for a region this
instance still serves (the catalogue): that one is enabled on first use and
recorded in the account's `auto_regions`, so Settings shows
*enabled on first use* next to it. A region the instance does not advertise is
always refused. Unsigned callers and keys the control does not know are
forwarded untouched.

What the control adds is **one global bucket-name registry**, keyed by bucket
name, so a name cannot exist in two accounts or two regions — AWS keeps S3 names
unique partition-wide.

- `CreateBucket` is **reserved atomically** and recorded against the requesting
  account (from the access key); a second claim gets `409 BucketAlreadyExists`,
  whichever account or region asks. The one exception is the owner re-creating a
  bucket in its own region: that request is forwarded, so the emulator answers
  AWS's `200` (us-east-1, ACLs reset) or `BucketAlreadyOwnedByYou`.
- `DeleteBucket` on success releases the name.
- The registry is rebuilt from the emulator's `ListBuckets` at startup, on
  `POST /api/refresh`, and by the 10s poller. That listing is **per account**
  (the root account), so a reconcile prunes only that account's entries and
  never drops another account's buckets; an inventory that cannot be read is
  kept and marked `stale` rather than dropped.

If the emulator is down the gateway answers `503 ServiceUnavailable` instead of
hanging.
> [!NOTE]
> Use **path-style** S3 addressing (the provider flag `s3_use_path_style =
> true`, already used by `local.tfvars`). Virtual-hosted requests are parsed
> best-effort. Presigned SigV4 credentials in the query string are honoured too.

## Tokens and authentication

**Settings use the `MC_` prefix** (control plane); the emulator's own settings
keep upstream's `MINISTACK_*` names in `../ministack/.env`. `CONTROL_*` stays for
the container-internal paths and ports.

| Credential | Where | What it protects |
| --- | --- | --- |
| `MC_ADMIN_TOKEN` | `.env` (optional) | Scripted API access (`Bearer`); writes refuse without a session or this token. Empty means `up.sh` seeds one into `.env` on first run; set it to pin your own. |
| `MC_ADMIN_USER` / `MC_ADMIN_PASSWORD` / `MC_ADMIN_EMAIL` | `.env` | Bootstrap local admin, seeded **only when the user store is empty**. Leave the password empty and `up.sh` seeds one into `.env` on first run; the email is an optional attribute on the user record. |

### Settings (`.env`)

The dotenv files carry no comments — this table is their documentation. The
endpoints, node name, console/gateway addresses and database path are **required**:
the control exits at startup naming whatever is missing.

| Key | Default | What it does |
| --- | --- | --- |
| `MC_DATA_DIR` | `./data` | host directory for `control.db` (compose interpolation) |
| `MC_UI_PORT` | `4570` | loopback port for the console and control API |
| `MC_GATEWAY_PORT` | `4571` | loopback port for the emulator gateway |
| `MINISTACK_NODE_URL` | required | the emulator endpoint the control talks to |
| `MINISTACK_NODE_NAME` | required | node name shown in the console |
| `CONTROL_DB` | required | SQLite path inside the container |
| `CONTROL_PORT` | `8080` | console/API port inside the container |
| `CONTROL_GATEWAY_PORT` | `4566` | emulator gateway port inside the container |
| `MC_ADMIN_TOKEN` | generated | bearer token for scripted API access; empty means `up.sh` seeds one |
| `MC_ADMIN_USER` | `admin` | username of the seeded bootstrap administrator |
| `MC_ADMIN_PASSWORD` | generated | its password; empty means `up.sh` seeds one — change it after the first sign-in |
| `MC_ADMIN_EMAIL` | empty | optional address, recorded on the user record only |
| `CONTROL_POLL_SECONDS` | `10` | seconds between emulator health polls |
| `MC_SESSION_SECONDS` | `28800` | session lifetime (8h), extended on activity |
| `MC_RECENT_LIMIT` | `5` | services shown under **Recently visited** |
| `MC_CONSOLE_URL` | required | console address shown in the UI |
| `MC_GATEWAY_URL` | required | emulator gateway address shown in the UI |

On a fresh database `MC_ADMIN_USER` is seeded as the **default global admin**, with
`MC_ADMIN_PASSWORD` if it is set or a generated one otherwise; every later account
is created by that admin or by sign-up (when enabled). No other account comes from
`.env`.

Generate them once (never commit `.env`):

```sh
python3 -c "import secrets; print(secrets.token_hex(24))"
```

The control's tokens are **not** AWS credentials — they gate the control plane
only. Back up the control directory; it holds every account, session and key.

## Login and access

There is no direct access to the backend stack. The emulator publishes no host
port; the only ways in are the dashboard (`4570`) and the emulator gateway (`4571`),
and the dashboard requires a session.

- Sign in at <https://ministack-control.example.com/login> (or <http://127.0.0.1:4570/login>)
  with the seeded `.env` admin or another local user. Sessions are server-side,
  `HttpOnly` cookies, 8h by default, persisted across restarts and extended on
  activity.
- Scripted API access uses `Authorization: Bearer <MC_ADMIN_TOKEN>`
  instead of a session. The gateway (`4571`) is SigV4 and needs no session.

### Storage (one SQLite database)

Everything the control persists lives in `data/control/control.db`: local users
(PBKDF2-SHA256, 260k rounds), accounts and their principals, live sessions,
resource ownership, settings and the bucket registry. One `0600` file, one
transaction per write, and a single thing to back up. The pre-2026-11-11 side
files (`accounts.json`, `sessions.json`, `ownership.json`, `settings.json`,
`nodes.json`, `registry.json`, `users.db`) are imported once on startup and
renamed to `*.imported`; nothing reads them afterwards, so they can be deleted.

| Page | What it does |
| --- | --- |
| `/login` | email-or-username + password |
| `/signup` | creates an account (fresh 12-digit ID, unique alias) and signs in; **the first one becomes the default global admin**. Link-free by design — reachable only when sign-up is enabled |

The control seeds **nothing** from `.env`. The first account created — by local
sign-up — is the platform owner: `global_admin` and `default_admin` are set on
it, and it can promote other accounts to global admin from **Accounts**. From
then on `control.db` is the source of truth; there is no env-var password to
change. SQLite is deliberate for one control replica: swap the connection for
Postgres when a second one runs.

**Retiring the default admin.** The default admin is meant to be temporary. Once
a second enabled global admin exists, the Dashboard shows a banner to disable or
delete it. `POST /api/accounts/{id}/disabled` disables an account; disabling the
last enabled global admin is refused, and disabling an account also drops its
sessions and blocks sign-in. Sign-up itself can be turned on or off
in **Settings** (`/api/settings`, `signup_enabled`).

### Accounts and identities

An **account** is the tenancy boundary — the 12-digit ID a client signs as.
Humans are never accounts: they are principals inside one.

| Path | What it does |
| --- | --- |
| **Local user** (`/login`, `/signup`) | password verified against `control.db`; a signup mints the account and its alias |

Every principal is a local user with its own password and IAM access key.

Accounts are the tenancy boundary and live in `control.db`: one `accounts` table
keyed by ID.

`GET /api/accounts/me` returns the session's `user`, `account`, `alias`, `role`,
`name` and `email`. `POST /api/me` updates the caller's own `name`, `email` and —
with `current_password` + `new_password` — password; it refuses without a session, so
the bearer token cannot edit a person's account.

### Credentials and IAM

`AUTH=true`, so the emulator **verifies** IAM-user signatures and evaluates
their policies. Two kinds of credential exist, and they are not the same thing:

| Credential | How it identifies the account | Verified? |
| --- | --- | --- |
| a **12-digit access key** (the account ID) | from the key itself | no — root; any secret is accepted, so `test`/`test` still works |
| an **IAM access key** (`AKIA…`) | from IAM state inside that account | yes — secret, session token and request time |

A principal starts with **no access keys**. The IAM user and its
`ministack-admin` inline policy (`Action: *`, `Resource: *`) are created the first
time a key is generated — sign-in and sign-up never issue one. The console manages
keys in **Settings → Access keys** through `GET`/`POST /api/credentials`:
`action: create` (with a `name`), `delete` (with `access_key_id`) or `rotate`
(delete every key, then create `primary`). The store is a list per principal and
the cap is two keys per account — `create_access_key()` refuses before it calls
the emulator, so a refused request never leaves an orphan key behind. The flat
`access_key_id` / `secret_access_key` fields mirror the first key, which is what
the classic pages and the provision response still read. Same-account calls are
then a real, enforced identity:

```sh
aws --endpoint-url https://ministack.example.com sts get-caller-identity
# Arn: arn:aws:iam::111111111111:user/mathewmusango
```

The gateway **preserves the client's `Host` header** on purpose: SigV4 covers
it, so rewriting it to the container name would fail every verified request with
`SignatureDoesNotMatch`.

Provisioning calls use the account ID as a root key, which is why the control can
set up IAM in any account without holding a long-lived secret. A principal's
issued secret lives in the `accounts` table in `control.db`, which is why that
file is `0600` and never leaves the host.

### Account to first S3 call

**Create the account and its login.** Sign up at `/signup` (username, optional
email, password of 8+ characters; the first account becomes the platform owner),
or have the platform administrator provision one and hand back the one-time key
pair:

```sh
curl -sS -X POST https://ministack-control.example.com/api/accounts \
  -H "Authorization: Bearer $MC_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.test","password":"Correct-Horse-1","name":"Alice"}'
# → account_id, alias, iam_user, aws_access_key_id, aws_secret_access_key, regions
```

**Get a secret key.** Sign in and open **Settings → Access keys → Create**
(`POST /api/credentials {"action":"create","name":"laptop"}`). The secret is
shown once, with **Download .csv**; an account holds at most two keys, so a
rotation can overlap. Creating the first key also creates the principal's IAM
user and its `ministack-admin` policy.

**Enable the region.** A new account starts with `us-east-1` alone. Add more in
**Settings → Regions** (`POST /api/regions {"region":"eu-west-1","enabled":true}`);
signing for a region the account has not enabled is `403 AccessDenied`.

**Use the service** — path-style, signed as the account's `AKIA…` key:

```sh
export AWS_ACCESS_KEY_ID=AKIA…
export AWS_SECRET_ACCESS_KEY=…
export AWS_DEFAULT_REGION=us-east-1
export AWS_ENDPOINT_URL=https://ministack.example.com

aws sts get-caller-identity          # arn:aws:iam::<account>:user/alice
aws s3 mb s3://alice-artifacts
aws s3 cp ./file.txt s3://alice-artifacts/
aws s3 ls                            # alice-artifacts only: ListBuckets is per region
```

A bucket name claimed in any account or region is refused everywhere else —
`409 BucketAlreadyExists`, one message, one registry. Your own bucket in its own
region is AWS's answer: `200` in us-east-1 with the ACLs reset, and
`BucketAlreadyOwnedByYou` elsewhere.

### Resource browser

`https://ministack-control.example.com/resources` is our own browser, not an embed. It
signs each read as that account's 12-digit **root**
(`Credential=<id>/<date>/<region>/<service>/aws4_request`, dummy signature), so
the control holds no AWS secret and can list **every** account.

- Three selects: **account** (every account in `control.db`, alias + ID),
  **region**, **service** (`BROWSE_SERVICES` in `control/app.py`).
- The "Signed as" line comes from STS `GetCallerIdentity`, so the page proves
  which account actually answered.
- Rows are `kind / name / region / owner / detail`.
- **Region-scoped objects.** Every row carries the region it lives in and its
  owner (`{account, user?}`). An S3 bucket's region is the one it was created
  in; the registry still records the region a name was claimed in.
- **View from all regions.** `GET /api/browse?region=all` sweeps every region the
  account has enabled (matched against what the node serves) and merges the rows;
  S3 rows dedupe by name, because a bucket name is unique partition-wide. The
  console exposes it as a toggle on the Resources page.
- **Owner metadata** comes from the `owners` table in `control.db`: a successful
  console action that names a resource records the creating principal. The
  emulator keeps no owner, so CLI-created resources simply show the account.
- JSON: `GET /api/browse?account=&region=&service=` — `400` for an unknown
  service or a missing account, `404` for an unknown account, `403` for a
  region the account has not enabled (or another tenancy).

Coverage: IAM, S3, DynamoDB, SQS, SNS, Lambda, CloudWatch Logs, Secrets
Manager, SSM, Kinesis and Step Functions. Listed shape only for now — no
per-resource drill-down or search; S3 buckets have an object view and write
actions where the console declares them.

> [!NOTE]
> StackPort is **gone** (2026-11-05): the service, its Traefik route and the
> `STACKPORT_*` settings were removed with the `MC_` config cleanup. `/resources`
> is the only browser.

## Console and control API (`https://ministack-control.example.com`)

The console is a **React SPA** built from `web/` (Cloudscape, the AWS-console
design system). The control container serves it at
`/`, so the dashboard, API and gateway share one host.

```sh
cd web && npm ci
npm run typecheck                  # tsc --noEmit (typed api/ + types)
npm test                           # Vitest + Testing Library in jsdom
```

The control image builds the console itself: `Dockerfile` has a Node stage that
runs `npm ci && npm run build` and a Python stage that copies `dist` to
`/app/static`, so the runtime container needs no host build and no bind mounts.
Rebuild after changing `control/` or `web/`:

```sh
podman-compose build ministack-control && podman-compose up -d ministack-control
```

`web/dist` and `web/node_modules` stay gitignored — they are build output, not
sources. The retired server-rendered pages remain reachable at `/classic`.
See [`web/README.md`](web/README.md) for the console's layout, the Cloudscape
pattern-to-screen mapping, the testing setup and the forked dependency repos.
It also records the upstream issue this console is a candidate answer to
([ministackorg/ministack#314](https://github.com/ministackorg/ministack/issues/314)).

Pages: **Dashboard** (`/`), **Resources** (`/resources/:service`), **Favorites**,
**Accounts**, **Onboarding**, **Settings**, **About**.

- **Region selector** — the picker lists the regions the signed-in account
  **enabled** (Settings → Regions; `us-east-1` cannot be disabled). Regions are
  **not** node-based: the single emulator serves every region, so a new account
  starts with `us-east-1` alone and enabling another is one toggle.
- **Credential download** — rotating a key returns `aws_access_key_id` and
  `aws_secret_access_key` once, with **Download .csv**, the same one-time step as
  the AWS console.
- **Tenancy is enforced** — a session may only read or act on **its own** account,
  and only in its enabled regions. `/api/browse`, `/api/exec` and `/api/users`
  return `403` otherwise. The `.env` operator (and the admin bearer token) is the
  one platform administrator that may cross accounts, and it is the only caller
  allowed to provision or delete accounts.
- **Accounts span regions** — a 12-digit account ID is global, exactly like AWS:
  the account selector and the region selector are independent, and one account
  works in every region it enables.
- **Default administrator** — the first account is the platform owner and is
  marked *default*. Once another global admin exists the Dashboard shows a banner
  to disable or delete it; disabling drops its sessions and blocks sign-in, and
  the last enabled global admin cannot be disabled.
- **Actions are CLI calls in a form** — `control/console.py` declares each
  operation, its parameters and the AWS call it maps to. `POST /api/exec` runs it
  signed as the account root, with a confirmation modal for destructive ones.
  Eleven services ship with actions: `s3`, `ec2`, `sqs`, `sns`, `dynamodb`, `iam`,
  `logs`, `secretsmanager`, `ssm`, `kinesis`, `stepfunctions`; every other service
  stays browsable (read-only). Coverage against the 101 upstream services and
  2,519 operations is generated locally by `scripts/upstream_services.py` into the
  gitignored `docs/` folder.
- **Resource tabs** — a service whose browse returns several kinds shows one tab
  per kind (IAM users/roles/groups/policies, EC2 instances/security groups/key
  pairs, and so on), each with its own count.
- **Theme** — system default, light or dark, switchable from the top navigation
  and Settings; the system choice follows the OS preference live.
- **Favorites and recently visited** live in the browser (`localStorage`), keyed by
  the signed-in account (`ministack:favorites:<id>`, `ministack:recent:<id>`), so
  a new account or a wiped database starts with empty lists. Favorites pin
  services in the top navigation.
- **Sessions survive restarts** — live sessions are rows in the `sessions` table
  of `control.db`, and the expiry slides on activity, so a container restart or a
  long working day does not sign you out. Logging out deletes the row.
- **Typed API surface** — `web/src/api.ts` and `web/src/types.ts` are
  TypeScript; the rest of the console is still JS via `allowJs`, so the
  migration is file-by-file with `npm run typecheck` as the gate.
- **Dashboard** — recently visited and favorite services first (each with its
  service icon), endpoint health (console, gateway, emulator), services
  answering, total resources and control uptime.
- **Services** — `/services` lists every service the emulator knows, with a
  label (acronyms upper-case, the rest CamelCase), availability, resource count
  and favorites. Each service opens its own page with a **sidebar of resource
  kinds** (IAM users/roles/groups/policies, EC2 instances/security groups/key
  pairs, …), the action form and the table. The account root is called out as
  not being an IAM user.
- **No Resources page** — the old grouped `/resources` view is gone; `/resources`
  redirects to Services and `/resources/:service` stays as the service detail
  URL.
- **S3 row actions** — select a bucket (radio) and **Delete** it with a
  confirmation modal, or **Create bucket** from the table header; both go
  through `POST /api/exec` like the action form.
- **Region picker** — grouped like the AWS console: friendly name and code, a
  count of regions not enabled, and **Manage regions** jumps to Settings.
- **Onboarding** provisions an account + local login + IAM key in one step and
  shows the secret once. The inviter stays signed in.

> [!NOTE]
> A bucket name is global in MiniStack — one registry reserves it across every
> account and region — but the **bucket** lives in exactly one region: another
> region of the same account does not list it, and a request signed for the wrong
> region is a `301 PermanentRedirect` to its home. Re-creating your own bucket in
> its own region follows AWS: `200` in us-east-1 (ACLs reset) and
> `BucketAlreadyOwnedByYou` elsewhere.

API responses carry `api_version` (`v1`); routes accept both `/api/...` and
`/api/v1/...`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | none | liveness only (`{"status":"ok"}`); counts, uptime, mode and seen regions live in `/api/meta` behind a session |
| GET | `/login` | none | sign-in page |
| POST | `/login` | credentials | start a session |
| GET | `/logout` | session | end a session |
| GET | `/api/meta` | session/token | product, API version, emulator version, enabled regions, visible accounts, session, uptime |
| GET | `/api/actions` | session/token | GUI action catalogue + service groups |
| GET | `/api/counts` | session/token | per-service resource counts for one account/region |
| POST | `/api/exec` | session/token | `{account, region, service, operation, params}` |
| POST | `/api/accounts` | platform admin | provision account + local user + one IAM key |
| DELETE | `/api/accounts/{id}` | platform admin | delete account, logins and IAM users |
| POST | `/api/regions` | session/token | enable/disable a region for an account |
| GET | `/api/nodes` | session/token | nodes + last health |
| GET | `/api/services` | session/token | service availability per node |
| GET | `/api/browse` | session/token | resources for one account/region/service |
| GET | `/api/users` | session/token | accounts, principals, key IDs |
| GET | `/api/accounts/me` | session | this session's user, account, alias, role, name, email |
| POST | `/api/me` | session | update your own name, email and password |
| GET | `/api/credentials` | session | this principal's keys (names, masked ID/secret) |
| GET | `/api/buckets` | session/token | global bucket registry |
| GET | `/api/s3` | session/token | registry + cached inventory |
| POST | `/api/credentials` | session | create, delete or rotate this principal's keys |
| POST | `/api/refresh` | session/token | reconcile the registry from the emulator |
| POST | `/api/reserve` | session/token | reserve `{name, region}` |
| DELETE | `/api/buckets/{name}` | session/token | release a name |
| POST | `/api/nodes/{name}/reset` | session/token | reset the emulator, drop its entries |

## Start

Prerequisite: the emulator is running. `up.sh` refuses to
start the gateway without it.

```sh
./scripts/up.sh           # .env, data dir, pull the image, start
```

The first run creates `.env` from `.env.example` (mode `0600`) and the data
directory if needed. If `MC_ADMIN_TOKEN` or `MC_ADMIN_PASSWORD` is empty, `up.sh`
generates a value and **writes it into `.env` before the container starts** —
nothing is printed, and the values survive a data wipe. Change the password after
the first sign-in. Set them in `.env` yourself to pin your own values.

Starting the container directly (bypassing `up.sh`) is supported only with those
keys already set: an empty `MC_ADMIN_TOKEN` leaves bearer access off, and an empty
`MC_ADMIN_PASSWORD` stops the control with a message rather than seeding an admin
nobody can sign in as.

`up.sh` pulls the image that `MC_IMAGE` names — `compose.yml` defaults it to the
published GHCR tag — and starts the container. The emulator is a separate image
and a separate repository.

**The control owns its data directory** (`MC_DATA_DIR`, `./data` unless `.env`
says otherwise), created by `up.sh` (mode `0755`). It holds one file, `control.db`; there is no migration path from the old
JSON side files. Back up the directory (or take a SQLite copy) while the control
is stopped — it writes on every change, so a live copy can lose data.

`MC_ADMIN_TOKEN` is optional: it is a bearer token for scripted API access, not a
password. Leave it empty and the control generates one on first run, stores it in
`control.db` and prints it once to the container log (`podman logs
ministack-control | grep generated`). Set it to pin your own, e.g.
`python3 -c "import secrets; print(secrets.token_hex(24))"`. Either way the
console session is unaffected.

Nothing here needs `sudo`: the data directory is bind-mounted and created by
your own user.

## Terraform rehearsal (my-portfolio prod)

Values from **Settings → Access keys** (or `GET /api/credentials` after signing
in — the secret itself is only ever returned once, when the key is created).
Write them into your own shell/profile; nothing here is pre-wired:

```sh
cd my-portfolio/terraform/infra/site

export AWS_ENDPOINT_URL=https://ministack.example.com
export AWS_ACCESS_KEY_ID=<the account's access key>
export AWS_SECRET_ACCESS_KEY=<the matching secret>
export AWS_REGION=us-east-1            # any region; the signature carries it
export TF_VAR_environment=prod TF_VAR_project=my-portfolio
export TF_VAR_aws_region=us-east-1
export TF_VAR_allowed_origin=https://mathewmusango.github.io
export TF_VAR_tags='{"project":"my-portfolio","managed_by":"terraform","repo":"mathewmusango/my-portfolio"}'

aws s3 mb s3://my-portfolio-tfstate-prod   # once per reset
terraform init \
  -backend-config="bucket=my-portfolio-tfstate-prod" \
  -backend-config="key=site/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="encrypt=true"
terraform apply
```

The metrics root follows with `key=metrics/terraform.tfstate`. For a different
region, change `AWS_REGION`/`TF_VAR_aws_region` — an S3 bucket lives in exactly
one region, so a state bucket is not visible, and its name is not reusable, in
another.

> [!NOTE]
> **A containerised client resolves names with its own DNS.** When the gateway is
> reached by a hostname through a reverse proxy, that name means something else
> inside a client container. Pass
> `--add-host ministack.example.com:host-gateway`, or put the client on the same
> network and use the container name and port.

## Limits

- The gateway **buffers** request and response bodies (no streaming); fine for
  state files and API payloads, not for multi-GB object transfers.
- Responses that embed a node's own endpoint (e.g. API Gateway execute-api
  URLs) point at that node directly, bypassing the gateway.
- Account **root** keys (the 12-digit ID) are accepted with any secret, by
  design; only issued `AKIA…` keys are verified. The control's own tokens
  authenticate the console, not AWS.
- S3 buckets are region-scoped on the fork image: `ListBuckets` answers per
  region, and a request signed for the wrong region is the `301` AWS returns.

## Operations

```sh
./scripts/up.sh                                   # start (pulls the image)
podman-compose -p ministack-control -f compose.yml ps
podman-compose -p ministack-control -f compose.yml logs -f
podman-compose -p ministack-control -f compose.yml down
```

This stops/starts the **control plane** only. The emulator runs from its own
compose file, in its own repository, and these commands never touch it.

Reset the emulator from the dashboard or `POST /api/nodes/ministack/reset`;
that clears its registry entries and starts the next scan clean.

## Files

- [`compose.yml`](compose.yml) — the control plane (gateway + console).
- [`control/app.py`](control/app.py) — gateway, console pages, control API.
- [`control/console.py`](control/console.py) — the GUI action catalogue and the
  AWS calls each operation maps to.
- `docs/` — **my notes, not committed** (gitignored): product positioning, the deferred-feature roadmap, and the generated coverage report from `scripts/upstream_services.py`.
- [`web/`](web/) — the React + Cloudscape console (its own README).
- [`scripts/qa_check.py`](scripts/qa_check.py) — QA gate: secrets, Python compile, and the signed-off markers from a **local** `qa/tasks.json` (gitignored).
- [`scripts/up.sh`](scripts/up.sh) — seed `.env`, build + start the control plane, readiness.
- [`.env.example`](.env.example) — settings template; `.env` is generated (gitignored).
- The emulator lives in [`../ministack`](../ministack).

`qa/` and `addons/` are local-only and gitignored: the QA evidence ledger, and the
lab's Gatus/Prometheus/Grafana declarations that the monitoring services collect
from this working tree. They are not part of the product repository.

> [!NOTE]
> The fields and naming above come from `services/README.md`. Scaffold new
> services with `./scripts/new-service` rather than copying an existing one.

## References

- [MiniStack documentation](https://ministack.org/docs/)
- [Multi-tenancy (accounts and regions)](https://ministack.org/docs/multi-tenancy)
- [MiniStack on GitHub](https://github.com/ministackorg/ministack)
- [StackPort (UI inspiration)](https://github.com/DaviReisVieira/stackport)
