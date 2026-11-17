---
sidebar_position: 3
title: Configuration
---

Settings use the `EP_` prefix and nothing else. The backend's own settings keep
their own names in the backend's `.env`; Emuplane never writes there.

## Two kinds of setting

That split is the porting contract:

- **Container settings** — read at runtime, and `docker-compose.yml` passes
  exactly this set. A Kubernetes ConfigMap is the same names and values, and a
  deployment may supply only what it needs because every other key has a default.
- **Deployment settings** — image, network, container names and published ports.
  `up.sh` and `token.sh` use them; they are never injected into the container.

## Container settings

| Key | Default | What it does |
| --- | --- | --- |
| `EP_BACKEND` | `generic` | backend profile: `generic`, `ministack`, `floci`, `localstack`, `moto`; only `ministack` is tested |
| `EP_BACKEND_URL` | required | the emulator endpoint the control talks to |
| `EP_CONSOLE_URL` | required | the address a browser uses; without a reverse proxy that is `http://localhost:4570` |
| `EP_GATEWAY_URL` | required | the address clients sign against; without a reverse proxy that is `http://localhost:4571` |
| `EP_PORT` | `4570` | console and control API port, the same inside the container and on the host |
| `EP_GATEWAY_PORT` | `4571` | gateway port, the same inside the container and on the host |
| `EP_STORE_ACCOUNT` | `111111111111` | account the control reads its own DynamoDB tables as |
| `EP_STORE_REGION` | `us-east-1` | region those tables live in |
| `EP_STORE_URL` | empty | where the control's own tables live; **empty means `EP_BACKEND_URL`**, so repointing the backend moves the accounts with it |
| `EP_POLL_SECONDS` | `10` | seconds between emulator health polls |
| `EP_SESSION_SECONDS` | `28800` | session lifetime, extended on activity |
| `EP_RECENT_LIMIT` | `5` | services under **Recently visited** |
| `TZ` | `Africa/Nairobi` | zone the console renders timestamps in |

Mail is optional, for the password-reset link:

| Key | Default | What it does |
| --- | --- | --- |
| `EP_MAIL_HOST` | empty | relay for the reset mail; **empty means mail is off** and `/forgot` falls back to an administrator-issued link |
| `EP_MAIL_PORT` | `587` | relay port (`465` with `EP_MAIL_SECURITY=ssl`) |
| `EP_MAIL_SECURITY` | `starttls` | `starttls`, `ssl`, or `none` for a local relay |
| `EP_MAIL_USER` / `EP_MAIL_PASSWORD` | empty | relay credentials; the password is a secret and belongs in `.env` only |
| `EP_MAIL_FROM` | empty | From header |
| `EP_RESET_SECONDS` | `1800` | how long a reset link stays valid |

## Nothing secret in `.env`

There is no seeded account and no pre-set token. Accounts come from sign-up. The
bearer token is optional: `./scripts/token.sh` mints one when a script needs the
control API, prints it once, and stores only a SHA-256 hash in the settings
store.
