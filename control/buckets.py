"""Creating a bucket the way the console's create page does it: `CreateBucket`, then each subresource the form asked for."""

from __future__ import annotations

import html
import json
import re
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from urllib.parse import quote

S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"

# The console's three encryption choices, as the SSEAlgorithm each one sends.
ENCRYPTION = ("AES256", "aws:kms", "aws:kms:dsse")

# Object Ownership: "ACLs disabled" is AWS's default and the console's default.
OWNERSHIP = ("BucketOwnerEnforced", "BucketOwnerPreferred")

PUBLIC_ACCESS = (
    "BlockPublicAcls",
    "IgnorePublicAcls",
    "BlockPublicPolicy",
    "RestrictPublicBuckets",
)

MAX_TAGS = 50

# What the console sends for text typed into the form, and what it will show back as text.
TEXT_TYPE = "text/plain; charset=utf-8"
TEXTUAL = (
    "text/",
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/javascript",
    "application/x-ndjson",
    "application/x-www-form-urlencoded",
)
# A type that says nothing either way, so the bytes decide.
UNKNOWN_TYPES = ("", "application/octet-stream", "binary/octet-stream")


def _textual(kind: str) -> bool:
    return kind.lower().startswith(TEXTUAL)

# A listing is capped, so emptying re-lists after each pass; this bounds the loop.
EMPTY_PASSES = 100

# AWS's global namespace, and the account-scoped one whose names carry the account, the region and `-an`.
NAMESPACE_GLOBAL = "global"
NAMESPACE_REGIONAL = "regional"

# S3's own naming rules, mirrored so the page can answer before the round trip.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
ACCOUNT_RE = re.compile(r"^\d{12}$")

NAME_HELP = (
    "Bucket names must be 3 to 63 characters: lowercase letters, digits, dots "
    "and hyphens, beginning and ending with a letter or number."
)

_MESSAGE_RE = re.compile(r"<Message>(.*?)</Message>", re.S)
_CODE_RE = re.compile(r"<Code>(.*?)</Code>", re.S)


def location_constraint(region: str) -> str:
    """The CreateBucket document: only the global us-east-1 endpoint accepts a request without one."""
    if region == "us-east-1":
        return ""
    return (
        f'<CreateBucketConfiguration xmlns="{S3_NS}">'
        f"<LocationConstraint>{html.escape(region)}</LocationConstraint>"
        "</CreateBucketConfiguration>"
    )


def valid_name(name: str) -> bool:
    return bool(
        NAME_RE.match(name) and ".." not in name and not IP_RE.match(name)
    )


def regional_suffix(account: str, region: str) -> str:
    """The Account Regional namespace suffix: `<account>-<region>-an`."""
    return f"{account}-{region}-an"


def resolve_name(payload: dict, region: str) -> tuple[str, str]:
    """The name this request creates, and why it cannot be one; a name already ending in the suffix is not suffixed twice."""
    base = str(payload.get("bucket") or "").strip()
    if str(payload.get("namespace") or NAMESPACE_GLOBAL) != NAMESPACE_REGIONAL:
        return (base, "") if valid_name(base) else ("", NAME_HELP)
    account = str(payload.get("account") or "").strip()
    if not ACCOUNT_RE.match(account):
        # The suffix *is* the account and region; without one it would compose a name that looks regional and is not.
        return "", "The Account Regional namespace needs the 12-digit account id."
    suffix = "." + regional_suffix(account, region)
    if base.endswith(suffix):
        base = base[: -len(suffix)]
    if not valid_name(base):
        return "", NAME_HELP
    name = base + suffix
    if len(name) > 63:
        return "", (
            "A name in the Account Regional namespace takes the suffix "
            f"{suffix}, so at most {63 - len(suffix)} characters are left for "
            "the name itself."
        )
    return name, ""


def _versioning() -> str:
    return (
        f'<VersioningConfiguration xmlns="{S3_NS}">'
        "<Status>Enabled</Status></VersioningConfiguration>"
    )


def _public_access(flags: dict) -> str:
    body = "".join(
        f"<{name}>{'true' if flags[name] else 'false'}</{name}>"
        for name in PUBLIC_ACCESS
    )
    return f'<PublicAccessBlockConfiguration xmlns="{S3_NS}">{body}</PublicAccessBlockConfiguration>'


def _tagging(tags: list[tuple[str, str]]) -> str:
    body = "".join(
        f"<Tag><Key>{html.escape(key)}</Key><Value>{html.escape(value)}</Value></Tag>"
        for key, value in tags
    )
    return f'<Tagging xmlns="{S3_NS}"><TagSet>{body}</TagSet></Tagging>'


def _encryption(algorithm: str, bucket_key: bool) -> str:
    # Bucket Keys are a KMS feature: sending it with SSE-S3 describes nothing real.
    key = (
        "<BucketKeyEnabled>true</BucketKeyEnabled>"
        if bucket_key and algorithm.startswith("aws:kms")
        else ""
    )
    return (
        f'<ServerSideEncryptionConfiguration xmlns="{S3_NS}">'
        "<Rule><ApplyServerSideEncryptionByDefault>"
        f"<SSEAlgorithm>{algorithm}</SSEAlgorithm>"
        "</ApplyServerSideEncryptionByDefault>"
        f"{key}</Rule></ServerSideEncryptionConfiguration>"
    )


