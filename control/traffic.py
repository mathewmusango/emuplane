"""The gateway's request record: a bounded ring buffer, shaped so a credential has nowhere to go.

Only names, sizes and the credential's *kind* are kept. A header value, a query value
and a body never enter the buffer, so an `Authorization`, `Cookie` or
`X-Amz-Security-Token` value cannot reach the inspector even though the gateway saw it.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

CAPACITY = 500

# The headers that carry a credential: named in the entry, never valued.
CREDENTIAL_HEADERS = {
    "authorization": "Authorization",
    "cookie": "Cookie",
    "proxy-authorization": "Proxy-Authorization",
    "x-amz-mfa": "X-Amz-Mfa",
    "x-amz-security-token": "X-Amz-Security-Token",
}

# Bucket and object subresources, as (GET, PUT, DELETE); HEAD reads like GET.
S3_BUCKET = {
    "accelerate": ("GetAccelerateConfiguration", "PutAccelerateConfiguration", None),
    "acl": ("GetBucketAcl", "PutBucketAcl", "DeleteBucketAcl"),
    "cors": ("GetBucketCors", "PutBucketCors", "DeleteBucketCors"),
    "encryption": (
        "GetBucketEncryption",
        "PutBucketEncryption",
        "DeleteBucketEncryption",
    ),
    "lifecycle": (
        "GetBucketLifecycleConfiguration",
        "PutBucketLifecycleConfiguration",
        "DeleteBucketLifecycle",
    ),
    "location": ("GetBucketLocation", None, None),
    "logging": ("GetBucketLogging", "PutBucketLogging", None),
    "notification": (
        "GetBucketNotificationConfiguration",
        "PutBucketNotificationConfiguration",
        None,
    ),
    "object-lock": (
        "GetObjectLockConfiguration",
        "PutObjectLockConfiguration",
        None,
    ),
    "ownershipControls": (
        "GetBucketOwnershipControls",
        "PutBucketOwnershipControls",
        "DeleteBucketOwnershipControls",
    ),
    "policy": ("GetBucketPolicy", "PutBucketPolicy", "DeleteBucketPolicy"),
    "policyStatus": ("GetBucketPolicyStatus", None, None),
    "publicAccessBlock": (
        "GetPublicAccessBlock",
        "PutPublicAccessBlock",
        "DeletePublicAccessBlock",
    ),
    "replication": (
        "GetBucketReplication",
        "PutBucketReplication",
        "DeleteBucketReplication",
    ),
    "requestPayment": (
        "GetBucketRequestPayment",
        "PutBucketRequestPayment",
        None,
    ),
    "tagging": ("GetBucketTagging", "PutBucketTagging", "DeleteBucketTagging"),
    "versioning": ("GetBucketVersioning", "PutBucketVersioning", None),
    "website": ("GetBucketWebsite", "PutBucketWebsite", "DeleteBucketWebsite"),
}

S3_OBJECT = {
    "acl": ("GetObjectAcl", "PutObjectAcl", None),
    "attributes": ("GetObjectAttributes", None, None),
    "legal-hold": ("GetObjectLegalHold", "PutObjectLegalHold", None),
    "retention": ("GetObjectRetention", "PutObjectRetention", None),
    "tagging": ("GetObjectTagging", "PutObjectTagging", "DeleteObjectTagging"),
    "torrent": ("GetObjectTorrent", None, None),
}

S3_VERBS = {
    "GET": "GetObject",
    "HEAD": "HeadObject",
    "PUT": "PutObject",
    "POST": "PostObject",
    "DELETE": "DeleteObject",
}


def lower_headers(headers) -> dict[str, str]:
    """One case-insensitive view of a header collection, values included (never stored)."""
    try:
        items = headers.items()
    except AttributeError:
        return {}
    return {str(name).lower(): str(value) for name, value in items}


def authorization_kind(value: str) -> str:
    """What kind of credential it was: the scheme, never the key id or the signature."""
    if value.startswith("AWS4-HMAC-SHA256"):
        return "SigV4 (redacted)"
    scheme = value.split(" ", 1)[0].strip()
    return f"{scheme} (redacted)" if scheme else "Authorization (redacted)"


def credential_summary(headers) -> list[str]:
    """The credential-bearing headers that were present, by name, with no value."""
    found = []
    lowered = lower_headers(headers)
    for lower, display in CREDENTIAL_HEADERS.items():
        value = lowered.get(lower, "")
        if not value:
            continue
        if lower == "authorization":
            found.append(authorization_kind(value))
        else:
            found.append(f"{display} (redacted)")
    return found


def form_action(body: bytes, content_type: str) -> str:
    """The `Action` of a Query-protocol request, or "" for a body that is not one."""
    if not body or len(body) > 65536 or "json" in content_type:
        return ""
    text = body.decode("utf-8", "replace")
    if not text.startswith("Action="):
        return ""
    return (parse_qs(text).get("Action") or [""])[0]


def s3_operation(
    method: str, params: dict[str, list[str]], bucket: str, key: str
) -> str:
    """The S3 operation, from the subresource, in the order the emulator dispatches it."""
    if "uploadId" in params:
        if method == "DELETE":
            return "AbortMultipartUpload"
        if method == "POST":
            return "CompleteMultipartUpload"
        if method == "PUT" and "partNumber" in params:
            return "UploadPart"
        return "ListParts"
    if "uploads" in params:
        return "ListMultipartUploads" if method == "GET" else "CreateMultipartUpload"
    if "versions" in params:
        return "ListObjectVersions"
    if "restore" in params:
        return "RestoreObject"
    if "select" in params:
        return "SelectObjectContent"
    if "delete" in params and method == "POST":
        return "DeleteObjects"
    if not bucket:
        return "ListBuckets" if method == "GET" else method
    for name, (get, put, delete) in (S3_OBJECT if key else S3_BUCKET).items():
        if name not in params:
            continue
        chosen = {"GET": get, "HEAD": get, "PUT": put, "POST": put, "DELETE": delete}
        return chosen.get(method) or method
    if not key:
        if method == "GET":
            wanted = (params.get("list-type") or [""])[0]
            return "ListObjectsV2" if wanted == "2" else "ListObjects"
        if method == "HEAD":
            return "HeadBucket"
        return {"PUT": "CreateBucket", "DELETE": "DeleteBucket", "POST": "PostObject"}.get(
            method, method
        )
    return S3_VERBS.get(method, method)


def operation(
    method: str,
    path: str,
    headers,
    body: bytes,
    service: str,
    bucket: str = "",
    key: str = "",
) -> str:
    """The operation a client meant, read the way the emulator's router reads it."""
    lowered = lower_headers(headers)
    target = lowered.get("x-amz-target", "")
    if target:
        return target.rsplit(".", 1)[-1]
    action = form_action(body, lowered.get("content-type", ""))
    if action:
        return action
    params = parse_qs(urlsplit(path).query, keep_blank_values=True)
    named = (params.get("x-id") or [""])[0]
    if named:
        return named
    if service == "s3":
        return s3_operation(method, params, bucket, key)
    return method


