"""Amazon ECR on the wire: all 26 advertised operations, JSON 1.1.

The target prefix is `AmazonEC2ContainerRegistry_V20150921`. A repository is
keyed by name, so a stable repository carries the image/policy/tag tests while a
create or delete test makes its own. Layers are metadata stubs here, so the
upload sequence is driven end to end without a blob store.
"""

from __future__ import annotations

import base64
import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "AmazonEC2ContainerRegistry_V20150921"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
REPO = "ops-ecr"
MANIFEST = json.dumps(
    {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"mediaType": "application/vnd.docker.container.image.v1+json", "size": 1},
        "layers": [],
    }
)


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "ecr", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, action: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, action, payload)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def repository(endpoint, name: str = REPO) -> dict:
    return ok(endpoint, "DescribeRepositories", {"repositoryNames": [name]})["repositories"][0]


def ensure_repo(endpoint, name: str = REPO) -> str:
    status, text = call(endpoint, "CreateRepository", {"repositoryName": name})
    assert status == 200 or "RepositoryAlreadyExistsException" in text, text[:300]
    assert repository(endpoint, name)["repositoryName"] == name
    return name


def put_image(endpoint, tag: str, name: str = REPO) -> str:
    ensure_repo(endpoint, name)
    answer = ok(endpoint, "PutImage", {"repositoryName": name, "imageTag": tag, "imageManifest": MANIFEST})
    return answer["image"]["imageId"]["imageDigest"]


def tags(endpoint, name: str = REPO) -> list[dict]:
    return ok(endpoint, "ListTagsForResource", {"resourceArn": repository(endpoint, name)["repositoryArn"]})["tags"]


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------


def test_create_repository_is_read_back(endpoint):
    name = f"ops-ecr-created-{time.time_ns()}"
    created = ok(endpoint, "CreateRepository", {"repositoryName": name})["repository"]
    assert created["repositoryName"] == name
    assert repository(endpoint, name)["repositoryUri"].endswith(name)


def test_describe_repositories_lists_the_repository(endpoint):
    ensure_repo(endpoint)
    names = [item["repositoryName"] for item in ok(endpoint, "DescribeRepositories")["repositories"]]
    assert REPO in names


def test_delete_repository_removes_the_repository_it_created(endpoint):
    name = f"ops-ecr-deleted-{time.time_ns()}"
    ok(endpoint, "CreateRepository", {"repositoryName": name})
    ok(endpoint, "DeleteRepository", {"repositoryName": name})
    refused(endpoint, "DescribeRepositories", {"repositoryNames": [name]}, "RepositoryNotFoundException")


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def test_list_images_lists_the_image(endpoint):
    put_image(endpoint, "v1")
    image_ids = ok(endpoint, "ListImages", {"repositoryName": REPO})["imageIds"]
    assert "v1" in {item.get("imageTag") for item in image_ids}


def test_describe_images_reads_the_image(endpoint):
    put_image(endpoint, "v1")
    details = ok(endpoint, "DescribeImages", {"repositoryName": REPO, "imageIds": [{"imageTag": "v1"}]})["imageDetails"]
    assert "v1" in details[0]["imageTags"]


def test_put_image_is_read_back_by_batch_get(endpoint):
    tag = f"ops-tag-{time.time_ns()}"
    put_image(endpoint, tag)
    images = ok(endpoint, "BatchGetImage", {"repositoryName": REPO, "imageIds": [{"imageTag": tag}]})["images"]
    assert images[0]["imageId"]["imageTag"] == tag


def test_batch_get_image_answers_the_image(endpoint):
    put_image(endpoint, "v1")
    answer = ok(endpoint, "BatchGetImage", {"repositoryName": REPO, "imageIds": [{"imageTag": "v1"}]})
    assert answer["images"]
    assert answer["failures"] == []


def test_batch_delete_image_removes_the_image_it_created(endpoint):
    repo = f"ops-ecr-del-{time.time_ns()}"
    ensure_repo(endpoint, repo)
    tag = f"ops-del-{time.time_ns()}"
    put_image(endpoint, tag, repo)
    deleted = ok(endpoint, "BatchDeleteImage", {"repositoryName": repo, "imageIds": [{"imageTag": tag}]})
    assert deleted["imageIds"]
    remaining = ok(endpoint, "DescribeImages", {"repositoryName": repo})["imageDetails"]
    assert tag not in {tag for item in remaining for tag in item["imageTags"]}


def test_get_authorization_token_answers_a_token(endpoint):
    data = ok(endpoint, "GetAuthorizationToken")["authorizationData"][0]
    assert data["authorizationToken"]
    assert data["proxyEndpoint"].startswith("https://")


# ---------------------------------------------------------------------------
# Repository policy
# ---------------------------------------------------------------------------


def test_get_repository_policy_reads_the_policy(endpoint):
    ensure_repo(endpoint)
    policy = json.dumps({"Version": "2012-10-17", "Statement": []})
    ok(endpoint, "SetRepositoryPolicy", {"repositoryName": REPO, "policyText": policy})
    assert ok(endpoint, "GetRepositoryPolicy", {"repositoryName": REPO})["policyText"] == policy


def test_set_repository_policy_is_read_back(endpoint):
    ensure_repo(endpoint)
    policy = json.dumps({"Version": "2012-10-17", "Statement": []})
    ok(endpoint, "SetRepositoryPolicy", {"repositoryName": REPO, "policyText": policy})
    assert ok(endpoint, "GetRepositoryPolicy", {"repositoryName": REPO})["policyText"] == policy


