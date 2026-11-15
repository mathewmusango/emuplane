# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
the minor number is bumped by hand, patch releases are the bot's.

## [Unreleased]

### Added

- Console: the five AWS sign-in screens — user type (root / IAM) → email or
  account ID → password → MFA code — as one `/signin` route in
  `web/src/pages/SignIn.jsx`, submitting to `web/src/authStub.js` until the
  control plane's auth endpoints land (ARCHITECTURE.md slice 3). The code screen
  appears only when the principal has MFA enabled (`?mfa=1` in the preview). The
  route is served without a session (`PUBLIC_SPA_ROUTES`) and linked from the
  classic login page; `/login` stays server-rendered, because it is the only form
  that mints a session today.
- CI: shared check leaves (python, js, shell, yaml, docker), a Vitest + `tsc`
  suite for `web/`, the security leaves (`dependency-review`, `pip-audit`,
  `npm-audit`), CodeQL and Semgrep.
- Release: the image is built, scanned with Trivy, and only then pushed to
  GHCR — a failing scan never leaves a tag behind. The GitHub release follows
  the image, and a tag that is not the tip of `main` is refused.
- `dependabot.yml` (github-actions + `web/` npm, 7-day cooldown, minor/patch
  grouped), `renovate.json` for the Dockerfile base-image digests, `ruff.toml`,
  and the issue/PR templates.
- **Local password recovery.** `POST /api/users/<username>/password` sets a new
  password (platform admin or bearer token), and `./scripts/password.sh <username>`
  does it from the host for someone locked out of everything. Both revoke that
  principal's sessions. `/forgot` is the public page that explains the path, since
  this deployment has no mail transport to send a reset link.
- **One icon set for both surfaces.** `scripts/favicons.sh` renders
  `favicon.ico` and the 32/192/512 PNGs plus `apple-touch-icon.png` from a single
  source image into `web/public`; the console's `index.html` and the
  server-rendered auth pages declare the same links, and the server serves those
  paths (they were 404 before). Brand files revalidate instead of being cached
  `immutable`, so a new logo reaches a returning visitor.
- **`scripts/build.sh`**, and `./scripts/up.sh --build` to rebuild and restart in
  one step.
- **A dev loop that skips the image.** `compose.dev.yml` mounts `web/dist` at
  `/app/static` and the control sources at their flattened `/app/` names, and
  `scripts/dev.sh` drives it: `web` rebuilds the console on the host (~2s),
  `api` restarts the container (~4s). `up.sh --build` stays the release path.
- **Password-reset links.** `POST /api/users/<username>/reset-link` (platform
  admin or bearer token) and `./scripts/reset-link.sh <username>` mint a
  single-use `/reset?token=…` URL, valid for `EP_RESET_SECONDS` (30 min). The
  user chooses their own password there, so whoever issues the link never learns
  it; setting it revokes that principal's sessions. Tokens live in the new
  `emuplane-resets` table as SHA-256 digests and are deleted when used.
- **Password-reset mail over a real relay.** `control/mail.py` sends through
  SMTP (`EP_MAIL_*`, standard library only, credentials never logged) and
  `/forgot` is now a form: the address is looked up, a single-use link is mailed,
  and the answer is identical whether or not the account exists. With no relay
  configured the page keeps the admin-issued path.
- **`scripts/profile-login.sh`** captures a real Firefox (Gecko) profile of a page
  load through `MOZ_PROFILER_STARTUP`/`MOZ_PROFILER_SHUTDOWN` and writes
  `docs/profile.json`, which https://profiler.firefox.com opens directly.

### Changed

- **Sign-up is one step again.** The emailed one-time password and the `/mailbox`
  page were removed on request: `Create Account` takes email, account name and
  password, creates the account and signs in. The SES send path went with them;
  transactional mail stays a slice-7 design, not code.
- **The image build is cached end to end.** `npm ci` keeps its package-cache
  mount and now uses `--prefer-offline`; `npm run build` gets a cache mount for
  Vite's transform cache; `.dockerignore` covers the remaining local build output.
  Measured here: no-change rebuild ~6s, console source change ~30s, cold ~65s.
