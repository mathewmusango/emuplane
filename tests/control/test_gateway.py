"""S3 through the gateway — the surface `aws cli` and Terraform actually hit, as SigV4-shaped HTTP."""

from __future__ import annotations

from conftest import ACCOUNT, OTHER, s3

LOCATION = (
    b'<CreateBucketConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    b"<LocationConstraint>eu-west-1</LocationConstraint>"
    b"</CreateBucketConfiguration>"
)


def test_a_create_is_forwarded_and_the_name_is_claimed(control, gateway):
    status, _headers, body = s3(gateway, "PUT", "/gw-created-bucket")
    assert status == 200, body

    claim = control.REGISTRY.buckets.get("gw-created-bucket")
    assert claim is not None, "the gateway must claim the name it creates"
    assert claim["account_id"] == ACCOUNT
    assert claim["region"] == "us-east-1"


def test_a_name_held_by_another_account_is_refused(control, gateway):
    assert s3(gateway, "PUT", "/gw-shared-name", account=OTHER)[0] == 200

    status, _headers, body = s3(gateway, "PUT", "/gw-shared-name", account=ACCOUNT)
    assert status == 409
    assert b"BucketAlreadyExists" in body
    assert control.REGISTRY.buckets["gw-shared-name"]["account_id"] == OTHER


def test_a_region_outside_the_catalogue_is_refused(control, gateway):
    status, _headers, body = s3(gateway, "PUT", "/gw-mars-bucket", region="mars-north-1")
    assert status == 403
    assert b"not enabled" in body
    assert "gw-mars-bucket" not in control.REGISTRY.buckets


def test_a_known_region_is_enabled_on_first_use(control, gateway):
    account = control.ACCOUNTS.accounts[ACCOUNT]
    assert "eu-west-1" not in control.ACCOUNTS.regions_of(account)

    status, _headers, body = s3(
        gateway, "PUT", "/gw-eu-bucket", region="eu-west-1", body=LOCATION
    )
    assert status == 200, body
    assert "eu-west-1" in control.ACCOUNTS.regions_of(control.ACCOUNTS.accounts[ACCOUNT])


def test_a_request_signed_for_another_region_answers_301(control, gateway):
    assert s3(gateway, "PUT", "/gw-301-bucket")[0] == 200

    status, headers, _body = s3(
        gateway, "HEAD", "/gw-301-bucket/anything", region="us-west-2"
    )
    assert status == 301
    assert headers.get("x-amz-bucket-region") == "us-east-1"


def test_a_delete_releases_the_name(control, gateway):
    assert s3(gateway, "PUT", "/gw-release-bucket")[0] == 200
    assert "gw-release-bucket" in control.REGISTRY.buckets

    status, _headers, body = s3(gateway, "DELETE", "/gw-release-bucket")
    assert status in (200, 204), body
    assert "gw-release-bucket" not in control.REGISTRY.buckets


def test_a_bucket_under_mfa_delete_refuses_a_delete(control, gateway):
    """No standard tool can put a code on DeleteBucket, so the bucket waits until the flag is off."""
    assert s3(gateway, "PUT", "/gw-mfa-bucket")[0] == 200
    control.REGISTRY.set_flag("gw-mfa-bucket", "mfa_delete", "Enabled")

    status, _headers, body = s3(gateway, "DELETE", "/gw-mfa-bucket")
    assert status == 403
    assert b"turn it off before deleting the bucket" in body

    control.REGISTRY.set_flag("gw-mfa-bucket", "mfa_delete", "")
    assert s3(gateway, "DELETE", "/gw-mfa-bucket")[0] in (200, 204)


def test_an_unknown_access_key_does_not_become_an_account(control, gateway):
    """The 12-digit account is the root; an unknown access key resolves to no account rather than to itself."""
    key = "AKIDEXAMPLE000000000"
    assert not control.ACCOUNTS.account_for_key(key)

    status, _headers, _body = s3(gateway, "PUT", "/gw-unknown-key", account=key)
    claim = control.REGISTRY.buckets.get("gw-unknown-key") or {}
    assert claim.get("account_id") != key
