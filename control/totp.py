"""RFC 6238 TOTP: the six-digit code an authenticator derives from a base32 seed."""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time

PERIOD = 30
DIGITS = 6


def _key(secret: str) -> bytes:
    cleaned = "".join(ch for ch in (secret or "").upper() if ch.isalnum())
    cleaned += "=" * ((8 - len(cleaned) % 8) % 8)
    return base64.b32decode(cleaned, casefold=True)


def code_at(secret: str, moment: float | None = None) -> str:
    """The code for the 30-second step containing `moment` (now by default)."""
    counter = int((time.time() if moment is None else moment) // PERIOD)
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 10 ** DIGITS:0{DIGITS}d}"


def matches(secret: str, code: str, window: int = 1) -> bool:
    """True when `code` is the current code, allowing one step either side for clock skew."""
    candidate = (code or "").strip()
    if len(candidate) != DIGITS or not candidate.isdigit():
        return False
    try:
        now = time.time()
        return any(
            code_at(secret, now + drift * PERIOD) == candidate
            for drift in range(-window, window + 1)
        )
    except (ValueError, TypeError):
        return False
