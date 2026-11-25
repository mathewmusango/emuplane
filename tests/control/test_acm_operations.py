"""ACM on the wire: every advertised operation, driven through the JSON protocol.

A certificate created here is left in place; DeleteCertificate mints one of its own to
remove. Every create is proven by a read, never undone. A sweep against the lab re-runs
over the certificates an earlier sweep left and over any an EC2 Verified Access run
created, so a certificate is found by its domain, never by position or count.

ImportCertificate is driven with a synthetic PEM body and a placeholder private key on
purpose: `_import_certificate` validates only that `PrivateKey` is non-empty and decodes
the PEM fields, and parses no X.509. No key material is needed, so no generation
dependency is involved.
"""

from __future__ import annotations

import json
import uuid

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "acm."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

# The emulator stores these verbatim and returns them from GetCertificate; it parses no
# X.509, and the private key is only checked for emptiness.
CERT_PEM = (
    "-----BEGIN CERTIFICATE-----\n"
    "AQIDBAUGBwgJCgsMDQ4PEA==\n"
    "-----END CERTIFICATE-----\n"
)
CHAIN_PEM = (
    "-----BEGIN CERTIFICATE-----\n"
    "CgsMDQ4PEA==\n"
    "-----END CERTIFICATE-----\n"
)
PLACEHOLDER_KEY = "placeholder-key-the-emulator-never-parses"

# One stable ARN: a re-import replaces the same certificate, so a sweep does not accumulate them.
IMPORT_ARN = f"arn:aws:acm:{REGION}:{ACCOUNT}:certificate/ops-acm-import"


def domain(label: str) -> str:
    return f"ops-acm-{label}.emuplane.test"


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "acm", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def requested(endpoint, name: str, **params) -> str:
    """One RequestCertificate, and the ARN it answered; a create has no duplicate code here."""
    return ok(endpoint, "RequestCertificate", DomainName=name, **params)["CertificateArn"]


def certificate(endpoint, label: str) -> str:
    """The certificate for `label`'s domain: the one an earlier sweep left, or a new one."""
    wanted = domain(label)
    for item in ok(endpoint, "ListCertificates")["CertificateSummaryList"]:
        if item["DomainName"] == wanted:
            return item["CertificateArn"]
    return requested(endpoint, wanted)


def imported(endpoint) -> str:
    """Import the placeholder pair into the module's stable ARN; a re-import replaces it."""
    return ok(
        endpoint,
        "ImportCertificate",
        CertificateArn=IMPORT_ARN,
        Certificate=CERT_PEM,
        CertificateChain=CHAIN_PEM,
        PrivateKey=PLACEHOLDER_KEY,
    )["CertificateArn"]


def test_request_certificate_is_read_back_by_describe_and_list(s3_endpoint):
    name = f"ops-acm-created-{uuid.uuid4().hex[:8]}.emuplane.test"
    arn = requested(
        s3_endpoint,
        name,
        SubjectAlternativeNames=[f"www.{name}"],
        Tags=[{"Key": "origin", "Value": "request"}],
    )
    described = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)["Certificate"]
    assert described["DomainName"] == name
    assert described["SubjectAlternativeNames"] == [name, f"www.{name}"]
    assert described["Status"] == "ISSUED"
    assert {"Key": "origin", "Value": "request"} in ok(
        s3_endpoint, "ListTagsForCertificate", CertificateArn=arn
    )["Tags"]
    listed = ok(s3_endpoint, "ListCertificates")["CertificateSummaryList"]
    assert arn in [item["CertificateArn"] for item in listed]


def test_request_certificate_validates_a_wildcard_through_its_base_domain(s3_endpoint):
    base = f"ops-acm-wildcard-{uuid.uuid4().hex[:8]}.emuplane.test"
    arn = requested(s3_endpoint, f"*.{base}", SubjectAlternativeNames=[base])
    options = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)[
        "Certificate"
    ]["DomainValidationOptions"]
    assert [option["DomainName"] for option in options] == [f"*.{base}", base]
    assert {option["ResourceRecord"]["Name"] for option in options} == {
        f"_acme-challenge.{base}."
    }
    assert len({option["ResourceRecord"]["Value"] for option in options}) == 1


def test_describe_certificate_reports_the_certificate_shape(s3_endpoint):
    arn = certificate(s3_endpoint, "describe")
    described = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)["Certificate"]
    assert described["CertificateArn"] == arn
    assert described["DomainName"] == domain("describe")
    assert described["Status"] == "ISSUED"
    assert described["Type"] == "AMAZON_ISSUED"
    assert described["KeyAlgorithm"] == "RSA_2048"
    assert described["SignatureAlgorithm"] == "SHA256WITHRSA"
    assert described["InUseBy"] == []
    assert isinstance(described["CreatedAt"], (int, float))
    assert described["NotAfter"] > described["NotBefore"]
    assert described["Options"] == {
        "CertificateTransparencyLoggingPreference": "ENABLED",
        "Export": "DISABLED",
    }
    record = described["DomainValidationOptions"][0]
    assert record["ValidationMethod"] == "DNS"
    assert record["ValidationStatus"] == "SUCCESS"
    assert record["ResourceRecord"]["Type"] == "CNAME"
    assert record["ResourceRecord"]["Name"] == f"_acme-challenge.{domain('describe')}."


