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
        "description": "Identities, policies and access keys (global service).",
        "operations": [
            {
                "id": "get-account-summary",
                "label": "Account summary",
                "cli": "aws iam get-account-summary",
                "params": [],
                "run": _query("iam", "GetAccountSummary"),
            },
            {
                "id": "list-users",
                "label": "List users",
                "cli": "aws iam list-users",
                "params": [field("PathPrefix", "Path prefix")],
                "run": _query("iam", "ListUsers", names=("PathPrefix",)),
            },
            {
                "id": "get-user",
                "label": "Get user",
                "cli": "aws iam get-user --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "GetUser", names=("UserName",)),
            },
            {
                "id": "create-user",
                "label": "Create user",
                "cli": "aws iam create-user --user-name <name>",
                "params": [
                    field("UserName", "User name", True),
                    field("Path", "Path", False, placeholder="/"),
                ],
                "run": _query("iam", "CreateUser", names=("UserName", "Path")),
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
                "id": "list-access-keys",
                "label": "List access keys",
                "cli": "aws iam list-access-keys --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "ListAccessKeys", names=("UserName",)),
            },
            {
                "id": "list-groups-for-user",
                "label": "List groups for user",
                "cli": "aws iam list-groups-for-user --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "ListGroupsForUser", names=("UserName",)),
            },
            {
                "id": "list-attached-user-policies",
                "label": "List attached user policies",
                "cli": "aws iam list-attached-user-policies --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query(
                    "iam", "ListAttachedUserPolicies", names=("UserName",)
                ),
            },
            {
                "id": "list-user-policies",
                "label": "List inline user policies",
                "cli": "aws iam list-user-policies --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "ListUserPolicies", names=("UserName",)),
            },
            {
                "id": "list-mfa-devices",
                "label": "List MFA devices",
                "cli": "aws iam list-mfa-devices --user-name <name>",
                "params": [field("UserName", "User name", True)],
                "run": _query("iam", "ListMFADevices", names=("UserName",)),
            },
            {
                "id": "create-virtual-mfa-device",
                "label": "Create virtual MFA device",
                "cli": "aws iam create-virtual-mfa-device --virtual-mfa-device-name <name>",
                "params": [field("VirtualMFADeviceName", "Device name", True)],
                "run": _query(
                    "iam",
                    "CreateVirtualMFADevice",
                    names=("VirtualMFADeviceName",),
                ),
            },
            {
                "id": "enable-mfa-device",
                "label": "Enable MFA device",
                "cli": "aws iam enable-mfa-device --user-name … --serial-number … --authentication-code-1 … --authentication-code-2 …",
                "params": [
                    field("UserName", "User name", True),
                    field("SerialNumber", "Serial number", True),
                    field("AuthenticationCode1", "Code 1", True, placeholder="123456"),
                    field("AuthenticationCode2", "Code 2", True, placeholder="654321"),
                ],
                "run": _query(
                    "iam",
                    "EnableMFADevice",
                    names=(
                        "UserName",
                        "SerialNumber",
                        "AuthenticationCode1",
                        "AuthenticationCode2",
                    ),
                ),
            },
            {
                "id": "list-groups",
                "label": "List groups",
                "cli": "aws iam list-groups",
                "params": [field("PathPrefix", "Path prefix")],
                "run": _query("iam", "ListGroups", names=("PathPrefix",)),
            },
            {
                "id": "get-group",
                "label": "Get group",
                "cli": "aws iam get-group --group-name <name>",
                "params": [field("GroupName", "Group name", True)],
                "run": _query("iam", "GetGroup", names=("GroupName",)),
            },
            {
                "id": "create-group",
                "label": "Create group",
                "cli": "aws iam create-group --group-name <name>",
                "params": [
                    field("GroupName", "Group name", True),
                    field("Path", "Path", False, placeholder="/"),
                ],
                "run": _query("iam", "CreateGroup", names=("GroupName", "Path")),
            },
            {
                "id": "delete-group",
                "label": "Delete group",
                "cli": "aws iam delete-group --group-name <name>",
                "destructive": True,
                "params": [field("GroupName", "Group name", True)],
                "run": _query("iam", "DeleteGroup", names=("GroupName",)),
            },
            {
                "id": "list-attached-group-policies",
                "label": "List attached group policies",
                "cli": "aws iam list-attached-group-policies --group-name <name>",
                "params": [field("GroupName", "Group name", True)],
                "run": _query(
                    "iam", "ListAttachedGroupPolicies", names=("GroupName",)
                ),
            },
            {
                "id": "attach-group-policy",
                "label": "Attach group policy",
                "cli": "aws iam attach-group-policy --group-name … --policy-arn …",
                "params": [
                    field("GroupName", "Group name", True),
                    field("PolicyArn", "Policy ARN", True),
                ],
                "run": _query(
                    "iam", "AttachGroupPolicy", names=("GroupName", "PolicyArn")
                ),
            },
            {
                "id": "detach-group-policy",
                "label": "Detach group policy",
                "cli": "aws iam detach-group-policy --group-name … --policy-arn …",
                "destructive": True,
                "params": [
                    field("GroupName", "Group name", True),
                    field("PolicyArn", "Policy ARN", True),
                ],
                "run": _query(
                    "iam", "DetachGroupPolicy", names=("GroupName", "PolicyArn")
                ),
            },
            {
                "id": "list-group-policies",
                "label": "List inline group policies",
                "cli": "aws iam list-group-policies --group-name <name>",
                "params": [field("GroupName", "Group name", True)],
                "run": _query("iam", "ListGroupPolicies", names=("GroupName",)),
            },
            {
                "id": "delete-group-policy",
                "label": "Delete inline group policy",
                "cli": "aws iam delete-group-policy --group-name … --policy-name …",
                "destructive": True,
                "params": [
                    field("GroupName", "Group name", True),
                    field("PolicyName", "Policy name", True),
                ],
                "run": _query(
                    "iam", "DeleteGroupPolicy", names=("GroupName", "PolicyName")
                ),
            },
            {
                "id": "put-group-policy",
                "label": "Put inline group policy",
                "cli": "aws iam put-group-policy --group-name … --policy-name … --policy-document file://policy.json",
                "params": [
                    field("GroupName", "Group name", True),
                    field("PolicyName", "Policy name", True),
                    field("PolicyDocument", "Policy document (JSON)", True, kind="textarea"),
                ],
                "run": _query(
                    "iam",
                    "PutGroupPolicy",
                    names=("GroupName", "PolicyName", "PolicyDocument"),
                ),
            },
            {
                "id": "get-group-policy",
                "label": "Get inline group policy",
                "cli": "aws iam get-group-policy --group-name … --policy-name …",
                "params": [
                    field("GroupName", "Group name", True),
                    field("PolicyName", "Policy name", True),
                ],
                "run": _query(
                    "iam", "GetGroupPolicy", names=("GroupName", "PolicyName")
                ),
            },
            {
                "id": "add-user-to-group",
                "label": "Add user to group",
                "cli": "aws iam add-user-to-group --group-name … --user-name …",
                "params": [
                    field("GroupName", "Group name", True),
                    field("UserName", "User name", True),
                ],
                "run": _query(
                    "iam", "AddUserToGroup", names=("GroupName", "UserName")
                ),
            },
            {
                "id": "remove-user-from-group",
                "label": "Remove user from group",
                "cli": "aws iam remove-user-from-group --group-name … --user-name …",
                "destructive": True,
                "params": [
                    field("GroupName", "Group name", True),
                    field("UserName", "User name", True),
                ],
                "run": _query(
                    "iam", "RemoveUserFromGroup", names=("GroupName", "UserName")
                ),
            },
            {
                "id": "list-roles",
                "label": "List roles",
                "cli": "aws iam list-roles",
                "params": [field("PathPrefix", "Path prefix")],
                "run": _query("iam", "ListRoles", names=("PathPrefix",)),
            },
            {
                "id": "get-role",
                "label": "Get role",
                "cli": "aws iam get-role --role-name <name>",
                "params": [field("RoleName", "Role name", True)],
                "run": _query("iam", "GetRole", names=("RoleName",)),
            },
            {
                "id": "create-role",
                "label": "Create role",
                "cli": "aws iam create-role --role-name … --assume-role-policy-document file://trust.json",
                "params": [
                    field("RoleName", "Role name", True),
                    field("Path", "Path", False, placeholder="/"),
                    field("Description", "Description"),
                    field("AssumeRolePolicyDocument", "Trust policy (JSON)", True,
                          kind="textarea",
                          placeholder='{"Version": "2012-10-17", "Statement": []}'),
                ],
                "run": _query(
                    "iam",
                    "CreateRole",
                    names=("RoleName", "Path", "Description", "AssumeRolePolicyDocument"),
                ),
            },
            {
                "id": "delete-role",
                "label": "Delete role",
                "cli": "aws iam delete-role --role-name <name>",
                "destructive": True,
                "params": [field("RoleName", "Role name", True)],
                "run": _query("iam", "DeleteRole", names=("RoleName",)),
            },
            {
                "id": "list-attached-role-policies",
                "label": "List attached role policies",
                "cli": "aws iam list-attached-role-policies --role-name <name>",
                "params": [field("RoleName", "Role name", True)],
                "run": _query(
                    "iam", "ListAttachedRolePolicies", names=("RoleName",)
                ),
            },
            {
                "id": "list-role-policies",
                "label": "List inline role policies",
                "cli": "aws iam list-role-policies --role-name <name>",
                "params": [field("RoleName", "Role name", True)],
                "run": _query("iam", "ListRolePolicies", names=("RoleName",)),
            },
            {
                "id": "list-policies",
                "label": "List policies",
                "cli": "aws iam list-policies",
                "params": [
                    field("Scope", "Scope", False, placeholder="Local"),
                    field("PathPrefix", "Path prefix"),
                ],
                "run": _query("iam", "ListPolicies", names=("Scope", "PathPrefix")),
            },
            {
                "id": "get-policy",
                "label": "Get policy",
                "cli": "aws iam get-policy --policy-arn <arn>",
                "params": [field("PolicyArn", "Policy ARN", True)],
                "run": _query("iam", "GetPolicy", names=("PolicyArn",)),
            },
            {
                "id": "create-policy",
                "label": "Create policy",
                "cli": "aws iam create-policy --policy-name … --policy-document file://policy.json",
                "params": [
                    field("PolicyName", "Policy name", True),
                    field("Description", "Description"),
                    field("PolicyDocument", "Policy document (JSON)", True,
                          kind="textarea",
                          placeholder='{"Version": "2012-10-17", "Statement": []}'),
                ],
                "run": _query(
                    "iam",
                    "CreatePolicy",
                    names=("PolicyName", "Description", "PolicyDocument"),
                ),
            },
            {
                "id": "delete-policy",
                "label": "Delete policy",
                "cli": "aws iam delete-policy --policy-arn <arn>",
                "destructive": True,
                "params": [field("PolicyArn", "Policy ARN", True)],
                "run": _query("iam", "DeletePolicy", names=("PolicyArn",)),
            },
            {
                "id": "list-policy-versions",
                "label": "List policy versions",
                "cli": "aws iam list-policy-versions --policy-arn <arn>",
                "params": [field("PolicyArn", "Policy ARN", True)],
                "run": _query("iam", "ListPolicyVersions", names=("PolicyArn",)),
            },
            {
                "id": "list-open-id-connect-providers",
                "label": "List OIDC providers",
                "cli": "aws iam list-open-id-connect-providers",
                "params": [],
                "run": _query("iam", "ListOpenIDConnectProviders"),
            },
            {
                "id": "get-open-id-connect-provider",
                "label": "Get OIDC provider",
                "cli": "aws iam get-open-id-connect-provider --open-id-connect-provider-arn <arn>",
                "params": [field("OpenIDConnectProviderArn", "Provider ARN", True)],
                "run": _query(
                    "iam",
                    "GetOpenIDConnectProvider",
                    names=("OpenIDConnectProviderArn",),
                ),
            },
            {
                "id": "create-open-id-connect-provider",
                "label": "Create OIDC provider",
                "cli": "aws iam create-open-id-connect-provider --url … --client-id-list … --thumbprint-list …",
                "params": [
                    field("Url", "Provider URL", True, placeholder="https://oidc.example.com"),
                    field("ClientIDList.member.1", "Client ID", True),
                    field("ThumbprintList.member.1", "Thumbprint", True),
                ],
                "run": _query(
                    "iam",
                    "CreateOpenIDConnectProvider",
                    names=(
                        "Url",
                        "ClientIDList.member.1",
                        "ThumbprintList.member.1",
                    ),
                ),
            },
            {
                "id": "delete-open-id-connect-provider",
                "label": "Delete OIDC provider",
                "cli": "aws iam delete-open-id-connect-provider --open-id-connect-provider-arn <arn>",
                "destructive": True,
                "params": [field("OpenIDConnectProviderArn", "Provider ARN", True)],
                "run": _query(
                    "iam",
                    "DeleteOpenIDConnectProvider",
                    names=("OpenIDConnectProviderArn",),
                ),
            },
            {
                "id": "list-saml-providers",
                "label": "List SAML providers",
                "cli": "aws iam list-saml-providers",
                "params": [],
                "run": _query("iam", "ListSAMLProviders"),
            },
            {
                "id": "create-saml-provider",
                "label": "Create SAML provider",
                "cli": "aws iam create-saml-provider --name … --saml-metadata-document file://metadata.xml",
                "params": [
                    field("Name", "Provider name", True),
                    field("SAMLMetadataDocument", "Metadata XML", True, kind="textarea"),
                ],
                "run": _query(
                    "iam",
                    "CreateSAMLProvider",
                    names=("Name", "SAMLMetadataDocument"),
                ),
            },
            {
                "id": "delete-saml-provider",
                "label": "Delete SAML provider",
                "cli": "aws iam delete-saml-provider --saml-provider-arn <arn>",
                "destructive": True,
                "params": [field("SAMLProviderArn", "Provider ARN", True)],
                "run": _query(
                    "iam", "DeleteSAMLProvider", names=("SAMLProviderArn",)
                ),
            },
            {
                "id": "get-saml-provider",
                "label": "Get SAML provider",
                "cli": "aws iam get-saml-provider --saml-provider-arn <arn>",
                "params": [field("SAMLProviderArn", "Provider ARN", True)],
                "run": _query(
                    "iam", "GetSAMLProvider", names=("SAMLProviderArn",)
                ),
            },
            {
                "id": "get-account-password-policy",
                "label": "Get password policy",
                "cli": "aws iam get-account-password-policy",
                "params": [],
                "run": _query("iam", "GetAccountPasswordPolicy"),
            },
            {
                "id": "update-account-password-policy",
                "label": "Update password policy",
                "cli": "aws iam update-account-password-policy --minimum-password-length 12",
                "params": [
                    field("MinimumPasswordLength", "Minimum length"),
                    field("MaxPasswordAge", "Expire after (days)"),
                    field("PasswordReusePrevention", "Reuse prevention (generations)"),
                    field("RequireSymbols", "Require symbols"),
                    field("RequireNumbers", "Require numbers"),
                    field("RequireUppercaseCharacters", "Require upper case"),
                    field("RequireLowercaseCharacters", "Require lower case"),
                    field("AllowUsersToChangePassword", "Allow users to change"),
                ],
                "run": _query(
                    "iam",
                    "UpdateAccountPasswordPolicy",
                    names=(
                        "MinimumPasswordLength",
                        "MaxPasswordAge",
                        "PasswordReusePrevention",
                        "RequireSymbols",
                        "RequireNumbers",
                        "RequireUppercaseCharacters",
                        "RequireLowercaseCharacters",
                        "AllowUsersToChangePassword",
                    ),
                ),
            },
            {
                "id": "delete-account-password-policy",
                "label": "Delete password policy",
                "cli": "aws iam delete-account-password-policy",
                "destructive": True,
                "params": [],
                "run": _query("iam", "DeleteAccountPasswordPolicy"),
            },
            {
                "id": "list-account-aliases",
                "label": "List account aliases",
                "cli": "aws iam list-account-aliases",
                "params": [],
                "run": _query("iam", "ListAccountAliases"),
            },
            {
                "id": "create-account-alias",
                "label": "Create account alias",
                "cli": "aws iam create-account-alias --account-alias <alias>",
                "params": [field("AccountAlias", "Alias", True)],
                "run": _query(
                    "iam", "CreateAccountAlias", names=("AccountAlias",)
                ),
            },
            {
                "id": "delete-account-alias",
                "label": "Delete account alias",
                "cli": "aws iam delete-account-alias --account-alias <alias>",
                "destructive": True,
                "params": [field("AccountAlias", "Alias", True)],
                "run": _query(
                    "iam", "DeleteAccountAlias", names=("AccountAlias",)
                ),
            },
            {
                "id": "generate-credential-report",
                "label": "Generate credential report",
                "cli": "aws iam generate-credential-report",
                "params": [],
                "run": _query("iam", "GenerateCredentialReport"),
            },
            {
                "id": "get-credential-report",
                "label": "Get credential report",
                "cli": "aws iam get-credential-report",
                "params": [],
                "run": _query("iam", "GetCredentialReport"),
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
            {
                "id": 'update-role-description',
                "label": 'Update Role Description',
                "cli": "aws iam update-role-description",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('Description', 'Description', False),
                ],
                "run": _query("iam", 'UpdateRoleDescription', names=('RoleName', 'Description',)),
            },
            {
                "id": 'update-assume-role-policy',
                "label": 'Update Assume Role Policy',
                "cli": "aws iam update-assume-role-policy",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('PolicyDocument', 'PolicyDocument', True, kind="textarea"),
                ],
                "run": _query("iam", 'UpdateAssumeRolePolicy', names=('RoleName', 'PolicyDocument',)),
            },
            {
                "id": 'put-role-permissions-boundary',
                "label": 'Put Role Permissions Boundary',
                "cli": "aws iam put-role-permissions-boundary",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('PermissionsBoundary', 'PermissionsBoundary', True),
                ],
                "run": _query("iam", 'PutRolePermissionsBoundary', names=('RoleName', 'PermissionsBoundary',)),
            },
            {
                "id": 'delete-role-permissions-boundary',
                "label": 'Delete Role Permissions Boundary',
                "cli": "aws iam delete-role-permissions-boundary",
                
                "params": [field('RoleName', 'RoleName', True)],
                "run": _query("iam", 'DeleteRolePermissionsBoundary', names=('RoleName',)),
            },
            {
                "id": 'put-user-permissions-boundary',
                "label": 'Put User Permissions Boundary',
                "cli": "aws iam put-user-permissions-boundary",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('PermissionsBoundary', 'PermissionsBoundary', True),
                ],
                "run": _query("iam", 'PutUserPermissionsBoundary', names=('UserName', 'PermissionsBoundary',)),
            },
            {
                "id": 'delete-user-permissions-boundary',
                "label": 'Delete User Permissions Boundary',
                "cli": "aws iam delete-user-permissions-boundary",
                
                "params": [field('UserName', 'UserName', True)],
                "run": _query("iam", 'DeleteUserPermissionsBoundary', names=('UserName',)),
            },
            {
                "id": 'attach-role-policy',
                "label": 'Attach Role Policy',
                "cli": "aws iam attach-role-policy",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('PolicyArn', 'PolicyArn', True),
                ],
                "run": _query("iam", 'AttachRolePolicy', names=('RoleName', 'PolicyArn',)),
            },
            {
                "id": 'detach-role-policy',
                "label": 'Detach Role Policy',
                "cli": "aws iam detach-role-policy",
                'destructive': True,
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('PolicyArn', 'PolicyArn', True),
                ],
                "run": _query("iam", 'DetachRolePolicy', names=('RoleName', 'PolicyArn',)),
            },
            {
                "id": 'put-role-policy',
                "label": 'Put Role Policy',
                "cli": "aws iam put-role-policy",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('PolicyName', 'PolicyName', True),
                    field('PolicyDocument', 'PolicyDocument', True, kind="textarea"),
                ],
                "run": _query("iam", 'PutRolePolicy', names=('RoleName', 'PolicyName', 'PolicyDocument',)),
            },
            {
                "id": 'get-role-policy',
                "label": 'Get Role Policy',
                "cli": "aws iam get-role-policy",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('PolicyName', 'PolicyName', True),
                ],
                "run": _query("iam", 'GetRolePolicy', names=('RoleName', 'PolicyName',)),
            },
            {
                "id": 'delete-role-policy',
                "label": 'Delete Role Policy',
                "cli": "aws iam delete-role-policy",
                'destructive': True,
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('PolicyName', 'PolicyName', True),
                ],
                "run": _query("iam", 'DeleteRolePolicy', names=('RoleName', 'PolicyName',)),
            },
            {
                "id": 'detach-user-policy',
                "label": 'Detach User Policy',
                "cli": "aws iam detach-user-policy",
                'destructive': True,
                "params": [
                    field('UserName', 'UserName', True),
                    field('PolicyArn', 'PolicyArn', True),
                ],
                "run": _query("iam", 'DetachUserPolicy', names=('UserName', 'PolicyArn',)),
            },
            {
                "id": 'put-user-policy',
                "label": 'Put User Policy',
                "cli": "aws iam put-user-policy",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('PolicyName', 'PolicyName', True),
                    field('PolicyDocument', 'PolicyDocument', True, kind="textarea"),
                ],
                "run": _query("iam", 'PutUserPolicy', names=('UserName', 'PolicyName', 'PolicyDocument',)),
            },
            {
                "id": 'get-user-policy',
                "label": 'Get User Policy',
                "cli": "aws iam get-user-policy",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('PolicyName', 'PolicyName', True),
                ],
                "run": _query("iam", 'GetUserPolicy', names=('UserName', 'PolicyName',)),
            },
            {
                "id": 'delete-user-policy',
                "label": 'Delete User Policy',
                "cli": "aws iam delete-user-policy",
                'destructive': True,
                "params": [
                    field('UserName', 'UserName', True),
                    field('PolicyName', 'PolicyName', True),
                ],
                "run": _query("iam", 'DeleteUserPolicy', names=('UserName', 'PolicyName',)),
            },
            {
                "id": 'tag-role',
                "label": 'Tag Role',
                "cli": "aws iam tag-role",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('Tags.member.1.Key', 'Tags member 1 Key', True),
                    field('Tags.member.1.Value', 'Tags member 1 Value', False),
                ],
                "run": _query("iam", 'TagRole', names=('RoleName', 'Tags.member.1.Key', 'Tags.member.1.Value',)),
            },
            {
                "id": 'untag-role',
                "label": 'Untag Role',
                "cli": "aws iam untag-role",
                
                "params": [
                    field('RoleName', 'RoleName', True),
                    field('TagKeys.member.1', 'TagKeys member 1', True),
                ],
                "run": _query("iam", 'UntagRole', names=('RoleName', 'TagKeys.member.1',)),
            },
            {
                "id": 'list-role-tags',
                "label": 'List Role Tags',
                "cli": "aws iam list-role-tags",
                
                "params": [field('RoleName', 'RoleName', True)],
                "run": _query("iam", 'ListRoleTags', names=('RoleName',)),
            },
            {
                "id": 'tag-user',
                "label": 'Tag User',
                "cli": "aws iam tag-user",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('Tags.member.1.Key', 'Tags member 1 Key', True),
                    field('Tags.member.1.Value', 'Tags member 1 Value', False),
                ],
                "run": _query("iam", 'TagUser', names=('UserName', 'Tags.member.1.Key', 'Tags.member.1.Value',)),
            },
            {
                "id": 'untag-user',
                "label": 'Untag User',
                "cli": "aws iam untag-user",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('TagKeys.member.1', 'TagKeys member 1', True),
                ],
                "run": _query("iam", 'UntagUser', names=('UserName', 'TagKeys.member.1',)),
            },
            {
                "id": 'list-user-tags',
                "label": 'List User Tags',
                "cli": "aws iam list-user-tags",
                
                "params": [field('UserName', 'UserName', True)],
                "run": _query("iam", 'ListUserTags', names=('UserName',)),
            },
            {
                "id": 'tag-policy',
                "label": 'Tag Policy',
                "cli": "aws iam tag-policy",
                
                "params": [
                    field('PolicyArn', 'PolicyArn', True),
                    field('Tags.member.1.Key', 'Tags member 1 Key', True),
                    field('Tags.member.1.Value', 'Tags member 1 Value', False),
                ],
                "run": _query("iam", 'TagPolicy', names=('PolicyArn', 'Tags.member.1.Key', 'Tags.member.1.Value',)),
            },
            {
                "id": 'untag-policy',
                "label": 'Untag Policy',
                "cli": "aws iam untag-policy",
                
                "params": [
                    field('PolicyArn', 'PolicyArn', True),
                    field('TagKeys.member.1', 'TagKeys member 1', True),
                ],
                "run": _query("iam", 'UntagPolicy', names=('PolicyArn', 'TagKeys.member.1',)),
            },
            {
                "id": 'list-policy-tags',
                "label": 'List Policy Tags',
                "cli": "aws iam list-policy-tags",
                
                "params": [field('PolicyArn', 'PolicyArn', True)],
                "run": _query("iam", 'ListPolicyTags', names=('PolicyArn',)),
            },
            {
                "id": 'create-instance-profile',
                "label": 'Create Instance Profile',
                "cli": "aws iam create-instance-profile",
                
                "params": [
                    field('InstanceProfileName', 'InstanceProfileName', True),
                    field('Path', 'Path', False),
                ],
                "run": _query("iam", 'CreateInstanceProfile', names=('InstanceProfileName', 'Path',)),
            },
            {
                "id": 'get-instance-profile',
                "label": 'Get Instance Profile',
                "cli": "aws iam get-instance-profile",
                
                "params": [field('InstanceProfileName', 'InstanceProfileName', True)],
                "run": _query("iam", 'GetInstanceProfile', names=('InstanceProfileName',)),
            },
            {
                "id": 'delete-instance-profile',
                "label": 'Delete Instance Profile',
                "cli": "aws iam delete-instance-profile",
                'destructive': True,
                "params": [field('InstanceProfileName', 'InstanceProfileName', True)],
                "run": _query("iam", 'DeleteInstanceProfile', names=('InstanceProfileName',)),
            },
            {
                "id": 'list-instance-profiles',
                "label": 'List Instance Profiles',
                "cli": "aws iam list-instance-profiles",
                
                "params": [field('PathPrefix', 'PathPrefix', False)],
                "run": _query("iam", 'ListInstanceProfiles', names=('PathPrefix',)),
            },
            {
                "id": 'add-role-to-instance-profile',
                "label": 'Add Role To Instance Profile',
                "cli": "aws iam add-role-to-instance-profile",
                
                "params": [
                    field('InstanceProfileName', 'InstanceProfileName', True),
                    field('RoleName', 'RoleName', True),
                ],
                "run": _query("iam", 'AddRoleToInstanceProfile', names=('InstanceProfileName', 'RoleName',)),
            },
            {
                "id": 'remove-role-from-instance-profile',
                "label": 'Remove Role From Instance Profile',
                "cli": "aws iam remove-role-from-instance-profile",
                'destructive': True,
                "params": [
                    field('InstanceProfileName', 'InstanceProfileName', True),
                    field('RoleName', 'RoleName', True),
                ],
                "run": _query("iam", 'RemoveRoleFromInstanceProfile', names=('InstanceProfileName', 'RoleName',)),
            },
            {
                "id": 'list-instance-profiles-for-role',
                "label": 'List Instance Profiles For Role',
                "cli": "aws iam list-instance-profiles-for-role",
                
                "params": [field('RoleName', 'RoleName', True)],
                "run": _query("iam", 'ListInstanceProfilesForRole', names=('RoleName',)),
            },
            {
                "id": 'tag-instance-profile',
                "label": 'Tag Instance Profile',
                "cli": "aws iam tag-instance-profile",
                
                "params": [
                    field('InstanceProfileName', 'InstanceProfileName', True),
                    field('Tags.member.1.Key', 'Tags member 1 Key', True),
                    field('Tags.member.1.Value', 'Tags member 1 Value', False),
                ],
                "run": _query("iam", 'TagInstanceProfile', names=('InstanceProfileName', 'Tags.member.1.Key', 'Tags.member.1.Value',)),
            },
            {
                "id": 'untag-instance-profile',
                "label": 'Untag Instance Profile',
                "cli": "aws iam untag-instance-profile",
                
                "params": [
                    field('InstanceProfileName', 'InstanceProfileName', True),
                    field('TagKeys.member.1', 'TagKeys member 1', True),
                ],
                "run": _query("iam", 'UntagInstanceProfile', names=('InstanceProfileName', 'TagKeys.member.1',)),
            },
            {
                "id": 'list-instance-profile-tags',
                "label": 'List Instance Profile Tags',
                "cli": "aws iam list-instance-profile-tags",
                
                "params": [field('InstanceProfileName', 'InstanceProfileName', True)],
                "run": _query("iam", 'ListInstanceProfileTags', names=('InstanceProfileName',)),
            },
            {
                "id": 'create-service-linked-role',
                "label": 'Create Service Linked Role',
                "cli": "aws iam create-service-linked-role",
                
                "params": [
                    field('AWSServiceName', 'AWSServiceName', True),
                    field('CustomSuffix', 'CustomSuffix', False),
                    field('Description', 'Description', False),
                ],
                "run": _query("iam", 'CreateServiceLinkedRole', names=('AWSServiceName', 'CustomSuffix', 'Description',)),
            },
            {
                "id": 'delete-service-linked-role',
                "label": 'Delete Service Linked Role',
                "cli": "aws iam delete-service-linked-role",
                'destructive': True,
                "params": [field('RoleName', 'RoleName', True)],
                "run": _query("iam", 'DeleteServiceLinkedRole', names=('RoleName',)),
            },
            {
                "id": 'get-service-linked-role-deletion-status',
                "label": 'Get Service Linked Role Deletion Status',
                "cli": "aws iam get-service-linked-role-deletion-status",
                
                "params": [field('DeletionTaskId', 'DeletionTaskId', True)],
                "run": _query("iam", 'GetServiceLinkedRoleDeletionStatus', names=('DeletionTaskId',)),
            },
            {
                "id": 'update-access-key',
                "label": 'Update Access Key',
                "cli": "aws iam update-access-key",
                
                "params": [
                    field('AccessKeyId', 'AccessKeyId', True),
                    field('Status', 'Status', True),
                    field('UserName', 'UserName', False),
                ],
                "run": _query("iam", 'UpdateAccessKey', names=('AccessKeyId', 'Status', 'UserName',)),
            },
            {
                "id": 'delete-access-key',
                "label": 'Delete Access Key',
                "cli": "aws iam delete-access-key",
                'destructive': True,
                "params": [field('AccessKeyId', 'AccessKeyId', True)],
                "run": _query("iam", 'DeleteAccessKey', names=('AccessKeyId',)),
            },
            {
                "id": 'get-access-key-last-used',
                "label": 'Get Access Key Last Used',
                "cli": "aws iam get-access-key-last-used",
                
                "params": [field('AccessKeyId', 'AccessKeyId', True)],
                "run": _query("iam", 'GetAccessKeyLastUsed', names=('AccessKeyId',)),
            },
            {
                "id": 'deactivate-m-f-a-device',
                "label": 'Deactivate M F A Device',
                "cli": "aws iam deactivate-m-f-a-device",
                'destructive': True,
                "params": [
                    field('UserName', 'UserName', True),
                    field('SerialNumber', 'SerialNumber', True),
                ],
                "run": _query("iam", 'DeactivateMFADevice', names=('UserName', 'SerialNumber',)),
            },
            {
                "id": 'resync-m-f-a-device',
                "label": 'Resync M F A Device',
                "cli": "aws iam resync-m-f-a-device",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('SerialNumber', 'SerialNumber', True),
                    field('AuthenticationCode1', 'AuthenticationCode1', True),
                    field('AuthenticationCode2', 'AuthenticationCode2', True),
                ],
                "run": _query("iam", 'ResyncMFADevice', names=('UserName', 'SerialNumber', 'AuthenticationCode1', 'AuthenticationCode2',)),
            },
            {
                "id": 'delete-virtual-m-f-a-device',
                "label": 'Delete Virtual M F A Device',
                "cli": "aws iam delete-virtual-m-f-a-device",
                'destructive': True,
                "params": [field('SerialNumber', 'SerialNumber', True)],
                "run": _query("iam", 'DeleteVirtualMFADevice', names=('SerialNumber',)),
            },
            {
                "id": 'list-virtual-m-f-a-devices',
                "label": 'List Virtual M F A Devices',
                "cli": "aws iam list-virtual-m-f-a-devices",
                
                "params": [field('AssignmentStatus', 'AssignmentStatus', False)],
                "run": _query("iam", 'ListVirtualMFADevices', names=('AssignmentStatus',)),
            },
            {
                "id": 'create-login-profile',
                "label": 'Create Login Profile',
                "cli": "aws iam create-login-profile",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('Password', 'Password', True),
                    field('PasswordResetRequired', 'PasswordResetRequired', False),
                ],
                "run": _query("iam", 'CreateLoginProfile', names=('UserName', 'Password', 'PasswordResetRequired',)),
            },
            {
                "id": 'get-login-profile',
                "label": 'Get Login Profile',
                "cli": "aws iam get-login-profile",
                
                "params": [field('UserName', 'UserName', True)],
                "run": _query("iam", 'GetLoginProfile', names=('UserName',)),
            },
            {
                "id": 'update-login-profile',
                "label": 'Update Login Profile',
                "cli": "aws iam update-login-profile",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('Password', 'Password', True),
                    field('PasswordResetRequired', 'PasswordResetRequired', False),
                ],
                "run": _query("iam", 'UpdateLoginProfile', names=('UserName', 'Password', 'PasswordResetRequired',)),
            },
            {
                "id": 'delete-login-profile',
                "label": 'Delete Login Profile',
                "cli": "aws iam delete-login-profile",
                'destructive': True,
                "params": [field('UserName', 'UserName', True)],
                "run": _query("iam", 'DeleteLoginProfile', names=('UserName',)),
            },
            {
                "id": 'get-account-authorization-details',
                "label": 'Get Account Authorization Details',
                "cli": "aws iam get-account-authorization-details",
                
                "params": [field('Filter.member.1', 'Filter member 1', False)],
                "run": _query("iam", 'GetAccountAuthorizationDetails', names=('Filter.member.1',)),
            },
            {
                "id": 'generate-service-last-accessed-details',
                "label": 'Generate Service Last Accessed Details',
                "cli": "aws iam generate-service-last-accessed-details",
                
                "params": [field('Arn', 'Arn', True)],
                "run": _query("iam", 'GenerateServiceLastAccessedDetails', names=('Arn',)),
            },
            {
                "id": 'get-service-last-accessed-details',
                "label": 'Get Service Last Accessed Details',
                "cli": "aws iam get-service-last-accessed-details",
                
                "params": [field('JobId', 'JobId', True)],
                "run": _query("iam", 'GetServiceLastAccessedDetails', names=('JobId',)),
            },
            {
                "id": 'create-service-specific-credential',
                "label": 'Create Service Specific Credential',
                "cli": "aws iam create-service-specific-credential",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('ServiceName', 'ServiceName', True),
                ],
                "run": _query("iam", 'CreateServiceSpecificCredential', names=('UserName', 'ServiceName',)),
            },
            {
                "id": 'list-service-specific-credentials',
                "label": 'List Service Specific Credentials',
                "cli": "aws iam list-service-specific-credentials",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('ServiceName', 'ServiceName', False),
                ],
                "run": _query("iam", 'ListServiceSpecificCredentials', names=('UserName', 'ServiceName',)),
            },
            {
                "id": 'update-service-specific-credential',
                "label": 'Update Service Specific Credential',
                "cli": "aws iam update-service-specific-credential",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('ServiceSpecificCredentialId', 'ServiceSpecificCredentialId', True),
                    field('Status', 'Status', True),
                ],
                "run": _query("iam", 'UpdateServiceSpecificCredential', names=('UserName', 'ServiceSpecificCredentialId', 'Status',)),
            },
            {
                "id": 'reset-service-specific-credential',
                "label": 'Reset Service Specific Credential',
                "cli": "aws iam reset-service-specific-credential",
                
                "params": [
                    field('UserName', 'UserName', True),
                    field('ServiceSpecificCredentialId', 'ServiceSpecificCredentialId', True),
                ],
                "run": _query("iam", 'ResetServiceSpecificCredential', names=('UserName', 'ServiceSpecificCredentialId',)),
            },
            {
                "id": 'delete-service-specific-credential',
                "label": 'Delete Service Specific Credential',
                "cli": "aws iam delete-service-specific-credential",
                'destructive': True,
                "params": [
                    field('UserName', 'UserName', True),
                    field('ServiceSpecificCredentialId', 'ServiceSpecificCredentialId', True),
                ],
                "run": _query("iam", 'DeleteServiceSpecificCredential', names=('UserName', 'ServiceSpecificCredentialId',)),
            },
            {
                "id": 'upload-server-certificate',
                "label": 'Upload Server Certificate',
                "cli": "aws iam upload-server-certificate",
                
                "params": [
                    field('ServerCertificateName', 'ServerCertificateName', True),
                    field('CertificateBody', 'CertificateBody', True, kind="textarea"),
                    field('PrivateKey', 'PrivateKey', True, kind="textarea"),
                    field('CertificateChain', 'CertificateChain', False, kind="textarea"),
                    field('Path', 'Path', False),
                ],
                "run": _query("iam", 'UploadServerCertificate', names=('ServerCertificateName', 'CertificateBody', 'PrivateKey', 'CertificateChain', 'Path',)),
            },
            {
                "id": 'list-server-certificates',
                "label": 'List Server Certificates',
                "cli": "aws iam list-server-certificates",
                
                "params": [field('PathPrefix', 'PathPrefix', False)],
                "run": _query("iam", 'ListServerCertificates', names=('PathPrefix',)),
            },
            {
                "id": 'get-server-certificate',
                "label": 'Get Server Certificate',
                "cli": "aws iam get-server-certificate",
                
                "params": [field('ServerCertificateName', 'ServerCertificateName', True)],
                "run": _query("iam", 'GetServerCertificate', names=('ServerCertificateName',)),
            },
            {
                "id": 'update-server-certificate',
                "label": 'Update Server Certificate',
                "cli": "aws iam update-server-certificate",
                
                "params": [
                    field('ServerCertificateName', 'ServerCertificateName', True),
                    field('NewServerCertificateName', 'NewServerCertificateName', False),
                    field('NewPath', 'NewPath', False),
                ],
                "run": _query("iam", 'UpdateServerCertificate', names=('ServerCertificateName', 'NewServerCertificateName', 'NewPath',)),
            },
            {
                "id": 'delete-server-certificate',
                "label": 'Delete Server Certificate',
                "cli": "aws iam delete-server-certificate",
                'destructive': True,
                "params": [field('ServerCertificateName', 'ServerCertificateName', True)],
                "run": _query("iam", 'DeleteServerCertificate', names=('ServerCertificateName',)),
            },
            {
                "id": 'list-server-certificate-tags',
                "label": 'List Server Certificate Tags',
                "cli": "aws iam list-server-certificate-tags",
                
                "params": [field('ServerCertificateName', 'ServerCertificateName', True)],
                "run": _query("iam", 'ListServerCertificateTags', names=('ServerCertificateName',)),
            },
            {
                "id": 'create-policy-version',
                "label": 'Create Policy Version',
                "cli": "aws iam create-policy-version",
                
                "params": [
                    field('PolicyArn', 'PolicyArn', True),
                    field('PolicyDocument', 'PolicyDocument', True, kind="textarea"),
                    field('SetAsDefault', 'SetAsDefault', False),
                ],
                "run": _query("iam", 'CreatePolicyVersion', names=('PolicyArn', 'PolicyDocument', 'SetAsDefault',)),
            },
            {
                "id": 'get-policy-version',
                "label": 'Get Policy Version',
                "cli": "aws iam get-policy-version",
                
                "params": [
                    field('PolicyArn', 'PolicyArn', True),
                    field('VersionId', 'VersionId', True),
                ],
                "run": _query("iam", 'GetPolicyVersion', names=('PolicyArn', 'VersionId',)),
            },
            {
                "id": 'delete-policy-version',
                "label": 'Delete Policy Version',
                "cli": "aws iam delete-policy-version",
                'destructive': True,
                "params": [
                    field('PolicyArn', 'PolicyArn', True),
                    field('VersionId', 'VersionId', True),
                ],
                "run": _query("iam", 'DeletePolicyVersion', names=('PolicyArn', 'VersionId',)),
            },
            {
                "id": 'list-entities-for-policy',
                "label": 'List Entities For Policy',
                "cli": "aws iam list-entities-for-policy",
                
                "params": [
                    field('PolicyArn', 'PolicyArn', True),
                    field('EntityFilter', 'EntityFilter', False),
                ],
                "run": _query("iam", 'ListEntitiesForPolicy', names=('PolicyArn', 'EntityFilter',)),
            },
            {
                "id": 'update-s-a-m-l-provider',
                "label": 'Update S A M L Provider',
                "cli": "aws iam update-s-a-m-l-provider",
                
                "params": [
                    field('SAMLProviderArn', 'SAMLProviderArn', True),
                    field('SAMLMetadataDocument', 'SAMLMetadataDocument', True, kind="textarea"),
                    field('AssertionEncryptionMode', 'AssertionEncryptionMode', False),
                ],
                "run": _query("iam", 'UpdateSAMLProvider', names=('SAMLProviderArn', 'SAMLMetadataDocument', 'AssertionEncryptionMode',)),
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
        "body": body[:200000],
        "error": "" if ok else _error_message(body, status),
    }
