#!/usr/bin/env python3
"""Write `openapi.json` from the control's own route table.

    python3 scripts/openapi.py           # rewrite the document
    python3 scripts/openapi.py --check   # fail when the document is stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from control_routes import routes, shape

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "control" / "app.py"
SPEC = ROOT / "openapi.json"
VERSION = re.compile(r'^API_VERSION = "([^"]+)"', re.M)


def api_version(app: Path) -> str:
    found = VERSION.search(app.read_text(encoding="utf-8"))
    if not found:
        raise SystemExit(f"openapi: no API_VERSION in {app}")
    return found.group(1)


def tag(path: str) -> str:
    segments = [segment for segment in path.split("/") if segment]
    return segments[1] if len(segments) > 1 else "root"


def operation_id(method: str, path: str) -> str:
    parts = [part.strip("{}") for part in path.split("/") if part]
    return "_".join([method.lower(), *parts])


def document(found: list[tuple[str, str]], version: str) -> dict[str, object]:
    paths: dict[str, dict[str, object]] = {}
    for method, pattern in found:
        path, parameters = shape(pattern)
        operation: dict[str, object] = {
            "tags": [tag(path)],
            "operationId": operation_id(method, path),
            "summary": f"{method} {path}",
            "responses": {"200": {"description": "What the route read or wrote."}},
        }
        if parameters:
            operation["parameters"] = parameters
        paths.setdefault(path, {})[method.lower()] = operation
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Emuplane control API",
            "version": version,
            "description": (
                "The console's own HTTP API, served on the control port. Generated "
                "from control/app.py by scripts/openapi.py. The AWS gateway on "
                "port 4571 is a different API and is not described here."
            ),
        },
        "servers": [
            {
                "url": "http://localhost:4570",
                "description": "The control container's published address.",
            }
        ],
        "security": [{"bearerAuth": []}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": (
                        "The token minted inside the container by "
                        "python /app/api_token.py. A console session cookie is "
                        "accepted too, but only for its own account."
                    ),
                }
            }
        },
        "paths": dict(sorted(paths.items())),
    }


def render() -> str:
    return json.dumps(document(routes(APP), api_version(APP)), indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    text = render()
    if args.check:
        current = SPEC.read_text(encoding="utf-8") if SPEC.is_file() else ""
        if current != text:
            print("openapi.json is out of date: run scripts/openapi.py", file=sys.stderr)
            return 1
        print(f"openapi.json is current ({len(json.loads(text)['paths'])} paths)")
        return 0

    SPEC.write_text(text, encoding="utf-8")
    print(f"wrote {SPEC.relative_to(ROOT)} ({len(json.loads(text)['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
