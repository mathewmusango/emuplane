# Contributing to Emuplane

Emuplane is maintained by one person, in the open. [Bug reports][bugs], [ideas][issues],
[questions][discussions] and [pull requests][pulls] are all welcome — the bar for a
pull request is strict, and this file says where it sits. What is strict is the bar,
not the tone: a change has to be about a real problem, arrive with the evidence that
shows it, and land finished.

[bugs]: https://github.com/mathewmusango/emuplane/issues/new/choose
[issues]: https://github.com/mathewmusango/emuplane/issues
[discussions]: https://github.com/mathewmusango/emuplane/discussions
[pulls]: https://github.com/mathewmusango/emuplane/pulls

## Start with an issue

A change begins as an [issue][issues], because the issue is the unit here. Its label
picks the changelog section and the version bump — the release plan reads closed
issues and writes [CHANGELOG.md](CHANGELOG.md) from them — so a pull request that
closes nothing has nowhere to land.

The exception is `documentation`: prose, a README line, a page that needs a sentence.
It carries no release note and no bump, because the site deploys the moment it merges
and documentation never decides when a release happens. Use it rather than borrowing
`changed` for an edit nobody has to act on.

Past a typo, open the issue and wait for an answer before writing the code. The
answer confirms the scope and says what is already in flight. A large pull request
that drifted from an unconfirmed scope is closed whatever its quality.

A [bug report][bugs] is easiest to act on with the version or commit, what you did,
what happened and what you expected; the template asks for exactly that. An idea is
an issue too: say what problem it solves. A "no" comes with a reason. A question
about how a rule is meant to behave belongs in [Discussions][discussions] rather
than in the tracker.

## Send a pull request

Five steps, then the bar it is measured against.

1. **Get an answer on the issue.** Past a typo, the answer comes before the code: it
   confirms the scope and says what is already in flight.
2. **Branch off `main` with a prefix** — `feat/`, `fix/`, `docs/`, `ci/`, `chore/`,
   `refactor/`, `security/` or `test/`. The ruleset refuses anything else when the
   branch is created.
3. **Write the change complete** — the test that fails before it and passes after,
   and the page it changes, in the same branch.
4. **Run the three gates** below. Re-run the two generators too if the change
   touches the control API or the coverage page, and commit their output.
5. **Open the pull request against `main`**, its body saying `Closes #N` for the one
   issue it lands. [A workflow][link-gate] checks both things — that a line names an
   issue, and that it names exactly one — because that line is what the changelog and
   the release plan read.

`main` is squash-only and linear, with no bypass: the maintainer merges after
review, and nobody pushes to it, including the owner.

[link-gate]: .github/workflows/pr-issue-link.yml

## Run the gates before you open it

```bash
# The Python suite reads the emulator's source; point it at a checkout of the tag under test.
export EP_EMULATOR_SRC=/tmp/ministack
python3 scripts/qa_check.py --tests
cd web && npx tsc --noEmit && npm test
npm --prefix site run build
```

The three are [the QA check][qa], [the console's TypeScript and tests][web] and [the
documentation build][docs-site]. The last is the one that catches a broken
documentation link; `dev` will serve one happily. The docs workflow re-runs the
generators and fails on a dirty tree, so a tree it would rewrite is a closed pull
request rather than a rebase.

[qa]: scripts/qa_check.py
[web]: web
[docs-site]: site

## The bar

| Rule | What it means |
| --- | --- |
| **One issue, one pull request** | One pull request closes exactly one issue, and one issue lands in one pull request — the gate refuses a body that closes several. A fix, a refactor and a reformat are three pull requests; one that also rewrites files it did not need to touch is closed and asked for again. |
| **Evidence** | A behaviour change arrives with the run that shows it: the command, the request and the answer, taken from Emuplane against the emulator version this repository pins. The AWS documentation, a client library's model, another emulator's recording, or inference are not evidence — and a change that turns out to differ from AWS is reverted rather than argued with. |
| **The emulator boundary** | What [MiniStack][ministack] gets wrong belongs in [its tracker][ministack-issues]. What Emuplane adds on top belongs in [Beyond the emulator][extensions], with the rule it implements named. |
| **Infrastructure last** | Workflows, the [image][image], the compose files, dependencies and release plumbing come after an issue that says so — and expect the change to be written here. |
| **Green gates** | A red check is not reviewed, and a tree the generators would rewrite is closed. |
| **A known account** | A brand-new GitHub account can open an issue, not a pull request; the first accepted one comes after a maintainer has answered. |
| **Five at a time** | At most five open pull requests per contributor, lifted when the work was agreed in an issue. |
| **The written rules** | A control that cannot run, a comment that explains the design instead of the code, a dependency added without a need — each is a request to do the change again. |

Any one row closes a pull request on its own, and a good change can still be closed
for one of them. A [limitation][limits] is not an exception to any of this: it is
written down, in `Limits`, in the same change.

[ministack]: https://github.com/ministackorg/ministack
[ministack-issues]: https://github.com/ministackorg/ministack/issues
[image]: https://github.com/mathewmusango/emuplane/pkgs/container/emuplane
[limits]: https://mathewmusango.github.io/emuplane/docs/next/reference/limits/
[extensions]: https://mathewmusango.github.io/emuplane/docs/next/concepts/extensions/

## AI-assisted changes

Say so in the pull request when a tool wrote part of the change, and read every line
it produced before you send it. The evidence has to come from your own run, the
tests have to be tests you would defend in review, and the licence check is yours:
nothing generated into this repository may carry someone else's code. A pull request
whose author cannot explain it is closed like any other unreviewed change.

## Style

- **Comments are one line, per section.** Rationale belongs in the documentation or
  the commit body, never in source.
- Python is linted and formatted by [ruff](ruff.toml); the console is TypeScript
  with `strict` enabled in [its config](web/tsconfig.json).

## What lands

A real deployment running into a real problem: the console used on a lab,
[Terraform](https://developer.hashicorp.com/terraform) or the
[AWS CLI](https://aws.amazon.com/cli/) pointed at the gateway, a pipeline, an
upgrade that broke. Parity checklists, and surfaces added "for completeness", are
not it — a page exists because something can be read there, not because AWS has
one.

## Licence and conduct

[MIT](LICENSE), and there is no CLA — a contribution is offered under the project's
own licence. [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) applies to issues,
discussions and review.

Security problems go to [SECURITY.md](SECURITY.md), never to a public issue.
