---
sidebar_position: 3
title: Releasing and the changelog
---

`CHANGELOG.md` is built from **issues**, not from commits. An issue's labels pick
its section, and its title becomes the bullet — so the changelog reads the same
whatever the code is written in.

## The label decides the section

| Label | Section |
| --- | --- |
| `added`, `feature`, `enhancement` | Added |
| `changed`, `improvement` | Changed |
| `deprecated` | Deprecated |
| `removed` | Removed |
| `fixed`, `bug` | Fixed |
| `security` | Security |

`chore`, `skip-changelog`, `internal`, `question`, `duplicate`, `invalid` and
`wontfix` are left out, and so is an issue closed as **not planned**. The map lives
in [`.github/changelog.json`](https://github.com/mathewmusango/emuplane/blob/main/.github/changelog.json),
so a label is added in one place.

## A release

Before tagging:

```bash
GITHUB_TOKEN=… python3 scripts/changelog.py --version v0.2.0 --write
```

That reads every issue closed since the previous tag, groups it, and inserts the
section between `Unreleased` and the newest release. Without `--write` it prints
the section to stdout, which is the way to read it first.

Then tag the commit the section is in. The release workflow refuses a tag whose
commit is not the tip of `main`, and refuses one with no section for that tag:

```bash
python3 scripts/changelog.py --version v0.2.0 --check
```

## Two gates in CI

- **A pull request must name the issue it closes** — `Closes #12`, `Fixes #7`,
  `Resolves #3`. Without the link the change never reaches the changelog, so the
  workflow refuses it. Dependency bots are exempt: they have no issue to link.
- **An issue must carry a changelog label** — one from the table above, or an
  exclusion label such as `chore` or `skip-changelog`. Without it the issue would
  fall into a default section, so the workflow refuses it.

Both rules are `scripts/triage.py`, tested in `tests/changelog/`, so the regex lives
in one place rather than in the workflow YAML.

## Writing a bullet that reads well

The default bullet is the issue title. When the title is written for the tracker
rather than for a reader, put a line in the issue body:

```
Changelog: The gateway resolves the account from the access key, not from the header order.
```

That line becomes the bullet; the title stays however the tracker wants it.
