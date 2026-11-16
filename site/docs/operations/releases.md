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

## Choosing the version

The bump comes from the issue labels, so the version and the changelog have one
source. `.github/changelog.json` carries a `bump` per section:

| Section | Bump | Why |
| --- | --- | --- |
| Added, Changed, Deprecated | minor | new behaviour, nothing existing breaks |
| Removed | major | something that existed is gone |
| Fixed, Security | patch | the behaviour it already claimed is restored |

The **highest** bump among the release's issues wins and the lower numbers reset: a
feature on `1.4.2` is `1.5.0`, a removal on `1.4.2` is `2.0.0`.

Below `1.0.0` a removal moves the **minor** number instead — `0.1.0` → `0.2.0` —
because SemVer reserves the leading number for the first stable API. This project is
pre-1.0 and says so.

```bash
GITHUB_TOKEN=… python3 scripts/changelog.py --next-version            # what the issues imply
GITHUB_TOKEN=… python3 scripts/changelog.py --next-version --version v0.1.0
```

With no tag and no flag it starts from `0.0.0`, which is what the first release
needs. It prints a number and writes nothing.

**Why not Release Please, semantic-release or git-cliff.** All three derive the
version — and the entries — from commits. Here the unit is the issue, so a commit
prefix would be a second source of truth for one decision: a `fix:` commit closing
a `removed` issue would compute the wrong number. git-cliff answers a different
question ("what changed in the code"); it becomes interesting after Rust lands, for
per-crate notes from conventional commits, not for this changelog.

### Press to release

`.github/workflows/release-now.yml` is the unattended path, started by hand. It
reads the issues, writes the section, commits `Release v0.1.0`, tags that commit,
and dispatches `release.yml` **at the tag** — which is where the image takes its
semver tag from. GitHub exempts `workflow_dispatch` from the `GITHUB_TOKEN`
recursion rule, so no personal token is needed.

```bash
gh workflow run release-now.yml          # or Actions → "Release: now" → Run workflow
```

It refuses a minor or a major unless `force` is set, and it is idempotent: when the
section is already in `CHANGELOG.md` it tags instead of writing again, so pressing
twice finishes a half-done release instead of failing on its own work.

The one thing it needs from the repository is the ability to push to `main`; the
release commit *is* the tagged commit, so a PR-gated `main` rules that out.

## Writing a bullet that reads well
## Automating the release

Most of it already is. On a merge to `main`, one command says what the closed
issues mean:

```bash
GITHUB_TOKEN=… python3 scripts/release.py
# {"action": "release", "level": "patch", "version": "1.4.3", "count": 2}
```

The action comes from the repository's policy in `.github/changelog.json`, which
ships as `"auto": ["patch"]`:

| Result | Meaning |
| --- | --- |
| `nothing` | nothing changelog-worthy was closed; do not release |
| `release` | a patch: the section can be written, committed and tagged unattended |
| `pull-request` | a minor or major: open the release PR and let a person merge it |

A patch is a bug fix or a security fix — the behaviour the project already claimed,
restored. A minor adds behaviour and a major removes it, and those are the two a
person should read before they publish. Set `"auto": ["patch", "minor", "major"]`
to remove the human entirely.

## The two things that stop it being fully unattended

Neither is a preference; both are mechanics.

1. **A tag pushed with `GITHUB_TOKEN` does not start another workflow.** GitHub
   suppresses recursive runs, so a workflow that tags cannot rely on the
   tag-triggered `release.yml` to build the image. Either the same run calls the
   release jobs, or the tag is pushed with a GitHub App or a personal token.
2. **A bot commit to `main` collides with a PR-gated branch.** This repository
   releases by committing the section and tagging that commit, so `main` must
   accept a direct push from CI. If you gate `main` behind a pull request, the
   release PR is the only route that works.

So pick one pair: *direct push + tag in the same run* (fully unattended, `main`
stays open to CI), or *release PR* (one merge per release, `main` can be gated).
The script supports both; the workflow wiring is the difference.

## Writing a bullet that reads well

The default bullet is the issue title. When the title is written for the tracker
rather than for a reader, put a line in the issue body:

```
Changelog: The gateway resolves the account from the access key, not from the header order.
```

That line becomes the bullet; the title stays however the tracker wants it.
