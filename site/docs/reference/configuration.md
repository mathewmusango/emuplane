---
sidebar_position: 3
title: Configuration
---

Settings use the `EP_` prefix and nothing else. The backend's own settings keep
their own names in the backend's `.env`; Emuplane never writes there.

## Two kinds of setting

That split is the porting contract:

- **Container settings** — read at runtime, and
  [`docker-compose.yml`](https://github.com/mathewmusango/emuplane/blob/main/docker-compose.yml)
  passes exactly this set; a deployment may supply only what it needs because every
  other key has a default.
- **Deployment settings** — image, network, container names and published ports.
  They never reach the container.

## Container settings

| Key | Default | What it does |
| --- | --- | --- |
| `EP_BACKEND` | `ministack` | backend profile; `ministack` is the tested one (MiniStack 1.5.40-full), and `generic` is the neutral fallback for an emulator this repository has not been tested against |
| `EP_BACKEND_URL` | `http://localhost:4566` | the emulator endpoint the control talks to; the default is the single-host lab, and a container sets its own because `localhost` there is the container |
| `EP_CONSOLE_URL` | `http://localhost:4570` | the address a browser uses; set it to the proxy's address behind one |
| `EP_GATEWAY_URL` | `http://localhost:4571` | the address clients sign against; set it to the proxy's address behind one |
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