class TrafficLog:
    """What the gateway saw, newest last. The oldest entry leaves when the buffer is full."""

    def __init__(self, capacity: int = CAPACITY) -> None:
        self.capacity = max(1, int(capacity))
        self._entries: deque[dict] = deque(maxlen=self.capacity)
        self._lock = threading.Lock()
        self._next = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def record(
        self,
        *,
        method: str,
        path: str,
        headers,
        body: bytes,
        service: str,
        account: str,
        region: str,
        status: int,
        duration_ms: float,
        request_bytes: int,
        response_bytes: int,
        bucket: str = "",
        key: str = "",
        request_id: str = "",
    ) -> dict:
        split = urlsplit(path)
        lowered = lower_headers(headers)
        entry = {
            "method": method,
            "path": split.path,
            "query": sorted(parse_qs(split.query, keep_blank_values=True)),
            "bucket": bucket,
            "key": key,
            "service": service or "",
            "operation": operation(method, path, headers, body, service, bucket, key),
            "account": account or "",
            "region": region or "",
            "status": int(status or 0),
            "duration_ms": round(duration_ms, 3),
            "request_bytes": int(request_bytes or 0),
            "response_bytes": int(response_bytes or 0),
            "headers": sorted(lowered),
            "credentials": credential_summary(headers),
            "request_id": request_id,
            "signed": "authorization" in lowered,
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        }
        with self._lock:
            self._next += 1
            entry["id"] = self._next
            self._entries.append(entry)
            return dict(entry)

    def page(
        self,
        *,
        since: int | None = None,
        before: int | None = None,
        limit: int = 100,
        service: str = "",
        status: str = "",
        account: str = "",
    ) -> tuple[list[dict], int]:
        """Newest first, except a `since` poll, which is oldest first so a tail can append."""
        limit = max(1, min(int(limit or 100), self.capacity))
        with self._lock:
            entries = list(self._entries)
            latest = self._next

        def keep(entry: dict) -> bool:
            if service and entry["service"] != service:
                return False
            if account and entry["account"] != account:
                return False
            if status:
                wanted = str(status).strip().lower()
                if len(wanted) == 3 and wanted.endswith("xx"):
                    if not 100 <= entry["status"] <= 999:
                        return False
                    if str(entry["status"])[0] != wanted[0]:
                        return False
                elif str(entry["status"]) != wanted:
                    return False
            return True

        if since is not None:
            tail = [entry for entry in entries if entry["id"] > since and keep(entry)]
            return tail[:limit], latest
        if before is not None:
            older = [entry for entry in entries if entry["id"] < before and keep(entry)]
            return older[-limit:][::-1], latest
        return [entry for entry in entries if keep(entry)][-limit:][::-1], latest
