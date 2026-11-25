"""API Gateway v2 @connections on a live WebSocket: PostToConnection, GetConnection, DeleteConnection.

A connection id exists only after a real `websocket.connect`, which the in-process
HTTP stand-in cannot produce. These three tests therefore run against a lab
(`EP_LAB_EMULATOR`) and skip in CI, next to the matrix modules that need a live
endpoint for the same kind of reason.

The API is found-or-created behind a pinned `ms-custom-id`; the `$default` route is
a Lambda that echoes `requestContext.connectionId` back over the socket, which is
how the test learns the id a real client never sees. A `$connect` route is
deliberately absent, so the upgrade is accepted without an authorizer.
"""

from __future__ import annotations

import base64
import io
import json
import os
import socket
import zipfile
from urllib.parse import urlencode, urlsplit

import pytest

import signed
from conftest import ACCOUNT

pytestmark = pytest.mark.skipif(
    not os.environ.get("EP_LAB_EMULATOR"),
    reason="a connection id needs a real WebSocket upgrade; the in-process stand-in is HTTP only",
)

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

API = "ops-ws-connections"
API_ID = "opswscon"
STAGE = "prod"
ROUTE = "$default"

FUNCTION = "ops-ws-echo"
ROLE_NAME = "ops-ws-lambda"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"
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
import json

def handler(event, context):
    rc = event.get('requestContext', {})
    return {'statusCode': 200, 'body': json.dumps({'connectionId': rc.get('connectionId')})}
