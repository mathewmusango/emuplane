# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
the minor number is bumped by hand, patch releases are the bot's.

## [Unreleased]

### Added

- **One test tree, and S3's create proven over the wire.** `tests/` holds both
  suites: `tests/web` is the console's Vitest suite (moved out of `web/test`, and
  `tests/node_modules` lets it resolve the console's dependencies from there) and
  `tests/s3` is pytest, which `scripts/qa_check.py --tests` now runs beside it.
  The S3 tests drive `control/buckets.create` with the control's own
  `signed.request` against a stand-in HTTP server that hands every request to the
  emulator's `handle_request`, then read the settings back **through the API** —
  `?location`, `?ownershipControls`, `?versioning`, `?object-lock`,
  `?publicAccessBlock`, `?tagging`, `?encryption`. Every combination of region ×
  Object Ownership × Block Public Access × versioning × tags × encryption ×
  Object Lock × namespace is covered — 576 buckets, none of them deleted — plus a
  test pinning the signing-region check that refused create before it named its
  region.
- **The Account Regional namespace is real, not a disabled radio.** Choosing it
  appends `.<account>-<region>-an`, so `test` is created as
  `test.344381301567-us-east-1-an`. The suffix is added server-side and never
  twice, the page previews it beside the name field, and the name is held to 63
  characters minus the suffix. Directory bucket types stay unavailable: the
  emulator serves general purpose buckets in the global namespace only.
- **Creating a bucket is its own page, the way the console does it.** `/s3/create`
  carries that form: AWS Region, bucket type (general purpose is all this
  backend serves, and Directory says so), the bucket namespace, the bucket name
  with S3's own rules answered before the round
  trip, Object Ownership, Block Public Access (the master checkbox and its four
  settings), Bucket Versioning, up to 50 tags, default encryption (SSE-S3 /
  SSE-KMS / DSSE-KMS plus the bucket key) and Object Lock under *Advanced
  settings*, which turns Versioning on with it. `POST /api/s3/buckets`
  (`control/buckets.py`) sends `CreateBucket` with the region's
  `LocationConstraint` and the create-time `x-amz-object-ownership` and
  object-lock headers, then applies the rest the way the console does
  (`?publicAccessBlock`, `?versioning`, `?tagging`, `?encryption`). A follow-up
  failure still reports the bucket as created and names the step that failed. The
  name is claimed before the emulator sees it — the same claim the gateway makes
  — so a taken name gets one answer from both paths, and a failure releases it.
  The buckets page's *Create bucket* now opens the page and comes back with the
  new name; its name-only modal is gone.
- **Emptying a bucket from the S3 page.** *Empty* sits beside *Delete* and needs
  the bucket name typed first, like the delete dialog. S3 has no single call for
  it, so the console loops `delete-object` over the listing and re-lists until the
  bucket reports empty (a listing is capped, so one pass can stop short), then
  says how many objects went; a failure names what was already deleted. *Empty*
  and *Delete* now act in the bucket's own region instead of the page's, because
  the table lists every enabled region.
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

- **The create page takes its region from the top bar.** The *AWS Region* select
  is gone from General configuration: the region is the console's own, picked in
  the bar and written under the heading as text, so the form cannot disagree with
  the rest of the page. The Account Regional namespace suffix follows that
  selection — change the region in the bar and `.<account>-<region>-an` changes
  with it — and `buckets.resolve_name` refuses a regional name without a 12-digit
  account instead of composing a name that only looks regional.
- **The S3 tests are their own suite.** `tests/web/s3.test.jsx` holds the page's
  console tests — the table and its region column, the create page, *Empty*,
  *Delete*, the region picker and the namespace suffix — over shared fixtures in
  `tests/web/fixtures.jsx`, while `tests/s3/` grew a tag-escaping round trip and
  the regional-account rule.
