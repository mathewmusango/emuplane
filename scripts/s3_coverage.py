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
    "CreateBucket": "tests/s3/test_create.py, tests/control/test_gateway.py, tests/control/test_parity.py",
    "DeleteBucket": "tests/control/test_gateway.py, tests/control/test_parity.py",
    "HeadBucket": "tests/control/test_gateway.py (301 path), tests/s3/test_objects.py, tests/control/test_api.py",
    "ListBuckets": "tests/control/test_api.py (via /api/browse), tests/control/test_parity.py",
    "PutObject": "tests/control/test_api.py, tests/s3/test_objects.py, tests/control/test_parity.py, tests/control/test_object_upload.py",
    "DeleteObjects": "tests/s3/test_objects.py (Empty)",
    "GetObject": "tests/s3/test_objects.py, tests/control/test_parity.py, tests/control/test_object_upload.py",
    "ListObjects v1/v2": "tests/control/test_api.py (v2), tests/control/test_parity.py, tests/s3/test_objects.py (v1)",
    "DeleteObject": "tests/web/s3.test.jsx (object view), tests/s3/test_catalogue.py, tests/control/test_parity.py",
    "GetBucketVersioning": "tests/s3/test_create.py",
    "PutBucketVersioning": "tests/s3/test_create.py, tests/control/test_api.py, tests/web/s3.test.jsx",
    "GetBucketEncryption": "tests/s3/test_create.py, tests/control/test_api.py",
    "PutBucketEncryption": "tests/s3/test_create.py, tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx",
    "GetBucketTagging": "tests/s3/test_create.py, tests/control/test_api.py",
    "PutBucketTagging": "tests/s3/test_create.py, tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx",
    "PutPublicAccessBlock": "tests/s3/test_create.py",
    "GetPublicAccessBlock": "tests/s3/test_create.py",
    "GetObjectLockConfiguration": "tests/s3/test_create.py",
    "PutObjectLockConfiguration": "tests/s3/test_create.py (at create)",
    "ListObjectVersions": "tests/s3/test_objects.py",
    "GetBucketLifecycleConfiguration": "tests/s3/test_objects.py (documents)",
    "GetBucketCors": "tests/s3/test_objects.py (documents)",
    "GetBucketAcl": "tests/s3/test_objects.py (documents), tests/control/test_api.py",
    "GetBucketPolicy": "tests/s3/test_objects.py (documents), tests/control/test_api.py",
    "GetBucketNotificationConfiguration": "tests/s3/test_objects.py (documents)",
    "GetBucketLogging": "tests/s3/test_objects.py (documents)",
    "GetBucketReplication": "tests/s3/test_objects.py (documents)",
    "PutBucketLifecycleConfiguration": "tests/s3/test_objects.py (lifecycle round trip), tests/control/test_api.py (cors), tests/web/s3.test.jsx",
    "DeleteBucketLifecycle": "tests/s3/test_objects.py (lifecycle round trip)",
    "PutBucketCors": "tests/s3/test_objects.py (cors round trip), tests/control/test_api.py, tests/web/s3.test.jsx",
    "DeleteBucketCors": "tests/s3/test_objects.py (cors round trip), tests/control/test_api.py",
    "DeleteBucketEncryption": "tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx",
    "PutBucketAcl": "tests/s3/test_objects.py (ACL enabled/disabled), tests/web/s3.test.jsx",
    "PutBucketPolicy": "tests/s3/test_objects.py (policy round trip), tests/control/test_api.py, tests/web/s3.test.jsx",
    "DeleteBucketPolicy": "tests/s3/test_objects.py (policy round trip), tests/control/test_api.py",
    "DeleteBucketTagging": "tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx",
    "HeadObject": "tests/control/test_gateway.py (301 path), tests/s3/test_objects.py (HEAD first), tests/control/test_api.py",
    "CopyObject": "tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx",
    "CreateAccessPoint": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "GetAccessPoint": "tests/s3/test_access_points.py (row details)",
    "ListAccessPoints": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "DeleteAccessPoint": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "PutAccessPointPolicy": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "GetAccessPointPolicy": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "DeleteAccessPointPolicy": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "ListMultiRegionAccessPoints": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "ListAccessPointsForObjectLambda": "tests/s3/test_access_points.py, tests/control/test_access_point_api.py",
    "PutBucketLogging": "tests/s3/test_operations.py (logging written and read)",
    "PutBucketNotificationConfiguration": "tests/s3/test_operations.py (EventBridge rule)",
    "PutBucketReplication": "tests/s3/test_operations.py (replication config)",
    "DeleteBucketReplication": "tests/s3/test_operations.py (replication removed)",
    "DeletePublicAccessBlock": "tests/s3/test_operations.py (access block removed)",
    "CreateMultipartUpload": "tests/s3/test_operations.py (multipart)",
    "UploadPart": "tests/s3/test_operations.py (multipart)",
    "CompleteMultipartUpload": "tests/s3/test_operations.py (multipart)",
    "AbortMultipartUpload": "tests/s3/test_operations.py (multipart aborted)",
    "GetObjectTagging": "tests/s3/test_operations.py (object tags)",
    "PutObjectTagging": "tests/s3/test_operations.py (object tags)",
    "DeleteObjectTagging": "tests/s3/test_operations.py (object tags)",
    "PutObjectAnnotation": "tests/s3/test_operations.py (annotations)",
    "GetObjectAnnotation": "tests/s3/test_operations.py (annotations)",
    "ListObjectAnnotations": "tests/s3/test_operations.py (annotations)",
    "DeleteObjectAnnotation": "tests/s3/test_operations.py (annotations)",
    "PutObjectRetention": "tests/s3/test_operations.py (retention)",
    "GetObjectRetention": "tests/s3/test_operations.py (retention)",
    "PutObjectLegalHold": "tests/s3/test_operations.py (legal hold)",
    "GetObjectLegalHold": "tests/s3/test_operations.py (legal hold)",
    "CreateMultiRegionAccessPoint": "tests/s3/test_operations.py (MRAP create + describe)",
    "DescribeMultiRegionAccessPointOperation": "tests/s3/test_operations.py (MRAP create + describe)",
    "GetMultiRegionAccessPoint": "tests/s3/test_operations.py (MRAP read + policy)",
    "PutMultiRegionAccessPointPolicy": "tests/s3/test_operations.py (MRAP read + policy)",
    "GetMultiRegionAccessPointPolicy": "tests/s3/test_operations.py (MRAP read + policy)",
    "GetMultiRegionAccessPointRoutes": "tests/s3/test_operations.py (MRAP routes)",
    "SubmitMultiRegionAccessPointRoutes": "tests/s3/test_operations.py (MRAP routes)",
    "DeleteMultiRegionAccessPoint": "tests/s3/test_operations.py (MRAP deleted)",
    "CreateAccessPointForObjectLambda": "tests/s3/test_operations.py (Object Lambda create + read)",
    "GetAccessPointForObjectLambda": "tests/s3/test_operations.py (Object Lambda create + read)",
    "GetAccessPointConfigurationForObjectLambda": "tests/s3/test_operations.py (Object Lambda configuration)",
    "PutAccessPointConfigurationForObjectLambda": "tests/s3/test_operations.py (Object Lambda configuration)",
    "PutAccessPointPolicyForObjectLambda": "tests/s3/test_operations.py (Object Lambda policy)",
    "GetAccessPointPolicyForObjectLambda": "tests/s3/test_operations.py (Object Lambda policy)",
    "DeleteAccessPointPolicyForObjectLambda": "tests/s3/test_operations.py (Object Lambda policy)",
    "DeleteAccessPointForObjectLambda": "tests/s3/test_operations.py (Object Lambda deleted)",
    "WriteGetObjectResponse": "tests/s3/test_operations.py (unknown route refused)",
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
    "HeadBucket": "Bucket page (region check)",
    "GetObject": "Bucket page (Objects)",
    "CopyObject": "Bucket page (Objects)",
    "HeadObject": "Bucket page (Objects)",
    "ListObjectVersions": "Bucket page (Configuration documents)",
    "GetBucketVersioning": "Bucket page (Properties)",
    "PutBucketVersioning": "Bucket page (Properties, Edit)",
    "GetBucketEncryption": "Bucket page (Properties)",
    "GetBucketTagging": "Bucket page (Properties)",
    "GetPublicAccessBlock": "Bucket page (Permissions)",
    "PutPublicAccessBlock": "Bucket page (Permissions, Save)",
    "GetBucketLifecycleConfiguration": "Bucket page (Configuration documents)",
    "PutBucketLifecycleConfiguration": "Bucket page (Configuration documents, Edit)",
    "DeleteBucketLifecycle": "Bucket page (Configuration documents, Remove)",
    "PutBucketCors": "Bucket page (Configuration documents, Edit)",
    "DeleteBucketCors": "Bucket page (Configuration documents, Remove)",
    "PutBucketAcl": "Bucket page (Configuration documents, Edit)",
    "PutBucketPolicy": "Bucket page (Configuration documents, Edit)",
    "DeleteBucketPolicy": "Bucket page (Configuration documents, Remove)",
    "PutBucketTagging": "Bucket page (Properties, Edit)",
    "DeleteBucketTagging": "Bucket page (Properties, Remove tags)",
    "GetBucketCors": "Bucket page (Configuration documents)",
    "GetBucketAcl": "Bucket page (Configuration documents)",
    "GetBucketPolicy": "Bucket page (Configuration documents)",
    "GetBucketNotificationConfiguration": "Bucket page (Configuration documents)",
    "GetBucketLogging": "Bucket page (Configuration documents)",
    "GetBucketReplication": "Bucket page (Configuration documents)",
    "PutBucketEncryption": "Bucket page (Properties, Edit)",
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

