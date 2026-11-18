# Emuplane documentation site

The Docusaurus site published at <https://mathewmusango.github.io/emuplane/>.
One frozen copy of these pages is kept per release.

```bash
npm install
npm run start     # http://localhost:3000
npm run build     # the static site, in build/
```

## Generated pages

| Page | Generated from | Command |
| --- | --- | --- |
| `docs/reference/control-api.md` | the control's route dispatcher | `npm run api` |
| `docs/reference/s3-coverage.md` | `coverage/s3.json` + the emulator README | `npm run coverage` (`../scripts/coverage.py`) |

Both read the repository this directory lives in; CI re-runs them and fails on a diff.
Adding a service is a `coverage/<service>.json` data file, not another script.

## Cutting a version

```bash
npm run version 1.5.40
```

That copies `docs/` into `versioned_docs/version-1.5.40/` and writes `versions.json`;
`docs/` then becomes Next.

## Publishing

Push to `main`, or push a `v*` tag: the `docs` workflow builds on every pull request
and publishes on `main` and on tags.
