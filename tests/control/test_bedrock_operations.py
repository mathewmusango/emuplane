"""Bedrock's control plane on the wire: all 66 advertised operations, REST/JSON.

All four Bedrock planes sign with the `bedrock` credential scope, so the
in-process stand-in picks the control plane by path exactly as the emulator's
router does. The foundation-model catalog, inference profiles, guardrail
versions and the job families are deterministic records; stable names carry the
read tests and every delete test creates a resource of its own.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}
MODEL = "anthropic.claude-3-haiku-20240307-v1:0"
OTHER_MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"
AMAZON_MODEL = "amazon.nova-pro-v1:0"
MODEL_ARN = f"arn:aws:bedrock:{REGION}::foundation-model/{MODEL}"
FALLBACK_ARN = f"arn:aws:bedrock:{REGION}::foundation-model/{AMAZON_MODEL}"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ops-bedrock"

GUARDRAIL = "ops-bedrock-guardrail"
CUSTOM_MODEL = "ops-bedrock-custom"
PROMPT_ROUTER = "ops-bedrock-router"

LOG_CONFIG = {
    "cloudWatchConfig": {
        "logGroupName": "/aws/bedrock/invocations",
        "roleArn": ROLE_ARN,
    },
    "textDataDeliveryEnabled": True,
}


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload) if payload is not None else ""
    return signed.request(
        endpoint, "bedrock", ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def ok(endpoint, method: str, path: str, payload: dict | None = None, status: int = 200) -> dict:
    code, text = call(endpoint, method, path, payload)
    assert code == status, f"{method} {path} answered {code}: {text[:400]}"
    return json.loads(text or "{}")


def created(
    endpoint,
    method: str,
    path: str,
    payload: dict | None = None,
    statuses: tuple[int, ...] = (200, 201, 202),
) -> tuple[int, str]:
    """A create is idempotent across sweeps: the emulator's conflict code is not a failure."""
    code, text = call(endpoint, method, path, payload)
    assert code in statuses or "ConflictException" in text, (
        f"{method} {path} answered {code}: {text[:400]}"
    )
    return code, text


def arn(resource_type: str, name: str) -> str:
    return f"arn:aws:bedrock:{REGION}:{ACCOUNT}:{resource_type}/{name}"


def guardrail_id(endpoint, name: str = GUARDRAIL) -> str:
    for item in ok(endpoint, "GET", "/guardrails")["guardrails"]:
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"guardrail {name} is not listed")


def ensure_guardrail(endpoint, name: str = GUARDRAIL) -> dict:
    code, text = created(
        endpoint,
        "POST",
        "/guardrails",
        {
            "name": name,
            "blockedInputMessaging": "blocked input",
            "blockedOutputsMessaging": "blocked output",
        },
    )
    identifier = json.loads(text)["guardrailId"] if code == 202 else guardrail_id(endpoint, name)
    return ok(endpoint, "GET", f"/guardrails/{identifier}")


def ensure_custom_model(endpoint, name: str = CUSTOM_MODEL) -> dict:
    created(
        endpoint,
        "POST",
        "/custom-models/create-custom-model",
        {"modelName": name, "modelSourceConfig": {"baseModelArn": MODEL_ARN}},
    )
    return ok(endpoint, "GET", f"/custom-models/{name}")


def ensure_marketplace(endpoint, name: str) -> str:
    created(
        endpoint,
        "POST",
        "/marketplace-model/endpoints",
        {
            "endpointName": name,
            "modelSourceIdentifier": f"arn:aws:sagemaker:{REGION}:{ACCOUNT}:model-package/ops-bedrock",
            "endpointConfig": {"sageMaker": {"instanceType": "ml.m5.large"}},
        },
    )
    return arn("marketplace-model-endpoint", name)


def ensure_prompt_router(endpoint, name: str = PROMPT_ROUTER) -> str:
    created(
        endpoint,
        "POST",
        "/prompt-routers",
        {
            "promptRouterName": name,
            "models": [{"modelArn": MODEL_ARN}],
            "fallbackModel": {"modelArn": FALLBACK_ARN},
            "routingCriteria": {"responseQualityDifference": 0.1},
        },
    )
    return arn("prompt-router", name)


