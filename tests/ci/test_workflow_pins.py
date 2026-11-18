"""Every action reference is a commit SHA: a tag belongs to its owner and can be repointed, a commit cannot."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows"
PINNED = re.compile(r"@[0-9a-f]{40}$")


def references(path: Path) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0]
        if "uses:" not in code:
            continue
        found.append((number, code.split("uses:", 1)[1].strip().strip("\"'")))
    return found


def test_every_action_reference_is_a_commit():
    unpinned = [
        f"{path.name}:{number} {reference}"
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for number, reference in references(path)
        if not PINNED.search(reference)
    ]
    assert not unpinned, "actions must be pinned to a 40-character commit: " + "; ".join(unpinned)


def test_the_scan_sees_the_workflows():
    """A glob that silently matched nothing would make the test above pass for the wrong reason."""
    assert len(list(WORKFLOWS.glob("*.yml"))) >= 10