def _detail(text: str, status: int) -> str:
    """S3 answers errors as XML; the sentence inside is the useful part."""
    message = _MESSAGE_RE.search(text or "")
    if message:
        code = _CODE_RE.search(text or "")
        sentence = html.unescape(message.group(1)).strip()
        return f"{code.group(1).strip()}: {sentence}" if code else sentence
    return (text or "").strip()[:200] or f"HTTP {status}"


def _options(payload: dict, region: str) -> dict:
    """The form's values, checked once, in the shape the calls below need."""
    bucket, problem = resolve_name(payload, region)
    if problem:
        raise ValueError(problem)
    ownership = str(payload.get("ownership") or OWNERSHIP[0])
    if ownership not in OWNERSHIP:
        raise ValueError(f"unknown object ownership: {ownership}")
    encryption = str(payload.get("encryption") or ENCRYPTION[0])
    if encryption not in ENCRYPTION:
        raise ValueError(f"unknown encryption: {encryption}")
    tags: list[tuple[str, str]] = []
    for tag in payload.get("tags") or []:
        key = str((tag or {}).get("Key") or "").strip()
        if not key:
            raise ValueError("every tag needs a key")
        tags.append((key, str((tag or {}).get("Value") or "")))
    if len(tags) > MAX_TAGS:
        raise ValueError(f"a bucket takes at most {MAX_TAGS} tags")
    public = payload.get("block_public_access")
    return {
        "bucket": bucket,
        "ownership": ownership,
        "encryption": encryption,
        "bucket_key": bool(payload.get("bucket_key")),
        "versioning": bool(payload.get("versioning")),
        "object_lock": bool(payload.get("object_lock")),
        "mfa_delete": str(payload.get("mfa_delete") or "") == "Enabled",
        "tags": tags,
        # The console sends the block only when expanded; absent means "leave the emulator's default alone".
        "public": (
            None
            if public is None
            else {name: bool(public.get(name, True)) for name in PUBLIC_ACCESS}
        ),
    }