def ensure_imported_model(endpoint, name: str) -> str:
    code, _text = call(endpoint, "GET", f"/imported-models/{name}")
    if code != 200:
        created(
            endpoint,
            "POST",
            "/model-import-jobs",
            {
                "jobName": f"{name}-job",
                "importedModelName": name,
                "roleArn": ROLE_ARN,
                "modelDataSource": {"s3DataSource": {"s3Uri": "s3://ops-bedrock/models/"}},
            },
        )
    return name


def new_provisioned(endpoint, name: str) -> tuple[str, str]:
    answer = ok(
        endpoint,
        "POST",
        "/provisioned-model-throughput",
        {"provisionedModelName": name, "modelId": MODEL, "modelUnits": 2},
        status=201,
    )
    model_arn = answer["provisionedModelArn"]
    return model_arn.rsplit("/", 1)[-1], model_arn


def new_inference_profile(endpoint, name: str) -> tuple[str, str]:
    answer = ok(
        endpoint,
        "POST",
        "/inference-profiles",
        {"inferenceProfileName": name, "modelSource": {"copyFrom": MODEL_ARN}},
        status=201,
    )
    profile_arn = answer["inferenceProfileArn"]
    return profile_arn.rsplit("/", 1)[-1], profile_arn


def new_customization_job(endpoint, job_name: str) -> str:
    return ok(
        endpoint,
        "POST",
        "/model-customization-jobs",
        {
            "jobName": job_name,
            "customModelName": f"{job_name}-model",
            "roleArn": ROLE_ARN,
            "baseModelIdentifier": MODEL,
            "trainingDataConfig": {"s3Uri": "s3://ops-bedrock/train/"},
            "outputDataConfig": {"s3Uri": "s3://ops-bedrock/out/"},
        },
        status=201,
    )["jobArn"]


def new_import_job(endpoint, job_name: str, imported_name: str) -> str:
    return ok(
        endpoint,
        "POST",
        "/model-import-jobs",
        {
            "jobName": job_name,
            "importedModelName": imported_name,
            "roleArn": ROLE_ARN,
            "modelDataSource": {"s3DataSource": {"s3Uri": "s3://ops-bedrock/models/"}},
        },
        status=201,
    )["jobArn"]


def new_copy_job(endpoint, target: str) -> str:
    return ok(
        endpoint,
        "POST",
        "/model-copy-jobs",
        {"sourceModelArn": arn("custom-model", "ops-bedrock-copy-source"), "targetModelName": target},
        status=201,
    )["jobArn"]


def new_invocation_job(endpoint, job_name: str) -> str:
    return ok(
        endpoint,
        "POST",
        "/model-invocation-job",
        {
            "jobName": job_name,
            "modelId": MODEL,
            "roleArn": ROLE_ARN,
            "inputDataConfig": {"s3InputDataConfig": {"s3Uri": "s3://ops-bedrock/in/"}},
            "outputDataConfig": {"s3OutputDataConfig": {"s3Uri": "s3://ops-bedrock/out/"}},
        },
    )["jobArn"]


def new_evaluation_job(endpoint, job_name: str) -> str:
    return ok(
        endpoint,
        "POST",
        "/evaluation-jobs",
        {
            "jobName": job_name,
            "roleArn": ROLE_ARN,
            "evaluationConfig": {
                "automated": {
                    "datasetMetricConfigs": [
                        {
                            "taskType": "Generation",
                            "dataset": {"name": "Builtin.BoolQ"},
                            "metricNames": ["Builtin.Accuracy"],
                        }
                    ]
                }
            },
            "inferenceConfig": {
                "models": [{"bedrockModel": {"modelIdentifier": MODEL, "inferenceParams": "{}"}}]
            },
            "outputDataConfig": {"s3Uri": "s3://ops-bedrock/eval/"},
        },
        status=202,
    )["jobArn"]


# --- Foundation models ------------------------------------------------------


def test_list_foundation_models_answers_the_catalog(endpoint):
    models = ok(endpoint, "GET", "/foundation-models")["modelSummaries"]
    assert len(models) > 10
    assert MODEL in {item["modelId"] for item in models}
    assert all(item["modelLifecycle"]["status"] == "ACTIVE" for item in models)


