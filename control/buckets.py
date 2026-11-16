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
