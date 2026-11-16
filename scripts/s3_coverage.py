#!/usr/bin/env python3
"""Write `S3.md`: what S3 offers, and who tests each part of it.

Three sources, no hand-maintained list:

  * the operations upstream advertises — the `| **S3** |` row of the emulator's
    own README (`ministack-src`, a sibling checkout);
  * the console actions — `control/console.py`, which is what the API explorer
    and the create page are built from;
  * the emuplane tests — the map below, kept honest by hand because a test name
    cannot be derived from an operation name.

A fourth column of knowledge is the pages: an operation a console page performs
(`PAGES` below) is not a catalogue action, and without saying so the table would
read as though nobody in emuplane does it. The guess that an action id is a
substring of an operation was wrong (`delete-bucket` inside
`DeleteBucketEncryption`), so both maps are explicit.

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
    "PutObject": "tests/control/test_api.py, tests/s3/test_objects.py",
    "DeleteObjects": "tests/s3/test_objects.py (Empty)",
    "GetObject": "tests/s3/test_objects.py",
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
    "ListObjectVersions": "tests/s3/test_objects.py",
    "GetBucketLifecycleConfiguration": "tests/s3/test_objects.py (documents)",
    "GetBucketCors": "tests/s3/test_objects.py (documents)",
    "GetBucketAcl": "tests/s3/test_objects.py (documents)",
    "GetBucketPolicy": "tests/s3/test_objects.py (documents)",
    "GetBucketNotificationConfiguration": "tests/s3/test_objects.py (documents)",
    "GetBucketLogging": "tests/s3/test_objects.py (documents)",
    "GetBucketReplication": "tests/s3/test_objects.py (documents)",
    "HeadObject": "tests/control/test_gateway.py (301 path)",
    "CreateAccessPoint": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "GetAccessPoint": "tests/s3/test_access_points.py (row details)",
    "ListAccessPoints": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "DeleteAccessPoint": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "PutAccessPointPolicy": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "GetAccessPointPolicy": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "DeleteAccessPointPolicy": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "ListMultiRegionAccessPoints": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "ListAccessPointsForObjectLambda": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
}

# Catalogue action -> the operation it runs. An action's id cannot be matched to
# an operation string by substring: `delete-bucket` is inside
# `DeleteBucketEncryption`, which it does not do.
ACTION_OPERATIONS = {
    "create-bucket": ["CreateBucket"],
    "delete-bucket": ["DeleteBucket"],
    "list-objects": ["ListObjects v1/v2"],
    "put-object": ["PutObject"],
    "delete-object": ["DeleteObject", "DeleteObjects"],
}

# Operations a console page performs — a page, not an `/api/exec` action, so the
# catalogue does not list them and the column would read as gateway-only.
PAGES = {
    "ListBuckets": "Buckets page",
    "GetObject": "Bucket page (Objects)",
    "ListObjectVersions": "Bucket page (Configuration documents)",
    "GetBucketVersioning": "Bucket page (Properties)",
    "PutBucketVersioning": "Bucket page (Properties, Edit)",
    "GetBucketEncryption": "Bucket page (Properties)",
    "GetBucketTagging": "Bucket page (Properties)",
    "GetPublicAccessBlock": "Bucket page (Permissions)",
    "PutPublicAccessBlock": "Bucket page (Permissions, Save)",
    "GetBucketLifecycleConfiguration": "Bucket page (Configuration documents)",
    "GetBucketCors": "Bucket page (Configuration documents)",
    "GetBucketAcl": "Bucket page (Configuration documents)",
    "GetBucketPolicy": "Bucket page (Configuration documents)",
    "GetBucketNotificationConfiguration": "Bucket page (Configuration documents)",
    "GetBucketLogging": "Bucket page (Configuration documents)",
    "GetBucketReplication": "Bucket page (Configuration documents)",
    "PutBucketEncryption": "Create page (default encryption)",
    "PutBucketTagging": "Create page (tags)",
    "PutObjectLockConfiguration": "Create page (Object Lock)",
    "GetObjectLockConfiguration": "Create page (Copy settings)",
    "CreateAccessPoint": "Access Points page",
    "GetAccessPoint": "Access Points page",
    "ListAccessPoints": "Access Points page",
    "DeleteAccessPoint": "Access Points page",
    "PutAccessPointPolicy": "Access Points page (Edit policy)",
    "GetAccessPointPolicy": "Access Points page (Edit policy)",
    "DeleteAccessPointPolicy": "Access Points page (Remove policy)",
    "ListMultiRegionAccessPoints": "Access Points page (Multi-Region tab)",
    "ListAccessPointsForObjectLambda": "Access Points page (Object Lambda tab)",
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
            owned = [
                key for key in actions if name in ACTION_OPERATIONS.get(key, [])
            ]
            if name in PAGES:
                owned.append(PAGES[name])
            action = ", ".join(owned)
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