def test_describe_certificate_answers_not_found_for_an_unknown_arn(s3_endpoint):
    missing = f"arn:aws:acm:{REGION}:{ACCOUNT}:certificate/{uuid.uuid4()}"
    status, text = call(s3_endpoint, "DescribeCertificate", CertificateArn=missing)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_list_certificates_summarises_the_certificate_it_created(s3_endpoint):
    arn = certificate(s3_endpoint, "list")
    listed = ok(s3_endpoint, "ListCertificates")["CertificateSummaryList"]
    summary = next(item for item in listed if item["CertificateArn"] == arn)
    assert summary["DomainName"] == domain("list")
    assert summary["Status"] == "ISSUED"


def test_list_certificates_filters_by_status(s3_endpoint):
    arn = certificate(s3_endpoint, "status")
    issued = ok(s3_endpoint, "ListCertificates", CertificateStatuses=["ISSUED"])
    assert arn in [item["CertificateArn"] for item in issued["CertificateSummaryList"]]
    expired = ok(s3_endpoint, "ListCertificates", CertificateStatuses=["EXPIRED"])
    assert expired["CertificateSummaryList"] == []


def test_list_certificates_pages_with_max_items(s3_endpoint):
    wanted = {certificate(s3_endpoint, label) for label in ("page-a", "page-b", "page-c")}
    first = ok(s3_endpoint, "ListCertificates", MaxItems=2)
    assert len(first["CertificateSummaryList"]) == 2
    assert "NextToken" in first
    second = ok(s3_endpoint, "ListCertificates", MaxItems=2, NextToken=first["NextToken"])
    assert second["CertificateSummaryList"]
    first_arns = {item["CertificateArn"] for item in first["CertificateSummaryList"]}
    second_arns = {item["CertificateArn"] for item in second["CertificateSummaryList"]}
    assert not first_arns & second_arns
    everything = {
        item["CertificateArn"]
        for item in ok(s3_endpoint, "ListCertificates")["CertificateSummaryList"]
    }
    assert wanted <= everything


def test_delete_certificate_removes_the_certificate_it_created(s3_endpoint):
    name = f"ops-acm-delete-{uuid.uuid4().hex[:8]}.emuplane.test"
    arn = requested(s3_endpoint, name)
    ok(s3_endpoint, "DeleteCertificate", CertificateArn=arn)
    status, text = call(s3_endpoint, "DescribeCertificate", CertificateArn=arn)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text
    listed = ok(s3_endpoint, "ListCertificates")["CertificateSummaryList"]
    assert arn not in [item["CertificateArn"] for item in listed]


def test_get_certificate_returns_the_pem_body_and_never_the_key(s3_endpoint):
    arn = certificate(s3_endpoint, "get")
    got = ok(s3_endpoint, "GetCertificate", CertificateArn=arn)
    assert got["Certificate"].startswith("-----BEGIN CERTIFICATE-----")
    assert got["Certificate"].rstrip().endswith("-----END CERTIFICATE-----")
    assert got["CertificateChain"] == ""
    # The private key is only reachable through ExportCertificate, which the emulator does not model.
    assert "PrivateKey" not in got


def test_import_certificate_stores_the_pem_it_was_given(s3_endpoint):
    arn = imported(s3_endpoint)
    assert arn == IMPORT_ARN
    described = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)["Certificate"]
    assert described["Type"] == "IMPORTED"
    assert described["Status"] == "ISSUED"
    assert described["DomainValidationOptions"] == []
    got = ok(s3_endpoint, "GetCertificate", CertificateArn=arn)
    assert got["Certificate"] == CERT_PEM
    assert got["CertificateChain"] == CHAIN_PEM


def test_import_certificate_requires_a_private_key(s3_endpoint):
    status, text = call(
        s3_endpoint, "ImportCertificate", CertificateArn=IMPORT_ARN, Certificate=CERT_PEM
    )
    assert status == 400, text[:300]
    assert "ValidationException" in text
    assert "privateKey" in text


def test_import_certificate_rejects_an_empty_private_key(s3_endpoint):
    status, text = call(
        s3_endpoint,
        "ImportCertificate",
        CertificateArn=IMPORT_ARN,
        Certificate=CERT_PEM,
        PrivateKey="",
    )
    assert status == 400, text[:300]
    assert "ValidationException" in text
    assert "privateKey" in text