def _local(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _root(xml: str):
    try:
        return ElementTree.fromstring(xml, forbid_dtd=True)
    except (ElementTree.ParseError, DefusedXmlException):
        return None


def _field(xml: str, name: str) -> str | None:
    """The text of the first `name` element anywhere in a document."""
    root = _root(xml)
    if root is None:
        return None
    for element in root.iter():
        if _local(element) == name:
            return element.text
    return None


def _flags(xml: str) -> dict:
    root = _root(xml)
    return {} if root is None else {_local(child): child.text == "true" for child in list(root)}


def _tags(xml: str) -> list[dict]:
    root = _root(xml)
    if root is None:
        return []
    found = []
    for element in root.iter():
        if _local(element) != "Tag":
            continue
        pair = {_local(child): child.text for child in list(element)}
        found.append({"Key": pair.get("Key") or "", "Value": pair.get("Value") or ""})
    return found


def _created(bucket: str, call) -> str:
    """ListBuckets is the only place S3 answers when a bucket was made."""
    status, body = call("GET", "/?x-id=ListBuckets")
    if not 200 <= status < 300:
        return ""
    for name, stamp in re.findall(
        r"<Bucket>.*?<Name>([^<]+)</Name>.*?<CreationDate>([^<]*)</CreationDate>",
        body,
        re.S,
    ):
        if name == bucket:
            return stamp
    return ""


def read_settings(bucket: str, call) -> dict:
    """The create form's settings, read back from `bucket`; a missing subresource keeps the default."""
    path = "/" + quote(bucket, safe="")
    settings = {
        "ownership": OWNERSHIP[0],
        "block_public_access": {name: False for name in PUBLIC_ACCESS},
        "public_access_block_configured": False,
        "versioning": False,
        "versioning_status": "Disabled",
        "mfa_delete": "",
        "created": "",
        "tags": [],
        "encryption": ENCRYPTION[0],
        "bucket_key": False,
        "object_lock": False,
    }

    def get(suffix: str) -> str:
        status, body = call("GET", path + suffix)
        return body if 200 <= status < 300 else ""

    ownership = _field(get("?ownershipControls"), "ObjectOwnership")
    if ownership in OWNERSHIP:
        settings["ownership"] = ownership

    flags = _flags(get("?publicAccessBlock"))
    if flags:
        settings["public_access_block_configured"] = True
        settings["block_public_access"] = {
            name: bool(flags.get(name)) for name in PUBLIC_ACCESS
        }

    versioning = get("?versioning")
    status = _field(versioning, "Status")
    settings["versioning"] = status == "Enabled"
    # S3 answers three ways: no Status is Disabled, and Enabled never goes back to Disabled — only Suspended.
    settings["versioning_status"] = (
        status if status in ("Enabled", "Suspended") else "Disabled"
    )
    # An endpoint that does not implement MFA delete omits the element, which is not the same as Disabled.
    settings["mfa_delete"] = _field(versioning, "MfaDelete") or ""
    settings["created"] = _created(bucket, call)
    settings["tags"] = _tags(get("?tagging"))

    encryption = _field(get("?encryption"), "SSEAlgorithm")
    if encryption in ENCRYPTION:
        settings["encryption"] = encryption
    settings["bucket_key"] = _field(get("?encryption"), "BucketKeyEnabled") == "true"
    settings["object_lock"] = _field(get("?object-lock"), "ObjectLockEnabled") == "Enabled"

    return {"ok": True, "bucket": bucket, "settings": settings}


def create(region: str, payload: dict, s3) -> dict:
    """Create the bucket, then apply the settings; a follow-up failure still reports `created: True`."""
    try:
        options = _options(payload, region)
    except ValueError as exc:
        return {"ok": False, "status": 400, "error": str(exc)}

    bucket = options["bucket"]
    path = "/" + quote(bucket, safe="")
    headers = {"x-amz-object-ownership": options["ownership"]}
    if options["object_lock"]:
        # Object Lock is creation-time only, and it turns versioning on with it.
        headers["x-amz-bucket-object-lock-enabled"] = "true"

    status, text = s3("PUT", path, location_constraint(region), headers)
    if not 200 <= status < 300:
        return {
            "ok": False,
            "status": status or 502,
            "bucket": bucket,
            "error": _detail(text, status),
        }

    steps: list[tuple[str, str, str]] = []
    if options["public"] is not None:
        steps.append(
            ("Block Public Access", "?publicAccessBlock", _public_access(options["public"]))
        )
    if options["versioning"] or options["object_lock"] or options["mfa_delete"]:
        # MFA delete only exists on a versioned bucket, so asking for it turns versioning on.
        steps.append(("Bucket versioning", "?versioning", _versioning()))
    if options["tags"]:
        steps.append(("Tags", "?tagging", _tagging(options["tags"])))
    steps.append(
        (
            "Default encryption",
            "?encryption",
            _encryption(options["encryption"], options["bucket_key"]),
        )
    )

    for label, suffix, body in steps:
        status, text = s3("PUT", path + suffix, body, {})
        if not 200 <= status < 300:
            return {
                "ok": False,
                "status": status or 502,
                "bucket": bucket,
                "created": True,
                "error": f"{label} failed: {_detail(text, status)}",
            }

    return {"ok": True, "status": 200, "bucket": bucket, "created": True}


def _bucket_path(bucket: str) -> str:
    return "/" + quote(bucket, safe="")


def put_object(bucket: str, key: str, body, call, content_type: str = "") -> dict:
    """PutObject: the key is percent-encoded, and `content_type` is what S3 stores and serves back."""
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    elif isinstance(body, str):
        headers["Content-Type"] = TEXT_TYPE
    status, text = call(
        "PUT", _bucket_path(bucket) + "/" + quote(key, safe="/"), body, headers
    )
    if 200 <= status < 300:
        return {
            "ok": True,
            "status": status,
            "key": key,
            "size": len(body if isinstance(body, bytes) else body.encode()),
        }
    return {"ok": False, "status": status or 502, "error": _detail(text, status)}


def copy_object(
    source_bucket: str,
    key: str,
    destination_bucket: str,
    destination_key: str,
    call,
) -> dict:
    """CopyObject: a PUT to the destination, so `call` must be signed for the destination's region."""
    source = "/" + quote(source_bucket, safe="") + "/" + quote(key, safe="/")
    status, text = call(
        "PUT",
        _bucket_path(destination_bucket) + "/" + quote(destination_key, safe="/"),
        "",
        {"x-amz-copy-source": source},
    )
    if 200 <= status < 300:
        return {
            "ok": True,
            "status": status,
            "bucket": source_bucket,
            "key": key,
            "destination": destination_bucket,
            "destination_key": destination_key,
            "etag": _field(text, "ETag"),
        }
    return {"ok": False, "status": status or 502, "error": _detail(text, status)}


def update_settings(bucket: str, payload: dict, call) -> dict:
    """The properties a bucket page can edit, each its own subresource call."""
    path = _bucket_path(bucket)
    # `(label, method, suffix, body)`: most steps are a PUT, but removing encryption is a DELETE.
    steps: list[tuple[str, str, str, str]] = []
    if (
        "versioning_status" in payload
        or "versioning" in payload
        or payload.get("mfa_delete") is not None
    ):
        mfa = payload.get("mfa_delete")
        if mfa not in (None, "", "Enabled", "Disabled"):
            return {"ok": False, "status": 400, "error": f"unknown MFA delete: {mfa}"}
        if "versioning_status" in payload:
            state = payload["versioning_status"]
        elif "versioning" in payload:
            state = "Enabled" if payload.get("versioning") else "Suspended"
        else:
            # Only MFA delete changed, so the versioning state S3 holds is the one to send back with it.
            held = _field(call("GET", path + "?versioning")[1], "Status")
            state = held if held in ("Enabled", "Suspended") else ""
        if state not in ("", "Enabled", "Suspended"):
            return {"ok": False, "status": 400, "error": f"unknown state: {state}"}
        # MFA delete only exists on a versioned bucket, so enabling it turns versioning on in the same call.
        if mfa == "Enabled":
            state = "Enabled"
        document = f"<Status>{state}</Status>" if state else ""
        if mfa in ("Enabled", "Disabled"):
            document += f"<MfaDelete>{mfa}</MfaDelete>"
        if document:
            steps.append(
                (
                    "Bucket versioning",
                    "PUT",
                    "?versioning",
                    f'<VersioningConfiguration xmlns="{S3_NS}">{document}'
                    "</VersioningConfiguration>",
                )
            )
    if payload.get("ownership") is not None:
        ownership = str(payload["ownership"])
        if ownership not in OWNERSHIP:
            return {"ok": False, "status": 400, "error": f"unknown ownership: {ownership}"}
        steps.append(
            (
                "Object Ownership",
                "PUT",
                "?ownershipControls",
                f'<OwnershipControls xmlns="{S3_NS}"><Rule>'
                f"<ObjectOwnership>{ownership}</ObjectOwnership>"
                "</Rule></OwnershipControls>",
            )
        )
    if payload.get("remove_public_access_block"):
        # DeletePublicAccessBlock: the bucket keeps no public access block configuration at all.
        steps.append(("Block Public Access", "DELETE", "?publicAccessBlock", ""))
    elif payload.get("block_public_access") is not None:
        flags = payload["block_public_access"] or {}
        steps.append(
            (
                "Block Public Access",
                "PUT",
                "?publicAccessBlock",
                _public_access({name: bool(flags.get(name)) for name in PUBLIC_ACCESS}),
            )
        )
    if payload.get("remove_encryption"):
        # DeleteBucketEncryption: the bucket falls back to S3's own default (SSE-S3), not unencrypted.
        steps.append(("Default encryption", "DELETE", "?encryption", ""))
    elif payload.get("encryption") is not None:
        algorithm = str(payload["encryption"])
        if algorithm not in ENCRYPTION:
            return {"ok": False, "status": 400, "error": f"unknown encryption: {algorithm}"}
        steps.append(
            (
                "Default encryption",
                "PUT",
                "?encryption",
                _encryption(algorithm, bool(payload.get("bucket_key"))),
            )
        )
    if payload.get("remove_tags"):
        # DeleteBucketTagging: the bucket ends up with no tag set at all.
        steps.append(("Tags", "DELETE", "?tagging", ""))
    if payload.get("tags") is not None:
        tags = [
            (str((tag or {}).get("Key") or "").strip(), str((tag or {}).get("Value") or ""))
            for tag in payload["tags"]
        ]
        if any(not key for key, _ in tags):
            return {"ok": False, "status": 400, "error": "every tag needs a key"}
        steps.append(("Tags", "PUT", "?tagging", _tagging(tags)))
    if not steps:
        return {"ok": False, "status": 400, "error": "nothing to update"}

    for label, method, suffix, body in steps:
        status, text = call(method, path + suffix, body)
        if not 200 <= status < 300:
            return {
                "ok": False,
                "status": status or 502,
                "error": f"{label} failed: {_detail(text, status)}",
            }
    return {"ok": True, "status": 200, "bucket": bucket}


def empty_bucket(bucket: str, call) -> dict:
    """Empty a bucket with DeleteObjects, 1000 keys a request, re-listing until nothing is left."""
    path = _bucket_path(bucket)
    removed = 0
    for _pass in range(EMPTY_PASSES):
        status, body = call("GET", path + "?list-type=2")
        if not 200 <= status < 300:
            return {"ok": False, "status": status, "error": _detail(body, status)}
        keys = [html.unescape(key) for key in re.findall(r"<Key>(.*?)</Key>", body, re.S)]
        if not keys:
            return {"ok": True, "status": 200, "removed": removed}
        payload = (
            f'<Delete xmlns="{S3_NS}"><Quiet>true</Quiet>'
            + "".join(f"<Object><Key>{html.escape(key)}</Key></Object>" for key in keys)
            + "</Delete>"
        )
        status, text = call("POST", path + "?delete", payload)
        if not 200 <= status < 300:
            return {
                "ok": False,
                "status": status or 502,
                "removed": removed,
                "error": _detail(text, status),
            }
        removed += len(keys)
    return {"ok": False, "status": 500, "removed": removed, "error": "the bucket never emptied"}


# The bucket configuration S3 answers as documents, shown as they come; `versions` is a listing, not a setting.
DOCUMENTS = {
    "lifecycle": "?lifecycle",
    "cors": "?cors",
    "policy": "?policy",
    "acl": "?acl",
    "logging": "?logging",
    "notifications": "?notification",
    "website": "?website",
    "replication": "?replication",
    "versions": "?versions",
}

# The documents the page can write: expected root (None for JSON), S3's DELETE, and what switches it off instead.
EDITABLE = {
    "lifecycle": ("LifecycleConfiguration", "DeleteBucketLifecycle", None),
    "cors": ("CORSConfiguration", "DeleteBucketCors", None),
    "policy": (None, "DeleteBucketPolicy", None),
    "acl": ("AccessControlPolicy", None, None),
    "logging": ("BucketLoggingStatus", None, '<BucketLoggingStatus xmlns="{ns}" />'),
    "notifications": (
        "NotificationConfiguration",
        None,
        '<NotificationConfiguration xmlns="{ns}" />',
    ),
    "website": ("WebsiteConfiguration", "DeleteBucketWebsite", None),
    "replication": ("ReplicationConfiguration", "DeleteBucketReplication", None),
}


def _configured(xml: str) -> bool:
    """Whether a document says anything: S3 answers an unset subresource with an empty element, not a 404."""
    root = _root(xml)
    if root is None:
        return True  # not XML this module can judge: show it rather than hide it
    return bool(list(root)) or bool((root.text or "").strip())


_WRITE_HELP = {
    "xml": "The document must be XML with a <{root}> root.",
    "json": "The policy must be a JSON document with a `Statement`.",
}


def _check_document(label: str, text: str) -> str:
    """Why this document cannot be written, or '' when it can."""
    root, _delete, _empty = EDITABLE[label]
    if root is None:
        try:
            document = json.loads(text)
        except ValueError:
            return _WRITE_HELP["json"]
        return "" if isinstance(document, dict) and document.get("Statement") else _WRITE_HELP["json"]
    parsed = _root(text)
    if parsed is None or _local(parsed) != root:
        return _WRITE_HELP["xml"].format(root=root)
    return ""


def write_document(bucket: str, label: str, text: str, call) -> dict:
    """PutBucket<X>: one subresource, checked here so a typo never becomes bucket state."""
    if label not in EDITABLE:
        return {"ok": False, "status": 400, "error": f"{label} is not a document this page writes"}
    problem = _check_document(label, text)
    if problem:
        return {"ok": False, "status": 400, "error": problem}
    headers = {} if EDITABLE[label][0] else {"Content-Type": "application/json"}
    status, body = call("PUT", _bucket_path(bucket) + DOCUMENTS[label], text, headers)
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "document": label}
    return {
        "ok": False,
        "status": status or 502,
        "error": f"{label} failed: {_detail(body, status)}",
    }


