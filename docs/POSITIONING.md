# Positioning and naming

Status: **proposed, not decided** (2026-11-05). Nothing in this repository is
renamed on the strength of it, and no name below is cleared.

## The product direction

The console is the seed of a **multi-engine infrastructure control plane**, not
just a dashboard over one AWS emulator.

- **Control plane** — one UI, one authentication layer, inventory, permissions,
  policy, audit trail, navigation and API. This repository already owns that
  half for the cloud-emulator case.
- **Engines** — independently versioned integrations that understand one
  ecosystem each: cloud emulators (MiniStack, LocalStack, Moto), Kubernetes
  (Kubernetes, k3s, RKE2), containers (Podman, Docker), virtualization
  (KVM/libvirt, Proxmox, VMware), storage (MinIO, NFS), data (PostgreSQL,
  Redis), identity (Keycloak, OpenBao), observability (Prometheus, Grafana,
  Loki).
- **Resources** — one way to search and navigate across them, without forcing
  every technology into an AWS-shaped model. Each engine exposes only the
  capabilities it really has, and native objects are preserved rather than
  flattened.

Phase 1 stays where the code already is: cloud emulators. Kubernetes and the
rest are a direction, not a commitment to build six products.

> [!IMPORTANT]
> Engines must not become separate applications with separate dashboards. The
> control plane owns the experience; an engine owns its ecosystem's logic.

## Naming

| Candidate | Status |
| --- | --- |
| `MUS` | an abbreviation of the author's name; too generic to own in search, and already used by a feedback product |
| `MUSTAM` | preferred over `MUS`, but has existing commercial use (a Turkish machinery manufacturer) |
| **`Kisinga`** | preferred direction — Kiikamba for a burning firebrand / "keep the fire alive". Brand story: firebrand = bringing infrastructure to life |

If Kisinga is adopted, the shape discussed was: brand **Kisinga**, descriptor
*Infrastructure Control Plane*, **Kisinga Console**, **Kisinga Core + Engines**,
tagline *Ignite your infrastructure*, charcoal/ember palette, and a geometric
"K" built from connected layers with a small ember accent (not a stock flame).

Before any of that becomes real: check trademarks (KIPI and the markets where it
would be distributed), domains, GitHub/npm/PyPI, and validate the meaning,
pronunciation and cultural associations with fluent Kamba speakers.

## Claims to leave out until measured here

The same thread flagged several lines that should not reach a README or a launch
post — they are the upstream project's figures, not this deployment's:

- "60+ AWS services" — use [`SERVICES.md`](SERVICES.md): 101 services and 2,519
  operations, of which 11 have console actions.
- "under 2 seconds", "~30 MB RAM" — unmeasured; this control adds its own image.
- "no tokens, no telemetry" — a commitment to make deliberately, not a slogan.
- port `4566` as a universal port — that is LocalStack's convention; here the
  gateway is `https://aws.mus.com` (and `4571` on loopback).

Branding must also not be built around a competitor's licensing or pricing: that
changes, and it is not the value this project offers.

## What this note does not change

Container names (`core-ministack`, `core-ministack-control`), repositories,
hostnames (`ministack.mus.com`, `aws.mus.com`) and the `MINISTACK_*` environment
variables all stay as they are. A rename would be a deliberate, separate change
after the screening above.
