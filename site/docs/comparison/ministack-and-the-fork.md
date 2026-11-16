---
title: MiniStack and the fork
---

Emuplane runs on an AWS emulator, and the reference emulator is [MiniStack](https://ministack.org).
This project tracks a **fork** of it: a small set of changes the console needs,
kept deliberately narrow so the rest stays upstream's code.

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

:::note
The parity run for the current version is **outstanding**. The differences above
are the fork's documented intent; the per-release verification table gets its
first row with the next release.
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