def clear_document(bucket: str, label: str, call) -> dict:
    """Remove a document: DELETE where S3 has one, an empty document where it has not."""
    if label not in EDITABLE:
        return {"ok": False, "status": 400, "error": f"{label} is not a document this page writes"}
    _root_name, delete, empty = EDITABLE[label]
    path = _bucket_path(bucket) + DOCUMENTS[label]
    if delete:
        status, body = call("DELETE", path, "")
    elif empty:
        status, body = call("PUT", path, empty.format(ns=S3_NS), {})
    else:
        return {
            "ok": False,
            "status": 400,
            "error": f"S3 has no way to remove a {label} document; it is replaced, not deleted.",
        }
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "document": label}
    return {
        "ok": False,
        "status": status or 502,
        "error": f"{label} failed: {_detail(body, status)}",
    }


def read_documents(bucket: str, call) -> dict:
    """Each document S3 has for `bucket`, or None where it has none, with `editable` saying what may be written."""
    path = _bucket_path(bucket)
    found = {}
    for label, suffix in DOCUMENTS.items():
        status, body = call("GET", path + suffix)
        found[label] = body if 200 <= status < 300 and _configured(body) else None
    editable = {
        label: {
            "delete": bool(delete or empty),
            "kind": "xml" if root else "json",
            "root": root or "",
        }
        for label, (root, delete, empty) in EDITABLE.items()
    }
    return {"ok": True, "bucket": bucket, "documents": found, "editable": editable}