def test_delete_repository_policy_removes_it(endpoint):
    ensure_repo(endpoint)
    ok(endpoint, "SetRepositoryPolicy", {"repositoryName": REPO, "policyText": "{}"})
    ok(endpoint, "DeleteRepositoryPolicy", {"repositoryName": REPO})
    refused(endpoint, "GetRepositoryPolicy", {"repositoryName": REPO}, "RepositoryPolicyNotFound")


# ---------------------------------------------------------------------------
# Lifecycle policy
# ---------------------------------------------------------------------------


def test_put_lifecycle_policy_is_read_back(endpoint):
    ensure_repo(endpoint)
    policy = json.dumps({"rules": [{"rulePriority": 1, "selection": {"tagStatus": "ANY"}}]})
    ok(endpoint, "PutLifecyclePolicy", {"repositoryName": REPO, "lifecyclePolicyText": policy})
    assert ok(endpoint, "GetLifecyclePolicy", {"repositoryName": REPO})["lifecyclePolicyText"] == policy


def test_get_lifecycle_policy_reads_the_policy(endpoint):
    ensure_repo(endpoint)
    policy = json.dumps({"rules": []})
    ok(endpoint, "PutLifecyclePolicy", {"repositoryName": REPO, "lifecyclePolicyText": policy})
    assert ok(endpoint, "GetLifecyclePolicy", {"repositoryName": REPO})["lifecyclePolicyText"] == policy


def test_delete_lifecycle_policy_removes_it(endpoint):
    ensure_repo(endpoint)
    ok(endpoint, "PutLifecyclePolicy", {"repositoryName": REPO, "lifecyclePolicyText": json.dumps({"rules": []})})
    ok(endpoint, "DeleteLifecyclePolicy", {"repositoryName": REPO})
    refused(endpoint, "GetLifecyclePolicy", {"repositoryName": REPO}, "LifecyclePolicyNotFound")


# ---------------------------------------------------------------------------
# Tags and repository settings
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    ensure_repo(endpoint)
    arn = repository(endpoint)["repositoryArn"]
    ok(endpoint, "TagResource", {"resourceArn": arn, "tags": [{"Key": "env", "Value": "ops"}]})
    assert {"Key": "env", "Value": "ops"} in tags(endpoint)


def test_untag_resource_removes_the_key_it_names(endpoint):
    ensure_repo(endpoint)
    arn = repository(endpoint)["repositoryArn"]
    ok(endpoint, "TagResource", {"resourceArn": arn, "tags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "UntagResource", {"resourceArn": arn, "tagKeys": ["doomed"]})
    assert "doomed" not in {tag["Key"] for tag in tags(endpoint)}


def test_list_tags_for_resource_lists_the_tags(endpoint):
    ensure_repo(endpoint)
    arn = repository(endpoint)["repositoryArn"]
    ok(endpoint, "TagResource", {"resourceArn": arn, "tags": [{"Key": "team", "Value": "platform"}]})
    assert {"Key": "team", "Value": "platform"} in tags(endpoint)


def test_put_image_tag_mutability_changes_the_setting(endpoint):
    ensure_repo(endpoint)
    ok(endpoint, "PutImageTagMutability", {"repositoryName": REPO, "imageTagMutability": "IMMUTABLE"})
    assert repository(endpoint)["imageTagMutability"] == "IMMUTABLE"
    # Restore MUTABLE so later image writes to the shared repository still succeed.
    ok(endpoint, "PutImageTagMutability", {"repositoryName": REPO, "imageTagMutability": "MUTABLE"})


def test_put_image_scanning_configuration_changes_the_setting(endpoint):
    ensure_repo(endpoint)
    ok(
        endpoint,
        "PutImageScanningConfiguration",
        {"repositoryName": REPO, "imageScanningConfiguration": {"scanOnPush": True}},
    )
    assert repository(endpoint)["imageScanningConfiguration"]["scanOnPush"] is True


def test_describe_registry_answers_the_registry(endpoint):
    assert ok(endpoint, "DescribeRegistry")["registryId"] == ACCOUNT


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------


def test_get_download_url_for_layer_answers_a_url(endpoint):
    ensure_repo(endpoint)
    answer = ok(endpoint, "GetDownloadUrlForLayer", {"repositoryName": REPO, "layerDigest": "sha256:abc"})
    assert answer["downloadUrl"].endswith("/blobs/sha256:abc")


def test_batch_check_layer_availability_answers_each_layer(endpoint):
    ensure_repo(endpoint)
    answer = ok(endpoint, "BatchCheckLayerAvailability", {"repositoryName": REPO, "layerDigests": ["sha256:abc"]})
    assert answer["layers"][0]["layerDigest"] == "sha256:abc"


def test_initiate_layer_upload_answers_an_upload(endpoint):
    ensure_repo(endpoint)
    assert ok(endpoint, "InitiateLayerUpload", {"repositoryName": REPO})["uploadId"]


def test_upload_layer_part_is_accepted(endpoint):
    ensure_repo(endpoint)
    upload_id = ok(endpoint, "InitiateLayerUpload", {"repositoryName": REPO})["uploadId"]
    answer = ok(
        endpoint,
        "UploadLayerPart",
        {
            "repositoryName": REPO,
            "uploadId": upload_id,
            "partFirstByte": 0,
            "partLastByte": 3,
            "layerPartBlob": base64.b64encode(b"ops!").decode(),
        },
    )
    assert answer["uploadId"] == upload_id


def test_complete_layer_upload_answers_a_digest(endpoint):
    ensure_repo(endpoint)
    upload_id = ok(endpoint, "InitiateLayerUpload", {"repositoryName": REPO})["uploadId"]
    answer = ok(
        endpoint,
        "CompleteLayerUpload",
        {"repositoryName": REPO, "uploadId": upload_id, "layerDigests": ["sha256:abc"]},
    )
    assert answer["layerDigest"] == "sha256:abc"