"""


def apigw(endpoint, method: str, path: str, body="") -> tuple[int, str]:
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    return signed.request(
        endpoint, "apigateway", ACCOUNT, REGION, method, path, body, JSON if body else None
    )


def ok(endpoint, method: str, path: str, body="") -> dict:
    status, text = apigw(endpoint, method, path, body)
    assert status in (200, 201, 202, 204), f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text) if text.strip() else {}


def lam(endpoint, method: str, path: str, body="") -> tuple[int, str]:
    headers = JSON if body else None
    return signed.request(endpoint, "lambda", ACCOUNT, REGION, method, path, body, headers)


def package() -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("index.py", HANDLER)
    return base64.b64encode(buffer.getvalue()).decode()


def role(endpoint) -> None:
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


def function_arn(endpoint) -> str:
    role(endpoint)
    status, text = lam(
        endpoint,
        "POST",
        "/2015-03-31/functions",
        json.dumps(
            {
                "FunctionName": FUNCTION,
                "Runtime": "python3.12",
                "Role": ROLE,
                "Handler": "index.handler",
                "Code": {"ZipFile": package()},
            }
        ),
    )
    if status in (200, 201):
        return json.loads(text)["FunctionArn"]
    assert status == 409, f"CreateFunction answered {status}: {text[:400]}"
    status, text = lam(endpoint, "GET", f"/2015-03-31/functions/{FUNCTION}")
    assert status == 200, text[:400]
    return json.loads(text)["Configuration"]["FunctionArn"]


def socket_route(endpoint) -> str:
    """Find-or-create the WS API, its `$default` Lambda route and the stage."""
    status, text = apigw(
        endpoint,
        "POST",
        "/v2/apis",
        {
            "name": API,
            "protocolType": "WEBSOCKET",
            "description": "ops @connections fixture",
            "tags": {"ms-custom-id": API_ID},
        },
    )
    if status == 201:
        api_id = json.loads(text)["apiId"]
    else:
        assert status == 409, f"CreateApi answered {status}: {text[:400]}"
        api_id = ok(endpoint, "GET", f"/v2/apis/{API_ID}")["apiId"]

    routes = ok(endpoint, "GET", f"/v2/apis/{api_id}/routes").get("items", [])
    if not any(route["routeKey"] == ROUTE for route in routes):
        integration = ok(
            endpoint,
            "POST",
            f"/v2/apis/{api_id}/integrations",
            {
                "integrationType": "AWS_PROXY",
                "integrationUri": function_arn(endpoint),
                "integrationMethod": "POST",
                "description": "ops @connections echo",
            },
        )
        ok(
            endpoint,
            "POST",
            f"/v2/apis/{api_id}/routes",
            {"routeKey": ROUTE, "target": f"integrations/{integration['integrationId']}"},
        )

    stages = ok(endpoint, "GET", f"/v2/apis/{api_id}/stages").get("items", [])
    if not any(stage["stageName"] == STAGE for stage in stages):
        ok(endpoint, "POST", f"/v2/apis/{api_id}/stages", {"stageName": STAGE})
    return api_id


class WebSocket:
    """A blocking client: one handshake, text frames, close on read."""

    def __init__(self, host: str, port: int, path: str):
        self._socket = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._socket.sendall(handshake.encode())
        self._buffer = b""
        while b"\r\n\r\n" not in self._buffer:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise RuntimeError("the upgrade was closed before its headers")
            self._buffer += chunk
        head, _, self._buffer = self._buffer.partition(b"\r\n\r\n")
        assert b" 101 " in head.split(b"\r\n")[0], head[:200]

    def _read(self, size: int) -> bytes:
        while len(self._buffer) < size:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise RuntimeError("the socket closed mid-frame")
            self._buffer += chunk
        found, self._buffer = self._buffer[:size], self._buffer[size:]
        return found

    def send(self, text: str) -> None:
        payload = text.encode()
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        header = bytes([0x81])
        if len(payload) < 126:
            header += bytes([0x80 | len(payload)])
        elif len(payload) < 65536:
            header += bytes([0x80 | 126]) + len(payload).to_bytes(2, "big")
        else:
            header += bytes([0x80 | 127]) + len(payload).to_bytes(8, "big")
        self._socket.sendall(header + mask + masked)

    def recv(self, timeout: float = 15.0) -> str | None:
        self._socket.settimeout(timeout)
        first = self._read(2)
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        if length == 126:
            length = int.from_bytes(self._read(2), "big")
        elif length == 127:
            length = int.from_bytes(self._read(8), "big")
        payload = self._read(length)
        return None if opcode == 8 else payload.decode()

    def close(self) -> None:
        self._socket.close()


def open_connection(endpoint):
    """A WebSocket on the shared API, plus the connection id its `$default` Lambda echoed."""
    url = urlsplit(endpoint)
    api_id = socket_route(endpoint)
    path = f"/_aws/execute-api/{api_id}/{STAGE}"
    client = WebSocket(url.hostname, url.port or 80, path)
    client.send(json.dumps({"action": "identify"}))
    reply = client.recv()
    assert reply, "the $default Lambda answered nothing"
    return Connection(endpoint, api_id, client, json.loads(reply)["connectionId"])


class Connection:
    def __init__(self, endpoint: str, api_id: str, client: WebSocket, connection_id: str):
        self.endpoint = endpoint
        self.api_id = api_id
        self.client = client
        self.connection_id = connection_id

    def call(self, method: str = "GET", body: bytes | None = None):
        """The @connections runtime call, signed `execute-api` as the management plane expects."""
        path = f"/_aws/execute-api/{self.api_id}/{STAGE}/@connections/{self.connection_id}"
        headers = {"Content-Type": "application/octet-stream"} if body else None
        return signed.request(
            self.endpoint, "execute-api", ACCOUNT, REGION, method, path, body or "", headers
        )


@pytest.fixture
def connected(endpoint):
    connection = open_connection(endpoint)
    yield connection
    connection.client.close()


def test_post_to_connection_pushes_to_the_socket(connected):
    status, text = connected.call("POST", b"server-push")
    assert status == 200, text[:300]
    assert connected.client.recv(timeout=5) == "server-push"


def test_get_connection_reads_the_live_connection(connected):
    status, text = connected.call()
    assert status == 200, text[:300]
    answered = json.loads(text)
    assert answered["ConnectedAt"] and answered["LastActiveAt"]
    assert answered["Identity"]["sourceIp"]


def test_delete_connection_closes_it(connected):
    status, text = connected.call("DELETE")
    assert status == 204, text[:300]
    status, text = connected.call()
    assert status == 410, text[:300]