def head_bucket(bucket: str, call) -> dict:
    """HeadBucket: a 301 names the right region in `x-amz-bucket-region`, a 404 a name that is not there."""
    status, headers, _ = call("HEAD", _bucket_path(bucket))
    region = (headers.get("x-amz-bucket-region") or "").strip()
    if 200 <= status < 400:
        return {"ok": True, "exists": True, "status": status, "region": region}
    if status == 404:
        return {"ok": True, "exists": False, "status": status, "region": region}
    return {"ok": False, "status": status or 502, "error": f"HTTP {status}"}


def read_object(bucket: str, key: str, call) -> dict:
    """GetObject as content: HEAD first for type, size and ETag, then GET only when the bytes must be read."""
    path = _bucket_path(bucket) + "/" + quote(key, safe="/")
    status, headers, _ = call("HEAD", path)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _head_failure(status)}

    kind = (headers.get("content-type") or "").split(";")[0].strip()
    try:
        size = int(headers.get("content-length") or 0)
    except ValueError:
        size = 0
    meta = {
        "key": key,
        "size": size,
        "content_type": kind or "application/octet-stream",
        "etag": (headers.get("etag") or "").strip('"'),
        "last_modified": headers.get("last-modified") or "",
    }
    if kind.lower() not in UNKNOWN_TYPES and not _textual(kind):
        return {"ok": True, "status": status, "body": None, "binary": True, **meta}

    status, _headers, data = call("GET", path)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _head_failure(status)}
    text = None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and any(
        character < " " and character not in "\t\n\r" for character in text[:4096]
    ):
        text = None
    return {
        "ok": True,
        "status": status,
        "body": None if text is None else text[:20000],
        "binary": text is None,
        "truncated": text is not None and len(text) > 20000,
        **meta,
    }


def _head_failure(status: int) -> str:
    """A HEAD carries no body, so the status is all there is to name."""
    if status == 404:
        return "NoSuchKey: The specified key does not exist."
    return f"HTTP {status or 'unknown'}"


# The reads beside an object: no tags and no annotations are empty answers, and Object Lock says "not configured".
def _annotation_rows(xml: str) -> list[dict]:
    root = _root(xml)
    if root is None:
        return []
    rows = []
    for element in root.iter():
        if _local(element) != "AnnotationEntry":
            continue
        pair = {_local(child): child.text for child in list(element)}
        rows.append(
            {
                "name": pair.get("AnnotationName") or "",
                "size": pair.get("Size") or "0",
                "modified": pair.get("LastModified") or "",
                "etag": pair.get("ETag") or "",
            }
        )
    return rows


def _code(xml: str) -> str:
    found = _CODE_RE.search(xml or "")
    return found.group(1) if found else ""