def test_get_foundation_model_answers_its_details(endpoint):
    details = ok(endpoint, "GET", f"/foundation-models/{MODEL}")["modelDetails"]
    assert details["modelId"] == MODEL
    assert details["providerName"] == "Anthropic"
    assert details["responseStreamingSupported"] is True


def test_get_foundation_model_availability_answers_the_entitlement(endpoint):
    answer = ok(endpoint, "GET", f"/foundation-model-availability/{AMAZON_MODEL}")
    assert answer["modelId"] == AMAZON_MODEL
    assert answer["agreementAvailability"]["status"] == "AVAILABLE"
    assert answer["entitlementAvailability"] == "AVAILABLE"


def test_create_foundation_model_agreement_marks_the_model_available(endpoint):
    answer = ok(
        endpoint,
        "POST",
        "/create-foundation-model-agreement",
        {"modelId": MODEL, "offerToken": "ops-bedrock-offer"},
        status=202,
    )
    assert answer["modelId"] == MODEL
    availability = ok(endpoint, "GET", f"/foundation-model-availability/{MODEL}")
    assert availability["agreementAvailability"]["status"] == "AVAILABLE"


def test_delete_foundation_model_agreement_clears_the_availability(endpoint):
    ok(
        endpoint,
        "POST",
        "/create-foundation-model-agreement",
        {"modelId": OTHER_MODEL, "offerToken": "ops-bedrock-offer"},
        status=202,
    )
    ok(
        endpoint,
        "POST",
        "/delete-foundation-model-agreement",
        {"modelId": OTHER_MODEL},
        status=202,
    )
    availability = ok(endpoint, "GET", f"/foundation-model-availability/{OTHER_MODEL}")
    assert availability["agreementAvailability"]["status"] == "NOT_AVAILABLE"


def test_list_foundation_model_agreement_offers_answers_the_offer(endpoint):
    answer = ok(endpoint, "GET", f"/list-foundation-model-agreement-offers/{MODEL}")
    assert answer["modelId"] == MODEL
    assert len(answer["offers"]) == 1
    assert answer["offers"][0]["offerToken"]


# --- Inference profiles -----------------------------------------------------


def test_list_inference_profiles_lists_application_profiles(endpoint):
    _profile_id, profile_arn = new_inference_profile(endpoint, "ops-bedrock-profile-list")
    listed = ok(endpoint, "GET", "/inference-profiles?typeEquals=APPLICATION")
    found = {item["inferenceProfileArn"] for item in listed["inferenceProfileSummaries"]}
    assert profile_arn in found


def test_create_inference_profile_is_read_back(endpoint):
    profile_id, profile_arn = new_inference_profile(endpoint, "ops-bedrock-profile-create")
    assert ":application-inference-profile/" in profile_arn
    read = ok(endpoint, "GET", f"/inference-profiles/{profile_id}")
    assert read["inferenceProfileName"] == "ops-bedrock-profile-create"
    assert read["inferenceProfileArn"] == profile_arn


def test_get_inference_profile_answers_a_system_profile(endpoint):
    identifier = f"us.{MODEL}"
    profile = ok(endpoint, "GET", f"/inference-profiles/{identifier}")
    assert profile["inferenceProfileId"] == identifier
    assert profile["type"] == "SYSTEM_DEFINED"
    assert profile["models"][0]["modelArn"].endswith(MODEL)


def test_delete_inference_profile_removes_it(endpoint):
    profile_id, _profile_arn = new_inference_profile(endpoint, "ops-bedrock-profile-delete")
    ok(endpoint, "DELETE", f"/inference-profiles/{profile_id}")
    code, _text = call(endpoint, "GET", f"/inference-profiles/{profile_id}")
    assert code == 404


# --- Guardrails -------------------------------------------------------------


def test_list_guardrails_includes_the_guardrail(endpoint):
    ensure_guardrail(endpoint)
    listed = ok(endpoint, "GET", "/guardrails")
    assert GUARDRAIL in {item["name"] for item in listed["guardrails"]}


def test_create_guardrail_is_read_back(endpoint):
    guardrail = ensure_guardrail(endpoint, "ops-bedrock-guardrail-create")
    assert guardrail["name"] == "ops-bedrock-guardrail-create"
    assert guardrail["status"] == "READY"
    assert guardrail["version"] == "DRAFT"
    assert guardrail["guardrailArn"].endswith(f":guardrail/{guardrail['guardrailId']}")


