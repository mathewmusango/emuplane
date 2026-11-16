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

Creating a Multi-Region access point is asynchronous: the call answers with a
request token, and the operation it names is the only account of what became of
the request, so the console describes that operation at once and keeps the token
nowhere else.
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

# S3 Control's asynchronous operations: a POST to `.../<create|delete|put-policy>`
# answers with a token, and a GET to a token describes the operation.
ASYNC = "/v20180820/async-requests/mrap"

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


def _child(element, name: str):
    """The direct child called `name`, or None.

    `_field` searches at or under an element, which is wrong when one document
    carries the same name twice — an async operation reports its request and its
    answer side by side — so a section is entered by its own child.
    """
    if element is None:
        return None
    for child in list(element):
        if _local(child) == name:
            return child
    return None


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


def _mrap_members(entry) -> list[dict]:
    """An MRAP's member buckets, each with the region it lives in.

    A member is itself a `Region` element, so its own name has to come from a
    child called `Region` rather than from itself — `_field` on the member would
    answer the member's whitespace.
    """
    members = []
    for member in _children(entry, "Regions", "Region"):
        region = ""
        for child in list(member):
            if _local(child) == "Region":
                region = (child.text or "").strip()
        members.append({"bucket": _field(member, "Bucket"), "region": region})
    return members


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
        row["buckets"] = _mrap_members(entry)
        # An MRAP has no bucket of its own; its ARN names the account and alias,
        # and the report carries the account inside each member Region.
        members = _children(entry, "Regions", "Region")
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


# ---------------------------------------------------------------------------
# One access point in full
# ---------------------------------------------------------------------------
#
# A listing is not a detail: a Multi-Region Access Point's listing carries neither
# its policy nor its routing dials, and an Object Lambda access point's carries no
# configuration at all. The row's view therefore reads the instance resources
# themselves, which is what the console's detail pane shows.


def _mrap_policy_text(text: str) -> str:
    """The policy in force, from the Established (or else Proposed) state.

    AWS reports the policy twice while it propagates; MiniStack applies at once,
    so either the same text or an empty one.
    """
    state = _first(text, "Established")
    if state is None:
        state = _first(text, "Proposed")
    return _field(state, "Policy")


def read_multi_region_policy(name: str, rest) -> dict:
    """GetMultiRegionAccessPointPolicy; no policy at all is a state, not a failure."""
    status, text = rest(
        MULTI_REGION_HOME, "GET", MULTI_REGION + "/" + quote(name, safe="") + "/policy"
    )
    if 200 <= status < 300:
        return {
            "ok": True,
            "status": status,
            "name": name,
            "policy": _mrap_policy_text(text) or None,
        }
    if status == 404 and _code(text) == "NoSuchMultiRegionAccessPointPolicy":
        return {"ok": True, "status": 200, "name": name, "policy": None}
    return {"ok": False, "status": status or 502, "name": name, "error": _detail(text, status)}


def multi_region_detail(name: str, rest) -> dict:
    """GetMultiRegionAccessPoint, GetMultiRegionAccessPointPolicy, and the routes.

    Three reads on one resource, from the region that manages Multi-Region access
    points. Routes address the access point by ARN, which the report only implies,
    so they are read after it and skipped when the ARN cannot be built.
    """
    status, text = rest(MULTI_REGION_HOME, "GET", MULTI_REGION + "/" + quote(name, safe=""))
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "name": name, "error": _detail(text, status)}

    report = _first(text, "AccessPoint")
    members = _mrap_members(report)
    alias = _field(report, "Alias")
    account = ""
    for member in _children(report, "Regions", "Region"):
        account = _field(member, "BucketAccountId")
        if account:
            break
    arn = f"arn:aws:s3::{account}:accesspoint/{alias}" if account and alias else ""

    detail = {
        "section": "multi-region",
        "name": _field(report, "Name") or name,
        "alias": alias,
        "arn": arn,
        # `state` is the resource's own status; `status` in an answer is the HTTP code.
        "state": _field(report, "Status"),
        "created": _field(report, "CreatedAt"),
        "region": MULTI_REGION_HOME,
        "buckets": members,
        "policy": None,
        "routes": [],
        "errors": {},
    }

    status, text = rest(
        MULTI_REGION_HOME, "GET", MULTI_REGION + "/" + quote(name, safe="") + "/policy"
    )
    if 200 <= status < 300:
        detail["policy"] = _mrap_policy_text(text) or None
    elif not (status == 404 and _code(text) == "NoSuchMultiRegionAccessPointPolicy"):
        detail["errors"]["policy"] = _detail(text, status)

    if arn:
        status, text = rest(
            MULTI_REGION_HOME, "GET", MULTI_REGION + "/" + quote(arn, safe="") + "/routes"
        )
        if 200 <= status < 300:
            detail["routes"] = [
                {
                    "bucket": _field(route, "Bucket"),
                    "region": _field(route, "Region"),
                    "traffic": _field(route, "TrafficDialPercentage"),
                }
                for route in _children(_root(text), "Routes", "Route")
            ]
        else:
            detail["errors"]["routes"] = _detail(text, status)

    return {"ok": True, "status": 200, **detail}


