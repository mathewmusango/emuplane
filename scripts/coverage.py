#!/usr/bin/env python3
"""Render every service's coverage page from `coverage/<service>.json`.

One data file per service, one generated page per service. `--check` fails when any
page is stale, which is what CI runs.
"""

from __future__ import annotations

import sys

from coverage_engine import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
