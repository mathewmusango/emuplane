---
sidebar_position: 2
title: Accounts, regions and keys
---

An **account** in Emuplane is a tenancy: it owns its users, its buckets, its
access keys and its list of enabled regions. Nothing crosses it except the
deployment's bearer token.

```mermaid
flowchart LR
  acct["Account<br/>124969375555"]
  acct --> users["Users<br/>root + IAM"]
  acct --> keys["Access keys<br/>used by tools"]
  acct --> regions["Enabled regions<br/>us-east-1, us-west-2, …"]
  acct --> res["Buckets and access points<br/>scoped to the account"]
  users --> sessions["Sessions<br/>console cookies"]
```

## Accounts

- A 12-digit id, an alias, and a root user created at sign-up.
- IAM users belong to one account and can be given their own password.
- A signed-in user may touch **its own account only**. The deployment bearer
  token is the one principal that may cross tenancies, and it exists so an
  operator can administer the lab rather than to act as a global root.

## Regions

- `us-east-1` is always enabled; it cannot be removed.
- Every other region an account uses has to be **enabled**, either from the
  console or **on first use** — a request signed for a region the account has not
  used yet enables it, exactly as the console's region menu does.
- The gateway enforces this per request, so a bucket cannot be created in a
  region the account never turned on.
- A bucket keeps its own home region. A request signed for a different region
  gets `301 PermanentRedirect` with `x-amz-bucket-region`, and the console reads
  that to send the page to the right place.

## Access keys

Access keys are what your tools use. They are minted per account in the console,
shown **once**, and the secret is not readable afterwards.

The gateway resolves the key to its account and checks the request's signing
region. It does **not** verify the signature: a local emulator has no secret to
verify against, so the gateway is a router with an authorisation rule, not an
authenticator. Do not put anything in front of it that you would not put on a
lab network.

## Sessions

- A console session is a cookie; the server keeps it keyed by a hash of the
  token, so a stolen cookie store does not hand anyone a working session.
- Resetting a password revokes that user's sessions.
- `/forgot` issues a single-use link. With no mail transport configured — the
  default — it says to ask an administrator, and `./scripts/password.sh` does the
  reset.

## What a token is, and is not

| Credential | Used by | Scope |
| --- | --- | --- |
| Console session | a person in the browser | one account, until it expires or is revoked |
| Access key | aws-cli, terraform, SDKs | one account, through the gateway |
| Bearer token | the deployment / operators | every account — the only cross-tenant principal |
