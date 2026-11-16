"""Access points: the S3 Control API behind the console's Access Points page.

Access points are not bucket subresources: S3 Control serves them under
`/v20180820/...`, it names the account in `x-amz-account-id`, and a management
call is resolved in the region it was signed for. The console keeps that shape —
the signed client passed in as `rest(region, method, path, body)`, so nothing
here holds a credential and the region is an argument rather than ambient state.

The listing is one call, but `ListAccessPoints` leaves out the VPC id, so each
row is opened with `GetAccessPoint` — bounded, because a page is not a crawler.
Multi-Region access points are managed from us-west-2 only, which is why that
listing's region is fixed here rather than taken from the page.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote
from xml.etree import ElementTree

CONTROL_NS = "https://awss3control.amazonaws.com/doc/2018-08-20/"

# S3 Control's collection and instance prefixes.
ACCESS_POINTS = "/v20180820/accesspoint"
OBJECT_LAMBDA = "/v20180820/accesspointforobjectlambda"
MULTI_REGION = "/v20180820/mrap/instances"

# MRAP management is served from one region, on AWS and in the emulator.
MULTI_REGION_HOME = "us-west-2"

SECTIONS = ("general", "multi-region", "object-lambda")

PUBLIC_ACCESS = (
    "BlockPublicAcls",
    "IgnorePublicAcls",
    "BlockPublicPolicy",
    "RestrictPublicBuckets",
)

# A page opens at most this many access points for their details.
DETAIL_LIMIT = 100

NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])$")
VPC_RE = re.compile(r"^vpc-[0-9a-f]{8,17}$")

NAME_HELP = (
    "Access point names are 3 to 50 characters: lowercase letters, digits and "
    "hyphens, beginning and ending with a letter or number, without `--`."
)

_MESSAGE_RE = re.compile(r"<Message>(.*?)</Message>", re.S)
_CODE_RE = re.compile(r"<Code>(.*?)</Code>", re.S)


def _local(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _root(xml: str):
    try:
        return ElementTree.fromstring(xml or "")
    except ElementTree.ParseError:
        return None


def _first(xml: str, wanted: str):
    """The first element called `wanted` in a document, or None."""
    root = _root(xml)
    if root is None:
        return None
    for element in root.iter():
        if _local(element) == wanted:
            return element
    return None


def _field(element, name: str) -> str:
    """The text of the first `name` element at or under `element`."""
    if element is None:
        return ""
    for child in element.iter():
        if _local(child) == name:
            return (child.text or "").strip()
    return ""


def _children(element, container: str, entry: str) -> list:
    if element is None:
        return []
    for child in element.iter():
        if _local(child) == container:
            return [item for item in list(child) if _local(item) == entry]
    return []


def _entries(xml: str, container: str, entry: str) -> list | None:
    """The `entry` elements under `container`, or None when the answer is not XML.

    None is not "empty": a body this module cannot read must not be shown as an
    account with no access points.
    """
    root = _root(xml)
    if root is None:
        return None
    for element in root.iter():
        if _local(element) == container:
            return [item for item in list(element) if _local(item) == entry]
    return None


def _detail(text: str, status: int) -> str:
    """S3 Control answers errors as XML; the sentence inside is the useful part."""
    message = _MESSAGE_RE.search(text or "")
    if message:
        code = _CODE_RE.search(text or "")
        sentence = html.unescape(message.group(1)).strip()
        return f"{code.group(1).strip()}: {sentence}" if code else sentence
    return (text or "").strip()[:200] or f"HTTP {status}"


def _code(text: str) -> str:
    found = _CODE_RE.search(text or "")
    return found.group(1).strip() if found else ""


def _path(name: str) -> str:
    return ACCESS_POINTS + "/" + quote(name, safe="")


def _tag_elements(tags: list[str]) -> str:
    """`Key=Value` strings from the form, as the API's Tag elements."""
    parts = []
    for tag in tags:
        key, _, value = tag.partition("=")
        if not key.strip():
            continue
        parts.append(
            f"<Tag><Key>{html.escape(key.strip())}</Key>"
            f"<Value>{html.escape(value)}</Value></Tag>"
        )
    return "".join(parts)


def _create_body(bucket: str, vpc_id: str, public: dict | None, tags: list[str]) -> str:
    parts = [f"<Bucket>{html.escape(bucket)}</Bucket>"]
    if vpc_id:
        parts.append(
            f"<VpcConfiguration><VpcId>{html.escape(vpc_id)}</VpcId></VpcConfiguration>"
        )
    if public is not None:
        parts.append(
            "<PublicAccessBlockConfiguration>"
            + "".join(
                f"<{name}>{'true' if public.get(name) else 'false'}</{name}>"
                for name in PUBLIC_ACCESS
            )
            + "</PublicAccessBlockConfiguration>"
        )
    if tags:
        parts.append(f"<Tags>{_tag_elements(tags)}</Tags>")
    return (
        f'<CreateAccessPointRequest xmlns="{CONTROL_NS}">'
        + "".join(parts)
        + "</CreateAccessPointRequest>"
    )


