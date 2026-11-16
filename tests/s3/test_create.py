"""Creating a bucket with every option the console's create page offers.

Each case runs `control/buckets.create` — the real sequence the page triggers —
with the control's own signed client pointed at a stand-in server that hands the
request to the emulator's `handle_request`. The documents therefore go over a
socket, through the signing-region check and the emulator's real handlers, and
the assertions read the settings back *through the API* rather than out of a
module dict.

Nothing is deleted: the buckets stay in this process's copy of the emulator.
"""

from __future__ import annotations

import itertools
from xml.etree import ElementTree

import pytest

import buckets

ACCOUNT = "344381301567"

REGIONS = ("us-east-1", "eu-west-1")
OWNERSHIP = ("BucketOwnerEnforced", "BucketOwnerPreferred")
PUBLIC = (
    ("all", {name: True for name in buckets.PUBLIC_ACCESS}),
    (
        "custom",
        {name: True for name in buckets.PUBLIC_ACCESS} | {"BlockPublicPolicy": False},
    ),
    ("omitted", None),
)
VERSIONING = (False, True)
TAGS = (
    ("none", []),
    ("two", [{"Key": "team", "Value": "platform"}, {"Key": "env", "Value": "lab"}]),
)
ENCRYPTION = ("AES256", "aws:kms", "aws:kms:dsse")
LOCK = (False, True)
NAMESPACE = ("global", "regional")


# --------------------------------------------------------------------------
# reading a bucket's settings back from the wire


def _payload(index, combination) -> dict:
    region, ownership, public, versioning, tags, encryption, lock, namespace = combination
    return {
        "account": ACCOUNT,
        "region": region,
        "bucket": f"mx-{index:04d}",
        "namespace": namespace,
        "ownership": ownership,
        "block_public_access": public[1],
        "versioning": versioning,
        "tags": tags[1],
        "encryption": encryption,
        "bucket_key": encryption.startswith("aws:kms"),
        "object_lock": lock,
    }


def _combinations():
    for index, combination in enumerate(
        itertools.product(
            REGIONS, OWNERSHIP, PUBLIC, VERSIONING, TAGS, ENCRYPTION, LOCK, NAMESPACE
        )
    ):
        region, ownership, public, versioning, tags, encryption, lock, namespace = combination
        identify = "-".join(
            [
                region,
                ownership.removeprefix("BucketOwner"),
                public[0],
                f"v{int(versioning)}",
                tags[0],
                encryption,
                f"lock{int(lock)}",
                namespace,
            ]
        )
        yield pytest.param(_payload(index, combination), combination, id=identify)


