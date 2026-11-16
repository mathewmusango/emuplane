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

## Creating the labels

`.github/changelog.json` is the source of truth for both the gates and the
sections, so the repository's labels are derived from it:

```bash
python3 scripts/changelog.py --create-labels --dry-run   # say what is missing
python3 scripts/changelog.py --create-labels             # create it, leaving the rest alone
```

It is idempotent: a label that already exists is never touched, so colours edited
in the GitHub UI survive. It needs an authenticated `gh` and nothing else.

## `Unreleased`, and the first release

`--write` never invents a section for a version already in the file, and it never
touches `Unreleased`. So the two kinds of entry stay distinct:

- **`Unreleased` is the human scratchpad** — notes that matter before an issue
exists. It is yours to edit.
- **A released section is either generated from that release's issues, or authored.**
  The first release is authored, because it predates the issue convention.
- **Never both for the same change.** At release time the pending notes either
  become issues (and the section is generated) or the section is written by hand.
  A generated section that repeats an `Unreleased` bullet is the signal that a note
  should have become an issue.

The first release also measures from the repository's first commit, not from a tag
that does not exist yet, so `--since` is optional there too.

## Writing a bullet that reads well

The default bullet is the issue title. When the title is written for the tracker
rather than for a reader, put a line in the issue body:

```
Changelog: The gateway resolves the account from the access key, not from the header order.
```

That line becomes the bullet; the title stays however the tracker wants it.
