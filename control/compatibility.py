"""Which operations an emulator version can run, from the per-version change chain.

The window is the newest releases Emuplane supports. Each supported version is
described by the delta from the one below it; the floor's set is the base, so only
changes are written down. `compatibility.json` is the data; this module is the
reader, shared by the console gate, the coverage generator and the CI matrix.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def version_tuple(value: str) -> tuple[int, int, int] | None:
    found = _VERSION.match(str(value or "").strip())
    return tuple(int(part) for part in found.groups()) if found else None


def data_file() -> Path:
    """`EP_COMPATIBILITY` when set, else the repository root or the image's copy."""
    named = os.environ.get("EP_COMPATIBILITY", "").strip()
    if named:
        return Path(named)
    here = Path(__file__).resolve().parent
    for candidate in (
        here / "compatibility.json",
        here.parent / "compatibility.json",
        Path("/app/compatibility.json"),
    ):
        if candidate.is_file():
            return candidate
    return here.parent / "compatibility.json"


def split(entry: str) -> tuple[str, str]:
    """`ec2:CreateTransitGateway` -> (`ec2`, `CreateTransitGateway`)."""
    service, _, operation = str(entry).partition(":")
    return service.strip().lower(), operation.strip()


class Compatibility:
    """The window, and the operations each version in it can run."""

    def __init__(self, data: dict) -> None:
        self.data = data
        self.versions = [str(version) for version in data.get("versions") or []]
        self.window = int(data.get("window") or len(self.versions) or 0)
        self.ceiling = str(data.get("ceiling") or (self.versions[-1] if self.versions else ""))
        self.floor = self.versions[0] if self.versions else ""
        self.services = {
            str(key).lower(): dict(value or {})
            for key, value in (data.get("services") or {}).items()
        }
        self.deltas = {
            str(key): dict(value or {})
            for key, value in (data.get("deltas") or {}).items()
        }
        self._added: dict[tuple[str, str], str] = {}
        self._removed: dict[tuple[str, str], str] = {}
        self._advertised: dict[tuple[str, str], str] = {}
        for version in self.versions[1:]:
            delta = self.deltas.get(version, {})
            for entry in delta.get("added") or []:
                self._added[split(entry)] = version
            for entry in delta.get("removed") or []:
                self._removed[split(entry)] = version
            for entry in delta.get("advertised") or []:
                self._advertised[split(entry)] = version

    @property
    def supported(self) -> list[str]:
        """The newest `window` versions, oldest first."""
        return self.versions[-self.window :] if self.window else list(self.versions)

    def status(self, version: str) -> dict:
        """Where a version sits against the window, without guessing about its contents."""
        parsed = version_tuple(version)
        base = {
            "version": str(version or ""),
            "floor": self.floor,
            "ceiling": self.ceiling,
        }
        if parsed is None or not self.versions:
            return {**base, "state": "unknown", "supported": False}
        floor = version_tuple(self.floor)
        ceiling = version_tuple(self.ceiling)
        if floor and parsed < floor:
            return {**base, "state": "deprecated", "supported": False}
        if ceiling and parsed > ceiling:
            return {**base, "state": "untested", "supported": True}
        if version == self.ceiling:
            return {**base, "state": "supported", "supported": True}
        return {**base, "state": "outdated", "supported": True}

    def supports(self, service: str, operation: str, version: str) -> bool:
        """Whether `version` routes `service:operation`.

        Known versions are exact. Older than the floor is answered as the floor
        (best effort); newer than the ceiling is answered `True`, because the
        probe, not a guess, decides what an untested release does.
        """
        parsed = version_tuple(version)
        floor = version_tuple(self.floor)
        ceiling = version_tuple(self.ceiling)
        if parsed is None or not floor or not ceiling:
            return True
        if parsed > ceiling:
            return True
        effective = max(parsed, floor)
        key = (service.strip().lower(), operation.strip())
        added = self._added.get(key)
        if added and version_tuple(added) > effective:
            return False
        removed = self._removed.get(key)
        if removed and version_tuple(removed) <= effective:
            return False
        return True

    def since(self, service: str, operation: str) -> str:
        """The version an operation arrived in, or the floor for one the window inherited."""
        return self._added.get((service.strip().lower(), operation.strip()), self.floor)

    def advertised_since(self, service: str, operation: str) -> str:
        """The version that first advertised it; the coverage pages count advertised operations."""
        return self._advertised.get(
            (service.strip().lower(), operation.strip()), self.floor
        )

    def added(self, version: str) -> list[str]:
        """`service:operation` entries that version introduced."""
        return list(self.deltas.get(version, {}).get("added") or [])


_CACHE: Compatibility | None = None


def load(path: str | os.PathLike[str] | None = None) -> Compatibility:
    global _CACHE
    if path is not None:
        return Compatibility(json.loads(Path(path).read_text(encoding="utf-8")))
    if _CACHE is None:
        _CACHE = Compatibility(json.loads(data_file().read_text(encoding="utf-8")))
    return _CACHE
