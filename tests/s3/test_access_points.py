"""Access points over the wire: create, list, policy, delete, with the `x-amz-account-id` header S3 Control needs."""

from __future__ import annotations

import accesspoints
import buckets
import signed

ACCOUNT = "344381301567"


def _client(endpoint, region="us-east-1"):
    def rest(target_region, method, path, body=""):
        return signed.request(
            endpoint,
            "s3",
            ACCOUNT,
            target_region or region,
            method,
            path,
            body,
            {"x-amz-account-id": ACCOUNT},
        )

    return rest


def _bucket(rest, name, region="us-east-1"):
    created = buckets.create(
        region,
        {"account": ACCOUNT, "bucket": name, "block_public_access": None},
        lambda method, path, body="", headers=None: rest(region, method, path, body),
    )
    assert created["ok"], created.get("error")


def _create(rest, name, bucket, region="us-east-1", **extra):
    return accesspoints.create(
        region, {"name": name, "bucket": bucket, **extra}, rest
    )


def test_create_list_and_open_an_access_point(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-wire-bucket")

    made = _create(rest, "wire-point", "ap-wire-bucket")
    assert made["ok"], made.get("error")
    assert made["arn"] == f"arn:aws:s3:us-east-1:{ACCOUNT}:accesspoint/wire-point"
    assert made["alias"].endswith("-s3alias")

    listed = accesspoints.list_general("us-east-1", rest)
    assert listed["ok"], listed.get("error")
    rows = {row["name"]: row for row in listed["access_points"]}
    assert set(rows) == {"wire-point"}
    row = rows["wire-point"]
    assert row["bucket"] == "ap-wire-bucket"
    assert row["network_origin"] == "Internet"
    assert row["vpc_id"] == ""
    assert row["arn"] == made["arn"]
    assert row["created"]  # the detail call filled it


def test_a_vpc_access_point_reports_its_network_and_vpc(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-vpc-bucket")

    made = _create(
        rest, "vpc-point", "ap-vpc-bucket", vpc_id="vpc-0123456789abcdef0"
    )
    assert made["ok"], made.get("error")

    row = next(
        item
        for item in accesspoints.list_general("us-east-1", rest)["access_points"]
        if item["name"] == "vpc-point"
    )
    assert row["network_origin"] == "VPC"
    assert row["vpc_id"] == "vpc-0123456789abcdef0"


def test_a_listing_can_narrow_to_one_bucket(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-filter-one")
    _bucket(rest, "ap-filter-two")
    assert _create(rest, "filter-one-point", "ap-filter-one")["ok"]
    assert _create(rest, "filter-two-point", "ap-filter-two")["ok"]

    listed = accesspoints.list_general("us-east-1", rest, bucket="ap-filter-one")
    assert listed["ok"], listed.get("error")
    assert [row["name"] for row in listed["access_points"]] == ["filter-one-point"]


def test_access_points_are_scoped_to_their_region(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-region-bucket")

    assert _create(rest, "region-point", "ap-region-bucket")["ok"]

    here = accesspoints.list_general("us-east-1", rest)
    assert "region-point" in [row["name"] for row in here["access_points"]]
    elsewhere = accesspoints.list_general("us-west-2", rest)
    assert elsewhere["ok"], elsewhere.get("error")
    assert "region-point" not in [row["name"] for row in elsewhere["access_points"]]


def test_a_duplicate_name_is_refused_with_the_api_sentence(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-duplicate-bucket")
    assert _create(rest, "duplicate-point", "ap-duplicate-bucket")["ok"]

    again = _create(rest, "duplicate-point", "ap-duplicate-bucket")
    assert again["ok"] is False
    assert again["status"] == 409
    assert "AccessPointAlreadyOwnedByYou" in again["error"]


def test_a_bucket_in_another_region_is_refused(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-cross-region")

    refused = _create(rest, "cross-region-point", "ap-cross-region", region="us-west-2")
    assert refused["ok"] is False
    assert "same region" in refused["error"]


def test_a_missing_bucket_is_refused(s3_endpoint):
    rest = _client(s3_endpoint)

    refused = _create(rest, "nowhere-point", "ap-no-such-bucket")
    assert refused["ok"] is False
    assert "NoSuchBucket" in refused["error"]


def test_the_form_is_checked_before_the_round_trip(s3_endpoint):
    rest = _client(s3_endpoint)

    bad_name = _create(rest, "Bad_Name", "whatever")
    assert bad_name["ok"] is False and "lowercase" in bad_name["error"]

    no_bucket = _create(rest, "no-bucket-point", "")
    assert no_bucket["ok"] is False and "Choose the bucket" in no_bucket["error"]

    bad_vpc = _create(rest, "bad-vpc-point", "whatever", vpc_id="not-a-vpc")
    assert bad_vpc["ok"] is False and "vpc-" in bad_vpc["error"]


def test_a_policy_round_trips_and_can_be_removed(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-policy-bucket")
    assert _create(rest, "policy-point", "ap-policy-bucket")["ok"]

    empty = accesspoints.read_policy("us-east-1", "policy-point", rest)
    assert empty["ok"], empty.get("error")
    assert empty["policy"] is None

    document = (
        '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*",'
        '"Action":"s3:GetObject","Resource":"*"}]}'
    )
    written = accesspoints.write_policy("us-east-1", "policy-point", document, rest)
    assert written["ok"], written.get("error")

    read = accesspoints.read_policy("us-east-1", "policy-point", rest)
    assert read["ok"], read.get("error")
    assert "s3:GetObject" in read["policy"]

    removed = accesspoints.write_policy("us-east-1", "policy-point", None, rest)
    assert removed["ok"], removed.get("error")
    assert accesspoints.read_policy("us-east-1", "policy-point", rest)["policy"] is None


def test_a_policy_must_be_a_json_document(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-policy-form-bucket")
    assert _create(rest, "policy-form-point", "ap-policy-form-bucket")["ok"]

    broken = accesspoints.write_policy("us-east-1", "policy-form-point", "{not json", rest)
    assert broken["ok"] is False and "not JSON" in broken["error"]

    no_statement = accesspoints.write_policy(
        "us-east-1", "policy-form-point", '{"Version":"2012-10-17"}', rest
    )
    assert no_statement["ok"] is False and "Statement" in no_statement["error"]


def test_a_policy_sent_with_the_create_form_is_applied(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-create-policy-bucket")

    document = '{"Statement":[{"Effect":"Allow","Action":"s3:GetObject","Resource":"*"}]}'
    made = _create(
        rest, "create-policy-point", "ap-create-policy-bucket", policy=document
    )
    assert made["ok"], made.get("error")

    read = accesspoints.read_policy("us-east-1", "create-policy-point", rest)
    assert read["policy"] == document


def test_delete_removes_the_access_point_and_repeats_as_not_found(s3_endpoint):
    rest = _client(s3_endpoint)
    _bucket(rest, "ap-delete-bucket")
    assert _create(rest, "delete-point", "ap-delete-bucket")["ok"]

    removed = accesspoints.delete("us-east-1", "delete-point", rest)
    assert removed["ok"], removed.get("error")

    listed = accesspoints.list_general("us-east-1", rest)
    assert "delete-point" not in [row["name"] for row in listed["access_points"]]

    again = accesspoints.delete("us-east-1", "delete-point", rest)
    assert again["ok"] is False
    assert "NoSuchAccessPoint" in again["error"]


def test_the_multi_region_listing_is_served_from_its_own_region(s3_endpoint):
    rest = _client(s3_endpoint)

    listed = accesspoints.list_multi_region(rest)
    assert listed["ok"], listed.get("error")
    assert listed["region"] == "us-west-2"
    assert listed["access_points"] == []


def test_the_object_lambda_listing_answers_for_this_region(s3_endpoint):
    rest = _client(s3_endpoint)

    listed = accesspoints.list_object_lambda("us-east-1", rest)
    assert listed["ok"], listed.get("error")
    assert listed["access_points"] == []


def test_an_unknown_section_is_refused(s3_endpoint):
    refused = accesspoints.listing("directory", "us-east-1", _client(s3_endpoint))
    assert refused["ok"] is False
    assert "unknown access point section" in refused["error"]


def test_a_document_that_declares_entities_is_refused_before_expansion():
    """CodeQL's XML bomb: the DTD is refused, and the console hears the document is not XML."""
    # Expat expands this one happily, so the refusal is the guard's and not the runtime's.
    small = '<!DOCTYPE x [<!ENTITY a "aaa">]><x>&a;</x>'
    assert accesspoints._root(small) is None
    assert accesspoints._configuration_problem(small) == "the configuration is not XML"

    bomb = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;">]>'
        "<lolz>&lol1;</lolz>"
    )
    assert accesspoints._root(bomb) is None
    assert accesspoints._configuration_problem(bomb) == "the configuration is not XML"

    plain = (
        "<Configuration><SupportingAccessPoint>arn:aws:s3:us-east-1:1:accesspoint/ap"
        "</SupportingAccessPoint><FunctionArn>arn:aws:lambda:us-east-1:1:function:f"
        "</FunctionArn><Actions><Action>GetObject</Action></Actions></Configuration>"
    )
    assert accesspoints._configuration_problem(plain) == ""
