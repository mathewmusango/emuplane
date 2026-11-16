#!/usr/bin/env python3
"""Write `S3.md`: what S3 offers, and who tests each part of it.

Three sources, no hand-maintained list:

  * the operations upstream advertises — the `| **S3** |` row of the emulator's
    own README (`ministack-src`, a sibling checkout);
  * the console actions — `control/console.py`, which is what the API explorer
    and the create page are built from;
  * the emuplane tests — the map below, kept honest by hand because a test name
    cannot be derived from an operation name.

Everything not in the map is reachable through the gateway and covered only by
the emulator's own suite: that is the point of the last column.

Usage:
  python3 scripts/s3_coverage.py            # write S3.md
  python3 scripts/s3_coverage.py --check    # fail when S3.md is out of date
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMULATOR = ROOT.parent / "ministack-src"
README = EMULATOR / "README.md"
TARGET = ROOT / "S3.md"

# Operation -> the emuplane test that exercises it. Everything else is
# gateway-only: the emulator's own `tests/test_s3.py` covers it, emuplane does
# not look.
COVERED = {
    "CreateBucket": "tests/s3/test_create.py, tests/control/test_gateway.py",
    "DeleteBucket": "tests/control/test_gateway.py",
    "HeadBucket": "tests/control/test_gateway.py (301 path)",
    "ListBuckets": "tests/control/test_api.py (via /api/browse)",
    "PutObject": "tests/control/test_api.py",
    "ListObjects v1/v2": "tests/control/test_api.py (v2)",
    "DeleteObject": "tests/web/s3.test.jsx (Empty loop), tests/s3/test_catalogue.py",
    "GetBucketVersioning": "tests/s3/test_create.py",
    "PutBucketVersioning": "tests/s3/test_create.py",
    "GetBucketEncryption": "tests/s3/test_create.py",
    "PutBucketEncryption": "tests/s3/test_create.py",
    "GetBucketTagging": "tests/s3/test_create.py",
    "PutBucketTagging": "tests/s3/test_create.py",
    "PutPublicAccessBlock": "tests/s3/test_create.py",
    "GetPublicAccessBlock": "tests/s3/test_create.py",
    "GetObjectLockConfiguration": "tests/s3/test_create.py",
    "PutObjectLockConfiguration": "tests/s3/test_create.py (at create)",
}

GROUPS = [
    (
        "Buckets and objects",
        [
            "CreateBucket", "DeleteBucket", "ListBuckets", "HeadBucket",
            "PutObject", "GetObject", "DeleteObject", "HeadObject",
            "CopyObject", "ListObjects v1/v2", "DeleteObjects",
        ],
    ),
    (
        "Bucket configuration",
        [
            "GetBucketVersioning", "PutBucketVersioning",
            "GetBucketEncryption", "PutBucketEncryption", "DeleteBucketEncryption",
            "GetBucketLifecycleConfiguration", "PutBucketLifecycleConfiguration",
            "DeleteBucketLifecycle", "GetBucketCors", "PutBucketCors",
            "DeleteBucketCors", "GetBucketAcl", "PutBucketAcl",
            "GetBucketTagging", "PutBucketTagging", "DeleteBucketTagging",
            "GetBucketPolicy", "PutBucketPolicy", "DeleteBucketPolicy",
            "GetBucketNotificationConfiguration",
            "PutBucketNotificationConfiguration",
            "GetBucketLogging", "PutBucketLogging",
            "PutPublicAccessBlock", "GetPublicAccessBlock",
            "DeletePublicAccessBlock",
        ],
    ),
    (
        "Objects in depth",
        [
            "ListObjectVersions", "CreateMultipartUpload", "UploadPart",
            "CompleteMultipartUpload", "AbortMultipartUpload",
            "GetObjectTagging", "PutObjectTagging", "DeleteObjectTagging",
            "PutObjectAnnotation", "GetObjectAnnotation", "ListObjectAnnotations",
            "DeleteObjectAnnotation",
        ],
    ),
    (
        "Object Lock",
        [
            "PutObjectLockConfiguration", "GetObjectLockConfiguration",
            "PutObjectRetention", "GetObjectRetention", "PutObjectLegalHold",
            "GetObjectLegalHold",
        ],
    ),
    (
        "Replication and access points",
        [
            "PutBucketReplication", "GetBucketReplication", "DeleteBucketReplication",
            "CreateAccessPoint", "GetAccessPoint", "ListAccessPoints",
            "DeleteAccessPoint", "PutAccessPointPolicy", "GetAccessPointPolicy",
            "DeleteAccessPointPolicy",
        ],
    ),
    (
        "Multi-Region Access Points and Object Lambda",
        [
            "CreateMultiRegionAccessPoint", "DeleteMultiRegionAccessPoint",
            "PutMultiRegionAccessPointPolicy",
            "DescribeMultiRegionAccessPointOperation", "GetMultiRegionAccessPoint",
            "GetMultiRegionAccessPointPolicy", "ListMultiRegionAccessPoints",
            "GetMultiRegionAccessPointRoutes", "SubmitMultiRegionAccessPointRoutes",
            "CreateAccessPointForObjectLambda", "GetAccessPointForObjectLambda",
            "ListAccessPointsForObjectLambda", "DeleteAccessPointForObjectLambda",
            "GetAccessPointConfigurationForObjectLambda",
            "PutAccessPointConfigurationForObjectLambda",
            "PutAccessPointPolicyForObjectLambda",
            "GetAccessPointPolicyForObjectLambda",
            "DeleteAccessPointPolicyForObjectLambda", "WriteGetObjectResponse",
        ],
    ),
]


def upstream_operations() -> list[str]:
    if not README.is_file():
        raise SystemExit(f"s3_coverage: {README} is missing (ministack-src checkout)")
    for line in README.read_text(encoding="utf-8").splitlines():
        if line.startswith("| **S3** |"):
            cell = line.split("|")[2]
            return [part.strip() for part in cell.split(",") if part.strip()]
    raise SystemExit("s3_coverage: no `| **S3** |` row in the emulator README")


def console_actions() -> dict[str, str]:
    sys.path.insert(0, str(ROOT / "control"))
    import console  # noqa: PLC0415 - read only here

    return {
        operation["id"]: operation["label"]
        for operation in console.CATALOGUE["s3"]["operations"]
    }


def render() -> str:
    operations = upstream_operations()
    actions = console_actions()
    grouped = {name for _, names in GROUPS for name in names}
    ungrouped = [name for name in operations if name not in grouped]

    lines = [
        "# S3 coverage",
        "",
        "Generated by `scripts/s3_coverage.py` from the `| **S3** |` row of the",
        "emulator's README and `control/console.py`. Do not edit by hand — re-run",
        "the script.",
        "",
        f"- Operations upstream advertises: **{len(operations)}**",
        f"- Console actions (`/api/exec`, the create page): **{len(actions)}**",
        f"- Operations with an emuplane test: **{len([o for o in operations if o in COVERED])}**",
        "- Reachable through the gateway, tested by the emulator only: the rest",
        "",
        "The gateway is a passthrough: an operation without an entry in the last",
        "column is not untested — the emulator's own `tests/test_s3.py` covers this",
        "surface, and emuplane simply does not look at it. That is a different",
        "claim from \"nobody tests it\".",
        "",
    ]
    if ungrouped:
        lines += ["", "Ungrouped by this script: " + ", ".join(ungrouped)]

    for title, names in GROUPS:
        listed = [name for name in names if name in operations]
        if not listed:
            continue
        lines += [
            "",
            f"## {title}",
            "",
            "| Operation | Console action | Emuplane test |",
            "| --- | --- | --- |",
        ]
        for name in listed:
            action = ", ".join(
                key for key in actions if key.replace("-", "").lower() in name.lower().replace(" ", "")
            )
            test = COVERED.get(name, "—")
            lines.append(f"| `{name}` | {action or '—'} | {test} |")

    lines += [
        "",
        "## Console actions",
        "",
        "| Action | Label |",
        "| --- | --- |",
    ]
    lines += [f"| `{key}` | {label} |" for key, label in sorted(actions.items())]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    text = render()
    if "--check" in sys.argv[1:]:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != text:
            print("S3.md is out of date: re-run scripts/s3_coverage.py", file=sys.stderr)
            return 1
        print("S3.md is current")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
