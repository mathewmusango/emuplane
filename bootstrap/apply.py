#!/usr/bin/env python3
"""First-setup job: apply `template.yml` as the stack that owns the control's own DynamoDB tables."""

from __future__ import annotations

import http.client
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

HERE = Path(__file__).resolve().parent

# `control/` holds the DynamoDB client; in the image both live side by side in /app.
for candidate in (HERE, HERE.parent / "control", HERE.parent):
    if (candidate / "dynamo.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from dynamo import Dynamo, DynamoError  # noqa: E402
from store import PREFIX as STORE_PREFIX, TABLES  # noqa: E402

API_VERSION = "2010-05-15"
STACK = os.environ.get("EP_STACK_NAME", "emuplane")
PREFIX = os.environ.get("EP_TABLE_PREFIX") or STORE_PREFIX
TEMPLATE = Path(os.environ.get("MC_TEMPLATE") or HERE / "template.yml")


class StackError(RuntimeError):
    """CloudFormation refused a call; the message carries its code."""


def endpoint() -> str:
    return (
        os.environ.get("EP_STORE_URL")
        or os.environ.get("EP_BACKEND_URL")
        or "http://localhost:4566"
    ).rstrip("/")


def call(action: str, params: dict[str, str]) -> ET.Element:
    """One CloudFormation query call, signed like the store's DynamoDB calls: no boto3, no secret."""
    url = urlsplit(endpoint())
    account = os.environ.get("EP_STORE_ACCOUNT") or "111111111111"
    region = os.environ.get("EP_STORE_REGION") or "us-east-1"
    body = urlencode({"Action": action, "Version": API_VERSION, **params}).encode()
    now = datetime.now(timezone.utc)
    headers = {
        "Host": f"{url.hostname}:{url.port or 80}",
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={account}/{now:%Y%m%d}/{region}"
            "/cloudformation/aws4_request, SignedHeaders=host, Signature=local"
        ),
        "x-amz-date": now.strftime("%Y%m%dT%H%M%SZ"),
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
    }
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=10)
    try:
        conn.request("POST", url.path or "/", body=body, headers=headers)
        response = conn.getresponse()
        text = response.read().decode(errors="replace")
    finally:
        conn.close()

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        root = ET.Element("Unparseable")
    if response.status >= 400:
        code = text_of(root, "Code") or f"HTTP {response.status}"
        message = text_of(root, "Message") or text.strip()[:200]
        raise StackError(f"{code}: {message}")
    return root


def text_of(root: ET.Element, name: str) -> str:
    """The first element called `name`, whatever namespace it carries."""
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == name:
            return (element.text or "").strip()
    return ""


def status() -> str:
    """The stack's status, or '' when no stack of that name exists."""
    try:
        root = call("DescribeStacks", {"StackName": STACK})
    except StackError as exc:
        if "does not exist" in str(exc).lower():
            return ""
        raise
    return text_of(root, "StackStatus")


def missing_tables() -> list[str]:
    dynamo = Dynamo()
    return [PREFIX + store for store in TABLES if not dynamo.table_exists(PREFIX + store)]


def wait_for_terminal_state() -> str:
    for _ in range(90):
        state = status()
        if state and state.endswith(("_COMPLETE", "_FAILED")):
            return state
        time.sleep(2)
    return status()


def drop_tables() -> int:
    """Delete the stack and every control table: the one-off that returns to a first setup."""
    if status():
        call("DeleteStack", {"StackName": STACK})
        wait_for_terminal_state()
        print(f"bootstrap: stack {STACK} deleted", flush=True)
    dynamo = Dynamo()
    dropped = 0
    for store in TABLES:
        name = PREFIX + store
        try:
            dynamo.call("DeleteTable", {"TableName": name})
            dropped += 1
        except DynamoError as exc:
            if exc.code != "ResourceNotFoundException":
                raise
    print(f"bootstrap: dropped {dropped} table(s) under `{PREFIX}`", flush=True)
    return 0


def stack_params() -> dict[str, str]:
    """The request body shared by CreateStack and UpdateStack."""
    return {
        "StackName": STACK,
        "TemplateBody": TEMPLATE.read_text(encoding="utf-8"),
        "Parameters.member.1.ParameterKey": "TablePrefix",
        "Parameters.member.1.ParameterValue": PREFIX,
        "TimeoutInMinutes": "10",
    }


def apply_update() -> tuple[bool, str]:
    """Bring an existing stack to the current template; `No updates are to be performed` is success."""
    try:
        call("UpdateStack", stack_params())
    except StackError as exc:
        message = str(exc).lower()
        if "no update" in message or "no changes" in message:
            return True, "already current"
        return False, str(exc)
    return wait_for_terminal_state() == "UPDATE_COMPLETE", ""


def main() -> int:
    if "--drop-tables" in sys.argv[1:]:
        return drop_tables()

    if "--delete" in sys.argv[1:]:
        # For smoke runs of the template, and for a deliberate teardown.
        try:
            call("DeleteStack", {"StackName": STACK})
        except (OSError, StackError) as exc:
            print(f"bootstrap: cannot delete {STACK}: {exc}", flush=True)
            return 1
        state = wait_for_terminal_state()
        print(f"bootstrap: stack {STACK} deleted ({state or 'gone'})", flush=True)
        return 0 if not state or state == "DELETE_COMPLETE" else 1

    if not TEMPLATE.is_file():
        print(f"bootstrap: template not found at {TEMPLATE}", flush=True)
        return 1

    state = status()
    if state:
        if state.endswith("COMPLETE") and "IN_PROGRESS" not in state and not state.startswith("ROLLBACK"):
            # The stack is ours and healthy; make sure it matches this template.
            print(f"bootstrap: checking stack {STACK} against {TEMPLATE.name}", flush=True)
            updated, problem = apply_update()
            if not updated:
                print(f"bootstrap: cannot update the stack: {problem}", flush=True)
                return 1
        elif state.endswith("IN_PROGRESS"):
            print(f"bootstrap: stack {STACK} is {state}; waiting for it", flush=True)
            state = wait_for_terminal_state()
        if state.endswith("_FAILED") or state.startswith("ROLLBACK"):
            print(f"bootstrap: stack {STACK} is {state}; delete it and re-run", flush=True)
            return 1
    else:
        missing = missing_tables()
        if len(missing) < len(TABLES):
            have = len(TABLES) - len(missing)
            print(
                f"bootstrap: {have} table(s) already exist without a stack owning them; "
                f"CloudFormation cannot adopt them, so no stack was created",
                flush=True,
            )
            print(
                "bootstrap: the control will run against those tables. To bring them "
                "under the stack, drop the control tables on a fresh setup and re-run.",
                flush=True,
            )
        else:
            print(f"bootstrap: creating stack {STACK} from {TEMPLATE.name}", flush=True)
            try:
                call("CreateStack", stack_params())
            except (OSError, StackError) as exc:
                print(f"bootstrap: cannot create the stack at {endpoint()}: {exc}", flush=True)
                return 1
            state = wait_for_terminal_state()
            if state != "CREATE_COMPLETE":
                print(f"bootstrap: stack {STACK} ended {state or 'unknown'}", flush=True)
                return 1

    missing = missing_tables()
    if missing:
        print(
            "bootstrap: the stack is up but these tables are missing: "
            + ", ".join(missing),
            flush=True,
        )
        return 1
    print(
        f"bootstrap: stack {STACK} owns {len(TABLES)} tables under `{PREFIX}` — provisioned",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, DynamoError) as exc:
        print(f"bootstrap: cannot reach the emulator at {endpoint()}: {exc}", flush=True)
        raise SystemExit(1)
