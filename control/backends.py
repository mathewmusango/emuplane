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
}


def profile(identifier: str | None) -> Backend:
    """The profile for `EP_BACKEND`; unset or unknown falls back to `ministack`, the tested backend."""
    return PROFILES.get((identifier or "").strip().lower(), PROFILES["ministack"])