- **The S3 page is one flat table, the way the console shows it.** *Buckets* is
  the heading; *General purpose buckets* is the table, listing every bucket in
  every enabled region with **Name / AWS Region / Creation date** (region display
  name and code together, from `web/src/regionNames.js`). The region switch, its
  tabs, the *All AWS Regions* toggle and the kinds side navigation are gone — one
  table, no hashes in the URL. Header actions follow the console: refresh, *Copy
  ARN*, *Empty*, *Delete*, *Create bucket* (which opens the create page); the
  bucket name is the link into the
  bucket (no *Open* column); the filter reads *Find buckets by name*. The service
  chooser moves off the S3 page (the bar's services menu is how you switch), and
  the API explorer is gone from the S3 page — its table carries the actions. The
  explorer stays on the services whose tables have no actions of their own.
- **The signed client is its own module.** `control/signed.py` holds the
  SigV4-shaped request the control makes as an account root (a credential name
  and `Signature=local` — the gateway's own property), so the create sequence can
  be exercised on a socket without a store behind it. `app.signed_rest` keeps its
  signature and delegates.
- **The new modules ship.** `Dockerfile` and `compose.dev.yml` copy and mount
  `control/*.py` one by one, so `buckets.py` and `signed.py` were added to both —
  the image cannot import a module its `COPY` line omits, and the dev overlay
  mounts only what it lists. A control that is missing one of them answers 404 to
  the route that needs it, which is what "Could not create the bucket: not found"
  was.
- **Local runtime state is ignored.** `.gitignore` covers `node_modules/`,
  `tests/node_modules` (a symlink is not a directory, so the trailing-slash
  pattern alone misses it) and `.pytest_cache/`.
- **The service nav names the service.** *Amazon S3* sits at the top of the S3
  sidebar, above *Buckets* — the console's own nav header — and `/s3/create`
  keeps the service nav instead of falling back to the global one. The section
  links go to `/<service>/home`, so the create page's *General purpose buckets*
  link is the list rather than itself.
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
- **Copying the account ID says so.** The icon becomes a tick and "Copied"
  appears beside it for a moment — the old feedback was only in the tooltip,
  which is no use once the pointer is on the button.
- **The menu footer is one presentable set.** Multi-session, Add session and
  Switch role now share Sign out's shape — same height, radius and weight — with
  Sign out keeping the accent as the only control that ends the session. The
  bordered boxes looked unfinished beside it.
- **Add session opens its own window.** `window.open('/login?add=1&popup=1')` —
  signing in there stores the identity, posts `emuplane:identity-added` to the
  opener and closes itself; the console reloads onto the identity the browser is
  now signed in as (the cookie is shared), with the previous one in the switch
  list. A blocked popup falls back to the same sign-in page in this tab.
- **Fixed: signing in with multi-session on called a boolean.** The identity
  store's `remember` was shadowed by the "remember this account" checkbox state
  in `SignIn`, so the import resolved to that boolean — the console reported
  `D is not a function` after a minified build. The import is aliased and a test
  now signs in with the feature on and asserts the token is stored.
- **"Add session" appears under the toggle** once multi-session is on: it opens
  the sign-in page in add mode (`/login?add=1`), which says what it is doing and
  stores the new identity alongside the current one instead of replacing it.
- **Multi-session support is real, and opt-in.** Turning it on in the account
  menu hands the browser this session's token (`POST /api/auth/remember`), and
  each later sign-in stores its own; the menu then lists the identities and
  switching re-mints the cookie through `POST /api/auth/switch` for a token that
  is still live (a dead one is refused and dropped from the list). Because the
  token sits in `localStorage`, the feature is off by default and turning it off
  deletes every stored token.
- **The menu footer is boxes.** Divider, then "Turn on multi-session support" and
  — for an IAM user — "Switch role" as bordered boxes, with Sign out as the only
  filled control.
- **The account chip is smaller than the line beneath it was ever allowed to
  be**: 0.78rem bold in a 1.75rem pill with tighter padding, so the account and
  its 12-digit ID sit on one line without dominating the bar, and the identity
  under it (0.72rem) reads as a label rather than a caption.
- **The identity line under the chip is readable now** (0.8rem, was 0.68rem). It
  sat at caption size, which read as decoration rather than the name of the
  identity you are signed in as. The 3.25rem bar still holds both lines.
- **Missing service icons fixed.** `serviceIconUrl()` is `undefined` for a
  service with no mapped artwork, so the shortcut list drew a broken `<img>` for
  every such service. It renders `ServiceIcon`, which falls back to a neutral
  glyph.
- **The services menu stars a service on hover.** Each row in the menu carries a
  star that appears on hover or keyboard focus and stays lit for a favourite, so
  a service can be kept without leaving the menu — the same gesture as All
  services, and the pane updates in place.
- **Favorites is a pane in the services menu**, directly under Recently visited:
  the starred services, alphabetical, in the same list as every other pane —
  rather than a page of its own.
- **A service lives at `/<service>/home?region=<region>`**, the console's own URL
  shape: the service is a path segment and the region is in the query, so a
  copied link reproduces the view. `?region=` is adopted on load and kept in step
  as the selector changes; `/resources/<service>` redirects into it and the
  server serves `/<service>/home` as a console route.
- **Breadcrumbs tell one story.** The root crumb still said "MiniStack" and pages
  repeated "Home" beneath it. The bar now reads `Home / <page>`, with services as
  `Home / All services` and a service as `Home / All services / S3` (its display
  name, not its id).
- **A service's page has no star and no Refresh.** Favourites are managed from
  All services and the services menu; a per-service star and a refresh button in
  the page header were two more places to keep in step.
- **All services keeps the service artwork.** Each line is the service's icon
  beside its name (a neutral glyph where there is no artwork), so a column of
  links is still scannable by sight rather than by reading every word.
- **All services is one page, three columns.** `Services by category` in a single
  card: a category heading with an icon, then a plain alphabetical run of links,
  flowing down column one into two and three (`columns: 3`, two at ≤1100px, one
  at ≤700px). The All services / Services by category and Grid / List switchers
  and Refresh are gone — there is one way to read the page. A hover-only star
  still favourites a service.
- **Home is tidier.** The grid's cards share a height per row (`align-items:
  stretch`) instead of each hugging its own content, and service shortcuts are a
  two-column list of links with their icons rather than a strip of buttons that
  wrapped at awkward widths. `Console Home` is just **Home**.
- **Favorites is gone**, as a page and as a nav entry: the star in the top bar
  and the item in the services menu are removed with it, and `/favorites`
  redirects to `/services`, where favourites still pin a service to the top.
- **The account menu leads with the account's identity** — Account ID (grouped,
  copyable), Account name, Account colour, Account alias, and for an IAM user its
  own username — then the links: Account, Organization, Service quotas, Billing
  and Cost Management, Security credentials. `/api/meta` now carries each
  account's `name` so the menu can show the label apart from the alias.
- **The account chip names the account, and the line under it names the identity.**
  Both identities show `<account> (<account ID>)` on the chip — in this lab
  `management (124969375555)` — and the small line beneath carries the account
  name for root and the username for an IAM user. The bar grows to 3.25rem to
  hold the two lines (`--topbar-h`, which the content offset now reads too).
  "Turn on multi-session support" is present in the menu and disabled: one
  identity per browser session is what this build does.
- **The bar's right side is quieter**: notifications, help and settings icons are
  removed. Settings is still one click away in the account menu, and About is
  reachable from there too.
- **The sidebar belongs to the service you are in.** On `/<service>/home` it
  switches from the console nav to that service: `Buckets` (S3) or `Resources`,
  a section listing the actions this console actually offers for it, and a link
  back to All services. An action link carries `#<operation-id>`, which the page
  reads and opens, so the nav and the page agree.
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

### Changed

- **The S3 page reads like the console's.** Breadcrumb `Amazon S3 / Buckets`
  (the long service name comes from `serviceLongName`), the page heading is
  `Buckets`, and the region toggle is now the console's two tabs — *General
  purpose buckets* and *All AWS Regions* — driving the same all-regions fetch.
### Fixed

- **A service the console does not serve is no longer a page.** `/:service/home`
  is a catch-all, so `/s3files/home` and `/s3tables/home` rendered the shell with
  `unknown service` under it — the answer `/api/browse` gives them, and the one
  any invented name gets. Those names are not services, so the route sends the
  caller to *All services* as soon as the catalogue says the name is not one of
  the twelve the console serves.
- **S3's other tabs are children of S3.** *Directory buckets*, *Table buckets*,
  *Vector buckets* and *File systems* were inert labels under *Amazon S3* in the
  sidebar. They are pages of S3 now — `/s3/directory-buckets`,
  `/s3/table-buckets`, `/s3/vector-buckets`, `/s3/files` — reached from that
  sidebar, keeping the *Amazon S3* header and its own nav. The directory and
  vector bucket types are not served by the emulator, and those two pages say so;
  the other two list what the emulator holds.
- **Table buckets and File systems list what the emulator holds.**
  `GET /api/s3/table-buckets` and `GET /api/s3/file-systems`
  (`control/s3extra.py`) ask the emulator's own S3 Tables (`GET /buckets`) and S3
  Files (`GET /file-systems`) APIs through the same root-signed client, and the
  console renders the answer as a table. A refusal, or a body that is not the JSON
  those APIs document, is an error on the page — never an empty table that would
  read as "you have none". Verified live: both answer `200` with an empty list on
  an instance that has never created one.
- **The S3 table reports each bucket's own region.** `_annotate` stamped every S3
  row with the region being queried, which was true only while `ListBuckets`
  answered per region. The fork's listing is account-global (AWS parity), so every
  enabled region answers with every bucket, the first pass wins the dedupe, and
  buckets created in `us-east-2` or `us-west-2` were listed as `us-east-1`. The
  registry's own region is authoritative now, with the queried region kept as the
  fallback for a name it has never seen. Verified on the live instance: a bucket
  created in each enabled region lists with the region it was made in.
- **Creating a bucket works in every region, not only `us-east-1`.** AWS accepts
  an omitted `CreateBucketConfiguration` only on the global `us-east-1` endpoint;
  a regional endpoint requires the constraint and otherwise refuses with
  `IllegalLocationConstraintException: The unspecified location constraint is
  incompatible for the region specific endpoint this request was sent to` — which
  is exactly what the console's `create-bucket` was sending. `control/console.py`
  now takes the document from `buckets.location_constraint` (`_create_bucket_body`,
  threaded through `_s3`'s body argument) and still sends no body for `us-east-1`,
  where a constraint of its own name is itself invalid.
- **Put object sends the object's body.** The entry built its request with an
  empty payload, so the form's *Body* field was accepted and dropped and every
  object landed 0 bytes long. `_s3` now hands a callable body the form and the
  region, and `put-object` uses it (`_object_body`); the other S3 entries have no
  payload of their own and are unchanged.
- **Object keys are percent-encoded on the way out.** A key holding a space (or
  any reserved character) never left the box: the request line carried it raw and
  the HTTP client answered `InvalidURL: URL can't contain control characters`,
  which surfaced as a failed run. `_s3` now takes `quote_params` and encodes `Key`
  with `safe="/"` for `put-object` and `delete-object` — the separators S3 reads
  stay literal — and the emulator decodes the path, so a key round-trips
  unchanged (`notes/2026 Q4.csv`, `odd+#%/name.txt`). Emptying a bucket therefore
  works on keys like these too.
- **The picker writes the region into the URL on the click itself** (`Shell`'s
  `changeRegion`), instead of relying on the page's effect to notice afterwards.
  Both paths now exist — immediate write and effect sync — so the address bar
  changes even if a render is deferred.
- **Switching region updates the URL.** The page adopted `?region=` on every
  render where it differed, so the picker's choice was overwritten by the URL a
  moment later — switching looked like it did nothing. The URL now seeds the page
  once, on mount, and then follows the selection (the round trip `/s3/home`
  `?region=us-east-1` → picker → `?region=us-west-2` is covered by a test).

- **Enabling a region works again.** Removing the global-admin endpoint in
  `4f6464a` sliced from that route to the next occurrence of the buckets regex,
  which took `/api/regions`, `/api/refresh`, `/api/reserve`,
  `/api/nodes/<name>/reset` and the whole of `_route_delete` with it — Settings
  answered "not found" and `DELETE` would have thrown. All five are restored, and
  a QA row now pins their markers so the same slice cannot pass the gate.

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
