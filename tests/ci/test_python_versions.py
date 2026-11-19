"""The badge, the matrix and the image name one range: a bump to any of them fails the other two."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SERIES = r"\d+\.\d+"
IMAGE = re.compile(rf"^FROM docker\.io/library/python:({SERIES})-alpine", re.MULTILINE)
MATRIX = re.compile(r"python-version:\s*\[([^\]]*)\]")
BADGE = re.compile(r'badge/python-([^"]*)-blue')


def matrix() -> list[str]:
    """The versions `tests.yml` runs, in the order it lists them."""
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    return re.findall(SERIES, MATRIX.search(text).group(1))


def image() -> str:
    """The interpreter the runtime image carries."""
    return IMAGE.search((ROOT / "Dockerfile").read_text(encoding="utf-8")).group(1)


def badge() -> list[str]:
    """The versions the README advertises."""
    return re.findall(SERIES, BADGE.search((ROOT / "README.md").read_text(encoding="utf-8")).group(1))


def test_the_badge_is_the_matrix():
    assert badge() == matrix(), f"the badge says {badge()}, the matrix runs {matrix()}"


def test_the_matrix_is_a_contiguous_range():
    """A gap would let the badge promise a version that no job runs."""
    seen = [tuple(int(part) for part in series.split(".")) for series in matrix()]
    for previous, following in zip(seen, seen[1:]):
        assert following == (previous[0], previous[1] + 1), f"{previous} then {following} skips a version"


def test_the_image_ships_a_tested_interpreter():
    assert image() in matrix(), f"the image ships {image()}, the matrix runs {matrix()}"