def object_lambda_detail(region: str, name: str, rest) -> dict:
    """GetAccessPointForObjectLambda, its configuration, and its policy.

    The policy is read last and its absence is a state — S3 answers
    `NoSuchAccessPointPolicy` for an access point that never had one.
    """
    base = OBJECT_LAMBDA + "/" + quote(name, safe="")
    status, text = rest(region, "GET", base)
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "name": name, "error": _detail(text, status)}

    record = _first(text, "GetAccessPointForObjectLambdaResult")
    if record is None:
        record = _root(text)
    detail = {
        "section": "object-lambda",
        "name": _field(record, "Name") or name,
        "created": _field(record, "CreationDate"),
        "alias": "",
        "state": "",
        "region": region,
        "configuration": None,
        "policy": None,
        "errors": {},
    }
    for child in list(record) if record is not None else []:
        if _local(child) == "Alias":
            detail["alias"] = _field(child, "Value")
            detail["state"] = _field(child, "Status")

    status, text = rest(region, "GET", base + "/configuration")
    if 200 <= status < 300:
        configuration = _first(text, "Configuration")
        # The configuration is shown as the document S3 answers with, not as a
        # form: a Lambda's payload is arbitrary JSON and a form would flatten it.
        detail["configuration"] = (
            ElementTree.tostring(configuration, encoding="unicode")
            if configuration is not None
            else text
        )
    else:
        detail["errors"]["configuration"] = _detail(text, status)

    status, text = rest(region, "GET", base + "/policy")
    if 200 <= status < 300:
        result = _first(text, "GetAccessPointPolicyForObjectLambdaResult")
        if result is None:
            result = _root(text)
        detail["policy"] = _field(result, "Policy") or None
    elif status == 404 and _code(text) == "NoSuchAccessPointPolicy":
        detail["policy"] = None
    else:
        detail["errors"]["policy"] = _detail(text, status)

    return {"ok": True, "status": 200, **detail}


def detail(section: str, region: str, name: str, rest) -> dict:
    """One access point, read from the section that owns it."""
    if section == "multi-region":
        return multi_region_detail(name, rest)
    if section == "object-lambda":
        return object_lambda_detail(region, name, rest)
    return {
        "ok": False,
        "status": 400,
        "error": f"{section} access points have no detail view here",
    }


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


# ---------------------------------------------------------------------------
# Creating a Multi-Region access point
# ---------------------------------------------------------------------------
#
# CreateMultiRegionAccessPoint is asynchronous: S3 Control answers with a request
# token long before the access point exists, and DescribeMultiRegionAccessPointOperation
# on that token is the only account of what became of the request. The console
# describes it as soon as the create answers, because the token exists only in
# that answer — nothing here keeps it.
#
# The members are the operator's own buckets, one per Region: S3 refuses two
# buckets in one Region, and a Multi-Region access point over fewer than two
# Regions is not what its name says.


def _mrap_create_body(name: str, buckets: list[str]) -> str:
    members = "".join(
        f"<Region><Bucket>{html.escape(bucket)}</Bucket></Region>" for bucket in buckets
    )
    # AWS blocks public access on a Multi-Region access point by default, and this
    # console has no control for the four dials, so the default is sent explicitly
    # rather than left to the emulator's own default.
    public = "".join(f"<{field}>true</{field}>" for field in PUBLIC_ACCESS)
    return (
        f'<CreateMultiRegionAccessPointRequest xmlns="{CONTROL_NS}">'
        f"<Details><Name>{html.escape(name)}</Name>"
        f"<Regions>{members}</Regions>"
        f"<PublicAccessBlock>{public}</PublicAccessBlock>"
        "</Details></CreateMultiRegionAccessPointRequest>"
    )