def _policy_body(policy: str) -> str:
    return (
        f'<PutAccessPointPolicyRequest xmlns="{CONTROL_NS}">'
        f"<Policy>{html.escape(policy)}</Policy>"
        "</PutAccessPointPolicyRequest>"
    )


def _form(payload: dict) -> tuple[str, str, str, dict | None, list[str]]:
    """The create form's values, checked once, in the shape the call needs."""
    name = str(payload.get("name") or "").strip()
    if not NAME_RE.match(name) or "--" in name:
        raise ValueError(NAME_HELP)
    bucket = str(payload.get("bucket") or "").strip()
    if not bucket:
        raise ValueError("Choose the bucket this access point is attached to.")
    vpc_id = str(payload.get("vpc_id") or "").strip()
    if vpc_id and not VPC_RE.match(vpc_id):
        raise ValueError("A VPC id looks like `vpc-` followed by 8 to 17 hex digits.")
    public = payload.get("block_public_access")
    if public is not None:
        public = {key: bool((public or {}).get(key, True)) for key in PUBLIC_ACCESS}
    tags = [str(tag).strip() for tag in payload.get("tags") or [] if str(tag).strip()]
    return name, bucket, vpc_id, public, tags


def _policy_problem(policy: str) -> str:
    """S3 wants a policy document; the emulator stores the text, so check it here."""
    try:
        document = json.loads(policy)
    except ValueError as exc:
        return f"the policy is not JSON ({exc.msg})"
    if not isinstance(document, dict) or not document.get("Statement"):
        return "the policy needs a `Statement`"
    return ""


def create(region: str, payload: dict, rest) -> dict:
    """CreateAccessPoint, then the optional policy the form carries.

    A policy that fails to apply still reports `created: True`: the access point
    exists, and saying otherwise would send the operator looking for a name that
    is taken.
    """
    try:
        name, bucket, vpc_id, public, tags = _form(payload)
    except ValueError as exc:
        return {"ok": False, "status": 400, "error": str(exc)}

    status, text = rest(
        region, "PUT", _path(name), _create_body(bucket, vpc_id, public, tags)
    )
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "name": name, "error": _detail(text, status)}

    result = {"name": name, "arn": _field(_first(text, "CreateAccessPointResult"), "AccessPointArn")}
    result["alias"] = _field(_first(text, "CreateAccessPointResult"), "Alias")

    policy = str(payload.get("policy") or "").strip()
    if policy:
        problem = _policy_problem(policy)
        if problem:
            return {
                "ok": False,
                "status": 400,
                "created": True,
                "error": f"Access point policy failed: {problem}",
                **result,
            }
        status, text = rest(region, "PUT", _path(name) + "/policy", _policy_body(policy))
        if not 200 <= status < 300:
            return {
                "ok": False,
                "status": status or 502,
                "created": True,
                "error": f"Access point policy failed: {_detail(text, status)}",
                **result,
            }

    return {"ok": True, "status": 200, "created": True, **result}


def _base_row(region: str, entry) -> dict:
    return {
        "name": _field(entry, "Name"),
        "alias": _field(entry, "Alias"),
        "arn": _field(entry, "AccessPointArn"),
        "network_origin": _field(entry, "NetworkOrigin") or "Internet",
        "vpc_id": "",
        "created": "",
        "status": "READY",
        "bucket": "",
        "buckets": [],
        "region": region,
    }


def list_general(region: str, rest, bucket: str = "") -> dict:
    """ListAccessPoints in `region`, each row opened for the VPC id."""
    path = ACCESS_POINTS + (f"?bucket={quote(bucket, safe='')}" if bucket else "")
    status, text = rest(region, "GET", path)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(text, status)}
    found = _entries(text, "AccessPointList", "AccessPoint")
    if found is None:
        return {
            "ok": False,
            "status": status,
            "error": "the answer was not an access point listing",
        }

    rows = [_base_row(region, entry) for entry in found]
    for row in rows[:DETAIL_LIMIT]:
        code, body = rest(region, "GET", _path(row["name"]))
        if not 200 <= code < 300:
            continue  # the listing is the truth; a failed detail only blanks a column
        row["vpc_id"] = _field(_first(body, "VpcConfiguration"), "VpcId")
        row["created"] = _field(_first(body, "GetAccessPointResult"), "CreationDate")
        row["arn"] = _field(_first(body, "GetAccessPointResult"), "AccessPointArn") or row["arn"]
        row["bucket"] = _field(_first(body, "GetAccessPointResult"), "Bucket") or row["bucket"]
    return {"ok": True, "status": status, "region": region, "access_points": rows}


