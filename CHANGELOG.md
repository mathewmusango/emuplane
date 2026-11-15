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
  control plane's auth endpoints land (ARCHITECTURE.md slice 3). Dev-server
  only for now: the server still owns `/login`.
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

- The compose files were renamed: the generic definition is `docker-compose.yml`,
  and the untracked deployment overlay is `compose.yml` — `scripts/up.sh` layers
  it by default, or whatever `MC_OVERLAY` names.
- CI now calls the shared workflow leaves — `checks-*`, `tests-vitest`,
  `release-image-ghcr`, `release-github`, `security-dependency-review` and
  `security-npm-audit` — pinned at
  `my-workflows@v2026.1112.2318Z`, instead of carrying copies of their logic.
  The release leaf builds and scans before it pushes; the tag-must-be-`main`
  guard stays local because a tag ruleset cannot express it.
- `checks.yml` grants `pull-requests: read`: the leaves use `dorny/paths-filter`,
  and a called workflow can only downgrade the token it is given.
- `docker-compose.yml` is generic: the image comes from `MC_IMAGE` (default: the
  published GHCR tag), ports and the data directory have defaults, `.env` is
  optional, and no container names, hostnames or routes are baked in. A private
  `compose.yml` (gitignored) layers the names, routes and mounts of a
  specific deployment on top.
- `scripts/up.sh` pulls instead of building, and layers the overlay when it is
  present.
- README rewritten around what this service is, how a client gets credentials,
  and how accounts and regions are separated.