def test_get_guardrail_reports_its_draft_version(endpoint):
    guardrail = ensure_guardrail(endpoint)
    assert guardrail["name"] == GUARDRAIL
    assert guardrail["version"] == "DRAFT"
    assert guardrail["blockedInputMessaging"] == "blocked input"


def test_update_guardrail_sets_the_description(endpoint):
    guardrail = ensure_guardrail(endpoint, "ops-bedrock-guardrail-update")
    ok(
        endpoint,
        "PUT",
        f"/guardrails/{guardrail['guardrailId']}",
        {"description": "updated by the ops sweep"},
        status=202,
    )
    read = ok(endpoint, "GET", f"/guardrails/{guardrail['guardrailId']}")
    assert read["description"] == "updated by the ops sweep"


def test_delete_guardrail_removes_it(endpoint):
    guardrail = ensure_guardrail(endpoint, "ops-bedrock-guardrail-delete")
    ok(endpoint, "DELETE", f"/guardrails/{guardrail['guardrailId']}", status=202)
    code, _text = call(endpoint, "GET", f"/guardrails/{guardrail['guardrailId']}")
    assert code == 404


def test_create_guardrail_version_answers_the_next_number(endpoint):
    guardrail = ensure_guardrail(endpoint, "ops-bedrock-guardrail-version")
    version = ok(
        endpoint,
        "POST",
        f"/guardrails/{guardrail['guardrailId']}",
        {"description": "a published snapshot"},
        status=202,
    )
    assert version["version"].isdigit()
    read = ok(
        endpoint,
        "GET",
        f"/guardrails/{guardrail['guardrailId']}?guardrailVersion={version['version']}",
    )
    assert read["version"] == version["version"]


# --- Custom models ----------------------------------------------------------


def test_list_custom_models_includes_the_model(endpoint):
    ensure_custom_model(endpoint)
    listed = ok(endpoint, "GET", "/custom-models")
    assert arn("custom-model", CUSTOM_MODEL) in {
        item["modelArn"] for item in listed["modelSummaries"]
    }


def test_create_custom_model_is_read_back(endpoint):
    model = ensure_custom_model(endpoint, "ops-bedrock-custom-create")
    assert model["modelName"] == "ops-bedrock-custom-create"
    assert model["modelArn"] == arn("custom-model", "ops-bedrock-custom-create")


def test_get_custom_model_reports_its_base_model(endpoint):
    model = ensure_custom_model(endpoint)
    assert model["modelName"] == CUSTOM_MODEL
    assert model["baseModelArn"].endswith(MODEL)


def test_delete_custom_model_removes_it(endpoint):
    ensure_custom_model(endpoint, "ops-bedrock-custom-delete")
    ok(endpoint, "DELETE", "/custom-models/ops-bedrock-custom-delete")
    code, _text = call(endpoint, "GET", "/custom-models/ops-bedrock-custom-delete")
    assert code == 404


# --- Imported models --------------------------------------------------------


def test_list_imported_models_includes_the_model(endpoint):
    name = ensure_imported_model(endpoint, "ops-bedrock-imported-list")
    listed = ok(endpoint, "GET", "/imported-models")
    assert name in {item["modelName"] for item in listed["modelSummaries"]}


def test_get_imported_model_reports_its_job(endpoint):
    name = ensure_imported_model(endpoint, "ops-bedrock-imported-get")
    model = ok(endpoint, "GET", f"/imported-models/{name}")
    assert model["modelName"] == name
    assert model["jobName"] == f"{name}-job"


def test_delete_imported_model_removes_it(endpoint):
    name = ensure_imported_model(endpoint, "ops-bedrock-imported-delete")
    ok(endpoint, "DELETE", f"/imported-models/{name}")
    code, _text = call(endpoint, "GET", f"/imported-models/{name}")
    assert code == 404


# --- Provisioned throughput -------------------------------------------------


def test_create_provisioned_model_throughput_is_read_back(endpoint):
    pid, model_arn = new_provisioned(endpoint, "ops-bedrock-provisioned-create")
    assert ":provisioned-model/" in model_arn
    read = ok(endpoint, "GET", f"/provisioned-model-throughput/{pid}")
    assert read["provisionedModelName"] == "ops-bedrock-provisioned-create"
    assert read["modelArn"].endswith(MODEL)