def _mrap_form(payload: dict) -> tuple[str, list[str]]:
    """The create form's name and members, checked once, in the shape the call needs."""
    name = str(payload.get("name") or "").strip()
    if not NAME_RE.match(name) or "--" in name:
        raise ValueError(NAME_HELP)
    buckets: list[str] = []
    for entry in payload.get("buckets") or []:
        bucket = str(entry).strip()
        if bucket and bucket not in buckets:
            buckets.append(bucket)
    if len(buckets) < 2:
        raise ValueError(
            "A Multi-Region access point needs member buckets in at least two Regions."
        )
    return name, buckets


def _async_operation(element) -> dict:
    """One `AsyncOperation`, as the page shows it.

    The document repeats itself: `RequestParameters` carries what was asked for
    and `ResponseDetails` what came back, both under a `Name`, so each section is
    entered by its own child rather than searched from the root.
    """
    asked = None
    request = _child(element, "RequestParameters")
    if request is not None:
        for child in list(request):
            asked = child  # `...Request`: the operation's own element
            break
    answered = _child(element, "ResponseDetails")

    operation = {
        "token": _field(element, "RequestTokenARN"),
        "operation": _field(element, "Operation"),
        "status": _field(element, "RequestStatus"),
        "created": _field(element, "CreationTime"),
        "name": _field(asked, "Name"),
        "buckets": [
            _field(member, "Bucket")
            for member in _children(asked, "Regions", "Region")
        ],
        "results": [
            {"region": _field(result, "Name"), "status": _field(result, "RequestStatus")}
            for result in _children(answered, "Regions", "Region")
        ],
        "error": None,
    }
    failure = _child(answered, "ErrorDetails")
    if failure is not None:
        # A failed operation is the answer, not an error page: it carries the code
        # S3 refused with and the name it refused for.
        operation["error"] = {
            "code": _field(failure, "Code"),
            "message": _field(failure, "Message"),
        }
    return operation


def describe_operation(token: str, rest) -> dict:
    """DescribeMultiRegionAccessPointOperation, on the token a create answered with."""
    status, text = rest(MULTI_REGION_HOME, "GET", ASYNC + "/" + quote(token, safe=""))
    if not 200 <= status < 300:
        return {"ok": False, "status": status or 502, "error": _detail(text, status)}
    element = _first(text, "AsyncOperation")
    if element is None:
        return {
            "ok": False,
            "status": status,
            "error": "the answer was not an asynchronous operation",
        }
    return {"ok": True, "status": 200, "operation": _async_operation(element)}


def _mrap_async_body(operation: str, name: str, extra: str = "") -> str:
    """The `<Operation>Request` body Create, Delete and PutPolicy share."""
    return (
        f'<{operation}Request xmlns="{CONTROL_NS}">'
        f"<Details><Name>{html.escape(name)}</Name>{extra}</Details>"
        f"</{operation}Request>"
    )


def _mrap_answered(name: str, status: int, text: str, rest) -> dict:
    """The token an asynchronous request answered with, described.

    Create, delete and put-policy all answer 200 with nothing but a request
    token, and the token is the whole answer to "did it work?" — so the operation
    it names is read here and returned with it.
    """
    if not 200 <= status < 300:
        return {
            "ok": False,
            "status": status or 502,
            "name": name,
            "error": _detail(text, status),
        }

    token = _field(_root(text), "RequestTokenARN")
    if not token:
        return {
            "ok": False,
            "status": 502,
            "name": name,
            "error": "the request answered with no request token to describe",
        }

    described = describe_operation(token, rest)
    if not described.get("ok"):
        return {
            "ok": False,
            "status": described.get("status") or 502,
            "name": name,
            "error": (
                "the request was accepted, but the operation that says whether it "
                f"worked could not be read: {described.get('error')}"
            ),
        }

    operation = described["operation"]
    result = {
        "name": name,
        "created": operation.get("status") == "SUCCEEDED",
        "operation": operation,
    }
    if not result["created"]:
        failure = operation.get("error") or {}
        result["error"] = (
            f"{failure['code']}: {failure['message']}"
            if failure.get("code")
            else f"the operation ended {operation.get('status') or 'without a status'}"
        )
    return {"ok": True, "status": 200, **result}


