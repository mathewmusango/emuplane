#!/usr/bin/env python3
"""The backends Emuplane can front, each a profile — a name, a port and its quirks — never a variant of the code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Backend:
    """What the console and the operator need to know about a backend."""

    id: str
    title: str = ""          # the backend's name, shown in About
    port: int = 4566         # the port that backend listens on by default
    logo: str = ""           # optional mark; empty means Emuplane's own
    note: str = ""           # one line of operator context, not behaviour


PROFILES: dict[str, Backend] = {
    "generic": Backend(
        "generic",
        note="Any backend that speaks the same wire protocol as the rest.",
    ),
    "ministack": Backend(
        "ministack",
        title="MiniStack",
        note="S3 state is account-scoped, and every region is served by one endpoint.",
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
