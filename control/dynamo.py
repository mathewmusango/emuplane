#!/usr/bin/env python3
"""DynamoDB as the emulator serves it: a stdlib-only client for the control's store, signed `Signature=local`."""

from __future__ import annotations

import http.client
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit


class DynamoError(RuntimeError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}" if code else f"HTTP {status}: {message}")
        self.status = status
        self.code = code


def _error(body: str) -> tuple[str, str]:
    try:
        data = json.loads(body)
    except ValueError:
        return "", body.strip()[:200]
    # both the JSON 1.0 and 1.1 error shapes
    code = data.get("__type") or data.get("code") or ""
    if "#" in code:  # "com.amazonaws.dynamodb.v20120810#ResourceNotFoundException"
        code = code.rsplit("#", 1)[1]
    return code, data.get("message") or data.get("Message") or ""


class Dynamo:
    """The control's view of one endpoint and one account."""

    def __init__(
        self,
        endpoint: str | None = None,
        account: str | None = None,
        region: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = (
            endpoint
            or os.environ.get("EP_STORE_URL")
            or os.environ.get("EP_BACKEND_URL")
            or "http://localhost:4566"
        ).rstrip("/")
        self.account = account or os.environ.get("EP_STORE_ACCOUNT") or "111111111111"
        self.region = region or os.environ.get("EP_STORE_REGION") or "us-east-1"
        self.timeout = timeout

    # -- transport ---------------------------------------------------------

    def call(self, operation: str, payload: dict) -> dict:
        url = urlsplit(self.endpoint)
        body = json.dumps(payload).encode()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        headers = {
            "Host": f"{url.hostname}:{url.port or 80}",
            "Authorization": (
                f"AWS4-HMAC-SHA256 Credential={self.account}/{stamp}/{self.region}"
                "/dynamodb/aws4_request, SignedHeaders=host, Signature=local"
            ),
            "x-amz-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "X-Amz-Target": f"DynamoDB_20120810.{operation}",
            "Content-Type": "application/x-amz-json-1.0",
            "Content-Length": str(len(body)),
        }
        conn = http.client.HTTPConnection(
            url.hostname, url.port or 80, timeout=self.timeout
        )
        try:
            conn.request("POST", url.path or "/", body=body, headers=headers)
            response = conn.getresponse()
            text = response.read().decode(errors="replace")
            if response.status >= 400:
                raise DynamoError(response.status, *_error(text))
            return json.loads(text) if text else {}
        finally:
            conn.close()

    # -- tables ------------------------------------------------------------

    def table_exists(self, name: str) -> bool:
        try:
            self.call("DescribeTable", {"TableName": name})
            return True
        except DynamoError as exc:
            if exc.code == "ResourceNotFoundException":
                return False
            raise

    # -- items -------------------------------------------------------------

    def get(self, table: str, key: str) -> str | None:
        """One item's payload, or None. A missing item is not an error."""
        try:
            answer = self.call(
                "GetItem",
                {"TableName": table, "Key": {"pk": {"S": key}}},
            )
        except DynamoError as exc:
            if exc.code == "ResourceNotFoundException":
                return None
            raise
        item = answer.get("Item") or {}
        return (item.get("payload") or {}).get("S")

    def put(self, table: str, key: str, payload: str) -> None:
        self.call(
            "PutItem",
            {"TableName": table, "Item": {"pk": {"S": key}, "payload": {"S": payload}}},
        )

    def delete(self, table: str, key: str) -> None:
        self.call("DeleteItem", {"TableName": table, "Key": {"pk": {"S": key}}})

    def scan(self, table: str) -> list[tuple[str, str]]:
        """Every (key, payload) in the table, following pagination."""
        found: list[tuple[str, str]] = []
        start = None
        while True:
            payload: dict = {"TableName": table}
            if start:
                payload["ExclusiveStartKey"] = start
            page = self.call("Scan", payload)
            for item in page.get("Items", []):
                found.append(
                    (
                        item.get("pk", {}).get("S", ""),
                        item.get("payload", {}).get("S", ""),
                    )
                )
            start = page.get("LastEvaluatedKey")
            if not start:
                return found
