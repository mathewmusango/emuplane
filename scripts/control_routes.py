"""Read the control's route table out of `control/app.py`.

One reader for both consumers — the docs page (`site/scripts/api_reference.py`)
and the OpenAPI document (`scripts/openapi.py`) — so the two cannot drift.
"""

from __future__ import annotations

import re
from pathlib import Path

METHODS = {
    "_route_get": "GET",
    "_route_post": "POST",
    "_route_delete": "DELETE",
}

IF_PATH = re.compile(r"^\s*if path (?:==|in) ")
FULLMATCH = re.compile(r'^\s*[A-Za-z_]\w* = re\.fullmatch\(r"([^"]+)"')
LITERAL = re.compile(r'"([^"]*)"')
CAPTURE = re.compile(r"\(([^()]*)\)")
API = "/api"

# The path parameter a collection's one-segment capture stands for.
PARAMETERS = {
    "accounts": "account_id",
    "buckets": "bucket",
    "nodes": "node",
    "users": "user",
}


def dispatchers(lines: list[str]) -> dict[str, tuple[int, int]]:
    found = {}
    for index, line in enumerate(lines):
        match = re.match(r"^    def (_route_(?:get|post|delete))\(self\)", line)
        if match:
            found[match.group(1)] = index
    if not found:
        raise SystemExit("control_routes: no `_route_*` dispatchers in app.py")

    ranges = {}
    starts = sorted(found.items(), key=lambda item: item[1])
    for position, (name, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        ranges[name] = (start, end)
    return ranges


def routes(app: Path) -> list[tuple[str, str]]:
    """Every (method, path) the control dispatches, regex routes included."""
    lines = app.read_text(encoding="utf-8").splitlines()
    found: set[tuple[str, str]] = set()
    for name, (start, end) in dispatchers(lines).items():
        method = METHODS[name]
        block = lines[start:end]
        index = 0
        while index < len(block):
            line = block[index]
            if IF_PATH.match(line):
                condition = line
                depth = line.count("(") - line.count(")")
                while depth > 0 and index + 1 < len(block):
                    index += 1
                    condition += block[index]
                    depth += block[index].count("(") - block[index].count(")")
                for literal in LITERAL.findall(condition):
                    if literal.startswith(API):
                        found.add((method, literal))
            shaped = FULLMATCH.match(line)
            if shaped and shaped.group(1).startswith(API):
                found.add((method, shaped.group(1)))
            index += 1
    return sorted(found, key=lambda item: (item[1], item[0]))


def parameter_name(pattern: str, segments: list[str], index: int) -> str:
    if index == 0:
        raise SystemExit(f"control_routes: {pattern!r} captures before any collection")
    collection = segments[index - 1]
    name = PARAMETERS.get(collection, "")
    if not name:
        raise SystemExit(
            f"control_routes: {pattern!r} captures under /{collection}/; "
            "add it to PARAMETERS"
        )
    return name


def shape(pattern: str) -> tuple[str, list[dict[str, object]]]:
    """A regex route as an OpenAPI path plus its path parameters."""
    captures = CAPTURE.findall(pattern)
    if not captures:
        return pattern, []
    order = iter(range(len(captures)))
    marked = CAPTURE.sub(lambda _found: f"\x00{next(order)}\x00", pattern)
    segments = marked.split("/")
    shaped: list[str] = []
    parameters: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        marker = re.fullmatch(r"\x00(\d+)\x00", segment)
        if not marker:
            shaped.append(segment)
            continue
        expression = captures[int(marker.group(1))]
        name = parameter_name(pattern, segments, index)
        shaped.append("{" + name + "}")
        schema: dict[str, object] = {"type": "string"}
        if expression != "[^/]+":
            schema["pattern"] = "^" + expression + "$"
        parameters.append(
            {"name": name, "in": "path", "required": True, "schema": schema}
        )
    return "/".join(shaped), parameters
