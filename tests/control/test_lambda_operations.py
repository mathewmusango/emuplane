"""Lambda on the wire: every advertised operation, driven through the REST protocol.

A function created here is left in place; the delete action creates a function of its own.
The handler is a two-line Python function, so an invoke has something real to run.
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from urllib.parse import quote, urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
ROLE_NAME = "ops-lambda"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
TRUST = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)
HANDLER = """
def handler(event, context):
    return {"echo": event.get("value", "")}
"""


def ensure_role(endpoint) -> None:
    """A live emulator checks the role exists; in-process it is always admitted."""
    body = urlencode(
        {
            "Action": "CreateRole",
            "Version": "2010-05-08",
            "RoleName": ROLE_NAME,
            "AssumeRolePolicyDocument": TRUST,
        }
    )
    status, text = signed.request(endpoint, "iam", ACCOUNT, REGION, "POST", "/", body, FORM)
    assert status == 200 or "EntityAlreadyExists" in text, text[:300]


def package() -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("index.py", HANDLER)
    return base64.b64encode(buffer.getvalue()).decode()


def call(endpoint, method: str, path: str, body=""):
    headers = {"Content-Type": "application/json"} if body else None
    return signed.request(endpoint, "lambda", ACCOUNT, REGION, method, path, body, headers)


def ok(endpoint, method: str, path: str, body="") -> str:
    status, text = call(endpoint, method, path, body)
    # A lab sweep re-runs against the functions an earlier sweep deliberately left behind.
    if 200 <= status < 300:
        return text
    assert status == 409 and "ResourceConflict" in text, f"{method} {path} answered {status}: {text[:400]}"
    return text


def create(endpoint, name: str) -> str:
    ensure_role(endpoint)
    ok(
        endpoint,
        "POST",
        "/2015-03-31/functions",
        json.dumps(
            {
                "FunctionName": name,
                "Runtime": "python3.12",
                "Role": ROLE,
                "Handler": "index.handler",
                "Code": {"ZipFile": package()},
            }
        ),
    )
    return name


def function_arn(name: str) -> str:
    return f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{name}"


def publish(endpoint, name: str) -> str:
    """Publish the function's current code; re-running answers the same version."""
    answer = json.loads(ok(endpoint, "POST", f"/2015-03-31/functions/{name}/versions"))
    return answer["Version"]


def queue(endpoint, name: str) -> str:
    """An SQS queue to map: an event source needs a source, and a create is idempotent."""
    body = urlencode({"Action": "CreateQueue", "Version": "2012-11-05", "QueueName": name})
    status, text = signed.request(endpoint, "sqs", ACCOUNT, REGION, "POST", "/", body, FORM)
    assert status == 200, f"CreateQueue answered {status}: {text[:300]}"
    return f"arn:aws:sqs:{REGION}:{ACCOUNT}:{name}"


def event_source_mapping(endpoint, name: str, source_arn: str) -> str:
    """Create this test's own mapping and return its UUID; a re-run reads the existing one."""
    body = json.dumps({"FunctionName": name, "EventSourceArn": source_arn, "BatchSize": 10})
    status, text = call(endpoint, "POST", "/2015-03-31/event-source-mappings", body)
    if 200 <= status < 300:
        return json.loads(text)["UUID"]
    assert status == 409 and "ResourceConflict" in text, f"{status}: {text[:300]}"
    query = urlencode({"FunctionName": name})
    listed = json.loads(
        ok(endpoint, "GET", f"/2015-03-31/event-source-mappings?{query}")
    )
    for mapping in listed["EventSourceMappings"]:
        if mapping["EventSourceArn"] == source_arn:
            return mapping["UUID"]
    raise AssertionError(f"no mapping for {source_arn}")


def layer(endpoint, name: str) -> tuple[str, str]:
    """Publish a version of this test's own layer; returns (version ARN, version number)."""
    answer = json.loads(
        ok(
            endpoint,
            "POST",
            f"/2015-03-31/layers/{name}/versions",
            json.dumps(
                {
                    "Content": {"ZipFile": package()},
                    "CompatibleRuntimes": ["python3.12"],
                }
            ),
        )
    )
    return answer["LayerVersionArn"], str(answer["Version"])


