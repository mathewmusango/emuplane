"""Console catalogue: every GUI action is an AWS API call, run through the same root-signed client."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote

import buckets


def field(name, label="", required=False, kind="text", placeholder="", default=""):
    return {
        "name": name,
        "label": label or name,
        "required": required,
        "type": kind,
        "placeholder": placeholder,
        "default": default,
    }


def _query(service, action, version="2010-05-08", names=(), ok=(200,), transform=None):
    def run(params, account, region, call, s3):
        sent = {name: params[name] for name in names if str(params.get(name, "")).strip()}
        if transform:
            sent = transform(sent)
        status, body = call(
            account, region, service, action=action, params=sent, version=version
        )
        return status in ok, status, body

    return run


def _rest_json(service, path, names=(), build=None, ok=(200,)):
    """A rest-json call: a JSON body to a path, with no query protocol and no target header."""

    def run(params, account, region, call, rest):
        body = build(params) if build else {
            name: params[name] for name in names if str(params.get(name, "")).strip()
        }
        status, text = rest(service, account, region, "POST", path, json.dumps(body))
        return status in ok, status, text

    return run


def _instance_ids(params):
    """EC2 lifecycle calls take a numbered list, not a bare InstanceId."""
    return {"InstanceId.1": params["InstanceId"]} if params.get("InstanceId") else {}


def _json(service, target, names=(), build=None, ok=(200,)):
    def run(params, account, region, call, s3):
        body = build(params) if build else {
            name: params[name] for name in names if str(params.get(name, "")).strip()
        }
        status, text = call(
            account, region, service, target=target, body=body
        )
        return status in ok, status, text

    return run


def _s3(method, path, body="", quote_params=()):
    def run(params, account, region, call, rest):
        # A request line cannot carry a raw key: percent-encode the path values, keeping "/" literal.
        values = {
            name: quote(str(params[name]), safe="/") if name in quote_params else params[name]
            for name in params
        }
        target = path.format(**values)
        # `body` may be a callable when the payload depends on the form or region.
        payload = body(params, region) if callable(body) else body
        status, text = rest("s3", account, region, method, target, payload or "")
        return 200 <= status < 300, status, text

    return run


def _create_bucket_body(_params, region):
    """A bare create still has to name the region on every non-us-east-1 endpoint."""
    return buckets.location_constraint(region)


def _object_body(params, _region):
    """PutObject's payload is the form's Body field; the bucket and key are path."""
    return params.get("Body") or ""


def _rest(service, method, path):
    def run(params, account, region, call, rest):
        target = path.format(**params)
        status, text = rest(service, account, region, method, target)
        return 200 <= status < 300, status, text

    return run


def _lambda_invoke(params, account, region, call, rest):
    status, text = rest(
        "lambda",
        account,
        region,
        "POST",
        "/2015-03-31/functions/" + params["FunctionName"] + "/invocations",
        params.get("Payload") or "{}",
    )
    return 200 <= status < 300, status, text


def _put_item(params):
    item = json.loads(params.get("ItemJson") or "{}")
    return {
        "TableName": params["TableName"],
        "Item": {key: {"S": str(value)} for key, value in item.items()},
    }


def _scan(params):
    body = {"TableName": params["TableName"]}
    if str(params.get("Limit", "")).strip():
        body["Limit"] = int(params["Limit"])
    return body


def _create_table(params):
    name = params.get("PartitionKey") or "pk"
    return {
        "TableName": params["TableName"],
        "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": [
            {"AttributeName": name, "AttributeType": params.get("PartitionKeyType") or "S"}
        ],
        "KeySchema": [{"AttributeName": name, "KeyType": "HASH"}],
    }


def _pass_state(params):
    return params.get("definition") or json.dumps(
        {"StartAt": "Done", "States": {"Done": {"Type": "Succeed"}}}
    )


CATALOGUE: dict[str, dict] = {
    "account": {
        "description": "The account the console is signed in to.",
        "operations": [
            {
                "id": "get-account-information",
                "label": "Account information",
                "cli": "aws account get-account-information",
                "run": _rest_json("account", "/getAccountInformation"),
            },
            {
                "id": "get-contact-information",
                "label": "Contact information",
                "cli": "aws account get-contact-information",
                "run": _rest_json("account", "/getContactInformation"),
            },
            {
                "id": "list-regions",
                "label": "List regions",
                "cli": "aws account list-regions",
                "run": _rest_json("account", "/listRegions"),
            },
            {
                "id": "get-region-opt-status",
                "label": "Region opt-in status",
                "cli": "aws account get-region-opt-status --region-name <region>",
                "params": [field("RegionName", "Region", True)],
                "run": _rest_json("account", "/getRegionOptStatus", names=("RegionName",)),
            },
        ],
    },
    "s3": {
        "description": "Buckets and objects. Bucket names are global across accounts.",
        "operations": [
            {
                "id": "create-bucket",
                "label": "Create bucket",
                "cli": "aws s3 mb s3://<bucket>",
                "params": [field("Bucket", "Bucket name", True, placeholder="my-bucket")],
                "run": _s3("PUT", "/{Bucket}", body=_create_bucket_body),
            },
            {
                "id": "delete-bucket",
                "label": "Delete bucket",
                "cli": "aws s3 rb s3://<bucket>",
                "destructive": True,
                "params": [field("Bucket", "Bucket name", True)],
                "run": _s3("DELETE", "/{Bucket}"),
            },
            {
                "id": "list-objects",
                "label": "List objects",
                "cli": "aws s3 ls s3://<bucket>",
                "params": [field("Bucket", "Bucket name", True)],
                "run": _s3("GET", "/{Bucket}?list-type=2"),
            },
            {
                "id": "put-object",
                "label": "Put object",
                "cli": "aws s3 cp <file> s3://<bucket>/<key>",
                "params": [
                    field("Bucket", "Bucket name", True),
                    field("Key", "Object key", True),
                    field("Body", "Body", False, kind="textarea", placeholder="contents"),
                ],
                "run": _s3(
                    "PUT", "/{Bucket}/{Key}", body=_object_body, quote_params=("Key",)
                ),
            },
            {
                "id": "delete-object",
                "label": "Delete object",
                "cli": "aws s3 rm s3://<bucket>/<key>",
                "destructive": True,
                "params": [
                    field("Bucket", "Bucket name", True),
                    field("Key", "Object key", True),
                ],
                "run": _s3("DELETE", "/{Bucket}/{Key}", quote_params=("Key",)),
            },
        ],
    },
    "ec2": {
        "description": "Instance lifecycle. The emulator returns metadata-level instances.",
        "operations": [
            {
                "id": "describe-instances",
                "label": "Describe instances",
                "cli": "aws ec2 describe-instances",
                "params": [],
                "run": _query("ec2", "DescribeInstances"),
            },
            {
                "id": "run-instances",
                "label": "Launch instance",
                "cli": "aws ec2 run-instances --image-id … --instance-type …",
                "params": [
                    field("ImageId", "AMI", True, placeholder="ami-12345678"),
                    field("InstanceType", "Instance type", False, default="t3.micro"),
                    field("MinCount", "Min count", False, kind="number", default="1"),
                    field("MaxCount", "Max count", False, kind="number", default="1"),
                ],
                "run": _query(
                    "ec2", "RunInstances",
                    names=("ImageId", "InstanceType", "MinCount", "MaxCount"),
                ),
            },
            {
                "id": "start-instances",
                "label": "Start instance",
                "cli": "aws ec2 start-instances --instance-ids <id>",
                "params": [field("InstanceId", "Instance ID", True)],
                "run": _query(
                    "ec2", "StartInstances", names=("InstanceId",),
                    transform=_instance_ids,
                ),
            },
            {
                "id": "stop-instances",
                "label": "Stop instance",
                "cli": "aws ec2 stop-instances --instance-ids <id>",
                "params": [field("InstanceId", "Instance ID", True)],
                "run": _query(
                    "ec2", "StopInstances", names=("InstanceId",),
                    transform=_instance_ids,
                ),
            },
            {
                "id": "terminate-instances",
                "label": "Terminate instance",
                "cli": "aws ec2 terminate-instances --instance-ids <id>",
                "destructive": True,
                "params": [field("InstanceId", "Instance ID", True)],
                "run": _query(
                    "ec2", "TerminateInstances", names=("InstanceId",),
                    transform=_instance_ids,
                ),
            },
        ],
    },
    "sqs": {
        "description": "Queues and messages.",
        "operations": [
            {
                "id": "create-queue",
                "label": "Create queue",
                "cli": "aws sqs create-queue --queue-name <name>",
                "params": [field("QueueName", "Queue name", True)],
                "run": _query("sqs", "CreateQueue", version="2012-11-05", names=("QueueName",)),
            },
            {
                "id": "delete-queue",
                "label": "Delete queue",
                "cli": "aws sqs delete-queue --queue-url <url>",
                "destructive": True,
                "params": [field("QueueUrl", "Queue URL", True)],
                "run": _query("sqs", "DeleteQueue", version="2012-11-05", names=("QueueUrl",)),
            },
            {
                "id": "send-message",
                "label": "Send message",
                "cli": "aws sqs send-message --queue-url <url> --message-body <body>",
                "params": [
                    field("QueueUrl", "Queue URL", True),
                    field("MessageBody", "Message body", True, kind="textarea"),
                ],
                "run": _query(
                    "sqs", "SendMessage", version="2012-11-05",
                    names=("QueueUrl", "MessageBody"),
                ),
            },
            {
                "id": "receive-message",
                "label": "Receive message",
                "cli": "aws sqs receive-message --queue-url <url>",
                "params": [
                    field("QueueUrl", "Queue URL", True),
                    field("MaxNumberOfMessages", "Max messages", False, kind="number", default="1"),
                ],
                "run": _query(
                    "sqs", "ReceiveMessage", version="2012-11-05",
                    names=("QueueUrl", "MaxNumberOfMessages"),
                ),
            },
            {
                "id": "purge-queue",
                "label": "Purge queue",
                "cli": "aws sqs purge-queue --queue-url <url>",
                "destructive": True,
                "params": [field("QueueUrl", "Queue URL", True)],
                "run": _query("sqs", "PurgeQueue", version="2012-11-05", names=("QueueUrl",)),
            },
        ],
    },
    "sns": {
        "description": "Topics and publishes.",
        "operations": [
            {
                "id": "create-topic",
                "label": "Create topic",
                "cli": "aws sns create-topic --name <name>",
                "params": [field("Name", "Topic name", True)],
                "run": _query("sns", "CreateTopic", names=("Name",)),
            },
            {
                "id": "delete-topic",
                "label": "Delete topic",
                "cli": "aws sns delete-topic --topic-arn <arn>",
                "destructive": True,
                "params": [field("TopicArn", "Topic ARN", True)],
                "run": _query("sns", "DeleteTopic", names=("TopicArn",)),
            },
            {
                "id": "publish",
                "label": "Publish",
                "cli": "aws sns publish --topic-arn <arn> --message <text>",
                "params": [
                    field("TopicArn", "Topic ARN", True),
                    field("Message", "Message", True, kind="textarea"),
                ],
                "run": _query("sns", "Publish", names=("TopicArn", "Message")),
            },
        ],
    },
    "dynamodb": {
        "description": "Tables and items.",
        "operations": [
            {
                "id": "list-tables",
                "label": "List tables",
                "cli": "aws dynamodb list-tables",
                "params": [],
                "run": _json("dynamodb", "DynamoDB_20120810.ListTables"),
            },
            {
                "id": "create-table",
                "label": "Create table",
                "cli": "aws dynamodb create-table --table-name …",
                "params": [
                    field("TableName", "Table name", True),
                    field("PartitionKey", "Partition key", False, default="pk"),
                    field("PartitionKeyType", "Key type", False, default="S"),
                ],
                "run": _json(
                    "dynamodb", "DynamoDB_20120810.CreateTable", build=_create_table
                ),
            },
            {
                "id": "delete-table",
                "label": "Delete table",
                "cli": "aws dynamodb delete-table --table-name <name>",
                "destructive": True,
                "params": [field("TableName", "Table name", True)],
                "run": _json(
                    "dynamodb", "DynamoDB_20120810.DeleteTable", names=("TableName",)
                ),
            },
            {
                "id": "scan",
                "label": "Scan table",
                "cli": "aws dynamodb scan --table-name <name>",
                "params": [
                    field("TableName", "Table name", True),
                    field("Limit", "Limit", False, kind="number"),
                ],
                "run": _json("dynamodb", "DynamoDB_20120810.Scan", build=_scan),
            },
            {
                "id": "put-item",
                "label": "Put item",
                "cli": "aws dynamodb put-item --table-name … --item '{…}'",
                "params": [
                    field("TableName", "Table name", True),
                    field("ItemJson", "Item (JSON object)", True, kind="textarea",
                          placeholder='{"pk": "one", "value": "hello"}'),
                ],
                "run": _json("dynamodb", "DynamoDB_20120810.PutItem", build=_put_item),
            },
        ],
    },
    "iam": {
        "description": "Users, access keys and attached policies (global service).",
        "operations": [
            {
                "id": "list-users",
                "label": "List users",
                "cli": "aws iam list-users",
                "params": [],
                "run": _query("iam", "ListUsers"),
            },
            {
                "id": "create-user",
                "label": "Create user",
                "cli": "aws iam create-user --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "CreateUser", names=("UserName",)),
            },
            {
                "id": "delete-user",
                "label": "Delete user",
                "cli": "aws iam delete-user --user-name <name>",
                "destructive": True,
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "DeleteUser", names=("UserName",)),
            },
            {
                "id": "create-access-key",
                "label": "Create access key",
                "cli": "aws iam create-access-key --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "CreateAccessKey", names=("UserName",)),
            },
            {
                "id": "attach-user-policy",
                "label": "Attach policy",
                "cli": "aws iam attach-user-policy --user-name … --policy-arn …",
                "params": [
                    field("UserName", "User name", True),
                    field("PolicyArn", "Policy ARN", True,
                          placeholder="arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"),
                ],
                "run": _query(
                    "iam", "AttachUserPolicy", names=("UserName", "PolicyArn")
                ),
            },
        ],
    },
    "lambda": {
        "description": "Functions: list, inspect, invoke and delete.",
        "operations": [
            {
                "id": "list-functions",
                "label": "List functions",
                "cli": "aws lambda list-functions",
                "params": [],
                "run": _rest("lambda", "GET", "/2015-03-31/functions/"),
            },
            {
                "id": "get-function",
                "label": "Get function",
                "cli": "aws lambda get-function --function-name <name>",
                "params": [field("FunctionName", "Function name", True)],
                "run": _rest("lambda", "GET", "/2015-03-31/functions/{FunctionName}"),
            },
            {
                "id": "invoke-function",
                "label": "Invoke function",
                "cli": "aws lambda invoke --function-name <name> --payload '<json>' out.json",
                "params": [
                    field("FunctionName", "Function name", True),
                    field("Payload", "Payload (JSON)", False, kind="textarea", default="{}"),
                ],
                "run": _lambda_invoke,
            },
            {
                "id": "delete-function",
                "label": "Delete function",
                "cli": "aws lambda delete-function --function-name <name>",
                "destructive": True,
                "params": [field("FunctionName", "Function name", True)],
                "run": _rest("lambda", "DELETE", "/2015-03-31/functions/{FunctionName}"),
            },
        ],
    },
    "logs": {
        "description": "Log groups and streams.",
        "operations": [
            {
                "id": "describe-log-groups",
                "label": "List log groups",
                "cli": "aws logs describe-log-groups",
                "params": [],
                "run": _json("logs", "Logs_20140328.DescribeLogGroups"),
            },
            {
                "id": "create-log-group",
                "label": "Create log group",
                "cli": "aws logs create-log-group --log-group-name <name>",
                "params": [field("logGroupName", "Log group name", True)],
                "run": _json(
                    "logs", "Logs_20140328.CreateLogGroup", names=("logGroupName",)
                ),
            },
            {
                "id": "delete-log-group",
                "label": "Delete log group",
                "cli": "aws logs delete-log-group --log-group-name <name>",
                "destructive": True,
                "params": [field("logGroupName", "Log group name", True)],
                "run": _json(
                    "logs", "Logs_20140328.DeleteLogGroup", names=("logGroupName",)
                ),
            },
            {
                "id": "describe-log-streams",
                "label": "List streams",
                "cli": "aws logs describe-log-streams --log-group-name <name>",
                "params": [field("logGroupName", "Log group name", True)],
                "run": _json(
                    "logs", "Logs_20140328.DescribeLogStreams", names=("logGroupName",)
                ),
            },
        ],
    },
    "secretsmanager": {
        "description": "Secrets (the lab's own credentials never live here).",
        "operations": [
            {
                "id": "list-secrets",
                "label": "List secrets",
                "cli": "aws secretsmanager list-secrets",
                "params": [],
                "run": _json("secretsmanager", "secretsmanager.ListSecrets"),
            },
            {
                "id": "create-secret",
                "label": "Create secret",
                "cli": "aws secretsmanager create-secret --name … --secret-string …",
                "params": [
                    field("Name", "Name", True),
                    field("SecretString", "Secret string", True, kind="textarea"),
                ],
                "run": _json(
                    "secretsmanager", "secretsmanager.CreateSecret",
                    names=("Name", "SecretString"),
                ),
            },
            {
                "id": "put-secret-value",
                "label": "Put value",
                "cli": "aws secretsmanager put-secret-value --secret-id …",
                "params": [
                    field("SecretId", "Secret ID", True),
                    field("SecretString", "Secret string", True, kind="textarea"),
                ],
                "run": _json(
                    "secretsmanager", "secretsmanager.PutSecretValue",
                    names=("SecretId", "SecretString"),
                ),
            },
            {
                "id": "delete-secret",
                "label": "Delete secret",
                "cli": "aws secretsmanager delete-secret --secret-id <id> --force-delete-without-recovery",
                "destructive": True,
                "params": [field("SecretId", "Secret ID", True)],
                "run": _json(
                    "secretsmanager", "secretsmanager.DeleteSecret",
                    build=lambda p: {
                        "SecretId": p["SecretId"],
                        "ForceDeleteWithoutRecovery": True,
                    },
                ),
            },
        ],
    },
    "ssm": {
        "description": "Parameter Store.",
        "operations": [
            {
                "id": "describe-parameters",
                "label": "List parameters",
                "cli": "aws ssm describe-parameters",
                "params": [],
                "run": _json("ssm", "AmazonSSM.DescribeParameters"),
            },
            {
                "id": "put-parameter",
                "label": "Put parameter",
                "cli": "aws ssm put-parameter --name … --value … --type String",
                "params": [
                    field("Name", "Name", True),
                    field("Value", "Value", True),
                    field("Type", "Type", False, default="String"),
                    field("Overwrite", "Overwrite", False, kind="checkbox"),
                ],
                "run": _json(
                    "ssm", "AmazonSSM.PutParameter",
                    build=lambda p: {
                        "Name": p["Name"],
                        "Value": p["Value"],
                        "Type": p.get("Type") or "String",
                        "Overwrite": bool(p.get("Overwrite")),
                    },
                ),
            },
            {
                "id": "get-parameter",
                "label": "Get parameter",
                "cli": "aws ssm get-parameter --name <name>",
                "params": [field("Name", "Name", True)],
                "run": _json("ssm", "AmazonSSM.GetParameter", build=lambda p: {
                    "Name": p["Name"], "WithDecryption": True,
                }),
            },
            {
                "id": "delete-parameter",
                "label": "Delete parameter",
                "cli": "aws ssm delete-parameter --name <name>",
                "destructive": True,
                "params": [field("Name", "Name", True)],
                "run": _json("ssm", "AmazonSSM.DeleteParameter", names=("Name",)),
            },
        ],
    },
    "kinesis": {
        "description": "Streams.",
        "operations": [
            {
                "id": "list-streams",
                "label": "List streams",
                "cli": "aws kinesis list-streams",
                "params": [],
                "run": _json("kinesis", "Kinesis_20131202.ListStreams"),
            },
            {
                "id": "create-stream",
                "label": "Create stream",
                "cli": "aws kinesis create-stream --stream-name … --shard-count 1",
                "params": [
                    field("StreamName", "Stream name", True),
                    field("ShardCount", "Shard count", False, kind="number", default="1"),
                ],
                "run": _json(
                    "kinesis", "Kinesis_20131202.CreateStream",
                    build=lambda p: {
                        "StreamName": p["StreamName"],
                        "ShardCount": int(p.get("ShardCount") or 1),
                    },
                ),
            },
            {
                "id": "delete-stream",
                "label": "Delete stream",
                "cli": "aws kinesis delete-stream --stream-name <name>",
                "destructive": True,
                "params": [field("StreamName", "Stream name", True)],
                "run": _json(
                    "kinesis", "Kinesis_20131202.DeleteStream",
                    names=("StreamName",),
                ),
            },
        ],
    },
    "stepfunctions": {
        "description": "State machines.",
        "operations": [
            {
                "id": "list-state-machines",
                "label": "List state machines",
                "cli": "aws stepfunctions list-state-machines",
                "params": [],
                "run": _json("states", "AWSStepFunctions.ListStateMachines"),
            },
            {
                "id": "create-state-machine",
                "label": "Create state machine",
                "cli": "aws stepfunctions create-state-machine …",
                "params": [
                    field("name", "Name", True),
                    field("roleArn", "Role ARN", True,
                          placeholder="arn:aws:iam::111111111111:role/service-role/StatesExecutionRole"),
                    field("definition", "Definition (JSON)", False, kind="textarea",
                          placeholder='{"StartAt": "Done", "States": {"Done": {"Type": "Succeed"}}}'),
                ],
                "run": _json(
                    "stepfunctions", "AWSStepFunctions.CreateStateMachine",
                    build=lambda p: {
                        "name": p["name"],
                        "roleArn": p["roleArn"],
                        "definition": _pass_state(p),
                    },
                ),
            },
            {
                "id": "delete-state-machine",
                "label": "Delete state machine",
                "cli": "aws stepfunctions delete-state-machine --state-machine-arn <arn>",
                "destructive": True,
                "params": [field("stateMachineArn", "State machine ARN", True)],
                "run": _json(
                    "stepfunctions", "AWSStepFunctions.DeleteStateMachine",
                    names=("stateMachineArn",),
                ),
            },
        ],
    },
}


def public_catalogue() -> dict:
    """The catalogue minus the callables, for the UI."""
    return {
        service: {
            "description": spec["description"],
            "operations": [
                {key: value for key, value in op.items() if key != "run"}
                for op in spec["operations"]
            ],
        }
        for service, spec in CATALOGUE.items()
    }


def _error_message(body: str, status: int) -> str:
    """The human half of a failed call: S3's XML ``<Message>`` or the AWS JSON message."""
    text = body or ""
    match = re.search(r"<Message>(.*?)</Message>", text, re.S)
    if match:
        return html.unescape(match.group(1)).strip()
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        for key in ("message", "Message", "error", "errorMessage"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"HTTP {status}" if status else "the emulator did not answer"


def run_action(service, operation, params, account, region, call, s3):
    spec = CATALOGUE.get(service)
    if spec is None:
        return {"ok": False, "error": f"no actions for service {service}"}
    op = next((item for item in spec["operations"] if item["id"] == operation), None)
    if op is None:
        return {"ok": False, "error": f"unknown action {operation} for {service}"}
    missing = [
        item["name"]
        for item in op.get("params", [])
        if item.get("required") and not str(params.get(item["name"], "")).strip()
    ]
    if missing:
        return {"ok": False, "error": "missing parameter: " + ", ".join(missing)}
    try:
        ok, status, body = op["run"](params, account, region, call, s3)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON parameter: {exc}"}
    except (KeyError, ValueError) as exc:
        return {"ok": False, "error": f"invalid parameter: {exc}"}
    return {
        "ok": ok,
        "status": status,
        "cli": op.get("cli", ""),
        "body": body[:20000],
        "error": "" if ok else _error_message(body, status),
    }