# Neither "no Object Lock" answer is an error: both are "not configured", so only a real failure keeps its message.
_LOCK_ABSENT = ("NoSuchObjectLockConfiguration", "InvalidRequest", "ObjectLockConfigurationNotFoundError")


def read_object_meta(bucket: str, key: str, call) -> dict:
    """GetObjectTagging, ListObjectAnnotations, GetObjectRetention, GetObjectLegalHold: states beside the object."""
    path = _bucket_path(bucket) + "/" + quote(key, safe="/")
    found: dict = {"bucket": bucket, "key": key, "errors": {}}

    status, body = call("GET", path + "?tagging")
    found["tags"] = _tags(body) if 200 <= status < 300 else []
    if not 200 <= status < 300:
        found["errors"]["tags"] = _detail(body, status)

    status, body = call("GET", path + "?annotation")
    found["annotations"] = _annotation_rows(body) if 200 <= status < 300 else []
    if not 200 <= status < 300:
        found["errors"]["annotations"] = _detail(body, status)

    for label, suffix in (("retention", "?retention"), ("legal_hold", "?legal-hold")):
        status, body = call("GET", path + suffix)
        if 200 <= status < 300 and _configured(body):
            found[label] = body
        else:
            found[label] = None
            if not 200 <= status < 300 and _code(body) not in _LOCK_ABSENT:
                found["errors"][label] = _detail(body, status)
    return {"ok": True, "status": 200, **found}


def write_object_tags(bucket: str, key: str, tags, call) -> dict:
    """PutObjectTagging, or DeleteObjectTagging when the tag set is empty."""
    path = _bucket_path(bucket) + "/" + quote(key, safe="/") + "?tagging"
    pairs = [
        (str((tag or {}).get("Key") or "").strip(), str((tag or {}).get("Value") or ""))
        for tag in tags or []
    ]
    if not pairs:
        status, body = call("DELETE", path, "")
        if 200 <= status < 300:
            return {"ok": True, "status": status, "bucket": bucket, "key": key, "tags": []}
        return {"ok": False, "status": status or 502, "error": _detail(body, status)}
    if any(not tag_key for tag_key, _value in pairs):
        return {"ok": False, "status": 400, "error": "every tag needs a key"}
    status, body = call("PUT", path, _tagging(pairs))
    if 200 <= status < 300:
        return {
            "ok": True,
            "status": status,
            "bucket": bucket,
            "key": key,
            "tags": [{"Key": name, "Value": value} for name, value in pairs],
        }
    return {"ok": False, "status": status or 502, "error": _detail(body, status)}


def write_annotation(bucket: str, key: str, name: str, text: str, call) -> dict:
    """PutObjectAnnotation: the annotation's own content is text."""
    if not name:
        return {"ok": False, "status": 400, "error": "an annotation name is required"}
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + "?annotation&annotationName="
        + quote(name, safe="")
    )
    status, body = call("PUT", path, "" if text is None else str(text))
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "key": key, "name": name}
    return {"ok": False, "status": status or 502, "name": name, "error": _detail(body, status)}


def clear_annotation(bucket: str, key: str, name: str, call) -> dict:
    """DeleteObjectAnnotation."""
    if not name:
        return {"ok": False, "status": 400, "error": "an annotation name is required"}
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + "?annotation&annotationName="
        + quote(name, safe="")
    )
    status, body = call("DELETE", path, "")
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "key": key, "name": name}
    return {"ok": False, "status": status or 502, "name": name, "error": _detail(body, status)}


_RETENTION_MODES = ("GOVERNANCE", "COMPLIANCE")


def write_retention(bucket: str, key: str, mode: str, until: str, call) -> dict:
    """PutObjectRetention on the object's current version."""
    mode = str(mode or "").strip().upper()
    if mode not in _RETENTION_MODES:
        return {
            "ok": False,
            "status": 400,
            "error": "the retention mode is GOVERNANCE or COMPLIANCE",
        }
    until = str(until or "").strip()
    if not until:
        return {"ok": False, "status": 400, "error": "a retain-until date is required"}
    body = (
        f'<Retention xmlns="{S3_NS}"><Mode>{mode}</Mode>'
        f"<RetainUntilDate>{html.escape(until)}</RetainUntilDate></Retention>"
    )
    path = _bucket_path(bucket) + "/" + quote(key, safe="/") + "?retention"
    status, answer = call("PUT", path, body)
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "key": key, "mode": mode}
    return {"ok": False, "status": status or 502, "error": _detail(answer, status)}


def write_legal_hold(bucket: str, key: str, status_value: str, call) -> dict:
    """PutObjectLegalHold on the object's current version."""
    status_value = str(status_value or "").strip().upper()
    if status_value not in ("ON", "OFF"):
        return {"ok": False, "status": 400, "error": "the legal hold is ON or OFF"}
    body = f'<LegalHold xmlns="{S3_NS}"><Status>{status_value}</Status></LegalHold>'
    path = _bucket_path(bucket) + "/" + quote(key, safe="/") + "?legal-hold"
    status, answer = call("PUT", path, body)
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "key": key, "legal_hold": status_value}
    return {"ok": False, "status": status or 502, "error": _detail(answer, status)}


