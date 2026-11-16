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

Emuplane is not an emulator. It is what you put in front of one — [MiniStack](https://github.com/ministackorg/ministack),
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
./scripts/up.sh
```

The first run creates `.env` from `.env.example`, applies the CloudFormation stack
that owns the control's DynamoDB tables, pulls the image and starts the console on
`http://localhost:4570`.

Nothing is seeded: create the first account at `/signup`. The API bearer token is
optional: mint one with `./scripts/token.sh` when something other than the console
needs the control API.

## Documentation

| Page | What it covers |
| --- | --- |
| [Quickstart](https://mathewmusango.github.io/emuplane/docs/getting-started/quickstart) | two containers, one sign-in, one bucket |
| [Architecture](https://mathewmusango.github.io/emuplane/docs/concepts/architecture) | the gateway, the control plane and the emulator |
| [Accounts, regions and keys](https://mathewmusango.github.io/emuplane/docs/concepts/tenancy) | tenancy, region enablement, credentials |
| [S3](https://mathewmusango.github.io/emuplane/docs/guides/s3) | the console's S3 pages |
| [Runbook](https://mathewmusango.github.io/emuplane/docs/operations/runbook) | start, operate, the dev loop |
| [Control API](https://mathewmusango.github.io/emuplane/docs/reference/control-api) | every console route |
| [Configuration](https://mathewmusango.github.io/emuplane/docs/reference/configuration) | every `EP_` setting |
| [Limits](https://mathewmusango.github.io/emuplane/docs/reference/limits) | what this deliberately does not do |
| [S3 coverage](https://mathewmusango.github.io/emuplane/docs/reference/s3-coverage) | every operation, and whether the console shows it |

## The emulator is a separate project

A backend is a **profile** in [`control/backends.py`](control/backends.py): a
display name, a default port and the quirks worth knowing. `EP_BACKEND` selects
it and `EP_BACKEND_URL` is the connection string, so changing backend is a `.env`
change, not a fork of this repository.

The reference backend is a fork of MiniStack with S3 region isolation —
[why, and what differs](https://mathewmusango.github.io/emuplane/docs/comparison/ministack-and-the-fork).

## Layout

| Path | What it is |
| --- | --- |
| [`control/`](control) | gateway, console pages, control API |
| [`web/`](web) | the React + Cloudscape console (its own README) |
| [`site/`](site) | the documentation site |
| [`bootstrap/`](bootstrap) | the CloudFormation template and init job for the control's tables |
| [`scripts/`](scripts) | `up.sh`, `build.sh`, `token.sh`, `qa_check.py` |
| [`docker-compose.yml`](docker-compose.yml) | the container contract |

## References

- [MiniStack documentation](https://ministack.org/docs/)
- [MiniStack on GitHub](https://github.com/ministackorg/ministack)
- [StackPort (UI inspiration)](https://github.com/DaviReisVieira/stackport)
