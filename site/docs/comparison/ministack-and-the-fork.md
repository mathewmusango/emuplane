---
title: MiniStack and the fork
---

Emuplane runs on an AWS emulator, and the reference emulator is [MiniStack](https://ministack.org).
This project tracks a **fork** of it —
[mathewmusango/ministack-upstream](https://github.com/mathewmusango/ministack-upstream),
built from upstream `v1.5.40`, the version it is forked from, with its S3 work on
`main`: a small set of changes
the console needs, kept deliberately narrow so the rest stays upstream's code.

The image the reference deployment runs is
`ghcr.io/mathewmusango/ministack-upstream:1.5.40-fork.3-full` — the `v1.5.40-fork.3`
release, `-full` being the Debian/glibc variant, named to drop in for upstream's
own `<version>-full` tags.

The fork's own notes are in `README.fork.md`, beside the code the image is built
from.

## Why a fork at all

An emulator answers requests. A console has to *show* them, which adds three
requirements an emulator does not have:

| Requirement | What it needed |
| --- | --- |
| **Isolation** — two accounts must not see each other's buckets | S3 state scoped by account **and** region, with one record per bucket and names unique per account |
| **Listing parity** — the console lists what AWS would list | `ListBuckets` answering account-wide, as AWS does, instead of per-region |
| **Identity** — someone has to sign in | Accounts, users, logins and access keys as first-class state, plus region enablement per account |

## What the fork changes

1. **S3 is account/region scoped.** The bucket store is keyed by account and
   region; a bucket name is unique within an account, refused in every region,
   and a bucket that is re-created keeps its owner.
2. **`ListBuckets` is account-global.** Every enabled region answers with every
   bucket the account owns, the way AWS does — so the console's listing is not a
   region's view pretending to be the account's.
3. **Tenancy and regions.** Accounts carry their enabled regions; the gateway
   refuses a request signed for a region the account has not enabled, and enables
   a region on first use.
4. **Accounts, logins and access keys.** The console's sign-in screens sit on top
   of real state rather than a single hard-coded identity.
5. **S3 usage**, so the console can show what an account has actually done.

Everything else — the services, the request handling, the emulator's own test
suite — is upstream's.

## What stays upstream's

The fork's `README.md` **is upstream's file**, unchanged, so the pending upstream
pull request carries only the code. Anything fork-specific lives in
`README.fork.md`: the S3 scoping, tenancy and regions, accounts and keys, usage,
and how the image is built and tagged.

## Compatibility with MiniStack

The fork is upstream `v1.5.40` plus one patch, so everything a client sees stays
the same:

- **Same API and ports.** Every service, operation and wire shape is upstream's;
  nothing is renamed and no endpoint moves.
- **Same configuration.** The emulator's own variables keep their names and
  meanings — `AUTH`, `PERSIST_STATE`, `S3_PERSIST`, `MINISTACK_REGION` and the
  rest.
- **Same image shape.** Built from upstream's `Dockerfile.full`, so the `-full`
  suffix keeps the pin a drop-in for upstream's own tag.
- **Same duplicate-name behaviour.** AWS's rule for an owner re-create is
  untouched: `200` in us-east-1 with the ACLs reset,
  `BucketAlreadyOwnedByYou` elsewhere.
- **One visible difference.** S3 state is region-scoped. A client that stays in
  one region sees no change at all.

| S3 behaviour | Plain MiniStack | The fork |
| --- | --- | --- |
| A bucket belongs to | the account, in every region | exactly one account and region |
| `ListBuckets` | every bucket in the account | the signing region's buckets |
| Wrong-region request | reaches the bucket | `301 PermanentRedirect` with `x-amz-bucket-region` |
| State | shared namespace | one record under `(account, region, name)` |

## How the differences are verified

A difference is only recorded here once it has been observed, twice:

1. The Emuplane suite is run against the **unmodified** MiniStack, and whatever
   fails is a difference — either a bug in our code or a behaviour we are
   deliberately adding.
2. The same run is repeated against the **fork**, and the difference is recorded
   in the release notes for the version it affects.

This is part of the release checklist, not an occasional audit: a release whose
parity run has not been done is not released.

## Measured, 2026-11-17

Both images were run side by side, each on its own port with `AUTH=true`, and asked
the same questions with raw signed requests. The account id in the credential was
the only thing that varied per request.

| Probe | upstream `1.5.40-full` | fork `1.5.40-fork.3-full` |
| --- | --- | --- |
| `CreateBucket` in us-west-2 with a `LocationConstraint` | 200 | 200 |
| `ListBuckets` signed for us-east-1, after a bucket in each region | sees both | sees both |
| `HEAD` a us-west-2 bucket signed for us-east-1 | `301` + `x-amz-bucket-region` | same |
| **Same name created in a second region** | **200 — re-owned** | **409 — refused** |
| Same name created by a second account | 409 | 409 |
| A second account listing or reading the first's bucket | cannot list, `403` on read | same |

So upstream 1.5.40 already redirects across regions, lists account-wide and keeps
accounts apart. **The only difference these probes found is the rename case** —
upstream lets a bucket name be re-used in another region, the fork refuses it —
which is the isolation the fork's patch adds, and it is narrower than the summary
table above suggests.

Emuplane itself ran against upstream without a change: `bootstrap/apply.py` created
the eleven tables, the control came up read-only as uid 10001, and the gateway
served `CreateBucket`, `ListBuckets`, cross-region `301` and duplicate-name `409`
through the same routes it uses against the fork. The earlier set of probes looked
identical through the gateway because the gateway answers the redirect itself — the
emulators only look different when probed directly.

:::note
The parity run for the current release is **outstanding** in the release notes; this
section records one dated experiment, not a per-release table.
:::

## Running against upstream

The backend is a profile plus a URL, so pointing at upstream MiniStack is a
configuration change, not a code change:

```bash title=".env"
EP_BACKEND=ministack
EP_BACKEND_URL=http://ministack:4566
```

`EP_BACKEND` names the profile (`generic`, `ministack`, `floci`, `localstack`,
`moto`) and decides how the control describes the backend in the console.