def create_multipart(bucket: str, key: str, content_type: str, call) -> dict:
    """CreateMultipartUpload: the upload id is the only handle for the parts."""
    headers = {"Content-Type": content_type or "application/octet-stream"}
    path = _bucket_path(bucket) + "/" + quote(key, safe="/") + "?uploads"
    status, body = call("POST", path, "", headers)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(body, status)}
    upload = re.search(r"<UploadId>(.*?)</UploadId>", body, re.S)
    if not upload:
        return {"ok": False, "status": status, "error": "the answer carried no UploadId"}
    return {
        "ok": True,
        "status": status,
        "bucket": bucket,
        "key": key,
        "upload_id": upload.group(1),
    }


def upload_part(
    bucket: str, key: str, upload_id: str, part_number: int, data, call
) -> dict:
    """UploadPart: the answer's ETag is what CompleteMultipartUpload needs."""
    if not upload_id:
        return {"ok": False, "status": 400, "error": "an upload id is required"}
    if not 1 <= int(part_number) <= 10000:
        return {"ok": False, "status": 400, "error": "a part number is between 1 and 10000"}
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + f"?partNumber={int(part_number)}&uploadId={quote(upload_id, safe='')}"
    )
    status, headers, body = call("PUT", path, data)
    if not 200 <= status < 300:
        return {
            "ok": False,
            "status": status or 502,
            "error": _detail(body.decode(errors="replace"), status),
        }
    return {
        "ok": True,
        "status": status,
        "part_number": int(part_number),
        "etag": headers.get("etag", ""),
    }


def complete_multipart(bucket: str, key: str, upload_id: str, parts, call) -> dict:
    """CompleteMultipartUpload: every part the console uploaded, in order."""
    if not upload_id:
        return {"ok": False, "status": 400, "error": "an upload id is required"}
    entries = "".join(
        f"<Part><PartNumber>{int((part or {}).get('part_number') or 0)}</PartNumber>"
        f"<ETag>{html.escape(str((part or {}).get('etag') or ''))}</ETag></Part>"
        for part in parts or []
    )
    if not entries:
        return {"ok": False, "status": 400, "error": "no parts were uploaded"}
    body = (
        f'<CompleteMultipartUpload xmlns="{S3_NS}">{entries}'
        "</CompleteMultipartUpload>"
    )
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + f"?uploadId={quote(upload_id, safe='')}"
    )
    status, answer = call("POST", path, body)
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "key": key}
    return {"ok": False, "status": status or 502, "error": _detail(answer, status)}


def abort_multipart(bucket: str, key: str, upload_id: str, call) -> dict:
    """AbortMultipartUpload: discards the parts already uploaded."""
    if not upload_id:
        return {"ok": False, "status": 400, "error": "an upload id is required"}
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + f"?uploadId={quote(upload_id, safe='')}"
    )
    status, body = call("DELETE", path, "")
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "key": key}
    return {"ok": False, "status": status or 502, "error": _detail(body, status)}


def read_annotation(bucket: str, key: str, name: str, call) -> dict:
    """GetObjectAnnotation: one annotation's own content, which is text."""
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + "?annotation&annotationName="
        + quote(name, safe="")
    )
    status, body = call("GET", path)
    if 200 <= status < 300:
        return {"ok": True, "status": status, "bucket": bucket, "key": key, "name": name, "body": body}
    return {
        "ok": False,
        "status": status or 502,
        "bucket": bucket,
        "key": key,
        "name": name,
        "error": _detail(body, status),
    }
def _tag(block: str, name: str) -> str:
    """The text of the first `name` element in a fragment, as the listing handlers need it."""
    found = re.search(rf"<{name}>(.*?)</{name}>", block or "", re.S)
    return found.group(1) if found else ""


def _text(element, name: str) -> str:
    """The text of the first `name` descendant of an element, for the parsed ACL."""
    if element is None:
        return ""
    for child in element.iter():
        if _local(child) == name:
            return child.text or ""
    return ""


def read_acl(bucket: str, key: str, call, version_id: str = "") -> dict:
    """GetObjectAcl: the owner and every grant, as the document answers them."""
    path = _bucket_path(bucket) + "/" + quote(key, safe="/") + "?acl"
    if version_id:
        path += "&versionId=" + quote(version_id, safe="")
    status, body = call("GET", path)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(body, status)}
    root = _root(body)
    owner = {"id": "", "display_name": ""}
    grants: list[dict] = []
    if root is not None:
        for element in root.iter():
            name = _local(element)
            if name == "Owner":
                owner = {
                    "id": _text(element, "ID") or "",
                    "display_name": _text(element, "DisplayName") or "",
                }
            if name != "Grant":
                continue
            grantee = next(
                (child for child in element if _local(child) == "Grantee"), None
            )
            grants.append(
                {
                    "type": _local(grantee) if grantee is not None else "",
                    "id": (_text(grantee, "ID") if grantee is not None else "") or "",
                    "display_name": (
                        _text(grantee, "DisplayName") if grantee is not None else ""
                    )
                    or "",
                    "uri": (_text(grantee, "URI") if grantee is not None else "") or "",
                    "permission": _text(element, "Permission") or "",
                }
            )
    return {
        "ok": True,
        "status": status,
        "bucket": bucket,
        "key": key,
        "version_id": version_id,
        "owner": owner,
        "grants": grants,
        "public": any(grant["uri"].endswith("/AllUsers") for grant in grants),
        "acl": body,
    }


