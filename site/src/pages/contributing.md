---
title: Contributing
description: How to obtain Emuplane, report a bug or an idea, and what a change has to look like to land.
hide_table_of_contents: false
---

Emuplane is maintained in the open, by one person. This page covers the three
things people ask for: how to get it, where to report something, and what a change
has to look like to land.

## Obtain it

The [image](https://github.com/mathewmusango/emuplane/pkgs/container/emuplane) is
published to the GitHub Container Registry, and every
[release](https://github.com/mathewmusango/emuplane/releases) tags its version and
moves `latest` to the same digest.

```bash
docker pull ghcr.io/mathewmusango/emuplane:latest
```

The [compose files](https://github.com/mathewmusango/emuplane/blob/main/docker-compose.yml)
name the pinned tag this documentation set is written against, so bringing the stack
up never changes the image under you. The [Quickstart](/docs/getting-started/quickstart)
takes it from there: the emulator, the compose file, the first account and the first
bucket.
[`docker-compose.all.yml`](https://github.com/mathewmusango/emuplane/blob/main/docker-compose.all.yml)
brings [MiniStack](https://github.com/ministackorg/ministack) along if you do not
have one.

## Report a bug, ask for a feature

Use the [issue tracker](https://github.com/mathewmusango/emuplane/issues), and
[open a bug report](https://github.com/mathewmusango/emuplane/issues/new/choose)
there. A report is easiest to act on with the version or commit, what you did, what
happened and what you expected — [the template](https://github.com/mathewmusango/emuplane/blob/main/.github/ISSUE_TEMPLATE/bug_report.md)
asks for exactly that. An idea is an issue too: say what problem it solves, and the
answer is a yes, a no with a reason, or a question.

Questions about how a rule is meant to behave belong in
[Discussions](https://github.com/mathewmusango/emuplane/discussions) rather than in
the tracker.

**A security problem is never a public issue.** Report it privately — see
[SECURITY.md](https://github.com/mathewmusango/emuplane/blob/main/SECURITY.md) for
the two private routes and what is in scope.

## Send a change

Pull requests are welcome under a strict bar. Five steps, then the bar it is
measured against.

1. **Get an answer on the issue.** Every change starts as an
   [issue](https://github.com/mathewmusango/emuplane/issues), because its label
   decides the changelog section and the version bump. Past a typo, the answer comes
   before the code.
2. **Branch off `main` with a prefix** — `feat/`, `fix/`, `docs/`, `ci/`, `chore/`,
   `refactor/`, `security/` or `test/`.
3. **Write the change complete** — the test that fails before it and passes after,
   and the page it changes.
4. **Run the three gates first** — the QA check, the console's TypeScript and tests,
   and the docs build. They are all three commands, under the bar below.
5. **Open the pull request against `main`**, its body saying `Closes #N` for the one
   issue it lands — a workflow checks that the line exists and that it names exactly
   one issue, since it is what the changelog and the release plan read.

`main` is squash-only and linear, with no bypass: the maintainer merges after
review, and nobody pushes to it, including the owner.

```bash
export EP_EMULATOR_SRC=/tmp/ministack
python3 scripts/qa_check.py --tests
cd web && npx tsc --noEmit && npm test
npm --prefix site run build
```

`build` is the one that catches a broken documentation link; `dev` will serve one
happily. If the change touches the control API or the coverage page, re-run the
generators and commit their output.

### The bar

| Rule | What it means |
| --- | --- |
| **One issue, one pull request** | One pull request closes exactly one issue, and one issue lands in one pull request. A fix, a refactor and a reformat are three pull requests. |
| **Evidence** | A behaviour change arrives with the run that shows it, against the emulator version this repository pins. The AWS documentation, a client library's model, another emulator's recording, or inference are not evidence. |
| **The emulator boundary** | What you find wrong in the emulator belongs in [MiniStack's tracker](https://github.com/ministackorg/ministack/issues); what Emuplane adds on top belongs in [Beyond the emulator](/docs/concepts/extensions). |
| **Infrastructure last** | Workflows, the image, the compose files, dependencies and release plumbing come after an issue that says so. |
| **Green gates** | A red check is not reviewed, and a tree the generators would rewrite is closed. |
| **A known account** | A brand-new GitHub account can open an issue, not a pull request. |
| **Five at a time** | At most five open pull requests per contributor, lifted when the work was agreed in an issue. |
| **The written rules** | A control that cannot run, a comment that explains the design instead of the code, a dependency added without a need. |

Any one row closes a pull request on its own. A limitation is not an exception: it
is written in [Limits](/docs/reference/limits) in the same change.

**AI-assisted changes are disclosed.** Say so in the pull request when a tool wrote
part of it, read every line it produced, and make sure the evidence comes from your
own run — a pull request its author cannot explain is closed.

The mechanics are in
[CONTRIBUTING.md](https://github.com/mathewmusango/emuplane/blob/main/CONTRIBUTING.md).

The licence is [MIT](https://github.com/mathewmusango/emuplane/blob/main/LICENSE)
and there is no CLA: a contribution is offered under the same licence, and the
[Code of Conduct](https://github.com/mathewmusango/emuplane/blob/main/CODE_OF_CONDUCT.md)
applies to issues, discussions and review.