def test_list_provisioned_model_throughputs_includes_the_model(endpoint):
    _pid, model_arn = new_provisioned(endpoint, "ops-bedrock-provisioned-list")
    listed = ok(endpoint, "GET", "/provisioned-model-throughputs")
    assert model_arn in {
        item["provisionedModelArn"] for item in listed["provisionedModelSummaries"]
    }


def test_get_provisioned_model_throughput_reports_its_units(endpoint):
    pid, _model_arn = new_provisioned(endpoint, "ops-bedrock-provisioned-get")
    read = ok(endpoint, "GET", f"/provisioned-model-throughput/{pid}")
    assert read["modelUnits"] == 2
    assert read["status"] == "InService"


def test_update_provisioned_model_throughput_renames_it(endpoint):
    pid, _model_arn = new_provisioned(endpoint, "ops-bedrock-provisioned-update")
    ok(
        endpoint,
        "PATCH",
        f"/provisioned-model-throughput/{pid}",
        {"desiredProvisionedModelName": "ops-bedrock-provisioned-renamed"},
    )
    read = ok(endpoint, "GET", f"/provisioned-model-throughput/{pid}")
    assert read["provisionedModelName"] == "ops-bedrock-provisioned-renamed"


def test_delete_provisioned_model_throughput_removes_it(endpoint):
    pid, _model_arn = new_provisioned(endpoint, "ops-bedrock-provisioned-delete")
    ok(endpoint, "DELETE", f"/provisioned-model-throughput/{pid}")
    code, _text = call(endpoint, "GET", f"/provisioned-model-throughput/{pid}")
    assert code == 404


# --- Model customization jobs ----------------------------------------------


def test_create_model_customization_job_is_read_back(endpoint):
    job_arn = new_customization_job(endpoint, "ops-bedrock-customization-create")
    assert ":model-customization-job/" in job_arn
    job = ok(endpoint, "GET", f"/model-customization-jobs/{job_arn}")
    assert job["jobName"] == "ops-bedrock-customization-create"
    assert job["outputModelName"] == "ops-bedrock-customization-create-model"


def test_list_model_customization_jobs_includes_the_job(endpoint):
    job_arn = new_customization_job(endpoint, "ops-bedrock-customization-list")
    listed = ok(endpoint, "GET", "/model-customization-jobs")
    assert job_arn in {item["jobArn"] for item in listed["modelCustomizationJobSummaries"]}


def test_stop_model_customization_job_marks_it_stopped(endpoint):
    job_arn = new_customization_job(endpoint, "ops-bedrock-customization-stop")
    ok(endpoint, "POST", f"/model-customization-jobs/{job_arn}/stop")
    job = ok(endpoint, "GET", f"/model-customization-jobs/{job_arn}")
    assert job["status"] == "Stopped"


def test_get_model_customization_job_reports_its_base_model(endpoint):
    job_arn = new_customization_job(endpoint, "ops-bedrock-customization-get")
    job = ok(endpoint, "GET", f"/model-customization-jobs/{job_arn}")
    assert job["baseModelArn"].endswith(MODEL)
    assert job["status"] == "InProgress"


# --- Model import jobs ------------------------------------------------------


def test_create_model_import_job_creates_the_imported_model(endpoint):
    job_arn = new_import_job(endpoint, "ops-bedrock-import-create", "ops-bedrock-import-model")
    assert ":model-import-job/" in job_arn
    model = ok(endpoint, "GET", "/imported-models/ops-bedrock-import-model")
    assert model["modelName"] == "ops-bedrock-import-model"


def test_list_model_import_jobs_includes_the_job(endpoint):
    job_arn = new_import_job(endpoint, "ops-bedrock-import-list", "ops-bedrock-import-list-model")
    listed = ok(endpoint, "GET", "/model-import-jobs")
    assert job_arn in {item["jobArn"] for item in listed["modelImportJobSummaries"]}


def test_get_model_import_job_reports_its_imported_model(endpoint):
    job_arn = new_import_job(endpoint, "ops-bedrock-import-get", "ops-bedrock-import-get-model")
    job = ok(endpoint, "GET", f"/model-import-jobs/{job_arn}")
    assert job["importedModelName"] == "ops-bedrock-import-get-model"
    assert job["status"] == "InProgress"


