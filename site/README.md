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

The **Docs** tab points at `/docs/next/` on purpose, so the working pages are the
ones a reader lands on; revert it to `{type: 'docSidebar', sidebarId: 'docs'}` at
the next version freeze, or a frozen release stays the site's front door.

The navbar is shared by every frozen version, so each
`versioned_sidebars/version-X-sidebars.json` carries the same three sidebars,
listing only the pages that version has. `npm run version` snapshots the current
`sidebars.js`, so a new version needs no editing; the older ones were backfilled
once, by hand.

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
