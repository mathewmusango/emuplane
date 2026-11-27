---
sidebar_position: 2
title: Image and versions
---

The image is `ghcr.io/mathewmusango/emuplane:<version>`, built and pushed by
`.github/workflows/release.yml` on every `v*` tag, together with the GitHub
Release.

| Bump | When | Example |
| --- | --- | --- |
| minor | a feature | `0.6.1` → `0.7.0` |
| patch | a dependency PR | `0.6.1` → `0.6.2` |
| major | by hand | `0.6.1` → `1.0.0` |

Below `1.0.0` a removal moves the **minor** number instead, because SemVer reserves
the leading number for the first stable API. The number is computed from issue
labels, and that rule lives in one place:
[Releasing and the changelog](releases.md#choosing-the-version).

The git tag carries a `v` (`v0.6.1`); the image tag does not (`0.6.1`). `latest`
follows the newest tag, and every compose file pins the release version itself —
the release pull request rewrites the pins, and `scripts/units.py --check` refuses a
release where any of them disagrees.

## These docs are versioned the same way

Every release gets a frozen copy of these pages, so a reader on an old version
sees the pages that matched that tag:

```bash
cd site
npm run version X.Y.Z
```

That copies `site/docs/` into `site/versioned_docs/version-X.Y.Z/` and writes
`versions.json`; `site/docs/` then becomes **Next**.

## Building the image locally

```bash
./scripts/build.sh              # incremental, cached
./scripts/build.sh --no-cache   # ignore the layer cache (base-image bump)
```

The Dockerfile is built to be cheap to rebuild: `npm ci` sits before `COPY web/`,
npm's and Vite's caches are `--mount=type=cache` so neither lands in a layer, and
the runtime image carries the built console without node_modules or a toolchain.