# Operation -> where the console shows or performs it. A row with an entry is
# reachable from the GUI; a row without one is gateway-only, and the point of the
# column is that the gap is visible per operation rather than inferred.
GUI = {
    "CreateBucket": "Buckets page › Create bucket",
    "DeleteBucket": "Buckets page › Delete",
    "ListBuckets": "Buckets page › table",
    "HeadBucket": "Bucket page (HeadBucket decides the region)",
    "PutObject": "Bucket page › Objects › Upload",
    "GetObject": "Bucket page › Objects › open",
    "CopyObject": "Bucket page › Objects › open › Copy",
    "HeadObject": "Bucket page › Objects › open (size, ETag, last modified)",
    "DeleteObject": "Bucket page › Objects › open › Delete",
    "DeleteObjects": "Buckets page › Empty",
    "ListObjects v1/v2": "Bucket page › Objects",
    "ListObjectVersions": "Bucket page › Configuration documents",
    "GetObjectTagging": "Bucket page › Objects › open › Tags",
    "ListObjectAnnotations": "Bucket page › Objects › open › Annotations",
    "GetObjectAnnotation": "Bucket page › Objects › open › Annotations › name",
    "GetObjectRetention": "Bucket page › Objects › open › Object Lock",
    "GetObjectLegalHold": "Bucket page › Objects › open › Object Lock",
    "GetBucketVersioning": "Bucket page › Properties",
    "PutBucketVersioning": "Bucket page › Properties › Edit",
    "GetBucketEncryption": "Bucket page › Properties",
    "PutBucketEncryption": "Bucket page › Properties › Edit",
    "DeleteBucketEncryption": "Bucket page › Properties › Remove default encryption",
    "GetBucketTagging": "Bucket page › Properties",
    "PutBucketTagging": "Create bucket page › Tags",
    "GetPublicAccessBlock": "Bucket page › Permissions",
    "PutPublicAccessBlock": "Bucket page › Permissions › Save",
    "GetObjectLockConfiguration": "Create bucket page › Copy settings",
    "PutObjectLockConfiguration": "Create bucket page › Object Lock",
    "GetBucketLifecycleConfiguration": "Bucket page › Configuration documents",
    "PutBucketLifecycleConfiguration": "Bucket page › Configuration documents › Edit",
    "DeleteBucketLifecycle": "Bucket page › Configuration documents › Remove",
    "PutBucketCors": "Bucket page › Configuration documents › Edit",
    "DeleteBucketCors": "Bucket page › Configuration documents › Remove",
    "PutBucketAcl": "Bucket page › Configuration documents › Edit (ACL-enabled buckets)",
    "PutBucketPolicy": "Bucket page › Configuration documents › Edit",
    "DeleteBucketPolicy": "Bucket page › Configuration documents › Remove",
    "PutBucketTagging": "Bucket page › Properties › Tags › Edit",
    "DeleteBucketTagging": "Bucket page › Properties › Tags › Remove tags",
    "GetBucketCors": "Bucket page › Configuration documents",
    "GetBucketAcl": "Bucket page › Configuration documents",
    "GetBucketPolicy": "Bucket page › Configuration documents",
    "GetBucketNotificationConfiguration": "Bucket page › Configuration documents",
    "GetBucketLogging": "Bucket page › Configuration documents",
    "GetBucketReplication": "Bucket page › Configuration documents",
    "CreateAccessPoint": "Access Points page › Create access point",
    "GetAccessPoint": "Access Points page › row details",
    "ListAccessPoints": "Access Points page › General purpose buckets",
    "DeleteAccessPoint": "Access Points page › Delete",
    "PutAccessPointPolicy": "Access Points page › Edit policy",
    "GetAccessPointPolicy": "Access Points page › Edit policy",
    "DeleteAccessPointPolicy": "Access Points page › Remove policy",
    "ListMultiRegionAccessPoints": "Access Points page › Multi-Region",
    "ListAccessPointsForObjectLambda": "Access Points page › Object Lambda",
}