# --- Model copy jobs --------------------------------------------------------


def test_create_model_copy_job_is_read_back(endpoint):
    job_arn = new_copy_job(endpoint, "ops-bedrock-copy-create")
    assert ":model-copy-job/" in job_arn
    job = ok(endpoint, "GET", f"/model-copy-jobs/{job_arn}")
    assert job["targetModelName"] == "ops-bedrock-copy-create"


def test_list_model_copy_jobs_includes_the_job(endpoint):
    job_arn = new_copy_job(endpoint, "ops-bedrock-copy-list")
    listed = ok(endpoint, "GET", "/model-copy-jobs")
    assert job_arn in {item["jobArn"] for item in listed["modelCopyJobSummaries"]}


def test_get_model_copy_job_reports_its_target(endpoint):
    job_arn = new_copy_job(endpoint, "ops-bedrock-copy-get")
    job = ok(endpoint, "GET", f"/model-copy-jobs/{job_arn}")
    assert job["jobArn"] == job_arn
    assert job["targetModelArn"].endswith(":custom-model/ops-bedrock-copy-get")


# --- Model invocation jobs --------------------------------------------------


def test_create_model_invocation_job_is_read_back(endpoint):
    job_arn = new_invocation_job(endpoint, "ops-bedrock-invocation-create")
    assert ":model-invocation-job/" in job_arn
    job = ok(endpoint, "GET", f"/model-invocation-job/{job_arn}")
    assert job["jobName"] == "ops-bedrock-invocation-create"


def test_list_model_invocation_jobs_includes_the_job(endpoint):
    job_arn = new_invocation_job(endpoint, "ops-bedrock-invocation-list")
    listed = ok(endpoint, "GET", "/model-invocation-jobs")
    assert job_arn in {item["jobArn"] for item in listed["invocationJobSummaries"]}


def test_stop_model_invocation_job_marks_it_stopped(endpoint):
    job_arn = new_invocation_job(endpoint, "ops-bedrock-invocation-stop")
    ok(endpoint, "POST", f"/model-invocation-job/{job_arn}/stop")
    job = ok(endpoint, "GET", f"/model-invocation-job/{job_arn}")
    assert job["status"] == "Stopped"


def test_get_model_invocation_job_reports_its_model(endpoint):
    job_arn = new_invocation_job(endpoint, "ops-bedrock-invocation-get")
    job = ok(endpoint, "GET", f"/model-invocation-job/{job_arn}")
    assert job["modelId"] == MODEL
    assert job["status"] == "InProgress"


# --- Evaluation jobs --------------------------------------------------------


def test_create_evaluation_job_is_read_back(endpoint):
    job_arn = new_evaluation_job(endpoint, "ops-bedrock-evaluation-create")
    assert ":evaluation-job/" in job_arn
    job = ok(endpoint, "GET", f"/evaluation-jobs/{job_arn}")
    assert job["jobName"] == "ops-bedrock-evaluation-create"


def test_list_evaluation_jobs_includes_the_job(endpoint):
    job_arn = new_evaluation_job(endpoint, "ops-bedrock-evaluation-list")
    listed = ok(endpoint, "GET", "/evaluation-jobs")
    assert job_arn in {item["jobArn"] for item in listed["jobSummaries"]}


def test_batch_delete_evaluation_job_deletes_the_job(endpoint):
    job_arn = new_evaluation_job(endpoint, "ops-bedrock-evaluation-batch-delete")
    answer = ok(
        endpoint,
        "POST",
        "/evaluation-jobs/batch-delete",
        {"jobIdentifiers": [job_arn]},
        status=202,
    )
    assert answer["evaluationJobs"][0]["jobIdentifier"] == job_arn
    code, _text = call(endpoint, "GET", f"/evaluation-jobs/{job_arn}")
    assert code == 404


def test_stop_evaluation_job_marks_it_stopped(endpoint):
    job_arn = new_evaluation_job(endpoint, "ops-bedrock-evaluation-stop")
    ok(endpoint, "POST", f"/evaluation-job/{job_arn}/stop")
    job = ok(endpoint, "GET", f"/evaluation-jobs/{job_arn}")
    assert job["status"] == "Stopped"


