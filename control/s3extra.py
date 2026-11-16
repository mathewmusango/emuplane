"""The S3 children whose listings live in other APIs: S3 Tables and S3 Files are asked directly."""

from __future__ import annotations

import json

# Section -> (service, path, key the list is named after).
SOURCES = {
    "table-buckets": ("s3tables", "/buckets", "tableBuckets"),
    "file-systems": ("s3files", "/file-systems", "fileSystems"),
}


def list_items(section: str, call) -> dict:
    """One listing, as `{"ok": True, "items": [...]}`; an unreadable body fails rather than listing nothing."""
    service, path, key = SOURCES[section]
    status, body = call(service, "GET", path)
    if not 200 <= status < 300:
        return {
            "ok": False,
            "status": status,
            "error": (body or "").strip()[:200] or f"HTTP {status}",
        }
    try:
        payload = json.loads(body or "{}")
    except ValueError:
        return {"ok": False, "status": status, "error": "the answer was not JSON"}
    items = payload.get(key)
    if not isinstance(items, list):
        return {
            "ok": False,
            "status": status,
            "error": f"the answer carried no {key}",
        }
    return {"ok": True, "status": status, "items": items}