def durable(endpoint) -> str:
    """A function whose invocations open a durable execution."""
    name = create(endpoint, "ops-lambda-durable")
    ok(
        endpoint,
        "PUT",
        f"/2015-03-31/functions/{name}/configuration",
        json.dumps({"DurableConfig": {"Enabled": True, "ExecutionTimeout": 900}}),
    )
    return name


def durable_execution(endpoint) -> tuple[str, str]:
    """One invocation's (execution ARN, checkpoint token)."""
    name = durable(endpoint)
    status, headers, body = signed.request_bytes(
        endpoint,
        "lambda",
        ACCOUNT,
        REGION,
        "POST",
        f"/2015-03-31/functions/{name}/invocations",
        json.dumps({"value": "durable"}),
    )
    assert status == 200, f"invoke answered {status}: {body[:300]}"
    arn = headers.get("x-amz-durable-execution-arn")
    token = headers.get("x-amz-durable-checkpoint-token")
    assert arn and token, headers
    return arn, token


def callback(endpoint) -> tuple[str, str, str]:
    """A callback operation left open on a fresh execution: (ARN, callback id, checkpoint token)."""
    arn, token = durable_execution(endpoint)
    answer = json.loads(
        ok(
            endpoint,
            "POST",
            f"/2025-12-01/durable-executions/{arn}/checkpoint",
            json.dumps(
                {
                    "CheckpointToken": token,
                    "Updates": [
                        {
                            "Id": "callback",
                            "Type": "CALLBACK",
                            "Action": "START",
                            "Name": "wait",
                            "CallbackOptions": {
                                "TimeoutSeconds": 300,
                                "HeartbeatTimeoutSeconds": 60,
                            },
                        }
                    ],
                }
            ),
        )
    )
    for entry in answer["NewExecutionState"]["Operations"]:
        if entry["Id"] == "callback":
            return arn, entry["CallbackDetails"]["CallbackId"], answer["CheckpointToken"]
    raise AssertionError("the checkpoint answer carries no callback operation")


def operation(endpoint, arn: str, token: str, name: str) -> dict:
    """One operation from the execution's state, by id."""
    query = urlencode({"CheckpointToken": token})
    answer = json.loads(
        ok(endpoint, "GET", f"/2025-12-01/durable-executions/{arn}/state?{query}")
    )
    for entry in answer["Operations"]:
        if entry["Id"] == name:
            return entry
    raise AssertionError(f"no operation {name} in {answer}")


def test_list_functions_answers_a_functions_array(s3_endpoint):
    assert "Functions" in json.loads(ok(s3_endpoint, "GET", "/2015-03-31/functions/"))


def test_create_function_is_read_back_by_get(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-created")
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}"))
    assert answer["Configuration"]["FunctionName"] == name


def test_invoke_function_runs_the_handler(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-invoked")
    text = ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/invocations",
        json.dumps({"value": "ran"}),
    )
    assert json.loads(text) == {"echo": "ran"}