- **Vendor code is split into its own chunks** in `vite.config.js` (rolldown's
  function form of `manualChunks`), so a page edit invalidates only the ~140 kB
  app chunks instead of the whole ~2.6 MB bundle in the browser cache.
- **Brand images are optimised.** The backend mark drops from 1280×719 / 80 kB to
  256×144 / 16 kB, and the icon PNGs are stripped, palettised and compressed
  (the 512px file goes 309 kB → 81 kB).
- **The product mark is the app icon, not a drawing.** `web/public/emuplane.png`
  (512²) replaces the hand-drawn `emuplane.svg`; the sign-in card, the console's
  fallback identity and every favicon derive from it. The SVG is gone, and the
  icon links are PNG-only. Its corners are cleared with a corner **flood fill**
  (`-draw "color 0,0 floodfill"` on the alpha channel) — the earlier attempt used
  `alpha 0,0 floodfill`, which silently leaves the white opaque, and a global
  `-transparent white` would punch out the white browser panel inside the mark.
  The sign-in card shows it at 5rem, so no white box appears in dark mode.
- **A console bar of its own.** `TopBar` replaces Cloudscape's TopNavigation so
  the services grid can sit immediately after the mark (icon only, no label), the
  way the console places it. The account chip opens a menu that differs by
  identity: root shows the account ID (grouped, copyable), account name and
  colour; an IAM user shows the account alias and its own username. "Switch role"
  is not a concept here, so the menu offers the honest equivalent — sign in as a
  different user — beside Sign out.
- **IAM users exist as a real thing.** `POST /api/users` adds a principal to the
  caller's own account (`Accounts.add_principal`), so an account can hold more
  than its root. Sign-in already distinguished them; now one can be created.
- **All services / Services by category** on `/services`: the flat list, or one
  table per category in the console's own category order.
- **The Identity section is gone.** With no global administrators there is no
  account list to browse: the console's `Accounts` and `Onboarding` pages, their
  routes and their nav section are removed, and `/accounts` / `/onboarding`
  redirect to Settings so old bookmarks still land somewhere sensible.
- **A reset cannot reuse the current password.** `/reset` (and
  `POST /api/users/<name>/password`) compares the new password against the stored
  hash with a side-effect-free `UserStore.matches()` and refuses it — and the
  link is no longer spent by a rejected attempt, because the token is consumed
  only after every check passes.
- **No global administrators, the AWS way.** Root owns its own account and its IAM
  users; no login can read another tenancy. `_platform()` is now true only for the
  bearer token — a deployment credential — so `/api/meta`, `/api/users` and
  `/api/exec` scope every session to its own account. `POST /api/accounts/<id>/admin`
  is gone, `global_admin`/`default_admin` are cleared on load, and the console's
  admin tab, toggle and "retire the default administrator" banner are removed.
- **The reset mail and page carry the mark.** The message is now
  `multipart/alternative` — the existing plain text plus an inline-styled HTML
  part — with `web/public/email-logo.png` attached as `multipart/related` and
  referenced by `cid:`, so the mark renders without the reader allowing remote
  content (a linked image is blocked by most clients and would point at a host
  the recipient cannot reach). `/reset`, the one auth page a link lands on, shows
  the same mark at 4.5rem.
- **The product owns the chrome.** The console's top navigation is Emuplane's mark
  and title, not the backend's: `web/public/backends/ministack.png` is deleted and
  the profiles no longer carry a logo. Which backend is being fronted is operator
  context now, shown in About, not branding.
- **The palette comes from the mark.** Navy ink (`#0b1b3f`), royal blue
  (`#1b4fd8`) for links and focus, the logo's orange (`#ff8a1f`) for primary
  actions, on a blue-tinted page (`#f3f6fc`) and a navy dark surface (`#0a1220`).
  The console takes it by overriding Cloudscape's tokens on `body` — they are
  published inside an `@layer`, so the unlayered override wins with no
  `!important` and no forked component library; each mode is declared separately
  because the light link blue is unreadable on the dark surface.
- **The user-type step puts Next and the signup route on one row** (`Next | OR |
  Create account`), and the password steps give both actions a 3.5rem box so the
  two-line "Sign in to a different account" is not squeezed. The sign-up page's
  alternative reads "Sign in to an existing account" on a rounded box rather than
  a pill, because it wraps.