def list_versions(
    bucket: str,
    call,
    prefix: str = "",
    key_marker: str = "",
    version_id_marker: str = "",
    max_keys: str = "",
) -> dict:
    """ListObjectVersions: every version and delete marker under the prefix, at any depth."""
    path = _bucket_path(bucket) + "?versions"
    for name, value in (
        ("prefix", prefix),
        ("key-marker", key_marker),
        ("version-id-marker", version_id_marker),
        ("max-keys", max_keys),
    ):
        if value:
            path += "&" + name + "=" + quote(value, safe="")
    status, body = call("GET", path)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(body, status)}
    versions = [
        {
            "key": _tag(block, "Key"),
            "version_id": _tag(block, "VersionId"),
            "latest": _tag(block, "IsLatest") == "true",
            "delete_marker": False,
            "size": _tag(block, "Size"),
            "modified": _tag(block, "LastModified"),
            "storage": _tag(block, "StorageClass"),
        }
        for block in re.findall(r"<Version>(.*?)</Version>", body, re.S)
    ]
    markers = [
        {
            "key": _tag(block, "Key"),
            "version_id": _tag(block, "VersionId"),
            "latest": _tag(block, "IsLatest") == "true",
            "delete_marker": True,
            "size": "",
            "modified": _tag(block, "LastModified"),
            "storage": "",
        }
        for block in re.findall(r"<DeleteMarker>(.*?)</DeleteMarker>", body, re.S)
    ]
    rows = sorted(versions + markers, key=lambda row: (row["key"], row["modified"]))
    # A listing is one page; the markers are how the rest is asked for.
    truncated = _tag(body, "IsTruncated").strip().lower() == "true"
    return {
        "ok": True,
        "status": status,
        "bucket": bucket,
        "prefix": prefix,
        "versions": rows,
        "truncated": truncated,
        "next_key_marker": (_tag(body, "NextKeyMarker") or "").strip() if truncated else "",
        "next_version_id_marker": (
            (_tag(body, "NextVersionIdMarker") or "").strip() if truncated else ""
        ),
    }


def delete_version(bucket: str, key: str, version_id: str, call) -> dict:
    """DeleteObject with a versionId: that version is gone for good."""
    if not version_id:
        return {"ok": False, "status": 400, "error": "a version id is required"}
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + "?versionId="
        + quote(version_id, safe="")
    )
    status, body = call("DELETE", path)
    if 200 <= status < 300:
        return {
            "ok": True,
            "status": status,
            "bucket": bucket,
            "key": key,
            "version_id": version_id,
        }
    return {"ok": False, "status": status or 502, "error": _detail(body, status)}


def list_uploads(
    bucket: str,
    call,
    prefix: str = "",
    key_marker: str = "",
    upload_id_marker: str = "",
    max_uploads: str = "",
) -> dict:
    """ListMultipartUploads: the uploads that were started and never finished."""
    path = _bucket_path(bucket) + "?uploads"
    for name, value in (
        ("prefix", prefix),
        ("key-marker", key_marker),
        ("upload-id-marker", upload_id_marker),
        ("max-uploads", max_uploads),
    ):
        if value:
            path += "&" + name + "=" + quote(value, safe="")
    status, body = call("GET", path)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(body, status)}
    rows = [
        {
            "key": _tag(block, "Key"),
            "upload_id": _tag(block, "UploadId"),
            "initiated": _tag(block, "Initiated"),
            "storage": _tag(block, "StorageClass"),
        }
        for block in re.findall(r"<Upload>(.*?)</Upload>", body, re.S)
    ]
    truncated = _tag(body, "IsTruncated").strip().lower() == "true"
    return {
        "ok": True,
        "status": status,
        "bucket": bucket,
        "uploads": rows,
        "truncated": truncated,
        "next_key_marker": (_tag(body, "NextKeyMarker") or "").strip() if truncated else "",
        "next_upload_id_marker": (
            (_tag(body, "NextUploadIdMarker") or "").strip() if truncated else ""
        ),
    }


def list_parts(
    bucket: str,
    key: str,
    upload_id: str,
    call,
    part_number_marker: str = "",
    max_parts: str = "",
) -> dict:
    """ListParts: what one incomplete upload already holds."""
    if not upload_id:
        return {"ok": False, "status": 400, "error": "an upload id is required"}
    path = (
        _bucket_path(bucket)
        + "/"
        + quote(key, safe="/")
        + "?uploadId="
        + quote(upload_id, safe="")
    )
    for name, value in (
        ("part-number-marker", part_number_marker),
        ("max-parts", max_parts),
    ):
        if value:
            path += "&" + name + "=" + quote(value, safe="")
    status, body = call("GET", path)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(body, status)}
    parts = [
        {
            "part_number": _tag(block, "PartNumber"),
            "size": _tag(block, "Size"),
            "etag": _tag(block, "ETag"),
            "modified": _tag(block, "LastModified"),
        }
        for block in re.findall(r"<Part>(.*?)</Part>", body, re.S)
    ]
    truncated = _tag(body, "IsTruncated").strip().lower() == "true"
    return {
        "ok": True,
        "status": status,
        "bucket": bucket,
        "key": key,
        "upload_id": upload_id,
        "parts": parts,
        "truncated": truncated,
        "next_part_number_marker": (
            (_tag(body, "NextPartNumberMarker") or "").strip() if truncated else ""
        ),
    }
