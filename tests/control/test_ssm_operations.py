"""SSM Parameter Store on the wire: every console action, driven through the JSON protocol.

A parameter written here is left in place; the delete actions write their own, and the tag
operations leave the parameter they tagged. Documents and automation executions follow the
same rule: only the delete test removes a document, and it creates that document to remove.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "AmazonSSM."
HEADERS = {"Content-Type": "application/x-amz-json-1.0"}

# Setting ids the emulator knows, each with the values it accepts.
TIER_SETTING = "/ssm/parameter-store/default-parameter-tier"
APPMANAGER_SETTING = "/ssm/appmanager/appmanager-enabled"
OPSINSIGHTS_SETTING = "/ssm/opsinsights/opscenter"

COMMAND_DOCUMENT = "ops-ssm-document"
COMMAND_CONTENT = json.dumps(
    {
        "schemaVersion": "2.2",
        "description": "ops: read a parameter",
        "mainSteps": [
            {
                "name": "Read",
                "action": "aws:runShellScript",
                "inputs": {"runCommand": ["echo ops"]},
            }
        ],
    }
)
# The emulator runs aws:sleep and an aws:executeAwsApi step over SSM itself, so an execution
# reaches Success with no dependant (role, instance, runtime) behind it.
AUTOMATION_DOCUMENT = "ops-ssm-automation"
AUTOMATION_CONTENT = json.dumps(
    {
        "schemaVersion": "0.3",
        "description": "ops: wait, then read a service setting",
        "mainSteps": [
            {"name": "Wait", "action": "aws:sleep", "inputs": {"Duration": "PT1S"}},
            {
                "name": "ReadSetting",
                "action": "aws:executeAwsApi",
                "inputs": {
                    "Service": "ssm",
                    "Api": "GetServiceSetting",
                    "SettingId": TIER_SETTING,
                },
            },
        ],
    }
)
STOPPABLE_DOCUMENT = "ops-ssm-automation-stoppable"
STOPPABLE_CONTENT = json.dumps(
    {
        "schemaVersion": "0.3",
        "description": "ops: sleep long enough to be stopped",
        "mainSteps": [
            {"name": "Wait", "action": "aws:sleep", "inputs": {"Duration": "PT10S"}}
        ],
    }
)


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "ssm", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def put(endpoint, name: str, value: str) -> None:
    # Overwrite keeps a re-run against the lab's existing parameter a success.
    ok(endpoint, "PutParameter", Name=name, Value=value, Type="String", Overwrite=True)


def wait_for(read, decided, seconds: float = 10.0):
    """Poll `read` until `decided` holds: a background thread's state is read, never assumed."""
    deadline = time.monotonic() + seconds
    value = read()
    while not decided(value) and time.monotonic() < deadline:
        time.sleep(0.1)
        value = read()
    assert decided(value), value
    return value


def create_document(endpoint, name: str, content: str, document_type: str = "Command"):
    """`CreateDocument` refuses a re-run's document; a lab sweep reuses the one it left."""
    status, text = call(
        endpoint, "CreateDocument", Name=name, Content=content, DocumentType=document_type
    )
    if status == 200:
        return json.loads(text)["DocumentDescription"]
    assert "DocumentAlreadyExists" in text, f"CreateDocument answered {status}: {text[:400]}"
    return None


def history_of(endpoint, name: str) -> list[dict]:
    """Every page of a parameter's history: each put adds a version, and so does a re-run."""
    entries: list[dict] = []
    params = {"Name": name}
    while True:
        page = ok(endpoint, "GetParameterHistory", **params)
        entries.extend(page["Parameters"])
        if not page.get("NextToken"):
            return entries
        params["NextToken"] = page["NextToken"]


def start_automation(endpoint, name: str, content: str) -> str:
    create_document(endpoint, name, content, "Automation")
    return ok(endpoint, "StartAutomationExecution", DocumentName=name)[
        "AutomationExecutionId"
    ]


def execution(endpoint, execution_id: str) -> dict:
    found = ok(endpoint, "GetAutomationExecution", AutomationExecutionId=execution_id)
    return found["AutomationExecution"]


def settled(endpoint, execution_id: str) -> dict:
    """The execution once its background thread has left Pending/InProgress."""
    return wait_for(
        lambda: execution(endpoint, execution_id),
        lambda found: found["AutomationExecutionStatus"] not in ("Pending", "InProgress"),
    )


