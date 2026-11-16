#!/usr/bin/env python3
"""QA gate: signed-off behaviour must still be there and nothing secret leaks; `--tests` also runs both suites."""

from __future__ import annotations

import argparse
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "qa" / "tasks.json"

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{20,}"),
]
IGNORED_DIRS = {".git", "node_modules", "dist", "target", "__pycache__"}
# CONTRIBUTING.md is absent on purpose while contributions are closed; see the note below.
POLICY_FILES = ("SECURITY.md", "LICENSE", "CODE_OF_CONDUCT.md")


def load() -> dict:
    if not MANIFEST.exists():
        return {"tasks": []}
    with open(MANIFEST, encoding="utf-8") as handle:
        return json.load(handle)


def verify(manifest: dict) -> list[str]:
    problems = []
    for task in manifest["tasks"]:
        if task.get("status") != "done" or task.get("reopened"):
            continue
        for item in task.get("evidence", []):
            path = ROOT / item["file"]
            if not path.is_file():
                problems.append(f"{task['id']}: missing {item['file']}")
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                problems.append(f"{task['id']}: cannot read {item['file']} ({exc})")
                continue
            if item["marker"] not in text:
                problems.append(
                    f"{task['id']}: marker missing from {item['file']} — "
                    f"was the work reverted? ({item['marker']})"
                )
    return problems


def tracked_files() -> list[Path]:
    try:
        output = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return [
            path
            for path in ROOT.rglob("*")
            if path.is_file() and not (set(path.parts) & IGNORED_DIRS)
        ]
    return [ROOT / line for line in output.splitlines() if line.strip()]


def security() -> list[str]:
    problems = []
    files = tracked_files()
    names = {path.relative_to(ROOT).as_posix() for path in files}
    for required in POLICY_FILES:
        if required not in names:
            problems.append(f"missing repo policy file {required}")
    if "CONTRIBUTING.md" not in names:
        print("qa: contributions are closed, so CONTRIBUTING.md is deliberately absent")
    if ".env" in names:
        problems.append(".env is tracked; secrets must never be committed")
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative.endswith((".png", ".jpg", ".ico", ".woff", ".woff2")):
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if relative.endswith(".example"):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"{relative}: looks like a committed secret")
                break
    return problems


def compile_python() -> list[str]:
    problems = []
    for path in (ROOT / "control").glob("*.py"):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            problems.append(f"{path.name}: {exc.msg}")
    return problems


def test_python() -> list[str]:
    """`tests/` needs pytest, which the runtime image does not ship: run it where it exists."""
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("pytest is not installed: skipped tests/")
        return []
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"], cwd=ROOT
    )
    return [] if result.returncode == 0 else ["python test suite failed"]


def coverage() -> list[str]:
    """The published coverage page is generated, so a stale one is a failure; without the emulator checkout it passes."""
    readme = ROOT.parent / "ministack-src" / "README.md"
    script = ROOT / "scripts" / "s3_coverage.py"
    if not readme.is_file() or not script.is_file():
        print("ministack-src is not checked out: skipped the S3 coverage check")
        return []
    result = subprocess.run([sys.executable, str(script), "--check"], cwd=ROOT)
    return (
        []
        if result.returncode == 0
        else ["the S3 coverage page is out of date: run scripts/s3_coverage.py"]
    )


def docs_assets() -> list[str]:
    """Every image the documentation names must be a file the site can serve."""
    problems = []
    docs = ROOT / "site" / "docs"
    static = ROOT / "site" / "static"
    mark = static / "img" / "mark.png"
    if docs.is_dir() and not mark.is_file():
        problems.append("site/static/img/mark.png is missing: run npm --prefix site run build")
    for page in sorted(docs.rglob("*.md*")) if docs.is_dir() else []:
        text = page.read_text(encoding="utf-8", errors="ignore")
        for reference in re.findall(r"!\[[^\]]*\]\(([^)\s]+)", text):
            if reference.startswith(("http://", "https://", "data:")):
                continue
            target = (
                static / reference.lstrip("/")
                if reference.startswith("/")
                else page.parent / reference
            )
            if not target.is_file():
                problems.append(
                    f"{page.relative_to(ROOT).as_posix()} shows {reference}, which is not a file"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", action="store_true")
    args = parser.parse_args()

    manifest = load()
    problems = verify(manifest) + security() + compile_python() + coverage() + docs_assets()
    if args.tests:
        result = subprocess.run(["npm", "test", "--silent"], cwd=ROOT / "web")
        if result.returncode != 0:
            problems.append("web test suite failed")
        problems.extend(test_python())

    if problems:
        print("QA gate failed:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    done = [task for task in manifest["tasks"] if task.get("status") == "done"]
    if manifest["tasks"]:
        print(
            f"QA gate passed: {len(done)}/{len(manifest['tasks'])} tasks signed off, "
            "no secret patterns, Python compiles"
        )
    else:
        print(
            "QA gate passed: no local qa/tasks.json, no secret patterns, "
            "Python compiles"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