# What counts as a read: the operations a page has to be able to show.
READ_PREFIXES = ("Get", "List", "Head", "Describe")


def is_read(operation: str) -> bool:
    return operation.startswith(READ_PREFIXES)


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
        f"- Operations shown in the console: **{len([o for o in operations if o in GUI])}**",
        f"- GET operations (Get/List/Head/Describe) shown in the console: "
        f"**{len([o for o in operations if is_read(o) and o in GUI])}** of "
        f"**{len([o for o in operations if is_read(o)])}**",
        f"- Operations with no emuplane test: "
        f"**{len([o for o in operations if o not in COVERED])}**",
        "",
        "The gateway is a passthrough, but nothing here is left to it: every",
        "operation names the emuplane test that exercises it, and",
        "`scripts/qa_check.py --tests` runs them on every run. The operations the",
        "console does not drive live in `tests/s3/test_operations.py`; the rest are",
        "tested beside the page that shows them.",
        "",
        "The *Shown in the console* column is the other half of the claim: an",
        "operation with an em dash there is reachable over the wire but nowhere in",
        "the console, which is what closing S3 has to remove.",
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
            "| Operation | Console action | Shown in the console | Emuplane test |",
            "| --- | --- | --- | --- |",
        ]
        for name in listed:
            owned = [
                key for key in actions if name in ACTION_OPERATIONS.get(key, [])
            ]
            if name in PAGES:
                owned.append(PAGES[name])
            action = ", ".join(owned)
            test = COVERED.get(name, "—")
            lines.append(
                f"| `{name}` | {action or '—'} | {GUI.get(name, '—')} | {test} |"
            )

    lines += [
        "",
        "## GET operations",
        "",
        "Every read operation, and where the console shows it. A box left unticked",
        "is an operation the emulator answers and the console cannot display.",
        "",
    ]
    for name in operations:
        if not is_read(name):
            continue
        shown = GUI.get(name)
        lines.append(
            f"- [{'x' if shown else ' '}] `{name}`"
            + (f" — {shown}" if shown else " — not shown")
        )

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