def list_multi_region(rest) -> dict:
    """ListMultiRegionAccessPoints, served from us-west-2."""
    status, text = rest(MULTI_REGION_HOME, "GET", MULTI_REGION)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(text, status)}
    found = _entries(text, "AccessPoints", "AccessPoint")
    if found is None:
        return {
            "ok": False,
            "status": status,
            "error": "the answer was not a Multi-Region access point listing",
        }
    rows = []
    for entry in found:
        row = _base_row(MULTI_REGION_HOME, entry)
        row["created"] = _field(entry, "CreatedAt")
        row["status"] = _field(entry, "Status") or "READY"
        members = _children(entry, "Regions", "Region")
        row["buckets"] = [
            {"bucket": _field(member, "Bucket"), "region": _field(member, "Region")}
            for member in members
        ]
        # An MRAP has no bucket of its own; its ARN names the account and alias,
        # and the report carries the account inside each member Region.
        account = _field(members[0] if members else None, "BucketAccountId")
        if account and row["alias"]:
            row["arn"] = f"arn:aws:s3::{account}:accesspoint/{row['alias']}"
        rows.append(row)
    return {"ok": True, "status": status, "region": MULTI_REGION_HOME, "access_points": rows}


def list_object_lambda(region: str, rest) -> dict:
    """ListAccessPointsForObjectLambda in the page's region."""
    status, text = rest(region, "GET", OBJECT_LAMBDA)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(text, status)}
    found = _entries(text, "ObjectLambdaAccessPointList", "ObjectLambdaAccessPoint")
    if found is None:
        return {
            "ok": False,
            "status": status,
            "error": "the answer was not an Object Lambda access point listing",
        }
    rows = []
    for entry in found:
        row = _base_row(region, entry)
        row["arn"] = _field(entry, "ObjectLambdaAccessPointArn")
        for child in entry.iter():
            if _local(child) == "Alias":
                row["alias"] = _field(child, "Value")
                row["status"] = _field(child, "Status") or "READY"
                break
        rows.append(row)
    return {"ok": True, "status": status, "region": region, "access_points": rows}


def listing(section: str, region: str, rest, bucket: str = "") -> dict:
    """One section of the page, in the region that section is read from."""
    if section == "multi-region":
        return list_multi_region(rest)
    if section == "object-lambda":
        return list_object_lambda(region, rest)
    if section == "general":
        return list_general(region, rest, bucket)
    return {"ok": False, "status": 400, "error": f"unknown access point section: {section}"}


def delete(region: str, name: str, rest) -> dict:
    status, text = rest(region, "DELETE", _path(name))
    if 200 <= status < 300:
        return {"ok": True, "status": status, "name": name}
    return {"ok": False, "status": status or 502, "name": name, "error": _detail(text, status)}


def read_policy(region: str, name: str, rest) -> dict:
    """GetAccessPointPolicy; no policy at all is a state, not a failure."""
    status, text = rest(region, "GET", _path(name) + "/policy")
    if 200 <= status < 300:
        return {
            "ok": True,
            "status": status,
            "name": name,
            "policy": _field(_first(text, "GetAccessPointPolicyResult"), "Policy"),
        }
    if status == 404 and _code(text) == "NoSuchAccessPointPolicy":
        return {"ok": True, "status": 200, "name": name, "policy": None}
    return {"ok": False, "status": status or 502, "name": name, "error": _detail(text, status)}


def write_policy(region: str, name: str, policy, rest) -> dict:
    """PutAccessPointPolicy, or DeleteAccessPointPolicy when the policy is empty."""
    text = "" if policy is None else str(policy).strip()
    if not text:
        status, body = rest(region, "DELETE", _path(name) + "/policy")
        if 200 <= status < 300:
            return {"ok": True, "status": status, "name": name, "policy": None}
        return {"ok": False, "status": status or 502, "name": name, "error": _detail(body, status)}

    problem = _policy_problem(text)
    if problem:
        return {"ok": False, "status": 400, "name": name, "error": problem}
    status, body = rest(region, "PUT", _path(name) + "/policy", _policy_body(text))
    if 200 <= status < 300:
        return {"ok": True, "status": status, "name": name, "policy": text}
    return {"ok": False, "status": status or 502, "name": name, "error": _detail(body, status)}
