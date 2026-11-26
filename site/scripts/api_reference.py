#!/usr/bin/env python3
"""Write the control API's route table into docs/reference/control-api.md."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = ROOT.parent
PAGE = ROOT / "docs" / "reference" / "control-api.md"
BEGIN = "<!-- routes:begin -->"
END = "<!-- routes:end -->"

sys.path.insert(0, str(REPOSITORY / "scripts"))

from control_routes import API, routes  # noqa: E402


def control_dir() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    named = os.environ.get("CONTROL_SRC", "")
    if named:
        return Path(named).resolve()
    return REPOSITORY


def groups(found: list[tuple[str, str]]) -> list[tuple[str, list[tuple[str, str]]]]:
    """Routes by the segment after /api, biggest group first."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for method, path in found:
        segment = path[len(API) :].lstrip("/").split("/")[0] or "root"
        grouped.setdefault(segment, []).append((method, path))
    return sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))


def table(found: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    for segment, items in groups(found):
        paths = sorted({path for _method, path in items})
        label = "path" if len(paths) == 1 else "paths"
        lines += [
            f"### /api/{segment} — {len(paths)} {label}",
            "",
            "| Path | Methods |",
            "| --- | --- |",
        ]
        for path in paths:
            methods = sorted({method for method, name in items if name == path})
            lines.append(f"| `{path}` | {', '.join(methods)} |")
        lines.append("")
    paths = {path for _method, path in found}
    lines.append(f"{len(found)} route/method pairs, {len(paths)} paths.")
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
