# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
the minor number is bumped by hand, patch releases are the bot's.

## [Unreleased]

### Added

- Console: the five AWS sign-in screens — user type (root / IAM) → email or
  account ID → password → MFA code — as one `/signin` route in
  `web/src/pages/SignIn.jsx`, submitting to `web/src/authStub.js` until the
  control plane's auth endpoints land (ARCHITECTURE.md slice 3). The code screen
  appears only when the principal has MFA enabled (`?mfa=1` in the preview). The
  route is served without a session (`PUBLIC_SPA_ROUTES`) and linked from the
  classic login page; `/login` stays server-rendered, because it is the only form
  that mints a session today.
- CI: shared check leaves (python, js, shell, yaml, docker), a Vitest + `tsc`
  suite for `web/`, the security leaves (`dependency-review`, `pip-audit`,
  `npm-audit`), CodeQL and Semgrep.
- Release: the image is built, scanned with Trivy, and only then pushed to
  GHCR — a failing scan never leaves a tag behind. The GitHub release follows
  the image, and a tag that is not the tip of `main` is refused.
- `dependabot.yml` (github-actions + `web/` npm, 7-day cooldown, minor/patch
  grouped), `renovate.json` for the Dockerfile base-image digests, `ruff.toml`,
  and the issue/PR templates.

### Changed

- **Sign-up is email-verified.** Email + account name first; the control mails a
  six-digit one-time password through the backend's SES (verifying its own sender
  identity once), keeps only the code's digest in the settings store with a
  15-minute expiry and five attempts, and creates the account once the code
  arrives. The password is collected on the first screen and travels as its
  PBKDF2 hash inside the pending record, so the second step asks for the code
  alone and no plaintext password leaves that request. `/mailbox?token=…` renders the message it just sent, scoped to
  that pending sign-up, so the flow works without a mail client; the backend's SES
  mailbox still holds the authoritative copy.
- **Both auth pages put their two actions on one line with OR between them.**

- **The sign-in page carries a theme switch.** It follows the system by default
  (`system` is the stored preference), and a click pins light or dark under
  `emuplane:theme` — shared with the console's own toggle. `signin.css` colours the
  page frame from the body's `awsui-dark-mode` class, so the space around the card
  matches the mode rather than the OS query.

- **The project is Emuplane, and it is not tied to one backend.** Renamed from
  MinStack Control: the image is `ghcr.io/mathewmusango/emuplane`, the stack and its
  tables are `emuplane` / `emuplane-*`, the cookie is `emuplane_session`, browser keys
  are `emuplane:*`, and every setting uses the `EP_` prefix (`EP_BACKEND_URL`,
  `EP_CONSOLE_URL`, `EP_PORT`, `EP_GATEWAY_PORT`, `EP_PUBLISHED_GATEWAY_PORT`, …).
- **A backend is a profile.** `control/backends.py` holds one row per backend —
  `generic`, `ministack`, `floci`, `localstack`, `moto` — with its display name,
  default port and logo. `EP_BACKEND` selects it and `EP_BACKEND_URL` is the
  connection string; `/api/meta` reports `backend`, `backend_id` and `backend_logo`,
  so the console wears the backend's own mark after sign-in while the sign-in pages
  carry Emuplane's.
- **The gateway listens on 8081, not 4566.** The control's own listener no longer
  reuses the backend's port: `EP_GATEWAY_PORT=8081` inside the container, published
  on `EP_PUBLISHED_GATEWAY_PORT=4571`, forwarding to the backend's `EP_BACKEND_PORT`.

### Changed

- **The API bearer token is a hashed record, not a setting.** `EP_ADMIN_TOKEN` is
  gone from `.env`: `./scripts/token.sh` mints a token, prints it once and stores
  only a SHA-256 digest in the settings store, the same contract as a session.
  Rotation invalidates the previous token immediately, and a running control
  re-reads the digest per request so a rotation takes effect without a restart.
  A fresh install therefore carries **no credential in any file**.
- **The sign-in screens are the login page.** `/login` is served by the console
  (`PUBLIC_SPA_ROUTES`) and the server-rendered form is gone; `POST /api/auth/login`
  verifies root (email or username) and IAM (account + username) credentials, checks
  the account and root-credential flags, and sets the session cookie. `mfa_required`
  comes from the answer, and `POST /api/auth/mfa` answers 501 until enrolment exists.
  `web/src/authStub.js` is deleted — the screens call the real endpoint.
- **Optional settings have defaults.** `MINISTACK_NODE_NAME` defaults to the
  emulator's compose service name, and `EP_STORE_ACCOUNT` / `EP_STORE_REGION` /
  `EP_STORE_URL` default inside the store client — a `.env` only has to name the
  emulator endpoint and the two public addresses users are shown. `bootstrap/apply.py`
  gained `--drop-tables`: the one-off that deletes the stack and every control table,
  which is the only way to return a pre-stack installation to a first setup.
- **The control's own substrate is provisioned by CloudFormation.**
  `bootstrap/template.yml` defines its ten DynamoDB tables as the stack
  `emuplane`; `bootstrap/apply.py` applies it as a first-setup init job
  (`docker-compose.yml`'s `bootstrap` service, run by `scripts/up.sh` before the
  console starts) and is idempotent. `control/store.py` no longer creates tables —
  it verifies them and refuses to serve, naming any that are missing. Tables that
  predate the stack are reported rather than adopted.
- **A fresh control has no accounts at all.** The seeded bootstrap administrator
  (`MC_ADMIN_USER` / `_EMAIL` / `_PASSWORD`) is retired: the only way in is
  sign-up, and the first account created becomes the platform owner, as AWS does
  it. Nothing is seeded from `.env` any more except the optional API bearer token.
- **The deployment is stateless.** `MC_DATA_DIR` and the `/var/lib/ministack/control`
  bind mount are gone; the running container mounts nothing from the host.
- The compose files were renamed: the generic definition is `docker-compose.yml`,
  and the untracked deployment overlay is `compose.yml` — `scripts/up.sh` layers
  it by default, or whatever `EP_OVERLAY` names.
- CI now calls the shared workflow leaves — `checks-*`, `tests-vitest`,
  `release-image-ghcr`, `release-github`, `security-dependency-review` and
  `security-npm-audit` — pinned at
  `my-workflows@v2026.1112.2318Z`, instead of carrying copies of their logic.
  The release leaf builds and scans before it pushes; the tag-must-be-`main`
  guard stays local because a tag ruleset cannot express it.
- `checks.yml` grants `pull-requests: read`: the leaves use `dorny/paths-filter`,
  and a called workflow can only downgrade the token it is given.
- `docker-compose.yml` is generic: the image comes from `EP_IMAGE` (default: the
  published GHCR tag), ports and the data directory have defaults, `.env` is
  optional, and no container names, hostnames or routes are baked in. A private
  `compose.yml` (gitignored) layers the names, routes and mounts of a
  specific deployment on top.
- `scripts/up.sh` pulls instead of building, and layers the overlay when it is
  present.
- README rewritten around what this service is, how a client gets credentials,
  and how accounts and regions are separated.