- **The sign-in pages were unified.** Both cards now use the same frame (8px
  radius, no shadow, `#f2f3f3` page), the same input size, and an OR rule between
  the primary action and the alternative. On `/login` the signup route is one box
  — `New Account?` with `Signup` directly under it. `/signup` keeps its two fields
  above the action row, with the eye control inside both password inputs.

- **The sign-in page carries a theme switch.** It follows the system by default
  (`system` is the stored preference), and a click pins light or dark under
  `emuplane:theme` — shared with the console's own toggle. `signin.css` colours the
  page frame from the body's `awsui-dark-mode` class, so the space around the card
  matches the mode rather than the OS query.

- **The project is Emuplane, and it is not tied to one backend.** Renamed from
  MinStack Control: the image is `ghcr.io/mathewmusango/emuplane`, the stack and its
  tables are `emuplane` / `emuplane-*`, the cookie is `emuplane_session`, browser keys
  are `emuplane:*`, and every setting uses the `EP_` prefix (`EP_BACKEND_URL`,
  `EP_CONSOLE_URL`, `EP_PORT`, `EP_GATEWAY_PORT`, `EP_PUBLISHED_GATEWAY_PORT`, …).
- **A backend is a profile.** `control/backends.py` holds one row per backend —
  `generic`, `ministack`, `floci`, `localstack`, `moto` — with its display name,
  default port and logo. `EP_BACKEND` selects it and `EP_BACKEND_URL` is the
  connection string; `/api/meta` reports `backend`, `backend_id` and `backend_logo`,
  so the console wears the backend's own mark after sign-in while the sign-in pages
  carry Emuplane's.
- **The gateway listens on 8081, not 4566.** The control's own listener no longer
  reuses the backend's port: `EP_GATEWAY_PORT=8081` inside the container, published
  on `EP_PUBLISHED_GATEWAY_PORT=4571`, forwarding to the backend's `EP_BACKEND_PORT`.

### Fixed

- **The page title no longer hides under the console bar.** `AppLayout`'s
  `headerSelector` measured the fixed bar but the content still slid 44px up, so
  Console Home's heading sat behind it. The offset is explicit now
  (`.console-offset`, `padding-block-start: 2.75rem`).
- **The IAM account menu shows the account ID** as well as the alias and the
  username — an IAM user needs the ID for the CLI, not just for root.

- **A deleted account could come back, and a concurrent writer could be clobbered.**
  The accounts store cached the table in memory and `_save()` replaced the whole
  table, so any process holding a stale copy rewrote rows it had not seen and
  recreated rows someone else had deleted. Writes are per row now (`_put`), and
  deletion is explicit (`db.delete`) — the same rule the session store follows.

- **The reveal eye is a control, not a hint.** It was drawn in the faint
  secondary ink at 16px, which read as decoration. It is now 18px, in the body
  ink at 75% opacity (full on hover/focus), a 2rem target, and `z-index: 2` so
  Cloudscape's positioned input wrapper cannot sit over it.
- **Server-rendered pages send `Cache-Control: no-store`.** `/signup`, `/forgot`
  and `/reset` sent no cache header at all, so a browser could keep showing the
  previous build's form after a redesign.

- **The sign-in pages no longer ask for `/api/meta`.** `SessionProvider` fetched it
  on every route, so `/login` — which has no session by design — logged a 401 that
  could only be a lie. It now skips the signed-out routes and refreshes on the way
  into the app, which is also what makes a fresh sign-in load current data.
- **`bootstrap/apply.py` updates an existing stack.** It only ever created one, so
  a table added to `template.yml` (the `resets` store) was never provisioned: the
  job created the stack once and then reported the missing table forever.
  `UpdateStack` now runs against a healthy stack, and "no updates are to be
  performed" counts as success.
- **The console reads the right theme key on boot.** `main.jsx` still read
  `ministack:theme` while `prefs.js` writes `emuplane:theme`, so a pinned theme was
  ignored until the first toggle.

- **A failed sign-in says why.** `web/src/api.ts` turned *every* 401 into “Your
  session expired. Sign in again.” — including the answer to a wrong password, so
  the real reason (and the fact that no account existed yet) was hidden. The
  session-expiry bounce now skips `/api/auth/*` and the signed-out routes.
