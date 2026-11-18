"""The npm audit gate: every lockfile, failing on any high or critical advisory not named in the allowlist."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / ".github" / "npm-audit-allowlist.json"
FAILING = {"high", "critical"}


def locks() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("package-lock.json")
        if "node_modules" not in path.parts and ".git" not in path.parts
    )


def report(directory: Path) -> dict:
    finished = subprocess.run(
        ["npm", "audit", "--package-lock-only", "--json"],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return json.loads(finished.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"npm audit in {directory} did not answer with JSON")


def advisories(document: dict) -> dict[str, str]:
    """The advisory rows only: a transitive entry carries its parent's name, not an advisory."""
    found: dict[str, str] = {}
    for entry in document.get("vulnerabilities", {}).values():
        for via in entry.get("via", []):
            if isinstance(via, dict) and via.get("severity") in FAILING:
                found[via["url"].rsplit("/", 1)[-1]] = via.get("title") or ""
    return found


def main() -> int:
    allowed = {
        entry["id"]
        for entry in json.loads(ALLOWLIST.read_text(encoding="utf-8"))["advisories"]
    }
    failed = False
    for lock in locks():
        where = lock.parent.relative_to(ROOT)
        found = advisories(report(lock.parent))
        if not found:
            print(f"clean  {where}")
        for advisory, title in sorted(found.items()):
            if advisory in allowed:
                print(f"allowed  {where}: {advisory} {title}")
                continue
            failed = True
            print(f"FAIL  {where}: {advisory} {title}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