def test_get_evaluation_job_reports_its_role(endpoint):
    job_arn = new_evaluation_job(endpoint, "ops-bedrock-evaluation-get")
    job = ok(endpoint, "GET", f"/evaluation-jobs/{job_arn}")
    assert job["roleArn"] == ROLE_ARN
    assert job["status"] == "InProgress"


# --- Marketplace model endpoints -------------------------------------------


def test_create_marketplace_model_endpoint_is_read_back(endpoint):
    endpoint_arn = ensure_marketplace(endpoint, "ops-bedrock-marketplace-create")
    record = ok(endpoint, "GET", f"/marketplace-model/endpoints/{endpoint_arn}")
    assert record["marketplaceModelEndpoint"]["endpointArn"] == endpoint_arn
    assert record["marketplaceModelEndpoint"]["endpointStatus"] == "InService"


def test_list_marketplace_model_endpoints_includes_the_endpoint(endpoint):
    endpoint_arn = ensure_marketplace(endpoint, "ops-bedrock-marketplace-list")
    listed = ok(endpoint, "GET", "/marketplace-model/endpoints")
    assert endpoint_arn in {
        item["endpointArn"] for item in listed["marketplaceModelEndpoints"]
    }


def test_register_marketplace_model_endpoint_answers_registered(endpoint):
    endpoint_arn = ensure_marketplace(endpoint, "ops-bedrock-marketplace-register")
    answer = ok(
        endpoint,
        "POST",
        f"/marketplace-model/endpoints/{endpoint_arn}/registration",
        {},
    )
    assert answer["marketplaceModelEndpoint"]["status"] == "REGISTERED"


def test_deregister_marketplace_model_endpoint_answers_deregistered(endpoint):
    endpoint_arn = ensure_marketplace(endpoint, "ops-bedrock-marketplace-deregister")
    ok(endpoint, "DELETE", f"/marketplace-model/endpoints/{endpoint_arn}/registration")
    record = ok(endpoint, "GET", f"/marketplace-model/endpoints/{endpoint_arn}")
    assert record["marketplaceModelEndpoint"]["status"] == "DEREGISTERED"


def test_get_marketplace_model_endpoint_reports_its_source(endpoint):
    endpoint_arn = ensure_marketplace(endpoint, "ops-bedrock-marketplace-get")
    record = ok(endpoint, "GET", f"/marketplace-model/endpoints/{endpoint_arn}")
    assert record["marketplaceModelEndpoint"]["modelSourceIdentifier"].endswith(
        "model-package/ops-bedrock"
    )


def test_delete_marketplace_model_endpoint_removes_it(endpoint):
    endpoint_arn = ensure_marketplace(endpoint, "ops-bedrock-marketplace-delete")
    ok(endpoint, "DELETE", f"/marketplace-model/endpoints/{endpoint_arn}")
    code, _text = call(endpoint, "GET", f"/marketplace-model/endpoints/{endpoint_arn}")
    assert code == 404


def test_update_marketplace_model_endpoint_sets_the_config(endpoint):
    endpoint_arn = ensure_marketplace(endpoint, "ops-bedrock-marketplace-update")
    answer = ok(
        endpoint,
        "PATCH",
        f"/marketplace-model/endpoints/{endpoint_arn}",
        {"endpointConfig": {"sageMaker": {"instanceType": "ml.m5.xlarge"}}},
    )
    assert answer["marketplaceModelEndpoint"]["endpointConfig"] == {
        "sageMaker": {"instanceType": "ml.m5.xlarge"}
    }


# --- Prompt routers ---------------------------------------------------------


def test_create_prompt_router_is_read_back(endpoint):
    name = "ops-bedrock-router-create"
    router_arn = ensure_prompt_router(endpoint, name)
    router = ok(endpoint, "GET", f"/prompt-routers/{router_arn}")
    assert router["promptRouterName"] == name
    assert router["status"] == "AVAILABLE"


def test_list_prompt_routers_includes_the_router(endpoint):
    router_arn = ensure_prompt_router(endpoint, "ops-bedrock-router-list")
    listed = ok(endpoint, "GET", "/prompt-routers")
    assert router_arn in {item["promptRouterArn"] for item in listed["promptRouterSummaries"]}