def test_put_parameter_is_read_back_by_get(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/created", "kept")
    assert ok(s3_endpoint, "GetParameter", Name="/ops/ssm/created")["Parameter"]["Value"] == "kept"


def test_put_parameter_is_read_back_by_describe(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/described", "listed")
    listed = ok(s3_endpoint, "DescribeParameters")["Parameters"]
    assert "/ops/ssm/described" in [parameter["Name"] for parameter in listed]


def test_delete_parameter_removes_the_parameter_it_created(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/deleted", "gone")
    ok(s3_endpoint, "DeleteParameter", Name="/ops/ssm/deleted")
    status, text = call(s3_endpoint, "GetParameter", Name="/ops/ssm/deleted")
    assert status == 400, text[:300]
    assert "ParameterNotFound" in text


def test_get_parameters_answers_the_named_parameters_and_flags_the_missing(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/batch", "batched")
    answer = ok(
        s3_endpoint, "GetParameters", Names=["/ops/ssm/batch", "/ops/ssm/never-written"]
    )
    assert [parameter["Name"] for parameter in answer["Parameters"]] == ["/ops/ssm/batch"]
    assert answer["InvalidParameters"] == ["/ops/ssm/never-written"]


def test_get_parameters_by_path_reads_a_level_and_the_subtree_when_recursive(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/tree/alpha", "a")
    put(s3_endpoint, "/ops/ssm/tree/nested/beta", "b")
    shallow = ok(s3_endpoint, "GetParametersByPath", Path="/ops/ssm/tree")["Parameters"]
    names = [parameter["Name"] for parameter in shallow]
    assert "/ops/ssm/tree/alpha" in names
    assert "/ops/ssm/tree/nested/beta" not in names
    deep = ok(
        s3_endpoint, "GetParametersByPath", Path="/ops/ssm/tree/", Recursive=True
    )["Parameters"]
    assert "/ops/ssm/tree/nested/beta" in [parameter["Name"] for parameter in deep]


def test_delete_parameters_removes_only_the_parameters_it_created(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/bulk-one", "one")
    put(s3_endpoint, "/ops/ssm/bulk-two", "two")
    answer = ok(
        s3_endpoint,
        "DeleteParameters",
        Names=["/ops/ssm/bulk-one", "/ops/ssm/bulk-two", "/ops/ssm/bulk-absent"],
    )
    assert sorted(answer["DeletedParameters"]) == ["/ops/ssm/bulk-one", "/ops/ssm/bulk-two"]
    assert answer["InvalidParameters"] == ["/ops/ssm/bulk-absent"]
    for name in ("/ops/ssm/bulk-one", "/ops/ssm/bulk-two"):
        status, text = call(s3_endpoint, "GetParameter", Name=name)
        assert status == 400, text[:300]
        assert "ParameterNotFound" in text


def test_get_parameter_history_reports_every_version_in_order(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/history", "first")
    put(s3_endpoint, "/ops/ssm/history", "second")
    history = history_of(s3_endpoint, "/ops/ssm/history")
    assert history[-2]["Value"] == "first"
    assert history[-1]["Value"] == "second"
    assert history[-1]["Name"] == "/ops/ssm/history"
    versions = [entry["Version"] for entry in history]
    assert versions == sorted(versions)


def test_label_parameter_version_labels_the_version_and_refuses_a_reserved_name(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/labelled", "labelled")
    version = ok(s3_endpoint, "GetParameter", Name="/ops/ssm/labelled")["Parameter"]["Version"]
    answer = ok(
        s3_endpoint,
        "LabelParameterVersion",
        Name="/ops/ssm/labelled",
        ParameterVersion=version,
        Labels=["ops-current", "aws:reserved"],
    )
    assert answer["ParameterVersion"] == version
    assert answer["InvalidLabels"] == ["aws:reserved"]
    labelled = ok(s3_endpoint, "GetParameter", Name="/ops/ssm/labelled:ops-current")[
        "Parameter"
    ]
    assert labelled["Value"] == "labelled"
    assert labelled["Selector"] == ":ops-current"


def test_add_tags_to_resource_is_read_back_by_list_tags(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/tagged", "tagged")
    ok(
        s3_endpoint,
        "AddTagsToResource",
        ResourceType="Parameter",
        ResourceId="/ops/ssm/tagged",
        Tags=[{"Key": "team", "Value": "ops"}, {"Key": "env", "Value": "lab"}],
    )
    tags = ok(
        s3_endpoint,
        "ListTagsForResource",
        ResourceType="Parameter",
        ResourceId="/ops/ssm/tagged",
    )["TagList"]
    assert {"Key": "team", "Value": "ops"} in tags
    assert {"Key": "env", "Value": "lab"} in tags


def test_remove_tags_from_resource_leaves_the_other_tags(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/tags-removed", "tagged")
    ok(
        s3_endpoint,
        "AddTagsToResource",
        ResourceType="Parameter",
        ResourceId="/ops/ssm/tags-removed",
        Tags=[{"Key": "keep", "Value": "kept"}, {"Key": "drop", "Value": "dropped"}],
    )
    ok(
        s3_endpoint,
        "RemoveTagsFromResource",
        ResourceType="Parameter",
        ResourceId="/ops/ssm/tags-removed",
        TagKeys=["drop"],
    )
    tags = ok(
        s3_endpoint,
        "ListTagsForResource",
        ResourceType="Parameter",
        ResourceId="/ops/ssm/tags-removed",
    )["TagList"]
    assert {"Key": "keep", "Value": "kept"} in tags
    assert "drop" not in [tag["Key"] for tag in tags]


def test_list_tags_for_resource_reads_a_parameter_by_name(s3_endpoint):
    put(s3_endpoint, "/ops/ssm/tag-listed", "tagged")
    ok(
        s3_endpoint,
        "AddTagsToResource",
        ResourceId="/ops/ssm/tag-listed",
        Tags=[{"Key": "purpose", "Value": "listed"}],
    )
    tags = ok(s3_endpoint, "ListTagsForResource", ResourceId="/ops/ssm/tag-listed")[
        "TagList"
    ]
    assert tags == [{"Key": "purpose", "Value": "listed"}]


def test_get_service_setting_answers_a_known_setting(s3_endpoint):
    setting = ok(s3_endpoint, "GetServiceSetting", SettingId=TIER_SETTING)["ServiceSetting"]
    assert setting["SettingId"] == TIER_SETTING
    assert setting["SettingValue"] in ("Standard", "Advanced", "Intelligent-Tiering")
    assert setting["Status"] in ("Default", "Customized")
    assert setting["ARN"].endswith(f":servicesetting{TIER_SETTING}")


def test_update_service_setting_is_read_back_by_get_service_setting(s3_endpoint):
    ok(s3_endpoint, "UpdateServiceSetting", SettingId=APPMANAGER_SETTING, SettingValue="True")
    setting = ok(s3_endpoint, "GetServiceSetting", SettingId=APPMANAGER_SETTING)[
        "ServiceSetting"
    ]
    assert setting["SettingValue"] == "True"
    assert setting["Status"] == "Customized"
    assert setting["LastModifiedUser"] != "System"


def test_reset_service_setting_restores_the_default(s3_endpoint):
    ok(s3_endpoint, "UpdateServiceSetting", SettingId=OPSINSIGHTS_SETTING, SettingValue="Enabled")
    reset = ok(s3_endpoint, "ResetServiceSetting", SettingId=OPSINSIGHTS_SETTING)["ServiceSetting"]
    assert reset["SettingValue"] == "Disabled"
    assert reset["Status"] == "Default"
    read_back = ok(s3_endpoint, "GetServiceSetting", SettingId=OPSINSIGHTS_SETTING)[
        "ServiceSetting"
    ]
    assert read_back["Status"] == "Default"


def test_create_document_is_read_back_by_describe(s3_endpoint):
    created = create_document(s3_endpoint, COMMAND_DOCUMENT, COMMAND_CONTENT)
    if created is not None:  # a lab sweep gets DocumentAlreadyExists instead
        assert created["Name"] == COMMAND_DOCUMENT
        assert created["DocumentType"] == "Command"
    described = ok(s3_endpoint, "DescribeDocument", Name=COMMAND_DOCUMENT)["Document"]
    assert described["Name"] == COMMAND_DOCUMENT


def test_describe_document_reports_the_document_it_created(s3_endpoint):
    create_document(s3_endpoint, COMMAND_DOCUMENT, COMMAND_CONTENT)
    described = wait_for(
        lambda: ok(s3_endpoint, "DescribeDocument", Name=COMMAND_DOCUMENT)["Document"],
        lambda document: document["Status"] == "Active",
    )
    assert described["DocumentType"] == "Command"
    assert described["DocumentFormat"] == "JSON"
    assert described["DocumentVersion"] == "1"
    assert described["Owner"] == ACCOUNT
    assert described["Description"] == "ops: read a parameter"


def test_get_document_returns_the_content_it_was_created_with(s3_endpoint):
    create_document(s3_endpoint, COMMAND_DOCUMENT, COMMAND_CONTENT)
    document = ok(s3_endpoint, "GetDocument", Name=COMMAND_DOCUMENT)
    assert document["Name"] == COMMAND_DOCUMENT
    assert document["DocumentFormat"] == "JSON"
    content = json.loads(document["Content"])
    assert content["schemaVersion"] == "2.2"
    assert content["mainSteps"][0]["action"] == "aws:runShellScript"


def test_list_documents_includes_the_document(s3_endpoint):
    create_document(s3_endpoint, COMMAND_DOCUMENT, COMMAND_CONTENT)
    listed = ok(
        s3_endpoint,
        "ListDocuments",
        Filters=[{"Key": "Name", "Values": [COMMAND_DOCUMENT]}],
    )["DocumentIdentifiers"]
    assert [document["Name"] for document in listed] == [COMMAND_DOCUMENT]
    assert listed[0]["DocumentType"] == "Command"


def test_delete_document_removes_the_document_it_created(s3_endpoint):
    create_document(s3_endpoint, "ops-ssm-document-deleted", COMMAND_CONTENT)
    ok(s3_endpoint, "DeleteDocument", Name="ops-ssm-document-deleted")
    status, text = call(s3_endpoint, "DescribeDocument", Name="ops-ssm-document-deleted")
    assert status == 400, text[:300]
    assert "InvalidDocument" in text


def test_start_automation_execution_reports_an_execution_to_read(s3_endpoint):
    execution_id = start_automation(s3_endpoint, AUTOMATION_DOCUMENT, AUTOMATION_CONTENT)
    assert execution_id
    found = execution(s3_endpoint, execution_id)
    assert found["AutomationExecutionId"] == execution_id
    assert found["DocumentName"] == AUTOMATION_DOCUMENT


def test_get_automation_execution_runs_the_document_steps(s3_endpoint):
    execution_id = start_automation(s3_endpoint, AUTOMATION_DOCUMENT, AUTOMATION_CONTENT)
    found = settled(s3_endpoint, execution_id)
    assert found["AutomationExecutionStatus"] == "Success"
    assert [step["StepName"] for step in found["StepExecutions"]] == [
        "Wait",
        "ReadSetting",
    ]
    assert [step["StepStatus"] for step in found["StepExecutions"]] == [
        "Success",
        "Success",
    ]
    assert found["ExecutionEndTime"] >= found["ExecutionStartTime"]


def test_describe_automation_executions_finds_the_execution(s3_endpoint):
    execution_id = start_automation(s3_endpoint, AUTOMATION_DOCUMENT, AUTOMATION_CONTENT)
    settled(s3_endpoint, execution_id)
    listed = ok(
        s3_endpoint,
        "DescribeAutomationExecutions",
        Filters=[{"Key": "ExecutionId", "Values": [execution_id]}],
    )["AutomationExecutionMetadataList"]
    assert [item["AutomationExecutionId"] for item in listed] == [execution_id]
    assert listed[0]["AutomationExecutionStatus"] == "Success"
    assert listed[0]["AutomationType"] == "Local"


def test_stop_automation_execution_cancels_the_execution_it_started(s3_endpoint):
    execution_id = start_automation(s3_endpoint, STOPPABLE_DOCUMENT, STOPPABLE_CONTENT)
    # Wait for the step loop to own the record before cancelling it, so the run's own
    # Status write cannot overwrite the cancel it was handed.
    wait_for(
        lambda: execution(s3_endpoint, execution_id),
        lambda found: found["AutomationExecutionStatus"] == "InProgress",
    )
    ok(s3_endpoint, "StopAutomationExecution", AutomationExecutionId=execution_id)
    found = settled(s3_endpoint, execution_id)
    assert found["AutomationExecutionStatus"] == "Cancelled"
