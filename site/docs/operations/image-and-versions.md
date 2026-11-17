---
sidebar_position: 2
title: Image and versions
---

The image is `ghcr.io/mathewmusango/emuplane:<version>`, built and pushed by
`.github/workflows/release.yml` on every `v*` tag, together with the GitHub
Release.

| Bump | When | Example |
| --- | --- | --- |
| minor | a feature | `0.1.0` → `0.2.0`, up to `0.10.0` |
| patch | a dependency PR | `0.1.0` → `0.1.10` |
| major | by hand | `0.1.0` → `1.0.0` |

The git tag carries a `v` (`v0.1.0`); the image tag does not (`0.1.0`). `latest`
follows the newest tag, and `docker-compose.yml`'s default image is the release
version itself — the release pull request rewrites it, and `scripts/units.py --check`
refuses a release where the two disagree.

## These docs are versioned the same way

Every release gets a frozen copy of these pages, so a reader on an old version
sees the pages that matched that tag:

```bash
cd site
npm run version 0.1.0
```

That copies `site/docs/` into `site/versioned_docs/version-0.1.0/` and writes
`versions.json`; `site/docs/` then becomes **Next**.

## Building the image locally

```bash
./scripts/build.sh              # incremental, cached
./scripts/build.sh --no-cache   # ignore the layer cache (base-image bump)
```

The Dockerfile is built to be cheap to rebuild: `npm ci` sits before `COPY web/`,
npm's and Vite's caches are `--mount=type=cache` so neither lands in a layer, and
the runtime image carries the built console without node_modules or a toolchain.