def _local(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _field(xml: str, name: str) -> str | None:
    """The text of the first `name` element anywhere in a document."""
    for element in ElementTree.fromstring(xml).iter():
        if _local(element) == name:
            return element.text
    return None


def _tags(xml: str) -> dict:
    found = {}
    for element in ElementTree.fromstring(xml).iter():
        if _local(element) != "Tag":
            continue
        pair = {_local(child): child.text for child in element}
        found[pair.get("Key")] = pair.get("Value")
    return found


def _blocks(xml: str) -> dict:
    return {_local(child): child.text == "true" for child in list(ElementTree.fromstring(xml))}


# --------------------------------------------------------------------------


@pytest.mark.parametrize("payload, expected", list(_combinations()))
def test_every_option_combination(payload, expected, s3):
    region, ownership, public, versioning, tags, encryption, lock, namespace = expected
    client = s3(ACCOUNT, region)

    result = buckets.create(region, payload, client)
    assert result["ok"], result.get("error")

    name = result["bucket"]
    assert name == buckets.resolve_name(payload, region)[0]
    if namespace == "regional":
        assert name == f"{payload['bucket']}.{ACCOUNT}-{region}-an"
    else:
        assert name == payload["bucket"]

    # The bucket exists where it was asked for.
    status, body = client("GET", f"/{name}?location")
    assert status == 200
    assert (_field(body, "LocationConstraint") or "") == (
        "" if region == "us-east-1" else region
    )

    # Object Ownership, applied through the create-time header.
    status, body = client("GET", f"/{name}?ownershipControls")
    assert status == 200
    assert _field(body, "ObjectOwnership") == ownership

    # Versioning — and Object Lock, which carries it.
    status, body = client("GET", f"/{name}?versioning")
    assert status == 200
    assert _field(body, "Status") == ("Enabled" if versioning or lock else None)

    status, body = client("GET", f"/{name}?object-lock")
    if lock:
        assert status == 200
        assert _field(body, "ObjectLockEnabled") == "Enabled"
    else:
        assert status == 404

    # Block Public Access: there is no configuration when none was asked for.
    status, body = client("GET", f"/{name}?publicAccessBlock")
    if public[1] is None:
        assert status == 404
    else:
        assert status == 200
        assert _blocks(body) == public[1]

    status, body = client("GET", f"/{name}?tagging")
    if tags[1]:
        assert status == 200
        assert _tags(body) == {tag["Key"]: tag["Value"] for tag in tags[1]}
    else:
        assert status == 404

    status, body = client("GET", f"/{name}?encryption")
    assert status == 200
    assert _field(body, "SSEAlgorithm") == encryption
    # A bucket key describes a KMS-encrypted bucket, so SSE-S3 must not carry one.
    assert (_field(body, "BucketKeyEnabled") == "true") == encryption.startswith("aws:kms")


def test_the_regional_namespace_needs_the_account():
    """The suffix is the account and the region; without them it composes a name
    that only looks regional."""
    payload = {"account": "", "bucket": "test", "namespace": "regional"}
    assert buckets.resolve_name(payload, "us-east-1") == (
        "",
        "The Account Regional namespace needs the 12-digit account id.",
    )
    payload["account"] = "11111111111"
    assert buckets.resolve_name(payload, "us-east-1")[1]


def test_tags_with_xml_characters_round_trip(s3):
    """A tag is escaped on the way out and comes back as typed."""
    client = s3(ACCOUNT, "us-east-1")
    result = buckets.create(
        "us-east-1",
        {
            "account": ACCOUNT,
            "bucket": "escaped-tags-bucket",
            "tags": [{"Key": "team<&>", "Value": "a & b <c>"}],
        },
        client,
    )
    assert result["ok"], result.get("error")

    status, body = client("GET", "/escaped-tags-bucket?tagging")
    assert status == 200
    assert _tags(body) == {"team<&>": "a & b <c>"}


def test_the_emulator_checks_the_signing_region(s3):
    """The check that refused the console's create before it named its region."""
    client = s3(ACCOUNT, "us-west-2")
    status, body = client("PUT", "/wrong-region-bucket", buckets.location_constraint("eu-west-1"))
    assert status == 400
    assert "IllegalLocationConstraintException" in body


def test_regional_namespace_appends_the_suffix(s3):
    payload = {
        "account": ACCOUNT,
        "region": "us-east-1",
        "bucket": "test",
        "namespace": "regional",
    }
    assert buckets.resolve_name(payload, "us-east-1")[0] == f"test.{ACCOUNT}-us-east-1-an"

    result = buckets.create("us-east-1", payload, s3(ACCOUNT, "us-east-1"))
    assert result["ok"], result.get("error")
    assert result["bucket"] == f"test.{ACCOUNT}-us-east-1-an"

    status, _body = s3(ACCOUNT, "us-east-1")("GET", f"/test.{ACCOUNT}-us-east-1-an?location")
    assert status == 200


def test_the_suffix_is_not_appended_twice():
    """A retry, or a pasted full name, still means one bucket."""
    payload = {
        "account": ACCOUNT,
        "bucket": f"twice.{ACCOUNT}-eu-west-1-an",
        "namespace": "regional",
    }
    assert buckets.resolve_name(payload, "eu-west-1") == (
        f"twice.{ACCOUNT}-eu-west-1-an",
        "",
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"bucket": ""},
        {"bucket": "ab"},
        {"bucket": "UPPER"},
        {"bucket": "dot..dot"},
        {"bucket": "192.168.1.1"},
        {"bucket": "-leading"},
        {"namespace": "regional", "bucket": "x" * 40},
    ],
)
def test_names_are_refused(payload):
    payload.update(account=ACCOUNT)
    _, problem = buckets.resolve_name(payload, "us-east-1")
    assert problem


