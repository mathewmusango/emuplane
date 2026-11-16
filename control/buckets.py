"""Creating a bucket the way the console's create page does it.

`CreateBucket` itself takes the name, the region, and — as headers — object
ownership and Object Lock. Everything else on that form (Block Public Access,
versioning, tags, default encryption) is a follow-up subresource call, so this
module makes them in the console's order and names the step that failed instead
of answering with a bare HTTP code.

The signed client is passed in as `s3(method, path, body, headers)`, so nothing
here holds a credential — the same property `console.py` keeps.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote
from xml.etree import ElementTree

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

# What the console sends for text typed into the form, and what it is willing to
# show back as text. Anything else is offered as a download.
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

# Namespaces: AWS's global one, and the account-scoped one whose names carry the
# account, the region and `-an` — that suffix is what makes the name unique
# without being global.
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
    """The CreateBucket document.

    Only the global us-east-1 endpoint accepts a request without one; every
    regional endpoint refuses it (IllegalLocationConstraintException), and a
    constraint naming us-east-1 is itself invalid there.
    """
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
    """The Account Regional namespace suffix: `<account>-<region>-an`.

    `test` in the armchair's account and region is created as
    `test.344381301567-us-east-1-an`, which is the name AWS gives it.
    """
    return f"{account}-{region}-an"


def resolve_name(payload: dict, region: str) -> tuple[str, str]:
    """The name this request creates, and why it cannot be one.

    The suffix is appended here rather than typed by the caller: a name that
    already ends with it is not suffixed twice, so a retry after a failure, or a
    pasted full name, still means one bucket.
    """
    base = str(payload.get("bucket") or "").strip()
    if str(payload.get("namespace") or NAMESPACE_GLOBAL) != NAMESPACE_REGIONAL:
        return (base, "") if valid_name(base) else ("", NAME_HELP)
    account = str(payload.get("account") or "").strip()
    if not ACCOUNT_RE.match(account):
        # The suffix *is* the account and region; without one it would compose a
        # name that looks regional and is not.
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
    # Bucket Keys are a KMS feature: the console shows the control either way,
    # but sending it with SSE-S3 describes nothing real.
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
        "tags": tags,
        # The console sends the block only when the operator left it expanded;
        # absent means "leave the emulator's default alone".
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
        return ElementTree.fromstring(xml)
    except ElementTree.ParseError:
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


def read_settings(bucket: str, call) -> dict:
    """The create form's settings, read back from `bucket`.

    `call(method, path)` is the root-signed client. Best effort per setting: a
    subresource this bucket does not have keeps the form's default rather than
    failing the whole copy — copying is a convenience, not a transaction.
    """
    path = "/" + quote(bucket, safe="")
    settings = {
        "ownership": OWNERSHIP[0],
        "block_public_access": {name: False for name in PUBLIC_ACCESS},
        "versioning": False,
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
        settings["block_public_access"] = {
            name: bool(flags.get(name)) for name in PUBLIC_ACCESS
        }

    settings["versioning"] = _field(get("?versioning"), "Status") == "Enabled"
    settings["tags"] = _tags(get("?tagging"))

    encryption = _field(get("?encryption"), "SSEAlgorithm")
    if encryption in ENCRYPTION:
        settings["encryption"] = encryption
    settings["bucket_key"] = _field(get("?encryption"), "BucketKeyEnabled") == "true"
    settings["object_lock"] = _field(get("?object-lock"), "ObjectLockEnabled") == "Enabled"

    return {"ok": True, "bucket": bucket, "settings": settings}


def create(region: str, payload: dict, s3) -> dict:
    """Create the bucket, then apply the settings the form asked for.

    A follow-up failure still reports `created: True`: the bucket exists, and
    saying otherwise would send the operator looking for a name that is taken.
    """
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
    if options["versioning"] or options["object_lock"]:
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
    """PutObject: the key is percent-encoded, the body is what was handed over.

    `body` is text from the form or bytes from a file, and `content_type` is what
    S3 stores and serves back — a PNG that arrives as `application/xml` is a
    wrong object, not a cosmetic detail.
    """
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
    """CopyObject: a PUT to the destination, with the source named in a header.

    The request is addressed to the *destination*, so `call` must be signed for
    the destination's region; the source is named, not reached, which is what lets
    a copy cross a bucket or a region.
    """
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
    # `(label, method, suffix, body)` — most steps are a PUT, but removing the
    # default encryption is a DELETE, and the page should not need two routes.
    steps: list[tuple[str, str, str, str]] = []
    if "versioning" in payload:
        status = "Enabled" if payload.get("versioning") else "Suspended"
        steps.append(
            (
                "Bucket versioning",
                "PUT",
                "?versioning",
                f'<VersioningConfiguration xmlns="{S3_NS}"><Status>{status}</Status>'
                "</VersioningConfiguration>",
            )
        )
    if payload.get("block_public_access") is not None:
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
        # DeleteBucketEncryption: the bucket falls back to S3's own default
        # (SSE-S3) rather than being left unencrypted.
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
    """Empty a bucket with DeleteObjects, 1000 keys a request.

    One call per up-to-1000 keys instead of one per key, and re-listing until the
    bucket answers with nothing: a listing is capped, so one pass can stop short.
    """
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


# The bucket configuration S3 answers as documents. The console shows them as
# they come: parsing every one into a form would be a UI project per subresource,
# and the GETs are the part people ask for.
#
# `versions` is the exception in kind: it is a listing (ListObjectVersions), not a
# setting, and it sits here because it is the version of the data rather than of
# the configuration.
DOCUMENTS = {
    "lifecycle": "?lifecycle",
    "cors": "?cors",
    "policy": "?policy",
    "acl": "?acl",
    "logging": "?logging",
    "notifications": "?notification",
    "replication": "?replication",
    "versions": "?versions",
}

# The documents the page can write, and what writing means for each: the expected
# root element (None for the policy, which is JSON), whether S3 has a DELETE, and
# — where it has none — the document that switches the feature off instead.
# `versions` is absent: it is a listing, not a setting.
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
    "replication": ("ReplicationConfiguration", "DeleteBucketReplication", None),
}


def _configured(xml: str) -> bool:
    """Whether a document says anything.

    S3 answers an unset subresource with an empty element —
    `<BucketLoggingStatus />`, `<NotificationConfiguration />` — not with a 404.
    Printing that as configuration is worse than printing nothing: it reads as
    though something is switched on. A document with no children and no text is
    the same state as a 404, and is reported the same way.
    """
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
    """PutBucket<X>: one subresource, in the format S3 takes for it.

    The document is checked here rather than at the emulator: a wrong root, or a
    policy that is not JSON, is the operator's typo and should not become bucket
    state.
    """
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
    """Each document S3 has for `bucket`, or None where it has none at all.

    `editable` travels with the documents so the page does not keep its own copy
    of what S3 allows: which documents can be written, and whether removing one
    means DELETE or an empty document.
    """
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
    """HeadBucket: does `bucket` exist, and where does it live?

    S3 answers a bucket in another region with 301 and names the right region in
    `x-amz-bucket-region`; a 404 is a name that is not there at all. The body of a
    HEAD is empty by definition, so there is no error document to read.
    """
    status, headers, _ = call("HEAD", _bucket_path(bucket))
    region = (headers.get("x-amz-bucket-region") or "").strip()
    if 200 <= status < 400:
        return {"ok": True, "exists": True, "status": status, "region": region}
    if status == 404:
        return {"ok": True, "exists": False, "status": status, "region": region}
    return {"ok": False, "status": status or 502, "error": f"HTTP {status}"}


def read_object(bucket: str, key: str, call) -> dict:
    """GetObject as content: text when it decodes, a download when it does not.

    `call(method, path)` answers `(status, headers, bytes)`. HeadObject goes
    first, because the type, the size and the ETag are headers: a PNG is then
    never downloaded just to be thrown away, and the page can show what only a
    HEAD knows. The GET follows only when the bytes have to be read — a textual
    type, or one that says nothing either way.
    """
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


# The reads that live beside an object rather than in it. Each is its own GET on
# the object's own path, and each answers something that is a state rather than a
# failure: no tags and no annotations are empty answers, and Object Lock says it
# is not configured in its own code.
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


# A bucket without Object Lock refuses the read outright; one with Object Lock
# but no retention on this object answers 404 with the same code. Neither is an
# error the page should shout about, so both are reported as "not configured" and
# only a real failure keeps its message.
_LOCK_ABSENT = ("NoSuchObjectLockConfiguration", "InvalidRequest", "ObjectLockConfigurationNotFoundError")


def read_object_meta(bucket: str, key: str, call) -> dict:
    """GetObjectTagging, ListObjectAnnotations, GetObjectRetention, GetObjectLegalHold.

    `call(method, path)` answers `(status, body)`. Everything here is a state
    beside the object, so a read that reports "not configured" comes back as
    empty with no error, and `errors` only carries what genuinely failed.
    """
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
