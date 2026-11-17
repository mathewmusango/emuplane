<h1 align="center">Emuplane</h1>
<p align="center"><strong>The control plane, console and gateway for AWS-compatible emulators.</strong></p>

<p align="center">
  <a href="https://mathewmusango.github.io/emuplane/"><img src="https://img.shields.io/badge/docs-emuplane-blue" alt="Documentation"></a>
  <a href="https://github.com/mathewmusango/emuplane/actions/workflows/release.yml"><img src="https://github.com/mathewmusango/emuplane/actions/workflows/release.yml/badge.svg" alt="Release"></a>
  <a href="https://github.com/mathewmusango/emuplane/actions/workflows/semgrep.yml"><img src="https://github.com/mathewmusango/emuplane/actions/workflows/semgrep.yml/badge.svg" alt="Semgrep"></a>
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
  <img src="https://img.shields.io/badge/python-3.13-blue" alt="Python">
  <a href="https://github.com/users/mathewmusango/packages/container/package/emuplane"><img src="https://img.shields.io/badge/ghcr.io-emuplane-blue?logo=github" alt="ghcr.io"></a>
</p>

---

Emuplane is not an emulator, and not a replacement for AWS. It is what you put in
front of one — [MiniStack](https://github.com/ministackorg/ministack),
[LocalStack](https://github.com/localstack/localstack), [Floci](https://github.com/floci-io/floci) or
[moto](https://github.com/getmoto/moto).

It is what makes an emulator usable by more than one person: it holds the
accounts and the logins inside them, issues the access keys clients sign with,
serves the console and control API, and is the endpoint Terraform and the AWS
CLI point at. Those accounts, logins and access keys are rows in the **emulator's
DynamoDB**, in tables a CloudFormation stack creates on the first deployment —
never files on the host.

Currently tested on MiniStack only; the others are profiles, not verified
targets.

```bash
cp .env.example .env        # set EP_BACKEND_URL to the backend's endpoint
podman-compose up -d        # or: docker compose up -d
```

Or bring the emulator along: `docker-compose.all.yml` with `.env.all.example`
runs MiniStack, the first-setup job and the control as one stack.

`bootstrap` runs first and applies the CloudFormation stack that owns the control's
DynamoDB tables; the console then answers on `http://localhost:4570`.

More: [Quickstart](https://mathewmusango.github.io/emuplane/docs/getting-started/quickstart)
— the emulator first, then the first account and the first bucket.

Nothing is seeded: create the first account at `/signup`. The API bearer token is
optional: mint one with `python /app/api_token.py` inside the container when
something other than the console needs the control API.

## Accessing it

| What | On the host | In the compose network | Behind a proxy |
| --- | --- | --- | --- |
| Console and control API | `http://localhost:4570/` | `http://emuplane:4570` | `EP_CONSOLE_URL` |
| AWS gateway | `http://localhost:4571` | `http://emuplane:4571` | `EP_GATEWAY_URL` |

```bash
export AWS_ENDPOINT_URL=http://localhost:4571
export AWS_ACCESS_KEY_ID=<the key id from the console>
export AWS_SECRET_ACCESS_KEY=<the secret, shown once>
aws s3 ls
```

The host ports bind `127.0.0.1` and the backend is never published — a client wants
the gateway, never the emulator. An issued `AKIA…` key is verified; the 12-digit
account id is that account's root and is accepted with any secret.

More: [Accessing it](https://mathewmusango.github.io/emuplane/docs/getting-started/access)
— the per-command form, the region rule, and the two kinds of key.

## Documentation

| Page | What it covers |
| --- | --- |
| [Quickstart](https://mathewmusango.github.io/emuplane/docs/getting-started/quickstart) | two containers, one sign-in, one bucket |
| [Accessing it](https://mathewmusango.github.io/emuplane/docs/getting-started/access) | the console and the CLI, by URL and by `host:port` |
| [Access keys](https://mathewmusango.github.io/emuplane/docs/getting-started/access-keys) | minting a key and using it from the CLI |
| [Architecture](https://mathewmusango.github.io/emuplane/docs/concepts/architecture) | the gateway, the control plane and the emulator |
| [Accounts, regions and keys](https://mathewmusango.github.io/emuplane/docs/concepts/tenancy) | tenancy, region enablement, credentials |
| [S3](https://mathewmusango.github.io/emuplane/docs/guides/s3) | the console's S3 pages |
| [Control API](https://mathewmusango.github.io/emuplane/docs/reference/control-api) | every console route |
| [Configuration](https://mathewmusango.github.io/emuplane/docs/reference/configuration) | every `EP_` setting |
| [Limits](https://mathewmusango.github.io/emuplane/docs/reference/limits) | what this deliberately does not do |
| [S3 coverage](https://mathewmusango.github.io/emuplane/docs/reference/s3-coverage) | every operation, and whether the console shows it |

## The emulator is a separate project

A backend is a **profile** in [`control/backends.py`](control/backends.py): a display
name, a default port and the quirks worth knowing. `EP_BACKEND` selects it and
`EP_BACKEND_URL` is the connection string, so changing backend is a `.env` change,
not a copy of this repository.

The reference backend is [MiniStack](https://github.com/ministackorg/ministack), run
as its published image: `ministackorg/ministack:1.5.40-full`.

## Layout

| Path | What it is |
| --- | --- |
| [`control/`](control) | gateway, console pages, control API |
| [`web/`](web) | the React + Cloudscape console (its own README) |
| [`site/`](site) | the documentation site |
| [`bootstrap/`](bootstrap) | the CloudFormation template and init job for the control's tables |
| [`scripts/`](scripts) | the QA gate and the maintainer's helpers |
| [`docker-compose.yml`](docker-compose.yml) | the container contract |

## References

- [MiniStack documentation](https://ministack.org/docs/)
- [MiniStack on GitHub](https://github.com/ministackorg/ministack)
- [StackPort (UI inspiration)](https://github.com/DaviReisVieira/stackport)
