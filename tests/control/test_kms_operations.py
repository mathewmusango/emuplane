"""KMS on the wire: all 41 advertised operations, JSON `TrentService`.

Keys are found by description rather than created blindly: `CreateKey` has no
unique name, so a second sweep must meet the key the first one made. The one
exception is the `CreateKey` test itself, which mints a run-unique key so the
call is always exercised. The lifecycle keys are restored (enabled, rotation
off, alias re-pointed) so the next sweep starts from the same state.

Symmetric encryption is the emulator's key-derived pad, not AES; signing, MACs,
data key pairs and imported material use the real `cryptography` primitives.
"""

from __future__ import annotations

import base64
import json
import os
import time

import signed
from conftest import ACCOUNT
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

REGION = "us-east-1"
REPLICA_REGION = "us-west-2"
TARGET = "TrentService."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

SYMMETRIC = "ops-kms-symmetric"
RSA_SIGN = "ops-kms-rsa-sign"
HMAC = "ops-kms-hmac"
LIFECYCLE = "ops-kms-lifecycle"
SCHEDULED = "ops-kms-schedule"
CANCELLED = "ops-kms-cancel"
MULTI_REGION = "ops-kms-mrk"
EXTERNAL = "ops-kms-external"
ALIAS = "alias/ops-kms-alias"
GRANTEE = f"arn:aws:iam::{ACCOUNT}:role/ops-kms"

POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "Enable IAM User Permissions",
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                "Action": "kms:*",
                "Resource": "*",
            }
        ],
    }
)


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, action: str, region: str = REGION, **payload):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "kms", ACCOUNT, region, "POST", "/", json.dumps(payload), headers
    )