@pytest.mark.parametrize(
    "options, message",
    [
        ({"encryption": "ROT13"}, "unknown encryption"),
        ({"ownership": "BucketOwner"}, "unknown object ownership"),
        ({"tags": [{"Key": "", "Value": "x"}]}, "every tag needs a key"),
        ({"tags": [{"Key": f"k{index}", "Value": "v"} for index in range(51)]}, "at most 50"),
    ],
)
def test_options_outside_the_form_are_refused(options, message):
    result = buckets.create(
        "us-east-1",
        {"account": ACCOUNT, "bucket": "refused-bucket"} | options,
        lambda *args, **kwargs: (200, ""),
    )
    assert result["ok"] is False
    assert result["status"] == 400
    assert message in result["error"]


def test_a_follow_up_failure_still_reports_the_bucket_created():
    def client(method, path, body="", headers=None):
        if path.endswith("?tagging"):
            return 400, "<Error><Code>InvalidTag</Code><Message>bad tag</Message></Error>"
        return 200, ""

    result = buckets.create(
        "us-east-1",
        {"account": ACCOUNT, "bucket": "partial-bucket", "tags": [{"Key": "a", "Value": "b"}]},
        client,
    )
    assert result["ok"] is False
    assert result["created"] is True
    assert "Tags failed" in result["error"]
    assert "bad tag" in result["error"]


def test_a_bucket_reads_back_as_the_copy_settings_form_shows_it(s3):
    """The create page's copy-settings reads the subresources it writes."""
    client = s3(ACCOUNT, "us-east-1")
    created = buckets.create(
        "us-east-1",
        {
            "account": ACCOUNT,
            "bucket": "copy-source-bucket",
            "ownership": "BucketOwnerPreferred",
            "block_public_access": {
                **{name: True for name in buckets.PUBLIC_ACCESS},
                "BlockPublicPolicy": False,
            },
            "versioning": True,
            "tags": [{"Key": "team", "Value": "platform"}],
            "encryption": "aws:kms",
            "bucket_key": True,
        },
        client,
    )
    assert created["ok"], created.get("error")

    read = buckets.read_settings(
        "copy-source-bucket", lambda method, path: client(method, path)
    )
    settings = read["settings"]
    assert settings["ownership"] == "BucketOwnerPreferred"
    assert settings["block_public_access"]["BlockPublicPolicy"] is False
    assert settings["block_public_access"]["BlockPublicAcls"] is True
    assert settings["versioning"] is True
    assert settings["tags"] == [{"Key": "team", "Value": "platform"}]
    assert settings["encryption"] == "aws:kms"
    assert settings["bucket_key"] is True
    assert settings["object_lock"] is False


def test_a_bucket_with_no_settings_reads_back_the_form_defaults(s3):
    client = s3(ACCOUNT, "us-east-1")
    assert buckets.create(
        "us-east-1", {"account": ACCOUNT, "bucket": "plain-settings-bucket"}, client
    )["ok"]

    read = buckets.read_settings(
        "plain-settings-bucket", lambda method, path: client(method, path)
    )
    settings = read["settings"]
    assert settings["ownership"] == "BucketOwnerEnforced"
    assert settings["block_public_access"] == {
        name: False for name in buckets.PUBLIC_ACCESS
    }
    assert settings["versioning"] is False
    assert settings["tags"] == []
    assert settings["encryption"] == "AES256"
