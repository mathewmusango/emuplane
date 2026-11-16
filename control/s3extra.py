"""The S3 children whose listings live in other APIs.

`ListBuckets` answers for general purpose buckets only. S3 Tables and S3 Files
are separate APIs on the same emulator, and the console's S3 nav shows them, so
it asks those APIs directly instead of pretending the bucket list is all there is.

The signed client is passed in as `call(service, method, path)`, so nothing here
holds a credential — the same property `buckets.py` keeps.
"""

from __future__ import annotations

import json

# Section -> (service, path, key the list is named after).
SOURCES = {
    "table-buckets": ("s3tables", "/buckets", "tableBuckets"),
    "file-systems": ("s3files", "/file-systems", "fileSystems"),
}


def list_items(section: str, call) -> dict:
    """One listing, as `{"ok": True, "items": [...]}` or `{"ok": False, ...}`.

    A body that is not the JSON this API documents is a failure, not an empty
    list: an empty table would read as "you have none", which may well be false.
    """
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