def ok(endpoint, action: str, region: str = REGION, **payload) -> dict:
    status, text = call(endpoint, action, region=region, **payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def describe(endpoint, key_id: str, region: str = REGION) -> dict:
    return ok(endpoint, "DescribeKey", region=region, KeyId=key_id)["KeyMetadata"]


def find_key(endpoint, description: str) -> str | None:
    for entry in ok(endpoint, "ListKeys")["Keys"]:
        if describe(endpoint, entry["KeyId"]).get("Description") == description:
            return entry["KeyId"]
    return None


def ensure_key(endpoint, description: str, **create) -> str:
    """Find the key by description, re-enabling it if a test left it disabled."""
    found = find_key(endpoint, description)
    if found:
        if describe(endpoint, found)["KeyState"] == "Disabled":
            ok(endpoint, "EnableKey", KeyId=found)
        return found
    return ok(endpoint, "CreateKey", Description=description, **create)["KeyMetadata"]["KeyId"]


def symmetric(endpoint) -> str:
    return ensure_key(endpoint, SYMMETRIC)


def signer(endpoint) -> str:
    return ensure_key(endpoint, RSA_SIGN, KeySpec="RSA_2048", KeyUsage="SIGN_VERIFY")


def mac_key(endpoint) -> str:
    return ensure_key(endpoint, HMAC, KeySpec="HMAC_256", KeyUsage="GENERATE_VERIFY_MAC")


def lifecycle(endpoint) -> str:
    return ensure_key(endpoint, LIFECYCLE)


def multi_region(endpoint) -> str:
    return ensure_key(endpoint, MULTI_REGION, MultiRegion=True)


def external(endpoint) -> str:
    found = find_key(endpoint, EXTERNAL)
    if found:
        return found
    return ok(endpoint, "CreateKey", Description=EXTERNAL, Origin="EXTERNAL")["KeyMetadata"]["KeyId"]


def ensure_alias(endpoint, target: str | None = None) -> None:
    target = target or symmetric(endpoint)
    status, text = call(endpoint, "CreateAlias", AliasName=ALIAS, TargetKeyId=target)
    assert status in (200, 400), f"CreateAlias answered {status}: {text[:400]}"
    if status == 400:
        assert "already exists" in text


def ensure_imported(endpoint) -> str:
    """The EXTERNAL key with material imported, wrapping 256 bits as AWS documents."""
    key = external(endpoint)
    if describe(endpoint, key)["KeyState"] == "PendingImport":
        params = ok(
            endpoint,
            "GetParametersForImport",
            KeyId=key,
            WrappingAlgorithm="RSAES_OAEP_SHA_256",
            WrappingKeySpec="RSA_2048",
        )
        public = serialization.load_der_public_key(base64.b64decode(params["PublicKey"]))
        material = os.urandom(32)
        wrapped = public.encrypt(
            material,
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        ok(
            endpoint,
            "ImportKeyMaterial",
            KeyId=key,
            ImportToken=params["ImportToken"],
            EncryptedKeyMaterial=base64.b64encode(wrapped).decode(),
            ExpirationModel="KEY_MATERIAL_DOES_NOT_EXPIRE",
        )
    return key


def grant(endpoint, name: str) -> tuple[str, str]:
    key = lifecycle(endpoint)
    answer = ok(
        endpoint,
        "CreateGrant",
        KeyId=key,
        GranteePrincipal=GRANTEE,
        Operations=["Encrypt", "Decrypt"],
        Name=name,
    )
    return answer["GrantId"], answer["GrantToken"]


def grant_ids(endpoint, key: str) -> list[str]:
    return [item["GrantId"] for item in ok(endpoint, "ListGrants", KeyId=key).get("Grants", [])]


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


def test_create_key_answers_key_metadata(endpoint):
    description = f"ops-kms-created-{time.time_ns()}"
    metadata = ok(endpoint, "CreateKey", Description=description)["KeyMetadata"]
    assert metadata["KeyId"]
    assert metadata["Description"] == description
    assert metadata["KeySpec"] == "SYMMETRIC_DEFAULT"
    assert metadata["Enabled"] is True


def test_replicate_key_creates_a_same_id_replica_in_another_region(endpoint):
    key = multi_region(endpoint)
    status, text = call(endpoint, "ReplicateKey", KeyId=key, ReplicaRegion=REPLICA_REGION)
    assert status in (200, 400), f"ReplicateKey answered {status}: {text[:400]}"
    if status == 400:
        assert "already exists" in text
    replica = describe(endpoint, key, region=REPLICA_REGION)
    assert replica["KeyId"] == key
    assert f":{REPLICA_REGION}:" in replica["Arn"]


def test_list_keys_includes_the_symmetric_key(endpoint):
    key = symmetric(endpoint)
    assert key in [entry["KeyId"] for entry in ok(endpoint, "ListKeys")["Keys"]]


def test_describe_key_reports_the_metadata(endpoint):
    key = symmetric(endpoint)
    metadata = describe(endpoint, key)
    assert metadata["KeyId"] == key
    assert metadata["KeyUsage"] == "ENCRYPT_DECRYPT"
    assert metadata["KeyState"] == "Enabled"


def test_get_public_key_answers_the_asymmetric_public_key(endpoint):
    key = signer(endpoint)
    answer = ok(endpoint, "GetPublicKey", KeyId=key)
    assert answer["KeyUsage"] == "SIGN_VERIFY"
    assert answer["KeySpec"] == "RSA_2048"
    assert base64.b64decode(answer["PublicKey"])


def test_sign_answers_a_signature(endpoint):
    key = signer(endpoint)
    message = base64.b64encode(b"Emuplane signs this").decode()
    answer = ok(
        endpoint,
        "Sign",
        KeyId=key,
        Message=message,
        MessageType="RAW",
        SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
    )
    assert answer["Signature"]
    assert answer["SigningAlgorithm"] == "RSASSA_PKCS1_V1_5_SHA_256"


def test_verify_accepts_the_signature_it_signed(endpoint):
    key = signer(endpoint)
    message = base64.b64encode(b"Emuplane verifies this").decode()
    signature = ok(
        endpoint,
        "Sign",
        KeyId=key,
        Message=message,
        MessageType="RAW",
        SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
    )["Signature"]
    answer = ok(
        endpoint,
        "Verify",
        KeyId=key,
        Message=message,
        MessageType="RAW",
        Signature=signature,
        SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
    )
    assert answer["SignatureValid"] is True


# ---------------------------------------------------------------------------
# Symmetric crypto and MACs
# ---------------------------------------------------------------------------


def test_encrypt_answers_a_ciphertext(endpoint):
    key = symmetric(endpoint)
    plaintext = base64.b64encode(b"Emuplane encrypts this").decode()
    answer = ok(
        endpoint,
        "Encrypt",
        KeyId=key,
        Plaintext=plaintext,
        EncryptionContext={"ops": "yes"},
    )
    assert base64.b64decode(answer["CiphertextBlob"])
    assert answer["EncryptionAlgorithm"] == "SYMMETRIC_DEFAULT"


def test_decrypt_returns_the_plaintext_it_encrypted(endpoint):
    key = symmetric(endpoint)
    plaintext = base64.b64encode(b"Emuplane round-trips this").decode()
    ciphertext = ok(
        endpoint,
        "Encrypt",
        KeyId=key,
        Plaintext=plaintext,
        EncryptionContext={"ops": "yes"},
    )["CiphertextBlob"]
    answer = ok(
        endpoint,
        "Decrypt",
        KeyId=key,
        CiphertextBlob=ciphertext,
        EncryptionContext={"ops": "yes"},
    )
    assert answer["Plaintext"] == plaintext


def test_generate_mac_answers_an_hmac(endpoint):
    key = mac_key(endpoint)
    answer = ok(
        endpoint,
        "GenerateMac",
        KeyId=key,
        Message=base64.b64encode(b"Emuplane MACs this").decode(),
        MacAlgorithm="HMAC_SHA_256",
    )
    assert answer["Mac"]
    assert len(base64.b64decode(answer["Mac"])) == 32


def test_verify_mac_accepts_the_mac_it_generated(endpoint):
    key = mac_key(endpoint)
    message = base64.b64encode(b"Emuplane verifies its MAC").decode()
    mac = ok(
        endpoint, "GenerateMac", KeyId=key, Message=message, MacAlgorithm="HMAC_SHA_256"
    )["Mac"]
    answer = ok(
        endpoint,
        "VerifyMac",
        KeyId=key,
        Message=message,
        Mac=mac,
        MacAlgorithm="HMAC_SHA_256",
    )
    assert answer["MacValid"] is True


# ---------------------------------------------------------------------------
# Data keys
# ---------------------------------------------------------------------------


def test_generate_data_key_answers_plaintext_and_ciphertext(endpoint):
    key = symmetric(endpoint)
    answer = ok(endpoint, "GenerateDataKey", KeyId=key, KeySpec="AES_256")
    assert len(base64.b64decode(answer["Plaintext"])) == 32
    assert base64.b64decode(answer["CiphertextBlob"])


def test_generate_data_key_without_plaintext_omits_the_plaintext(endpoint):
    key = symmetric(endpoint)
    answer = ok(endpoint, "GenerateDataKeyWithoutPlaintext", KeyId=key, KeySpec="AES_256")
    assert "Plaintext" not in answer
    assert base64.b64decode(answer["CiphertextBlob"])


def test_generate_data_key_pair_answers_the_private_key(endpoint):
    key = symmetric(endpoint)
    answer = ok(endpoint, "GenerateDataKeyPair", KeyId=key, KeyPairSpec="ECC_NIST_P256")
    assert answer["KeyPairSpec"] == "ECC_NIST_P256"
    assert base64.b64decode(answer["PublicKey"])
    assert base64.b64decode(answer["PrivateKeyPlaintext"])
    assert base64.b64decode(answer["PrivateKeyCiphertextBlob"])


def test_generate_data_key_pair_without_plaintext_omits_the_private_key(endpoint):
    key = symmetric(endpoint)
    answer = ok(
        endpoint, "GenerateDataKeyPairWithoutPlaintext", KeyId=key, KeyPairSpec="ECC_NIST_P256"
    )
    assert "PrivateKeyPlaintext" not in answer
    assert base64.b64decode(answer["PublicKey"])


def test_generate_random_answers_the_requested_bytes(endpoint):
    answer = ok(endpoint, "GenerateRandom", NumberOfBytes=32)
    assert len(base64.b64decode(answer["Plaintext"])) == 32


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------


def test_create_alias_points_at_the_key(endpoint):
    call(endpoint, "DeleteAlias", AliasName=ALIAS)
    ok(endpoint, "CreateAlias", AliasName=ALIAS, TargetKeyId=symmetric(endpoint))
    aliases = ok(endpoint, "ListAliases")["Aliases"]
    found = next(alias for alias in aliases if alias["AliasName"] == ALIAS)
    assert found["TargetKeyId"] == symmetric(endpoint)


def test_delete_alias_removes_the_alias_it_created(endpoint):
    ensure_alias(endpoint)
    ok(endpoint, "DeleteAlias", AliasName=ALIAS)
    assert ALIAS not in [alias["AliasName"] for alias in ok(endpoint, "ListAliases")["Aliases"]]


def test_list_aliases_includes_the_alias(endpoint):
    ensure_alias(endpoint)
    assert ALIAS in [alias["AliasName"] for alias in ok(endpoint, "ListAliases")["Aliases"]]


def test_update_alias_moves_it_to_another_key(endpoint):
    target = signer(endpoint)
    ensure_alias(endpoint)
    ok(endpoint, "UpdateAlias", AliasName=ALIAS, TargetKeyId=target)
    aliases = ok(endpoint, "ListAliases")["Aliases"]
    found = next(alias for alias in aliases if alias["AliasName"] == ALIAS)
    assert found["TargetKeyId"] == target


# ---------------------------------------------------------------------------
# Description, rotation, policy, enablement
# ---------------------------------------------------------------------------


def test_update_key_description_is_read_back_by_describe_key(endpoint):
    key = lifecycle(endpoint)
    ok(endpoint, "UpdateKeyDescription", KeyId=key, Description="ops updated description")
    assert describe(endpoint, key)["Description"] == "ops updated description"
    # Restore the description the find-or-create helper keys on.
    ok(endpoint, "UpdateKeyDescription", KeyId=key, Description=LIFECYCLE)


def test_enable_key_rotation_turns_it_on(endpoint):
    key = lifecycle(endpoint)
    ok(endpoint, "EnableKeyRotation", KeyId=key, RotationPeriodInDays=180)
    status = ok(endpoint, "GetKeyRotationStatus", KeyId=key)
    assert status["KeyRotationEnabled"] is True
    assert status["RotationPeriodInDays"] == 180


def test_disable_key_rotation_turns_it_off(endpoint):
    key = lifecycle(endpoint)
    ok(endpoint, "DisableKeyRotation", KeyId=key)
    assert ok(endpoint, "GetKeyRotationStatus", KeyId=key)["KeyRotationEnabled"] is False


def test_get_key_rotation_status_reads_the_setting(endpoint):
    key = lifecycle(endpoint)
    ok(endpoint, "EnableKeyRotation", KeyId=key)
    assert ok(endpoint, "GetKeyRotationStatus", KeyId=key)["KeyRotationEnabled"] is True


def test_get_key_policy_returns_the_default_policy(endpoint):
    key = lifecycle(endpoint)
    answer = ok(endpoint, "GetKeyPolicy", KeyId=key, PolicyName="default")
    assert answer["PolicyName"] == "default"
    assert json.loads(answer["Policy"])["Version"] == "2012-10-17"


def test_put_key_policy_is_read_back(endpoint):
    key = lifecycle(endpoint)
    ok(endpoint, "PutKeyPolicy", KeyId=key, PolicyName="default", Policy=POLICY)
    assert ok(endpoint, "GetKeyPolicy", KeyId=key, PolicyName="default")["Policy"] == POLICY


def test_list_key_policies_names_the_default_policy(endpoint):
    key = lifecycle(endpoint)
    assert ok(endpoint, "ListKeyPolicies", KeyId=key)["PolicyNames"] == ["default"]


def test_enable_key_marks_it_enabled(endpoint):
    key = lifecycle(endpoint)
    ok(endpoint, "EnableKey", KeyId=key)
    metadata = describe(endpoint, key)
    assert metadata["Enabled"] is True
    assert metadata["KeyState"] == "Enabled"


def test_disable_key_marks_it_disabled(endpoint):
    key = lifecycle(endpoint)
    ok(endpoint, "DisableKey", KeyId=key)
    metadata = describe(endpoint, key)
    assert metadata["Enabled"] is False
    assert metadata["KeyState"] == "Disabled"
    # Restore it for the tests that follow.
    ok(endpoint, "EnableKey", KeyId=key)


# ---------------------------------------------------------------------------
# Scheduled deletion
# ---------------------------------------------------------------------------


def test_schedule_key_deletion_marks_the_key_pending_deletion(endpoint):
    key = ensure_key(endpoint, SCHEDULED)
    answer = ok(endpoint, "ScheduleKeyDeletion", KeyId=key, PendingWindowInDays=7)
    assert answer["KeyState"] == "PendingDeletion"
    assert answer["DeletionDate"]
    # Cancel and re-enable so a re-run starts from an enabled key.
    ok(endpoint, "CancelKeyDeletion", KeyId=key)
    ok(endpoint, "EnableKey", KeyId=key)


def test_cancel_key_deletion_returns_the_key_to_disabled(endpoint):
    key = ensure_key(endpoint, CANCELLED)
    ok(endpoint, "ScheduleKeyDeletion", KeyId=key, PendingWindowInDays=7)
    assert ok(endpoint, "CancelKeyDeletion", KeyId=key)["KeyId"].endswith(key)
    assert describe(endpoint, key)["KeyState"] == "Disabled"
    ok(endpoint, "EnableKey", KeyId=key)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_adds_a_tag_the_list_reads_back(endpoint):
    key = symmetric(endpoint)
    ok(endpoint, "TagResource", KeyId=key, Tags=[{"TagKey": "env", "TagValue": "ops"}])
    tags = ok(endpoint, "ListResourceTags", KeyId=key)["Tags"]
    assert {"TagKey": "env", "TagValue": "ops"} in tags


def test_untag_resource_removes_the_key_it_names(endpoint):
    key = symmetric(endpoint)
    ok(endpoint, "TagResource", KeyId=key, Tags=[{"TagKey": "doomed", "TagValue": "yes"}])
    ok(endpoint, "UntagResource", KeyId=key, TagKeys=["doomed"])
    assert "doomed" not in {tag["TagKey"] for tag in ok(endpoint, "ListResourceTags", KeyId=key)["Tags"]}


def test_list_resource_tags_shows_the_tags(endpoint):
    key = symmetric(endpoint)
    ok(endpoint, "TagResource", KeyId=key, Tags=[{"TagKey": "team", "TagValue": "platform"}])
    tags = ok(endpoint, "ListResourceTags", KeyId=key)["Tags"]
    assert {"TagKey": "team", "TagValue": "platform"} in tags


# ---------------------------------------------------------------------------
# Imported key material
# ---------------------------------------------------------------------------


def test_get_parameters_for_import_answers_a_token_and_wrapping_key(endpoint):
    key = external(endpoint)
    answer = ok(
        endpoint,
        "GetParametersForImport",
        KeyId=key,
        WrappingAlgorithm="RSAES_OAEP_SHA_256",
        WrappingKeySpec="RSA_2048",
    )
    assert base64.b64decode(answer["ImportToken"])
    assert serialization.load_der_public_key(base64.b64decode(answer["PublicKey"]))
    assert answer["ParametersValidTo"]


def test_import_key_material_enables_the_key(endpoint):
    key = external(endpoint)
    # A previous sweep may have left material imported; return to PendingImport
    # so this call is the one that enables the key.
    if describe(endpoint, key)["KeyState"] == "Enabled":
        ok(endpoint, "DeleteImportedKeyMaterial", KeyId=key)
    ensure_imported(endpoint)
    metadata = describe(endpoint, key)
    assert metadata["KeyState"] == "Enabled"
    assert metadata["Origin"] == "EXTERNAL"


def test_delete_imported_key_material_returns_the_key_to_pending_import(endpoint):
    key = ensure_imported(endpoint)
    ok(endpoint, "DeleteImportedKeyMaterial", KeyId=key)
    assert describe(endpoint, key)["KeyState"] == "PendingImport"


# ---------------------------------------------------------------------------
# Grants
# ---------------------------------------------------------------------------


def test_create_grant_answers_a_grant_id_and_token(endpoint):
    grant_id, token = grant(endpoint, "ops-create")
    assert grant_id
    assert token


def test_list_grants_includes_the_grant(endpoint):
    grant_id, _token = grant(endpoint, "ops-list")
    assert grant_id in grant_ids(endpoint, lifecycle(endpoint))


def test_revoke_grant_removes_the_grant_it_created(endpoint):
    grant_id, _token = grant(endpoint, "ops-revoke")
    ok(endpoint, "RevokeGrant", KeyId=lifecycle(endpoint), GrantId=grant_id)
    assert grant_id not in grant_ids(endpoint, lifecycle(endpoint))


def test_retire_grant_removes_the_grant_by_its_token(endpoint):
    grant_id, token = grant(endpoint, "ops-retire")
    ok(endpoint, "RetireGrant", GrantToken=token)
    assert grant_id not in grant_ids(endpoint, lifecycle(endpoint))
