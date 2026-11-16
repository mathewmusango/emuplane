# The console

The React console, served from `/app/static`. Vite + [Cloudscape](https://cloudscape.design/),
the AWS console design system, and it talks only to the control plane's `/api/*` routes.

```sh
npm ci            # install
npm run dev       # http://localhost:5173, with /api proxied to 127.0.0.1:4570
npm run build     # writes dist/, which the container mounts at /app/static
npm run typecheck # tsc --noEmit over api.ts and types.ts
npm test          # Vitest + Testing Library in jsdom
```

`dist/` and `node_modules/` are ignored. The control mounts `dist/` read-only, so a
change means `npm run build` and a container restart; until it exists, `/` answers
`503` with these instructions. Node 22 — the image's `node:22-alpine` stage is the
reference.

## Where things are

| Path | Purpose |
| --- | --- |
| `src/main.jsx`, `src/App.jsx` | theme, `I18nProvider`, router, session provider, routes |
| `src/context.jsx` | `/api/meta` session state: account, region, principal |
| `src/api.ts`, `src/types.ts` | the typed API client and its response types |
| `src/pages/` | Dashboard, Resources, Services, Settings, About, SignIn, and the S3 and access-point pages |
| `src/components/` | shell, top bar, services menu, theme toggle |
| `public/` | the mark, the favicons and the per-backend logos, served at `/` |
| `../tests/web/` | the console suite, beside the other tests |

Pages are the organisms; Cloudscape components are the atoms and molecules, so no
hand-rolled primitives are added. Each page owns its fetching and passes plain props.

## Conventions

- **Cloudscape first** — `CopyToClipboard` for ids and keys, `CollectionPreferences`
  and `@cloudscape-design/collection-hooks` for tables, `ErrorBoundary` around the
  routes, `all.en` messages through `I18nProvider`.
- **One comment per block, one line** — reasoning belongs in `site/docs/`.
- **`signin.css` is the only departure from stock** — it copies AWS's sign-in; its
  selectors are scoped to `.signin__*` or Cloudscape's semantic prefixes, never the
  hashed class names, so an upgrade cannot silently restyle the page.
- **Masked material only** — an access key's secret is rendered once, when it is
  created, and never read back. An account holds at most two keys.
- **One font, reduced motion respected** — Open Sans comes with the global styles;
  local animation is disabled under `prefers-reduced-motion: reduce`.

## Status

- **The sign-in screens are the login page.** `/login` is served without a session
  and `POST /api/auth/login` sets the session cookie; `?next=` is honoured, path-only.
  The code screen appears only when the server answers `mfa_required`, which is false
  until enrolment exists — `POST /api/auth/mfa` answers `501`.
- **TypeScript is incremental.** `api.ts` and `types.ts` are typed and `allowJs` is
  on; a file migrates by being renamed and kept green under `npm run typecheck`.
- **Forks are not build inputs.** The Cloudscape packages are forked under the same
  account so a patch can be carried, but everything installs from npm.

## References

- [Cloudscape components](https://cloudscape.design/components/) and
  [collection hooks](https://cloudscape.design/get-started/dev-guides/collection-hooks/)
- [aws-icons](https://github.com/MKAbuMattar/aws-icons), the source of the service icons
