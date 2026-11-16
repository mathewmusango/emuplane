# Security policy

Emuplane is a local lab — a control plane, console and gateway in front of an AWS
emulator. It authenticates the people who use the console and issues the keys
clients sign with. It is not hardened against the internet, and this page says so
rather than implying otherwise.

## The trust model, stated plainly

- Console sessions are stored as digests, and so is the API bearer token; neither
  is recoverable from the store.
- Access keys issued in the console (`AKIA…`) are verified. A 12-digit account key
  is that account's **root** and is accepted with any secret.
- **The gateway does not verify SigV4 signatures.** It resolves the account from
  the access key and enforces region enablement; it is a router with an
  authorisation rule, not an authenticator.
- One account cannot see another's state. The deployment bearer token is the only
  cross-tenant caller, and it belongs to an operator, not to a login.

Deploy it on a lab network, or behind an authenticating proxy. Emuplane exposed
directly to the internet is a configuration choice, not a supported deployment.

## Reporting a vulnerability

Use **Security → Report a vulnerability** on this repository — it opens a private
advisory only you and the maintainer can see — or
[email](mailto:musangomathew@gmail.com).

Please do not open a public issue, and do not post a working exploit in
Discussions. Any other question about the model — how a rule is meant to behave,
why something is refused — is welcome in
[Discussions](https://github.com/mathewmusango/emuplane/discussions).

A report is easiest to act on with the version or commit, what you did, what
happened and what you expected. This is a single-maintainer project: reports are
acknowledged as soon as they are read, and fixes ship in the next release rather
than on a contractual timeline.

## In scope

- Crossing the tenancy boundary: one account reading or changing another's state.
- An authentication or session bypass in the console or the control API.
- Path traversal in the console's static serving or in an object download.
- Script injection in the server-rendered sign-in, reset or error pages.
- A password-reset link that works twice, or outlives `EP_RESET_SECONDS`.
- A gateway rule that can be bypassed: a resource in a region the account has not
  enabled, or one name claimed by two accounts.

## Out of scope

- Exposing the deployment to the internet without an authenticating proxy in front.
- The emulator's own behaviour where Emuplane is not involved — report those
  upstream.
- The absence of signature verification, described above: it is the design, and
  the lab is sized to it.
- Anything that depends on the operator having published the deployment, or having
  put a credential somewhere this repository says not to.

## Supported versions

Only the latest release. Emuplane is pre-1.0, versions are cut from `main`, and
`CHANGELOG.md` names what changed.
