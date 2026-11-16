---
sidebar_position: 1
title: Architecture
---

Three processes matter, and only two of them are Emuplane's: your tools, the
gateway, and the emulator — with the console and control plane sitting on top of
the emulator rather than in the request path.

```mermaid
flowchart TB
  subgraph tools["Your tools"]
    awscli["aws-cli / SDK"]
    tf["terraform"]
  end

  subgraph ep["Emuplane (one image, one container)"]
    gw["Gateway :8081<br/>access key → account<br/>region enabled?<br/>forward"]
    ctl["Control :8080<br/>console pages<br/>control API<br/>sessions"]
  end

  subgraph backend["Emulator"]
    emu["AWS APIs :4566"]
    ddb["DynamoDB<br/>emuplane tables"]
  end

  awscli --> gw
  tf --> gw
  gw --> emu
  ctl -->|signed reads| emu
  ctl -->|accounts, sessions,<br/>keys, settings| ddb
```

## The gateway owns one rule per request

1. **Which account?** The access key in the SigV4 header names one account; a key
   that names none is refused.
2. **Is its region enabled?** A signing region the account has not enabled is
   `403 AccessDenied` at the gateway, before the emulator is asked. This is what
   stops a bucket from appearing in a region the account never turned on.
3. **Forward.** Everything else the emulator decides.

The gateway checks the *shape* of the request, not the secret behind it: a local
emulator has no secret to check against, and the console's own calls are signed
the same way. Treat the gateway as a router with an authorisation rule, not as an
authenticator.

## The control plane owns the rest

Accounts, users, sessions, access keys, region enablement, both registries and
the console's settings are all Emuplane state — and all of it lives in the
emulator's DynamoDB, one table per store, prefixed `emuplane-`:

| Table | Holds |
| --- | --- |
| `emuplane-accounts` | accounts, their enabled regions, their root and IAM users |
| `emuplane-users` | the users of every account |
| `emuplane-sessions` | live sessions, keyed by a hash of the token |
| `emuplane-resets` | single-use password-reset links |
| `emuplane-owners` | which account claimed which resource name |
| `emuplane-settings` | deployment settings and the bearer token hash |
| `emuplane-buckets`, `emuplane-bucket_nodes` | the console's bucket and node registry |
| `emuplane-cells`, `emuplane-principals`, `emuplane-audit` | the substrate records |

There is no database container, no data volume and nothing on the host: the
console is stateless, so replacing the container costs nothing.

The control refuses to start on a missing table rather than serving and failing
later — which is why `bootstrap` runs first and why its failure is fatal.

## Why the console reads rather than trusts

The console asks the emulator for the resource it is about to show — an access
point's report, an object's own tags — rather than rendering a listing twice and
hoping. Two consequences follow, and both are deliberate:

- A read that fails is an **error**, never an empty table.
- A control the backend cannot carry is **absent**, never disabled-looking.

## Where the request path ends

Nothing in Emuplane talks to real AWS. There is no egress rule, no credential
store and no forwarding to a public endpoint; the only outbound call the code
makes is the optional password-reset mail.
