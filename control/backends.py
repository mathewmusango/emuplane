#!/usr/bin/env python3
"""The backends Emuplane can front, and the little that differs between them.

Emuplane is not an emulator: it is the control plane, console and gateway in
front of one. MiniStack, Floci, LocalStack and Moto all answer the same AWS wire
protocol, so the difference is a **profile** — a display name, a default port and
the handful of quirks worth knowing — never a fork of the code.

`EP_BACKEND` selects one (default `generic`); `EP_BACKEND_URL` is the connection
string and is the only thing that has to be right for the gateway to work.
Adding a backend is a row in `PROFILES`, or nothing at all if `generic` fits.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Backend:
    """What the console and the operator need to know about a backend."""

    id: str
    title: str = ""          # shown as the node's name; empty means the URL host
    port: int = 4566         # the port that backend listens on by default
    logo: str = ""           # console mark, served from web/public; empty is fine
    note: str = ""           # one line of operator context, not behaviour


PROFILES: dict[str, Backend] = {
    "generic": Backend(
        "generic",
        note="Any backend that speaks the same wire protocol as the rest.",
    ),
    "ministack": Backend(
        "ministack",
        title="MiniStack",
        logo="/backends/ministack.png",
        note="S3 state is account-scoped and the fork serves every region.",
    ),
    "floci": Backend(
        "floci",
        title="Floci",
        note="LocalStack-shaped; check its S3 region semantics before relying on them.",
    ),
    "localstack": Backend(
        "localstack",
        title="LocalStack",
        note="Community edition lacks some services the catalogue lists.",
    ),
    "moto": Backend(
        "moto",
        title="Moto",
        port=5000,
        note="Single-threaded test server; the poller and the console still work.",
    ),
}


def profile(identifier: str | None) -> Backend:
    """The profile for `EP_BACKEND`; an unknown id falls back to generic."""
    return PROFILES.get((identifier or "").strip().lower(), PROFILES["generic"])