- **Sessions are stored as digests.** `emuplane-sessions` rows were keyed by the
  raw token, so a copy of the table could replay a live session. They are keyed by
  `sha256(token)` now (`session_key()`), and start-up re-keys any row written the
  old way, dropping the raw copy.
- **A password reset takes effect immediately, and cannot be undone by a login.**
  `UserStore` served the copy it loaded at start-up, so an out-of-process reset was
  invisible until the next restart — and the next successful sign-in wrote that
  stale hash back over it. Reads now go through `_reload()`, which re-reads the
  table each time.

### Changed

- **The API bearer token is a hashed record, not a setting.** `EP_ADMIN_TOKEN` is
  gone from `.env`: `./scripts/token.sh` mints a token, prints it once and stores
  only a SHA-256 digest in the settings store, the same contract as a session.
  Rotation invalidates the previous token immediately, and a running control
  re-reads the digest per request so a rotation takes effect without a restart.
  A fresh install therefore carries **no credential in any file**.
- **The sign-in screens are the login page.** `/login` is served by the console
  (`PUBLIC_SPA_ROUTES`) and the server-rendered form is gone; `POST /api/auth/login`
  verifies root (email or username) and IAM (account + username) credentials, checks
  the account and root-credential flags, and sets the session cookie. `mfa_required`
  comes from the answer, and `POST /api/auth/mfa` answers 501 until enrolment exists.
  `web/src/authStub.js` is deleted — the screens call the real endpoint.
- **Optional settings have defaults.** `MINISTACK_NODE_NAME` defaults to the
  emulator's compose service name, and `EP_STORE_ACCOUNT` / `EP_STORE_REGION` /
  `EP_STORE_URL` default inside the store client — a `.env` only has to name the
  emulator endpoint and the two public addresses users are shown. `bootstrap/apply.py`
  gained `--drop-tables`: the one-off that deletes the stack and every control table,
  which is the only way to return a pre-stack installation to a first setup.
- **The control's own substrate is provisioned by CloudFormation.**
  `bootstrap/template.yml` defines its ten DynamoDB tables as the stack
  `emuplane`; `bootstrap/apply.py` applies it as a first-setup init job
  (`docker-compose.yml`'s `bootstrap` service, run by `scripts/up.sh` before the
  console starts) and is idempotent. `control/store.py` no longer creates tables —
  it verifies them and refuses to serve, naming any that are missing. Tables that
  predate the stack are reported rather than adopted.
- **A fresh control has no accounts at all.** The seeded bootstrap administrator
  (`MC_ADMIN_USER` / `_EMAIL` / `_PASSWORD`) is retired: the only way in is
  sign-up, and the first account created becomes the platform owner, as AWS does
  it. Nothing is seeded from `.env` any more except the optional API bearer token.
- **The deployment is stateless.** `MC_DATA_DIR` and the `/var/lib/ministack/control`
  bind mount are gone; the running container mounts nothing from the host.
- The compose files were renamed: the generic definition is `docker-compose.yml`,
  and the untracked deployment overlay is `compose.yml` — `scripts/up.sh` layers
  it by default, or whatever `EP_OVERLAY` names.
- CI now calls the shared workflow leaves — `checks-*`, `tests-vitest`,
  `release-image-ghcr`, `release-github`, `security-dependency-review` and
  `security-npm-audit` — pinned at
  `my-workflows@v2026.1112.2318Z`, instead of carrying copies of their logic.
  The release leaf builds and scans before it pushes; the tag-must-be-`main`
  guard stays local because a tag ruleset cannot express it.
- `checks.yml` grants `pull-requests: read`: the leaves use `dorny/paths-filter`,
  and a called workflow can only downgrade the token it is given.
- `docker-compose.yml` is generic: the image comes from `EP_IMAGE` (default: the
  published GHCR tag), ports and the data directory have defaults, `.env` is
  optional, and no container names, hostnames or routes are baked in. A private
  `compose.yml` (gitignored) layers the names, routes and mounts of a
  specific deployment on top.
- `scripts/up.sh` pulls instead of building, and layers the overlay when it is
  present.
- README rewritten around what this service is, how a client gets credentials,
  and how accounts and regions are separated.
