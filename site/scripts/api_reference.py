#!/usr/bin/env python3
"""Write the control API's route table into docs/reference/control-api.md.

Usage:
  npm run api                     # the repository this site lives in
  python3 scripts/api_reference.py <control checkout>
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = ROOT.parent
PAGE = ROOT / "docs" / "reference" / "control-api.md"
BEGIN = "<!-- routes:begin -->"
END = "<!-- routes:end -->"

METHODS = {
    "_route_get": "GET",
    "_route_post": "POST",
    "_route_delete": "DELETE",
}

IF_PATH = re.compile(r'^\s*if path (?:==|in) ')
FULLMATCH = re.compile(r'^\s*match = re\.fullmatch\(r"([^"]+)"')
LITERAL = re.compile(r'"([^"]*)"')
API = "/api"


def control_dir() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    named = os.environ.get("CONTROL_SRC", "")
    if named:
        return Path(named).resolve()
    return REPOSITORY


def dispatchers(lines: list[str]) -> dict[str, tuple[int, int]]:
    found = {}
    for index, line in enumerate(lines):
        match = re.match(r"^    def (_route_(?:get|post|delete))\(self\)", line)
        if match:
            found[match.group(1)] = index
    if not found:
        raise SystemExit("api_reference: no `_route_*` dispatchers in app.py")

    ranges = {}
    starts = sorted(found.items(), key=lambda item: item[1])
    for position, (name, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        ranges[name] = (start, end)
    return ranges


def routes(app: Path) -> list[tuple[str, str]]:
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


def table(found: list[tuple[str, str]]) -> str:
    paths = sorted({path for _method, path in found})
    lines = ["| Path | Methods |", "| --- | --- |"]
    for path in paths:
        methods = sorted({method for method, name in found if name == path})
        lines.append(f"| `{path}` | {', '.join(methods)} |")
    lines += ["", f"{len(found)} route/method pairs, {len(paths)} paths."]
    return "\n".join(lines)


def main() -> int:
    app = control_dir() / "control" / "app.py"
    if not app.is_file():
        raise SystemExit(f"api_reference: {app} is not there")

    page = PAGE.read_text(encoding="utf-8")
    if BEGIN not in page or END not in page:
        raise SystemExit(f"api_reference: {PAGE} has no generated block markers")

    head, _, rest = page.partition(BEGIN)
    _, _, tail = rest.partition(END)
    routes_found = routes(app)
    PAGE.write_text(head + BEGIN + "\n\n" + table(routes_found) + "\n\n" + END + tail)
    print(f"wrote {len(routes_found)} routes into {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
