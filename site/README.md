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
| `docs/reference/s3-files-coverage.md` | `coverage/s3-files.json` + the emulator README | `npm run coverage` |
| `docs/reference/iam-coverage.md` | `coverage/iam.json` + the emulator README | `npm run coverage` |
| `docs/reference/account-coverage.md` | `coverage/account.json` + the emulator README | `npm run coverage` |
| `src/pages/changelog.md` | `../CHANGELOG.md` | `npm run changelog` |

They read the repository this directory lives in; CI re-runs them and fails on a diff.
Adding a service is a `coverage/<service>.json` data file, not another script.

## Navigation

`sidebars.js` is one sidebar per navbar tab — **Docs** (tutorial, concepts,
guides), **Reference** (coverage, configuration, limits) and **API** (the
generated route table). A page belongs to exactly one of them. **Changelog** is a
link rather than a sidebar: its page lives in `src/pages/`, outside `docs/`, so
freezing a version does not freeze the changelog.

The **Docs** tab reads the `docs` sidebar, so it follows whichever version the
site serves. While the working docs are unfrozen, a reader who wants them takes
**Next** from the version menu — do **not** hardcode `/docs/next/` in the navbar:
the freeze that makes it wrong is the release, and nobody remembers then.

The navbar is shared by every frozen version, so each
`versioned_sidebars/version-X-sidebars.json` carries the same three sidebars,
listing only the pages that version has. `npm run version` snapshots the current
`sidebars.js`, so a new version needs no editing; the older ones were backfilled
once, by hand.

The working docs are the next release, so the version menu labels them with the
number a patch release would take — `0.3.2` while `0.3.1` is the newest release —
derived from `versions.json` in `docusaurus.config.js`. The dev server still calls
them **Next**, where they genuinely are a draft. The route stays `/docs/next/`:
renaming it to the label would collide with the copy the next freeze creates.

## Screenshots

`static/img/console/` is the console as it renders, captured from a control plane
running locally against MiniStack with a seeded demo account. The untracked
`qa/shots/capture.py` does it: it boots both servers, signs up a demo account,
creates the buckets and objects the pictures show, then drives Firefox through
the pages with Selenium. `static/img/sign-in.png` and `static/img/services.png`
are the two shots the README and the sign-in pages share.

## Cutting a version

```bash
npm run version 1.5.40
```

That copies `docs/` into `versioned_docs/version-1.5.40/` and writes `versions.json`;
`docs/` then becomes Next.

## Publishing

Push to `main`, or push a `v*` tag: the `docs` workflow builds on every pull request
and publishes on `main` and on tags.
