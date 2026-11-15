# MiniStack console

The React console served at `https://ministack-control.example.com/`. It is a Vite app built
with [Cloudscape](https://cloudscape.design/), the AWS console design system, and
talks only to the control plane's `/api/*` routes.

```sh
npm ci            # install
npm run dev       # http://localhost:5173, proxies /api to 127.0.0.1:4570
npm run build     # writes dist/, mounted at /app/static
npm run typecheck # tsc --noEmit (typed api.ts + types.ts)
npm test          # Vitest + Testing Library in jsdom
```

Dependencies are pinned by `package-lock.json` and Dependabot owns the bumps. The
toolchain is Vite 8 + Vitest 5 + jsdom 31 and needs **Node 22.12 or newer** — the
image's `node:22-alpine` stage satisfies it, so the container build stays the
reference. `npm audit` is expected to report zero vulnerabilities; treat a new
advisory as a task, not background noise.

`dist/` and `node_modules/` are gitignored. The control container mounts
`web/dist` read-only, so run `npm run build` and restart
`core-ministack-control` after a change. Until `dist/` exists, `/` answers `503`
with these instructions.

## Patterns

Mapped from [Cloudscape patterns](https://cloudscape.design/patterns/):

| Pattern | Where it shows up |
| --- | --- |
| Global actions | Resources header: refresh, favorite; page-level primary action in each page header |
| In-context actions | The action form next to the resource table; results in a result panel |
| Delete with confirmation | Any operation marked `destructive` opens a `Modal` naming the CLI call and the account/region |
| Empty states | Tables show a message plus a refresh action instead of a blank body |
| Loading and refreshing | Table `loading` state, header refresh, per-action spinner |
| User feedback | `Flashbar` reports the last action's success or failure |
| Errors and validation | Onboarding validates username, email, password and confirmation with `FormField.errorText` |
| Density settings | `CollectionPreferences` exposes page size and content density; the table honours it |
| Service navigation | Top navigation (search, account, region, favorites) plus side navigation; `/classic` keeps the old pages |
| Service dashboard | Dashboard cards, favorites first, availability, resource count, per-service icon |
| Resource tabs | One tab per resource kind (IAM users/roles/groups/policies, EC2 instances/security groups/key pairs) |
| Themes | System default, light and dark from the top navigation and Settings |
| Filtering | `TextFilter` wired through `@cloudscape-design/collection-hooks` |
| Disabled and read-only | A service without actions carries a **Read-only** badge and no form |

## Tenancy rules

| Rule | Where it is enforced |
| --- | --- |
| A session sees only its own account | `/api/meta` filters the account list, `/api/users` returns one account, `/api/browse` and `/api/exec` answer `403` for another account |
| Regions are opt-in per account | `control.db` stores `regions`; every browse/exec checks it; Settings toggles them; `us-east-1` cannot be disabled |
| Only the platform admin crosses accounts | The `.env` operator and the admin bearer token; only they may provision or delete accounts |
| The default admin is disposable | The first account is marked default; once another global admin exists, Dashboard banners to disable or delete it. Disabling drops its sessions and cannot remove the last enabled admin. |
| S3 names are global | Upstream limitation; the S3 page says so |

Service coverage against the upstream catalogue (101 services, 2,519
operations) is generated locally by `scripts/upstream_services.py` into the
gitignored `docs/` folder.

Deliberately deferred: configurable dashboard (`board-components`), saved filter
sets, help panel, multi-step create wizard, split view and an unsaved-changes
prompt. The action form is single-step on purpose — one operation at a time.

## Dependencies and forks

Everything is installed from npm. The GitHub repositories behind the
runtime dependencies are forked under `mathewmusango` so a patch can be carried
without waiting upstream, but **forks are not build inputs**:

| Package | Fork |
| --- | --- |
| `@cloudscape-design/components` | https://github.com/mathewmusango/components |
| `@cloudscape-design/global-styles` | https://github.com/mathewmusango/global-styles |
| `@cloudscape-design/collection-hooks` | https://github.com/mathewmusango/collection-hooks |
| MiniStack (the emulator we run) | https://github.com/mathewmusango/ministack-upstream |
| MiniStack MCP server | https://github.com/mathewmusango/ministack-mcp |

## Tracking

S3 parity against the upstream operation list is tracked on the `ministack` GitHub
project board (#10) as one draft issue per operation. Implementation stays in
`control/` and `web/`.

## Upstream

The console is a candidate answer to
[ministackorg/ministack#314](https://github.com/ministackorg/ministack/issues/314)
("Web UI"), where a Cloudscape-based console was explicitly requested. This
repository is private, so replying needs a public write-up or demo repo first.

## Layout

| Path | Purpose |
| --- | --- |
| `src/main.jsx` | theme mode, `I18nProvider`, router, session provider |
| `src/App.jsx` | routes, wrapped in Cloudscape's `ErrorBoundary` |
| `src/context.jsx` | `/api/meta` session state: account, region, principal |
| `src/api.ts` | typed API client (the first TypeScript module) |
| `src/types.ts` | API response types shared by the migration |
| `src/context.jsx` | `/api/meta` session state: account, region, principal |
| `src/prefs.js` | favorites, recent services and theme (localStorage, event-synced) |
| `src/components/Shell.jsx` | top navigation, side navigation, app layout |
| `src/pages/` | Dashboard, AllResources, Resources, Favorites, Accounts, Onboarding, Settings, About, SignIn |
| `src/authStub.js` | the sign-in stub: validation helpers and the two calls the auth endpoints will take |
| `test/` | Vitest setup and smoke tests |

The pages are the "organisms"; Cloudscape components are the atoms and
molecules, so no hand-rolled primitives are added. Each page owns its data
fetching and passes plain props down.

## Sign-in screens

`src/pages/SignIn.jsx` is the five screens of AWS's own sign-in flow, in one
route and one state machine — not five routes, because the flow is linear and
the e-mail/account you typed has to survive the steps:

| Step | Screen | Calls |
| --- | --- | --- |
| `type` | user-type cards (root / IAM), then email or account ID | nothing — client-side checks only |
| `root-password` | "Root user sign in", password | `api.signIn({ mode: 'root', email, password })` |
| `iam-password` | "IAM user sign in", account + username + password | `api.signIn({ mode: 'iam', account, username, password })` |
| `mfa` | "Additional verification required" | `api.verifyMfa({ code })` |

**These screens are the login page.** The control plane serves `/login` without a
session (`PUBLIC_SPA_ROUTES` in `control/app.py`) and `POST /api/auth/login`
verifies the password, checks the account is enabled and the root credential is not
revoked, then sets the same `HttpOnly` session cookie every later request uses. The
old server-rendered form is gone; `/signin` stays as an alias, and `src/api.ts`
does not bounce a 401 from either route (every other path still redirects to
`/login`). `?next=` is honoured (path-only, never protocol-relative).

**The code screen appears only when the server says so** (`mfa_required` in the
answer). Enrolment does not exist yet, so it is false for every account and the
third screen is not reached; `POST /api/auth/mfa` answers `501` until it does.

"Remember this account" (IAM branch) keeps the account ID or alias in
`localStorage` under `ministack:signin-account`; it is cleared on every other
successful sign-in. "Create a new AWS account" and "New to AWS? Sign up" open
the server's `/signup` page, and the help links (info icon, "not sure?",
"Forgot password?", "Having trouble?", "Don't have?") are popovers rather than
dead anchors.

## Service icons

The coloured service icons in `src/assets/aws/` are vendored from the MIT
[`aws-icons`](https://github.com/MKAbuMattar/aws-icons) package, which repackages
the AWS architecture-service icon set. They are imported as URLs, so Vite
fingerprints them and no runtime dependency is added. Services without a mapped
icon fall back to a neutral outline.

## TypeScript, incrementally

`api.ts` and `types.ts` are typed; everything else stays JavaScript because
`tsconfig.json` sets `allowJs: true`. The migration is deliberately one file at a time: rename it to `.ts`/`.tsx`, fix the types, keep `npm run typecheck` green.
Suggested order: `context`, `prefs`, shared components, then pages. There is no
build-time type gate yet — wire `typecheck` into CI when the pages are done.

## Conventions

- **Cloudscape first.** Use the component rather than a custom one:
  `CopyToClipboard` for IDs and keys, `CollectionPreferences` + `Pagination`
  with `@cloudscape-design/collection-hooks` for tables, `ErrorBoundary` around
  the route tree, `I18nProvider` with `all.en` messages.
- **Reduced motion.** Cloudscape's motion tokens honour the OS preference; the
  few local rules in `src/styles.css` disable animation under
  `prefers-reduced-motion: reduce` too.
- **Typography.** Open Sans ships with `@cloudscape-design/global-styles`; do
  not add a second font.
- **Accounts are global, regions are data.** The account selector and region
  selector are independent on purpose; a future per-region cluster only makes
  more regions selectable.
- **No secrets.** The console shows masked key material only: an access key ID
  and secret are rendered once, when a key is created (onboarding or Settings),
  and never read back afterwards. It never touches the lab's Keycloak/OpenBao
  credentials.
- **Access keys are named.** An account holds up to two (`MAX_ACCESS_KEYS`,
  AWS's own IAM limit), each with a label, a masked ID and a masked secret.
  Rotation is create-then-delete, so the overlap never leaves an account
  credential-less.

## References

- Cloudscape components — https://cloudscape.design/components/
- Cloudscape for developers — https://cloudscape.design/get-started/for-developers/
- Cloudscape design tokens — https://cloudscape.design/foundation/visual-foundation/design-tokens/
- Collection hooks — https://cloudscape.design/get-started/dev-guides/collection-hooks/
- Testing with Vitest — https://cloudscape.design/get-started/testing/frameworks/
- Cloudscape repository — https://github.com/cloudscape-design/components
- Cloudscape demos — https://github.com/cloudscape-design/demos
- Board components — https://github.com/cloudscape-design/board-components
- Atomic design, extended — https://bradfrost.com/blog/post/extending-atomic-design/
- `prefers-reduced-motion` — https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion
- Open Sans — https://fonts.google.com/specimen/Open+Sans