def test_get_prompt_router_reports_its_models(endpoint):
    router_arn = ensure_prompt_router(endpoint)
    router = ok(endpoint, "GET", f"/prompt-routers/{router_arn}")
    assert router["promptRouterName"] == PROMPT_ROUTER
    assert router["models"][0]["modelArn"] == MODEL_ARN


def test_delete_prompt_router_removes_it(endpoint):
    router_arn = ensure_prompt_router(endpoint, "ops-bedrock-router-delete")
    ok(endpoint, "DELETE", f"/prompt-routers/{router_arn}")
    code, _text = call(endpoint, "GET", f"/prompt-routers/{router_arn}")
    assert code == 404


# --- Invocation logging configuration --------------------------------------


def test_get_model_invocation_logging_configuration_answers_the_config(endpoint):
    ok(endpoint, "PUT", "/logging/modelinvocations", {"loggingConfig": LOG_CONFIG})
    answer = ok(endpoint, "GET", "/logging/modelinvocations")
    assert answer["loggingConfig"]["textDataDeliveryEnabled"] is True


def test_put_model_invocation_logging_configuration_is_read_back(endpoint):
    ok(
        endpoint,
        "PUT",
        "/logging/modelinvocations",
        {"loggingConfig": {"textDataDeliveryEnabled": False}},
    )
    answer = ok(endpoint, "GET", "/logging/modelinvocations")
    assert answer["loggingConfig"]["textDataDeliveryEnabled"] is False


def test_delete_model_invocation_logging_configuration_clears_it(endpoint):
    ok(endpoint, "PUT", "/logging/modelinvocations", {"loggingConfig": LOG_CONFIG})
    ok(endpoint, "DELETE", "/logging/modelinvocations")
    answer = ok(endpoint, "GET", "/logging/modelinvocations")
    assert "loggingConfig" not in answer


# --- Use case for model access ---------------------------------------------


def test_get_use_case_for_model_access_answers_the_form(endpoint):
    ok(
        endpoint,
        "POST",
        "/use-case-for-model-access",
        {"formData": "ops model access form"},
        status=201,
    )
    answer = ok(endpoint, "GET", "/use-case-for-model-access")
    assert answer["formData"] == "ops model access form"


def test_put_use_case_for_model_access_is_read_back(endpoint):
    ok(
        endpoint,
        "POST",
        "/use-case-for-model-access",
        {"formData": "another ops form"},
        status=201,
    )
    answer = ok(endpoint, "GET", "/use-case-for-model-access")
    assert answer["formData"] == "another ops form"


# --- Tags -------------------------------------------------------------------


def test_tag_resource_adds_a_tag(endpoint):
    guardrail = ensure_guardrail(endpoint)
    ok(
        endpoint,
        "POST",
        "/tagResource",
        {"resourceARN": guardrail["guardrailArn"], "tags": [{"key": "team", "value": "ml"}]},
    )
    tags = ok(endpoint, "POST", "/listTagsForResource", {"resourceARN": guardrail["guardrailArn"]})
    assert {"key": "team", "value": "ml"} in tags["tags"]


def test_untag_resource_removes_the_key(endpoint):
    guardrail = ensure_guardrail(endpoint)
    ok(
        endpoint,
        "POST",
        "/tagResource",
        {"resourceARN": guardrail["guardrailArn"], "tags": [{"key": "temporary", "value": "yes"}]},
    )
    ok(
        endpoint,
        "POST",
        "/untagResource",
        {"resourceARN": guardrail["guardrailArn"], "tagKeys": ["temporary"]},
    )
    tags = ok(endpoint, "POST", "/listTagsForResource", {"resourceARN": guardrail["guardrailArn"]})
    assert "temporary" not in {item["key"] for item in tags["tags"]}


def test_list_tags_for_resource_answers_the_tags(endpoint):
    guardrail = ensure_guardrail(endpoint)
    ok(
        endpoint,
        "POST",
        "/tagResource",
        {"resourceARN": guardrail["guardrailArn"], "tags": [{"key": "env", "value": "test"}]},
    )
    tags = ok(endpoint, "POST", "/listTagsForResource", {"resourceARN": guardrail["guardrailArn"]})
    assert {"key": "env", "value": "test"} in tags["tags"]