def test_add_tags_to_certificate_is_read_back_by_list_tags(s3_endpoint):
    arn = certificate(s3_endpoint, "tags")
    ok(
        s3_endpoint,
        "AddTagsToCertificate",
        CertificateArn=arn,
        Tags=[{"Key": "team", "Value": "platform"}],
    )
    tags = ok(s3_endpoint, "ListTagsForCertificate", CertificateArn=arn)["Tags"]
    assert {"Key": "team", "Value": "platform"} in tags


def test_add_tags_to_certificate_replaces_an_existing_key(s3_endpoint):
    arn = certificate(s3_endpoint, "tags")
    ok(
        s3_endpoint,
        "AddTagsToCertificate",
        CertificateArn=arn,
        Tags=[{"Key": "team", "Value": "platform"}],
    )
    ok(
        s3_endpoint,
        "AddTagsToCertificate",
        CertificateArn=arn,
        Tags=[{"Key": "team", "Value": "security"}],
    )
    tags = ok(s3_endpoint, "ListTagsForCertificate", CertificateArn=arn)["Tags"]
    assert {tag["Key"]: tag["Value"] for tag in tags}["team"] == "security"


def test_remove_tags_from_certificate_leaves_the_other_keys(s3_endpoint):
    arn = certificate(s3_endpoint, "tags")
    ok(
        s3_endpoint,
        "AddTagsToCertificate",
        CertificateArn=arn,
        Tags=[{"Key": "keep", "Value": "1"}, {"Key": "drop", "Value": "2"}],
    )
    ok(
        s3_endpoint,
        "RemoveTagsFromCertificate",
        CertificateArn=arn,
        Tags=[{"Key": "drop"}],
    )
    keys = [tag["Key"] for tag in ok(
        s3_endpoint, "ListTagsForCertificate", CertificateArn=arn
    )["Tags"]]
    assert "drop" not in keys
    assert "keep" in keys


def test_list_tags_for_certificate_reports_the_tag_set(s3_endpoint):
    arn = certificate(s3_endpoint, "tag-list")
    ok(
        s3_endpoint,
        "AddTagsToCertificate",
        CertificateArn=arn,
        Tags=[{"Key": "owner", "Value": "ops"}],
    )
    assert ok(s3_endpoint, "ListTagsForCertificate", CertificateArn=arn)["Tags"] == [
        {"Key": "owner", "Value": "ops"}
    ]


def test_update_certificate_options_reads_back_the_logging_preference(s3_endpoint):
    arn = certificate(s3_endpoint, "options")
    ok(
        s3_endpoint,
        "UpdateCertificateOptions",
        CertificateArn=arn,
        Options={"CertificateTransparencyLoggingPreference": "DISABLED"},
    )
    described = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)["Certificate"]
    assert described["Options"]["CertificateTransparencyLoggingPreference"] == "DISABLED"
    ok(
        s3_endpoint,
        "UpdateCertificateOptions",
        CertificateArn=arn,
        Options={"CertificateTransparencyLoggingPreference": "ENABLED"},
    )
    described = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)["Certificate"]
    assert described["Options"]["CertificateTransparencyLoggingPreference"] == "ENABLED"


def test_update_certificate_options_refuses_to_change_export(s3_endpoint):
    arn = certificate(s3_endpoint, "options")
    status, text = call(
        s3_endpoint,
        "UpdateCertificateOptions",
        CertificateArn=arn,
        Options={"Export": "ENABLED"},
    )
    assert status == 400, text[:300]
    assert "ValidationException" in text
    assert "Export option" in text


def test_update_certificate_options_refuses_an_imported_certificate(s3_endpoint):
    arn = imported(s3_endpoint)
    status, text = call(
        s3_endpoint,
        "UpdateCertificateOptions",
        CertificateArn=arn,
        Options={"CertificateTransparencyLoggingPreference": "ENABLED"},
    )
    assert status == 400, text[:300]
    assert "InvalidStateException" in text


def test_renew_certificate_keeps_the_certificate_issued(s3_endpoint):
    arn = certificate(s3_endpoint, "renew")
    ok(s3_endpoint, "RenewCertificate", CertificateArn=arn)
    described = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)["Certificate"]
    assert described["CertificateArn"] == arn
    assert described["Status"] == "ISSUED"


def test_resend_validation_email_for_a_dns_validated_certificate(s3_endpoint):
    arn = certificate(s3_endpoint, "resend")
    described = ok(s3_endpoint, "DescribeCertificate", CertificateArn=arn)["Certificate"]
    records = [
        option
        for option in described["DomainValidationOptions"]
        if option["ResourceRecord"]["Type"] == "CNAME"
    ]
    assert records, "a DNS-validated certificate carries the record the email would name"
    # The emulator keys on the certificate, so the request shape a client sends is the contract.
    ok(
        s3_endpoint,
        "ResendValidationEmail",
        CertificateArn=arn,
        DomainName=described["DomainName"],
        ValidationDomain=described["DomainName"],
    )
