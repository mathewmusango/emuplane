"""Importing the control must not touch the store: every other role waits on that."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CONTROL = Path(__file__).resolve().parent.parent.parent / "control"


def _env() -> dict[str, str]:
    """The two public addresses the module requires, pointed at a port nothing listens on."""
    return {
        **os.environ,
        "EP_BACKEND_URL": "http://127.0.0.1:1",
        "EP_GATEWAY_URL": "http://localhost:4571",
        "EP_CONSOLE_URL": "http://localhost:4570",
    }


def _run(source: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=CONTROL,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_import_needs_no_store():
    """`import app` succeeds against an endpoint with nothing listening."""
    result = _run("import app")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_store_is_still_required_at_startup():
    """Laziness must not turn a missing store into a running control."""
    result = _run("import app; app.main()")
    assert result.returncode == 1
    assert "cannot reach the store" in result.stdout + result.stderr
