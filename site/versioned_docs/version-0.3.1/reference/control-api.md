---
sidebar_position: 1
title: Control API
---

The console talks to one HTTP API on the control port. It is the same API an
operator can use by hand, and it is how the console avoids holding any AWS
secret: a route performs the signed call itself, as the account root, and answers
with what it read.

## Two callers, two credentials

| Caller | Credential | Reaches |
| --- | --- | --- |
| A person in the browser | the console session cookie | their own account only |
| The deployment | a bearer token minted inside the container (`python /app/api_token.py`) | every account |

A request with neither is refused. A request for an account the session does not
belong to is `403`, except for the bearer token, which is the one cross-tenant
principal.

## Answers

Every route answers JSON: `ok` for "the read or write happened", plus the data it
read. A failure answers a non-2xx status and `{"error": "…"}` with the
emulator's own sentence where there is one — the console shows that sentence
rather than inventing a friendlier one.

## The groups

- **Sign-in** — `/api/auth/*`: password, MFA, remember, switch identity.
- **Identity** — `/api/meta`, `/api/me`, `/api/accounts/me`: who is signed in,
  which account, which regions.
- **Accounts and people** — `/api/accounts`, `/api/users`, `/api/regions`,
  `/api/credentials`: create accounts, manage users, enable regions, mint and
  revoke access keys.
- **Reading the emulator** — `/api/browse`, `/api/counts`, `/api/services`,
  `/api/actions`, `/api/nodes`, `/api/refresh`: what the emulator holds, what the
  console serves, and which node answers for which region.
- **Acting on it** — `/api/exec`: one catalogue action, run as the account root.
- **The S3 pages** — `/api/s3/*`: buckets, objects, documents, settings, the three
  access point kinds, and the Multi-Region asynchronous operations. These do the
  work the console page claims, and nothing the page does not show.

## Calling it by hand

The console is one client; nothing stops you being another. The API explorer on a
service page is the same catalogue the console drives, and the same routes answer
the bearer token:

![The API explorer: the catalogue of actions, the form for the chosen one, and the aws command it maps to](/img/console/api-explorer.png)

```bash
curl -s http://localhost:4570/api/accounts/me -H "Authorization: Bearer $EP_TOKEN"
```

`$EP_TOKEN` is the token `scripts/token.sh` mints (or `python /app/api_token.py`
inside the container). A bearer caller has no account of its own, so a route that
needs one takes it from the request — that is what makes the token the one
cross-tenant principal.

## Every route

This table is generated from the control's own route table, so it cannot list a
route that does not exist or miss one that does. Regenerate it with:

```bash
npm run api   # reads the control checkout named by CONTROL_SRC
```

<!-- routes:begin -->

| Path | Methods |
| --- | --- |
| `/api/accounts` | POST |
| `/api/accounts/([0-9]{12})` | DELETE |
| `/api/accounts/([0-9]{12})/disabled` | POST |
| `/api/accounts/me` | GET |
| `/api/actions` | GET |
| `/api/auth/login` | POST |
| `/api/auth/mfa` | POST |
| `/api/auth/remember` | POST |
| `/api/auth/switch` | POST |
| `/api/browse` | GET |
| `/api/buckets` | GET |
| `/api/buckets/([^/]+)` | DELETE |
| `/api/counts` | GET |
| `/api/credentials` | GET, POST |
| `/api/exec` | POST |
| `/api/me` | POST |
| `/api/meta` | GET |
| `/api/nodes` | GET |
| `/api/nodes/([^/]+)/reset` | POST |
| `/api/refresh` | POST |
| `/api/regions` | POST |
| `/api/reserve` | POST |
| `/api/s3` | GET |
| `/api/s3/access-point-delete` | POST |
| `/api/s3/access-point-detail` | GET |
| `/api/s3/access-point-policy` | GET |
| `/api/s3/access-point-policy-edit` | POST |
| `/api/s3/access-points` | GET, POST |
| `/api/s3/bucket-document` | POST |
| `/api/s3/bucket-documents` | GET |
| `/api/s3/bucket-head` | GET |
| `/api/s3/bucket-settings` | GET |
| `/api/s3/bucket-settings-edit` | POST |
| `/api/s3/buckets` | POST |
| `/api/s3/empty` | POST |
| `/api/s3/file-systems` | GET |
| `/api/s3/mrap` | POST |
| `/api/s3/mrap-delete` | POST |
| `/api/s3/mrap-policy` | POST |
| `/api/s3/mrap-routes` | POST |
| `/api/s3/multipart-abort` | POST |
| `/api/s3/multipart-complete` | POST |
| `/api/s3/multipart-create` | POST |
| `/api/s3/multipart-part` | POST |
| `/api/s3/object` | GET, POST |
| `/api/s3/object-acl` | GET, POST |
| `/api/s3/object-annotation` | GET, POST |
| `/api/s3/object-copy` | POST |
| `/api/s3/object-download` | GET |
| `/api/s3/object-lambda` | POST |
| `/api/s3/object-lambda-configuration` | POST |
| `/api/s3/object-lambda-delete` | POST |
| `/api/s3/object-legal-hold` | POST |
| `/api/s3/object-meta` | GET |
| `/api/s3/object-retention` | POST |
| `/api/s3/object-rewrite` | POST |
| `/api/s3/object-tags` | POST |
| `/api/s3/object-upload` | POST |
| `/api/s3/object-version-delete` | POST |
| `/api/s3/objects` | GET |
| `/api/s3/table-buckets` | GET |
| `/api/s3/upload-parts` | GET |
| `/api/s3/uploads` | GET |
| `/api/s3/versions` | GET |
| `/api/services` | GET |
| `/api/settings` | GET |
| `/api/users` | GET, POST |

73 route/method pairs, 67 paths.

<!-- routes:end -->