def test_delete_function_removes_the_function_it_created(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-deleted")
    ok(s3_endpoint, "DELETE", f"/2015-03-31/functions/{name}")
    status, text = call(s3_endpoint, "GET", f"/2015-03-31/functions/{name}")
    assert status == 404, text[:300]


def test_get_function_configuration_names_the_function(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-configured")
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/configuration"))
    assert answer["FunctionName"] == name
    assert answer["Runtime"] == "python3.12"


def test_update_function_code_replaces_the_package(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-recoded")
    answer = json.loads(
        ok(
            s3_endpoint,
            "PUT",
            f"/2015-03-31/functions/{name}/code",
            json.dumps({"ZipFile": package()}),
        )
    )
    assert answer["CodeSha256"]
    assert answer["CodeSize"] > 0


def test_update_function_configuration_applies_the_settings(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-settings")
    ok(
        s3_endpoint,
        "PUT",
        f"/2015-03-31/functions/{name}/configuration",
        json.dumps({"Description": "ops settings", "MemorySize": 256, "Timeout": 5}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/configuration"))
    assert answer["Description"] == "ops settings"
    assert answer["MemorySize"] == 256
    assert answer["Timeout"] == 5


def test_add_permission_records_a_statement(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-permitted")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/policy",
        json.dumps(
            {
                "StatementId": "ops-invoke",
                "Action": "lambda:InvokeFunction",
                "Principal": "events.amazonaws.com",
            }
        ),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/policy"))
    policy = json.loads(answer["Policy"])
    assert "ops-invoke" in [statement["Sid"] for statement in policy["Statement"]]


def test_get_policy_returns_the_statement(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-policy")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/policy",
        json.dumps(
            {
                "StatementId": "ops-policy",
                "Action": "lambda:InvokeFunction",
                "Principal": "sns.amazonaws.com",
            }
        ),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/policy"))
    policy = json.loads(answer["Policy"])
    assert [statement["Sid"] for statement in policy["Statement"]] == ["ops-policy"]


def test_remove_permission_drops_the_statement_it_added(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-unpermitted")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/policy",
        json.dumps(
            {
                "StatementId": "ops-removed",
                "Action": "lambda:InvokeFunction",
                "Principal": "events.amazonaws.com",
            }
        ),
    )
    ok(s3_endpoint, "DELETE", f"/2015-03-31/functions/{name}/policy/ops-removed")
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/policy"))
    assert json.loads(answer["Policy"])["Statement"] == []


def test_publish_version_creates_a_numbered_version(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-versioned")
    answer = json.loads(ok(s3_endpoint, "POST", f"/2015-03-31/functions/{name}/versions"))
    assert answer["Version"].isdigit()
    assert answer["FunctionArn"] == f"{function_arn(name)}:{answer['Version']}"


def test_list_versions_by_function_includes_the_published_version(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-version-list")
    version = publish(s3_endpoint, name)
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/versions"))
    assert version in [entry["Version"] for entry in answer["Versions"]]


def test_create_alias_is_read_back_by_get(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-aliased")
    version = publish(s3_endpoint, name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/aliases",
        json.dumps({"Name": "ops-alias", "FunctionVersion": version}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/aliases/ops-alias"))
    assert answer["Name"] == "ops-alias"


def test_get_alias_reports_the_target_version(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-alias-read")
    version = publish(s3_endpoint, name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/aliases",
        json.dumps({"Name": "ops-alias-read", "FunctionVersion": version}),
    )
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/aliases/ops-alias-read")
    )
    assert answer["FunctionVersion"] == version
    assert answer["AliasArn"] == f"{function_arn(name)}:ops-alias-read"


def test_update_alias_changes_the_description(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-alias-updated")
    version = publish(s3_endpoint, name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/aliases",
        json.dumps({"Name": "ops-alias-updated", "FunctionVersion": version}),
    )
    ok(
        s3_endpoint,
        "PUT",
        f"/2015-03-31/functions/{name}/aliases/ops-alias-updated",
        json.dumps({"Description": "ops alias"}),
    )
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/aliases/ops-alias-updated")
    )
    assert answer["Description"] == "ops alias"


def test_list_aliases_includes_the_alias(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-alias-list")
    version = publish(s3_endpoint, name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/aliases",
        json.dumps({"Name": "ops-alias-list", "FunctionVersion": version}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/aliases"))
    assert "ops-alias-list" in [alias["Name"] for alias in answer["Aliases"]]


def test_delete_alias_removes_the_alias_it_created(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-alias-deleted")
    version = publish(s3_endpoint, name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/aliases",
        json.dumps({"Name": "ops-alias-gone", "FunctionVersion": version}),
    )
    ok(s3_endpoint, "DELETE", f"/2015-03-31/functions/{name}/aliases/ops-alias-gone")
    status, text = call(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/aliases/ops-alias-gone")
    assert status == 404, text[:300]


def test_tag_resource_writes_the_tags_list_tags_reads(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-tagged")
    arn = function_arn(name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/tags/{arn}",
        json.dumps({"Tags": {"ops-write": "ok"}}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/tags/{arn}"))
    assert answer["Tags"]["ops-write"] == "ok"


def test_list_tags_reports_the_created_tags(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-tag-list")
    arn = function_arn(name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/tags/{arn}",
        json.dumps({"Tags": {"ops-list": "one"}}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/tags/{arn}"))
    assert answer["Tags"]["ops-list"] == "one"


def test_untag_resource_removes_only_the_named_key(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-untagged")
    arn = function_arn(name)
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/tags/{arn}",
        json.dumps({"Tags": {"ops-drop": "yes", "ops-keep": "yes"}}),
    )
    ok(s3_endpoint, "DELETE", f"/2015-03-31/tags/{arn}?{urlencode({'tagKeys': 'ops-drop'})}")
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/tags/{arn}"))
    assert "ops-drop" not in answer["Tags"]
    assert answer["Tags"]["ops-keep"] == "yes"


def test_create_event_source_mapping_is_read_back_by_get(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-esm-created")
    ident = event_source_mapping(s3_endpoint, name, queue(s3_endpoint, "ops-lambda-esm-created"))
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/event-source-mappings/{ident}"))
    assert answer["UUID"] == ident


def test_get_event_source_mapping_reports_the_source(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-esm-read")
    source = queue(s3_endpoint, "ops-lambda-esm-read")
    ident = event_source_mapping(s3_endpoint, name, source)
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/event-source-mappings/{ident}"))
    assert answer["EventSourceArn"] == source
    assert answer["FunctionArn"] == function_arn(name)


def test_list_event_source_mappings_filters_by_function(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-esm-listed")
    ident = event_source_mapping(s3_endpoint, name, queue(s3_endpoint, "ops-lambda-esm-listed"))
    query = urlencode({"FunctionName": name})
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2015-03-31/event-source-mappings?{query}")
    )
    assert [mapping["UUID"] for mapping in answer["EventSourceMappings"]] == [ident]


def test_update_event_source_mapping_changes_the_batch_size(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-esm-updated")
    ident = event_source_mapping(s3_endpoint, name, queue(s3_endpoint, "ops-lambda-esm-updated"))
    ok(
        s3_endpoint,
        "PUT",
        f"/2015-03-31/event-source-mappings/{ident}",
        json.dumps({"BatchSize": 5}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/event-source-mappings/{ident}"))
    assert answer["BatchSize"] == 5


def test_delete_event_source_mapping_removes_the_mapping_it_created(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-esm-deleted")
    ident = event_source_mapping(s3_endpoint, name, queue(s3_endpoint, "ops-lambda-esm-deleted"))
    ok(s3_endpoint, "DELETE", f"/2015-03-31/event-source-mappings/{ident}")
    status, text = call(s3_endpoint, "GET", f"/2015-03-31/event-source-mappings/{ident}")
    assert status == 404, text[:300]


def test_create_function_url_config_is_read_back_by_get(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-url-created")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/url",
        json.dumps({"AuthType": "NONE"}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/url"))
    assert answer["FunctionUrl"].startswith("https://")


def test_get_function_url_config_reports_the_url(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-url-read")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/url",
        json.dumps({"AuthType": "NONE"}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/url"))
    assert answer["FunctionArn"] == function_arn(name)
    assert answer["AuthType"] == "NONE"


def test_update_function_url_config_changes_the_auth_type(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-url-updated")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/url",
        json.dumps({"AuthType": "NONE"}),
    )
    ok(
        s3_endpoint,
        "PUT",
        f"/2015-03-31/functions/{name}/url",
        json.dumps({"AuthType": "AWS_IAM"}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/url"))
    assert answer["AuthType"] == "AWS_IAM"


def test_list_function_url_configs_includes_the_config(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-url-listed")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/url",
        json.dumps({"AuthType": "NONE"}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/urls"))
    assert [config["FunctionArn"] for config in answer["FunctionUrlConfigs"]] == [
        function_arn(name)
    ]


def test_delete_function_url_config_removes_the_config_it_created(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-url-deleted")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/functions/{name}/url",
        json.dumps({"AuthType": "NONE"}),
    )
    ok(s3_endpoint, "DELETE", f"/2015-03-31/functions/{name}/url")
    status, text = call(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/url")
    assert status == 404, text[:300]


def test_put_function_concurrency_reserves_executions(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-concurrent")
    answer = json.loads(
        ok(
            s3_endpoint,
            "PUT",
            f"/2015-03-31/functions/{name}/concurrency",
            json.dumps({"ReservedConcurrentExecutions": 5}),
        )
    )
    assert answer["ReservedConcurrentExecutions"] == 5


def test_get_function_concurrency_reads_the_reservation(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-concurrency-read")
    ok(
        s3_endpoint,
        "PUT",
        f"/2015-03-31/functions/{name}/concurrency",
        json.dumps({"ReservedConcurrentExecutions": 3}),
    )
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/concurrency")
    )
    assert answer["ReservedConcurrentExecutions"] == 3


def test_delete_function_concurrency_clears_the_reservation(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-concurrency-deleted")
    ok(
        s3_endpoint,
        "PUT",
        f"/2015-03-31/functions/{name}/concurrency",
        json.dumps({"ReservedConcurrentExecutions": 2}),
    )
    ok(s3_endpoint, "DELETE", f"/2015-03-31/functions/{name}/concurrency")
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2015-03-31/functions/{name}/concurrency")
    )
    assert "ReservedConcurrentExecutions" not in answer


def test_put_function_event_invoke_config_is_read_back(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-async")
    ok(
        s3_endpoint,
        "PUT",
        f"/2019-09-25/functions/{name}/event-invoke-config",
        json.dumps({"MaximumRetryAttempts": 1}),
    )
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2019-09-25/functions/{name}/event-invoke-config")
    )
    assert answer["MaximumRetryAttempts"] == 1


def test_get_function_event_invoke_config_reports_the_settings(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-async-read")
    ok(
        s3_endpoint,
        "PUT",
        f"/2019-09-25/functions/{name}/event-invoke-config",
        json.dumps({"MaximumEventAgeInSeconds": 60}),
    )
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2019-09-25/functions/{name}/event-invoke-config")
    )
    assert answer["MaximumEventAgeInSeconds"] == 60
    # 1.5.45 qualifies the ARN with $LATEST; the older releases answered it bare.
    assert answer["FunctionArn"].startswith(function_arn(name))


def test_delete_function_event_invoke_config_removes_the_config_it_created(s3_endpoint):
    name = create(s3_endpoint, "ops-lambda-async-deleted")
    ok(
        s3_endpoint,
        "PUT",
        f"/2019-09-25/functions/{name}/event-invoke-config",
        json.dumps({"MaximumRetryAttempts": 0}),
    )
    ok(s3_endpoint, "DELETE", f"/2019-09-25/functions/{name}/event-invoke-config")
    status, text = call(
        s3_endpoint, "GET", f"/2019-09-25/functions/{name}/event-invoke-config"
    )
    assert status == 404, text[:300]


def test_publish_layer_version_creates_a_version(s3_endpoint):
    arn, version = layer(s3_endpoint, "ops-layer-published")
    assert version.isdigit()
    assert arn.endswith(f":{version}")


def test_get_layer_version_reads_the_published_version(s3_endpoint):
    arn, version = layer(s3_endpoint, "ops-layer-read")
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2015-03-31/layers/ops-layer-read/versions/{version}")
    )
    assert answer["LayerVersionArn"] == arn


def test_get_layer_version_by_arn_reads_the_published_version(s3_endpoint):
    arn, version = layer(s3_endpoint, "ops-layer-by-arn")
    query = urlencode({"find": "LayerVersion", "Arn": arn}, quote_via=quote)
    answer = json.loads(ok(s3_endpoint, "GET", f"/2015-03-31/layers?{query}"))
    assert answer["LayerVersionArn"] == arn
    assert str(answer["Version"]) == version


def test_list_layer_versions_includes_the_published_version(s3_endpoint):
    _, version = layer(s3_endpoint, "ops-layer-versions")
    answer = json.loads(ok(s3_endpoint, "GET", "/2015-03-31/layers/ops-layer-versions/versions"))
    assert int(version) in [entry["Version"] for entry in answer["LayerVersions"]]


def test_list_layers_includes_the_layer(s3_endpoint):
    arn, _ = layer(s3_endpoint, "ops-layer-listed")
    answer = json.loads(ok(s3_endpoint, "GET", "/2015-03-31/layers"))
    layers = {entry["LayerName"]: entry for entry in answer["Layers"]}
    assert layers["ops-layer-listed"]["LatestMatchingVersion"]["LayerVersionArn"] == arn


def test_add_layer_version_permission_records_a_statement(s3_endpoint):
    _, version = layer(s3_endpoint, "ops-layer-permitted")
    answer = json.loads(
        ok(
            s3_endpoint,
            "POST",
            f"/2015-03-31/layers/ops-layer-permitted/versions/{version}/policy",
            json.dumps(
                {
                    "StatementId": "ops-public",
                    "Action": "lambda:GetLayerVersion",
                    "Principal": "*",
                }
            ),
        )
    )
    assert json.loads(answer["Statement"])["Sid"] == "ops-public"


def test_get_layer_version_policy_returns_the_statement(s3_endpoint):
    _, version = layer(s3_endpoint, "ops-layer-policy")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/layers/ops-layer-policy/versions/{version}/policy",
        json.dumps(
            {
                "StatementId": "ops-policy",
                "Action": "lambda:GetLayerVersion",
                "Principal": "*",
            }
        ),
    )
    answer = json.loads(
        ok(
            s3_endpoint,
            "GET",
            f"/2015-03-31/layers/ops-layer-policy/versions/{version}/policy",
        )
    )
    policy = json.loads(answer["Policy"])
    assert [statement["Sid"] for statement in policy["Statement"]] == ["ops-policy"]


def test_remove_layer_version_permission_drops_the_statement_it_added(s3_endpoint):
    _, version = layer(s3_endpoint, "ops-layer-unpermitted")
    ok(
        s3_endpoint,
        "POST",
        f"/2015-03-31/layers/ops-layer-unpermitted/versions/{version}/policy",
        json.dumps(
            {
                "StatementId": "ops-removed",
                "Action": "lambda:GetLayerVersion",
                "Principal": "*",
            }
        ),
    )
    ok(
        s3_endpoint,
        "DELETE",
        f"/2015-03-31/layers/ops-layer-unpermitted/versions/{version}/policy/ops-removed",
    )
    status, text = call(
        s3_endpoint,
        "GET",
        f"/2015-03-31/layers/ops-layer-unpermitted/versions/{version}/policy",
    )
    assert status == 404, text[:300]


def test_delete_layer_version_removes_the_version_it_published(s3_endpoint):
    _, version = layer(s3_endpoint, "ops-layer-deleted")
    ok(s3_endpoint, "DELETE", f"/2015-03-31/layers/ops-layer-deleted/versions/{version}")
    status, text = call(
        s3_endpoint, "GET", f"/2015-03-31/layers/ops-layer-deleted/versions/{version}"
    )
    assert status == 404, text[:300]


def test_checkpoint_durable_execution_advances_the_token(s3_endpoint):
    arn, token = durable_execution(s3_endpoint)
    answer = json.loads(
        ok(
            s3_endpoint,
            "POST",
            f"/2025-12-01/durable-executions/{arn}/checkpoint",
            json.dumps(
                {
                    "CheckpointToken": token,
                    "Updates": [
                        {"Id": "step-one", "Type": "STEP", "Action": "START", "Name": "first"}
                    ],
                }
            ),
        )
    )
    assert answer["CheckpointToken"] != token
    assert "step-one" in [op["Id"] for op in answer["NewExecutionState"]["Operations"]]


def test_get_durable_execution_reports_the_invocation(s3_endpoint):
    arn, _ = durable_execution(s3_endpoint)
    answer = json.loads(ok(s3_endpoint, "GET", f"/2025-12-01/durable-executions/{arn}"))
    assert answer["DurableExecutionArn"] == arn
    assert answer["Status"] == "RUNNING"


def test_get_durable_execution_state_lists_the_operations(s3_endpoint):
    arn, token = durable_execution(s3_endpoint)
    query = urlencode({"CheckpointToken": token})
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2025-12-01/durable-executions/{arn}/state?{query}")
    )
    assert [op["Type"] for op in answer["Operations"]] == ["EXECUTION"]


def test_get_durable_execution_history_records_the_start(s3_endpoint):
    arn, _ = durable_execution(s3_endpoint)
    answer = json.loads(
        ok(s3_endpoint, "GET", f"/2025-12-01/durable-executions/{arn}/history")
    )
    assert "ExecutionStarted" in [event["EventType"] for event in answer["Events"]]


def test_list_durable_executions_by_function_includes_the_execution(s3_endpoint):
    name = durable(s3_endpoint)
    arn, _ = durable_execution(s3_endpoint)
    answer = json.loads(
        ok(
            s3_endpoint,
            "GET",
            f"/2025-12-01/functions/{name}/durable-executions",
        )
    )
    assert arn in [entry["DurableExecutionArn"] for entry in answer["DurableExecutions"]]


def test_stop_durable_execution_ends_it(s3_endpoint):
    arn, _ = durable_execution(s3_endpoint)
    ok(
        s3_endpoint,
        "POST",
        f"/2025-12-01/durable-executions/{arn}/stop",
        json.dumps({"ErrorType": "OpsStopped", "ErrorMessage": "stopped by the test"}),
    )
    answer = json.loads(ok(s3_endpoint, "GET", f"/2025-12-01/durable-executions/{arn}"))
    assert answer["Status"] == "STOPPED"
    assert answer["Error"]["ErrorType"] == "OpsStopped"


def test_send_durable_execution_callback_success_closes_the_callback(s3_endpoint):
    arn, ident, _ = callback(s3_endpoint)
    ok(s3_endpoint, "POST", f"/2025-12-01/durable-execution-callbacks/{ident}/succeed", "done")
    history = json.loads(
        ok(s3_endpoint, "GET", f"/2025-12-01/durable-executions/{arn}/history")
    )
    closed = [
        event for event in history["Events"] if event["EventType"] == "CallbackSucceeded"
    ]
    assert len(closed) == 1
    assert closed[0]["CallbackSucceededDetails"]["Result"]["Payload"] == "done"


def test_send_durable_execution_callback_failure_closes_the_callback(s3_endpoint):
    arn, ident, _ = callback(s3_endpoint)
    ok(
        s3_endpoint,
        "POST",
        f"/2025-12-01/durable-execution-callbacks/{ident}/fail",
        json.dumps({"ErrorType": "OpsFailed", "ErrorMessage": "nope"}),
    )
    history = json.loads(
        ok(s3_endpoint, "GET", f"/2025-12-01/durable-executions/{arn}/history")
    )
    closed = [
        event for event in history["Events"] if event["EventType"] == "CallbackFailed"
    ]
    assert len(closed) == 1
    assert closed[0]["CallbackFailedDetails"]["Error"]["Payload"]["ErrorType"] == "OpsFailed"


def test_send_durable_execution_callback_heartbeat_answers_the_callback(s3_endpoint):
    arn, ident, token = callback(s3_endpoint)
    status, text = call(
        s3_endpoint, "POST", f"/2025-12-01/durable-execution-callbacks/{ident}/heartbeat"
    )
    assert status == 200, text[:300]
    assert operation(s3_endpoint, arn, token, "callback")["Status"] == "STARTED"