def create_multi_region(payload: dict, rest) -> dict:
    """CreateMultiRegionAccessPoint, then the operation it answers with.

    `ok` says the request was submitted and its operation described; `created`
    says the operation itself ended SUCCEEDED. A failed operation is still `ok`,
    because the page has to show the status and the per-Region results S3
    reported — an empty row would read as though nothing was attempted.
    """
    try:
        name, buckets = _mrap_form(payload)
    except ValueError as exc:
        return {"ok": False, "status": 400, "error": str(exc)}

    status, text = rest(
        MULTI_REGION_HOME, "POST", ASYNC + "/create", _mrap_create_body(name, buckets)
    )
    return _mrap_answered(name, status, text, rest)


def delete_multi_region(name: str, rest) -> dict:
    """DeleteMultiRegionAccessPoint, then the operation it answers with."""
    key = str(name or "").strip()
    if not key:
        return {"ok": False, "status": 400, "error": "an access point name is required"}
    status, text = rest(
        MULTI_REGION_HOME,
        "POST",
        ASYNC + "/delete",
        _mrap_async_body("DeleteMultiRegionAccessPoint", key),
    )
    return _mrap_answered(key, status, text, rest)


def write_multi_region_policy(name: str, policy, rest) -> dict:
    """PutMultiRegionAccessPointPolicy, then the operation it answers with.

    A Multi-Region access point policy is replaced, never removed: S3 Control has
    no DeleteMultiRegionAccessPointPolicy, so an empty document is refused here
    rather than sent as a request that would quietly keep the old policy.
    """
    key = str(name or "").strip()
    if not key:
        return {"ok": False, "status": 400, "error": "an access point name is required"}
    text = "" if policy is None else str(policy).strip()
    if not text:
        return {
            "ok": False,
            "status": 400,
            "name": key,
            "error": "a Multi-Region access point policy is replaced, not removed: send a document.",
        }
    problem = _policy_problem(text)
    if problem:
        return {"ok": False, "status": 400, "name": key, "error": problem}

    status, body = rest(
        MULTI_REGION_HOME,
        "POST",
        ASYNC + "/put-policy",
        _mrap_async_body(
            "PutMultiRegionAccessPointPolicy",
            key,
            f"<Policy>{html.escape(text)}</Policy>",
        ),
    )
    return _mrap_answered(key, status, body, rest)


# A traffic dial is all-or-nothing: S3 accepts 0 (Inactive) or 100 (Active), and
# refuses an access point with every member switched off.
ROUTE_DIALS = ("0", "100")


def write_multi_region_routes(arn: str, routes: list, rest) -> dict:
    """SubmitMultiRegionAccessPointRoutes, addressed by the access point's ARN.

    This one is synchronous: S3 answers 200 with no token, so there is no
    operation to describe — the dials are read back from the access point.
    """
    key = str(arn or "").strip()
    if not key.startswith("arn:"):
        return {
            "ok": False,
            "status": 400,
            "error": "the routes are addressed by the access point's ARN",
        }

    updates = []
    for route in routes or []:
        bucket = str((route or {}).get("bucket") or "").strip()
        if not bucket:
            continue
        dial = str((route or {}).get("traffic") or "").strip()
        if dial not in ROUTE_DIALS:
            return {
                "ok": False,
                "status": 400,
                "arn": key,
                "error": "a traffic dial is 0 (Inactive) or 100 (Active)",
            }
        updates.append(
            f"<Route><Bucket>{html.escape(bucket)}</Bucket>"
            f"<TrafficDialPercentage>{dial}</TrafficDialPercentage></Route>"
        )
    if not updates:
        return {"ok": False, "status": 400, "arn": key, "error": "no routes to submit"}

    body = (
        f'<MultiRegionAccessPointRouteRequest xmlns="{CONTROL_NS}">'
        f"<RouteUpdates>{''.join(updates)}</RouteUpdates>"
        "</MultiRegionAccessPointRouteRequest>"
    )
    status, text = rest(
        MULTI_REGION_HOME, "PATCH", MULTI_REGION + "/" + quote(key, safe="") + "/routes", body
    )
    if 200 <= status < 300:
        return {"ok": True, "status": status, "arn": key}
    return {"ok": False, "status": status or 502, "arn": key, "error": _detail(text, status)}
