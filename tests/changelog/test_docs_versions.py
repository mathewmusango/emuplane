"""A version tag named in the working docs must be the release the site serves."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = ROOT / "site" / "docs"
VERSIONS = ROOT / "site" / "versions.json"

# A concrete image tag, which is the one place a page names a release outright.
# `ghcr.io/…:X.Y.Z` and `ghcr.io/…:vX.Y.Z` both count; a placeholder does not.
IMAGE = re.compile(r"ghcr\.io/mathewmusango/emuplane:v?(\d+\.\d+\.\d+)")


def served() -> str:
    """The release the site serves at /docs, which is what a reader sees first."""
    return json.loads(VERSIONS.read_text(encoding="utf-8"))[0]


def named_tags() -> list[tuple[str, str]]:
    found = []
    for page in sorted(DOCS.rglob("*.md")):
        for tag in IMAGE.findall(page.read_text(encoding="utf-8")):
            found.append((page.relative_to(ROOT).as_posix(), tag))
    return found


def test_the_docs_name_the_release_the_site_serves():
    want = served()
    stale = [f"{page}: {tag}" for page, tag in named_tags() if tag != want]
    assert not stale, (
        f"the served version is {want}; these pages name another image tag "
        f"(fixed copies of a release may differ, working docs may not): "
        + ", ".join(stale)
    )


def test_the_release_plan_bumps_the_docs_tag_before_freezing():
    """The freeze copies site/docs, so the plan has to bump a named tag first."""
    plan = (ROOT / ".github" / "workflows" / "release-plan.yml").read_text(encoding="utf-8")
    write = plan[plan.index("Write the section on a release branch"):]
    write = write[: write.index("Open or update the release pull request")]
    assert "site/docs" in write, "release-plan never touches site/docs"
    assert write.index("site/docs") < write.index("npm --prefix site run version"), (
        "the docs tag is bumped after the freeze, which copies it stale"
    )


def test_the_served_version_is_frozen():
    want = served()
    frozen = ROOT / "site" / "versioned_docs" / f"version-{want}"
    assert frozen.is_dir(), (
        f"versions.json leads with {want} but {frozen.relative_to(ROOT).as_posix()} "
        "is missing: /docs would serve a version with no pages behind it"
    )


def test_the_scan_finds_a_tag():
    """A regex that matched nothing would make the first test pass for the wrong reason."""
    assert named_tags(), "no ghcr.io/…/emuplane:<x.y.z> reference found in site/docs"
