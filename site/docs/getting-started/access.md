---
sidebar_position: 3
title: Accessing it
---

Two addresses matter, and they serve different callers: the **console** answers a
browser, and the **gateway** answers anything that signs a request.

| What | On the host | Inside the compose network | Behind a proxy |
| --- | --- | --- | --- |
| Console and control API | `http://localhost:4570/` | `http://emuplane:4570` | `EP_CONSOLE_URL` |
| AWS gateway | `http://localhost:4571` | `http://emuplane:4571` | `EP_GATEWAY_URL` |

The host side publishes **only on loopback** (`127.0.0.1`), so `localhost:4570` is
the address on the machine running compose. From another machine, use the proxy
address or publish the port yourself. The ports are fixed: the container listens on
4570 and 4571, and publishes the same numbers.

The backend — the emulator itself — is **never published**. The control reaches it
over the compose network at `EP_BACKEND_URL`, which is why no AWS client ever needs
the emulator's address: it needs the gateway's.

## The console

```text
http://localhost:4570/          → redirects to /login
http://localhost:4570/signup    → the first account
```

A deployment with a proxy puts a name in front of the same port; that name is what
`EP_CONSOLE_URL` holds, and what the reset mail links to.

## The AWS CLI

An endpoint and a key, then the CLI is ordinary:

```bash
export AWS_ENDPOINT_URL=http://localhost:4571
export AWS_ACCESS_KEY_ID=<the key id from the console>
export AWS_SECRET_ACCESS_KEY=<the secret, shown once>
export AWS_DEFAULT_REGION=us-east-1

aws s3 ls
aws s3api list-buckets
```

Per command instead of environment:

```bash
aws --endpoint-url http://localhost:4571 --region us-east-1 s3 ls
```

The address is the gateway's, wherever it answers — `http://localhost:4571`,
`http://10.0.0.5:4571` once published, or the proxy's hostname. The region has to be
one the account has **enabled**; `us-east-1` always is, and any other region is
enabled on first use or from the console.

## The two kinds of key

| Key | Secret | Verified |
| --- | --- | --- |
| `AKIA…` issued in the console (**Account → Access keys**) | its own secret, shown once | yes — the emulator checks the signature |
| the 12-digit account id | anything | no — it is that account's root |

So `AWS_ACCESS_KEY_ID=<account id>` with `AWS_SECRET_ACCESS_KEY=x` works, by design,
and is what lets the control act as the account owner. For a client you actually
care about, issue an `AKIA…` key and keep the 12-digit form out of your scripts.

A request with **no** key at all is anonymous: an object read succeeds only where
the bucket's own policy allows it, and `ListBuckets` is refused with `403
AccessDenied` — see [Limits](../reference/limits.md#the-gateway).
