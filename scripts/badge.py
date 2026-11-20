#!/usr/bin/env python3
"""The Best Practices badge: the claims file, the prefilled URLs, and the drift check.

The entry at bestpractices.dev is answered by a human. This file keeps what the
repository claims in `.bestpractices.json`, hands that to the badge site as
automation proposals, and notices when the saved entry and the claims disagree.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / ".bestpractices.json"
VERSIONS = ROOT / "site" / "versions.json"
PROJECT = 16933
HOST = "www.bestpractices.dev"
VERSION = re.compile(r"\bv\d+\.\d+\.\d+\b")


def newest_release() -> str:
    """The version the site serves as released."""
    return json.loads(VERSIONS.read_text(encoding="utf-8"))[0]


def normalize(claims: dict) -> dict:
    """The one ordering and formatting this file is written in."""
    return dict(sorted(claims.items()))


def load_claims() -> dict:
    return normalize(json.loads(CLAIMS.read_text(encoding="utf-8")))


def stale_versions(claims: dict) -> list[str]:
    """Justifications that name releases but never the newest one."""
    latest = f"v{newest_release()}"
    stale = []
    for key, value in claims.items():
        if not key.endswith("_justification"):
            continue
        found = VERSION.findall(value)
        if found and latest not in found:
            stale.append(f"{key}: {', '.join(found)}")
    return stale


def automation_url(claims: dict, section: str = "passing") -> str:
    """The prefilled edit URL: the badge site highlights these, a human saves them."""
    pairs = [(key, value) for key, value in claims.items() if value not in ("", None)]
    query = urllib.parse.urlencode(pairs, quote_via=urllib.parse.quote)
    return f"https://{HOST}/en/projects/{PROJECT}/{section}/edit?{query}"


def live_status(name: str) -> str:
    """The badge site answers baseline criteria under their OSPS identifier."""
    match = re.fullmatch(r"osps_([a-z]{2})_(\d{2})_(\d{2})_status", name)
    if not match:
        return name
    category, number, section = match.groups()
    return f"OSPS-{category.upper()}-{number}.{section}_status"


def fetch(url: str) -> str:
    """One GET, read whole; the badge site serves a small JSON document."""
    connection = http.client.HTTPSConnection(HOST, timeout=30)
    connection.request("GET", url, headers={"User-Agent": "emuplane-badge-check"})
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    connection.close()
    if response.status != 200:
        raise SystemExit(f"{url} answered {response.status}")
    return body


def check() -> int:
    claims = load_claims()
    entry = json.loads(fetch(f"/projects/{PROJECT}.json"))
    unanswered, divergent = [], []
    for key, value in claims.items():
        if not key.endswith("_status") or value == "?":
            continue
        saved = entry.get(live_status(key), "?")
        if saved in ("", "?"):
            unanswered.append(key)
        elif saved != value:
            divergent.append(f"{key}: claims {value}, entry says {saved}")
    for line in stale_versions(claims):
        divergent.append(f"stale release in {line}")
    for key in unanswered:
        print(f"not answered yet: {key}")
    for line in divergent:
        print(f"::error::{line}", file=sys.stderr)
    print(f"{len(claims)} claims, {len(unanswered)} unanswered, {len(divergent)} divergent")
    return 1 if divergent else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    verbs = parser.add_mutually_exclusive_group(required=True)
    verbs.add_argument("--write", action="store_true", help="rewrite .bestpractices.json in its canonical form")
    verbs.add_argument("--urls", action="store_true", help="print the prefilled automation URL")
    verbs.add_argument("--check", action="store_true", help="compare the claims with the saved entry")
    verbs.add_argument("--check-file", action="store_true", help="fail when the file is not what --write produces")
    parser.add_argument("--section", default="passing", help="the badge section, e.g. passing or baseline-1")
    args = parser.parse_args()

    if args.write:
        claims = load_claims()
        CLAIMS.write_text(json.dumps(claims, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(claims)} claims into {CLAIMS.name}")
        return 0
    if args.check_file:
        stored = json.loads(CLAIMS.read_text(encoding="utf-8"))
        if normalize(stored) != stored:
            print("::error::.bestpractices.json is not in canonical order; run scripts/badge.py --write", file=sys.stderr)
            return 1
        print(f"{CLAIMS.name} is canonical")
        return 0
    if args.urls:
        print(automation_url(load_claims(), args.section))
        return 0
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
