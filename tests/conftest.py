"""Paths, the emulator's HTTP surface, and the control's own signed client: the stand-in frames HTTP only, the emulator routes and handles it."""

from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import types
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
EMULATOR = Path(os.environ.get("EP_EMULATOR_SRC") or ROOT.parent / "ministack-src")
# A lab sweep signs as a real account, so the resources land where a person can see them.
LIVE_ENDPOINT = os.environ.get("EP_LAB_EMULATOR")
# The in-process stand-in tests the API records, not the container engine: a host
# that has a runtime would start real containers, so a create would spend the test
# waiting on an image pull. A lab sweep keeps the socket it was given.
if not LIVE_ENDPOINT:
    os.environ["DOCKER_HOST"] = "unix:///nonexistent/emuplane-in-process"

sys.path[:0] = [str(ROOT / "control"), str(EMULATOR)]

# The S3 handlers read `AUTH` from `ministack.app`, which drags in the server's dependencies; a stand-in is enough here.
if "ministack.app" not in sys.modules:
    _stub = types.ModuleType("ministack.app")
    _stub.AUTH = False
    sys.modules["ministack.app"] = _stub

import signed  # noqa: E402  (the code the control calls)


@pytest.fixture(scope="session")
def emulator():
    """The real `ministack.services.s3` — the parser, not a mock of it."""
    if not EMULATOR.is_dir():
        pytest.skip("ministack-src is not checked out beside the control")
    from ministack.services import s3

    return s3


@pytest.fixture(scope="session")
def s3_endpoint(emulator):
    """The emulator's HTTP surface: the credential's service name picks the handler, S3 by default."""

    # A live lab: the same calls, the account a person can open in the console.
    if LIVE_ENDPOINT:
        yield LIVE_ENDPOINT
        return

    handlers = {"s3": emulator}
    # The credential's service name is what a client signs with; the module is where the emulator implements it.
    service_modules = {
        "s3tables": "s3tables",
        "s3files": "s3files",
        "sts": "sts",
        "account": "account",
        "iam": "iam",
        "ec2": "ec2",
        "sqs": "sqs",
        "sns": "sns",
        "dynamodb": "dynamodb",
        "dynamodbstreams": "dynamodb_streams",
        "logs": "cloudwatch_logs",
        "monitoring": "cloudwatch",
        "cloudwatch": "cloudwatch",
        "secretsmanager": "secretsmanager",
        "rds-data": "rds_data",
        "imds": "imds",
        "ecs-metadata": "ecs_metadata",
        "ssm": "ssm",
        "kinesis": "kinesis",
        "stepfunctions": "stepfunctions",
        "states": "stepfunctions",
        "lambda": "lambda_svc",
        "acm": "acm",
        "mq": "mq",
        "geo": "location",
        "location": "location",
        "apigateway": "apigateway",
        "appsync": "appsync",
        "appsync-events": "appsync_events",
        "transcribe": "transcribe",
        "transfer": "transfer",
        "translate": "translate",
        "cloudformation": "cloudformation",
        "organizations": "organizations",
        "kms": "kms",
        "elasticfilesystem": "efs",
        "ses": "ses",
        "sesv2": "ses_v2",
        "signer": "signer",
        "waf": "waf_v1",
        "waf-regional": "waf_v1",
        "wafv2": "waf",
        "cur": "cur",
        "cloudcontrol": "cloudcontrol",
        "config": "config",
        "budgets": "budgets",
        "firehose": "firehose",
        "codebuild": "codebuild",
        "scheduler": "scheduler",
        "opensearch": "opensearch",
        "batch": "batch",
        "iotwireless": "iotwireless",
        "cloudtrail": "cloudtrail",
        "inspector2": "inspector2",
        "servicediscovery": "servicediscovery",
        "ecr": "ecr",
        "eks": "eks",
        "kinesisanalytics": "kinesisanalyticsv2",
        "elasticmapreduce": "emr",
        "kafka": "msk",
        "resource-groups": "resource_groups",
        "autoscaling": "autoscaling",
        "backup": "backup",
        "elasticloadbalancing": "alb",
        "route53": "route53",
        "aoss": "opensearchserverless",
        "appconfig": "appconfig",
        "bedrock": "bedrock",
        "bedrock-runtime": "bedrock_runtime",
        "bedrock-agent": "bedrock_agent",
        "bedrock-agent-runtime": "bedrock_agent_runtime",
        "bedrock-agentcore": "bedrock_agentcore",
        "iot": "iot",
        "iot-data": "iot_data",
        "iot-jobs-data": "iot_jobs_data",
        "cloudfront": "cloudfront",
        "cloudfront-keyvaluestore": "cloudfront_keyvaluestore",
        "rds": "rds",
        "documentdb": "documentdb",
        "elasticache": "elasticache",
        "ecs": "ecs",
        "events": "eventbridge",
        "dsql": "dsql",
        "athena": "athena",
        "glue": "glue",
        "cognito-idp": "cognito",
        "cognito-identity": "cognito",
    }
    for name, module in service_modules.items():
        try:
            handlers[name] = __import__(
                f"ministack.services.{module}", fromlist=["handle_request"]
            )
        except ImportError as exc:  # pragma: no cover - an older emulator checkout
            # A silent fallback answers as S3, so name the module that is missing instead.
            warnings.warn(f"tests: ministack.services.{module} is not importable ({exc})")

    def bedrock_service(method: str, path: str, body: bytes = b"") -> str:
        """All four Bedrock planes sign as `bedrock`; the path picks one, as in the emulator's router."""
        if (
            path.startswith(("/retrieveAndGenerate", "/rerank", "/optimize-prompt", "/generateQuery", "/sessions"))
            or re.match(r"^/agents/[^/]+/agentAliases/", path)
            or re.match(r"^/flows/[^/]+/aliases/[^/]+/executions", path)
            or re.match(r"^/flows/[^/]+/executions$", path)
            or (method == "POST" and re.match(r"^/flows/[^/]+/aliases/[^/]+$", path))
            or re.match(r"^/knowledgebases/[^/]+/retrieve$", path)
            # InvokeInlineAgent is POST /agents/{sessionId}; real SDKs pick the
            # runtime by host, which an in-process endpoint does not carry, so the
            # body's required `inputText` is the tell (PrepareAgent sends none).
            or (method == "POST" and re.match(r"^/agents/[^/]+$", path)
                and b"inputText" in (body or b""))
        ):
            return "bedrock-agent-runtime"
        if path.startswith(("/agents", "/knowledgebases", "/flows", "/prompts", "/tags")):
            return "bedrock-agent"
        if path.startswith(("/model/", "/guardrail/", "/async-invoke")):
            return "bedrock-runtime"
        return "bedrock"

    def route(headers: dict, method: str = "", path: str = "", body: bytes = b"",
              query: dict | None = None):
        # Two services are addressed by path alone and carry no SigV4 at all:
        # the ECS task metadata and credentials routes, which a container calls
        # on 169.254.170.2. The emulator's own router does the same.
        if path.startswith(("/v4/", "/v2/credentials/")):
            service = "ecs-metadata" if path.startswith("/v4/") else "imds"
            return handlers.get(service, emulator), {"key": "", "region": "us-east-1"}
        auth = headers.get("authorization", "")
        match = re.search(
            r"Credential=([^/]+)/\d{8}/([^/]+)/([^/]+)/aws4_request", auth
        )
        service = match.group(3) if match else "s3"
        # The scoped stores cannot resolve a record before the request's tenancy is
        # pinned, and DocumentDB claims a request by reading one.
        from ministack.core.responses import (
            set_request_account_id,
            set_request_region,
        )

        set_request_account_id(match.group(1) if match else "")
        set_request_region(match.group(2) if match else "us-east-1")
        # DynamoDB Streams signs as `dynamodb`; the target prefix is the only
        # thing that tells the two apart, as in the emulator's own router.
        if headers.get("x-amz-target", "").startswith("DynamoDBStreams_"):
            service = "dynamodbstreams"
        # DocumentDB signs as `rds`; the emulator's router claims its requests by
        # host or content, and an in-process call has no docdb host to read.
        if service == "rds":
            from ministack.services import documentdb  # noqa: PLC0415 - only for rds

            params = documentdb._parse_request_params(body, headers, query or {})
            if documentdb.claims_request(params):
                service = "documentdb"
        if service == "bedrock":
            service = bedrock_service(method, path, body)
        return handlers.get(service, emulator), {
            "key": match.group(1) if match else "",
            "region": match.group(2) if match else "us-east-1",
        }

    def control(s3, method: str, path: str, headers: dict, body: bytes, query: dict):
        """Paths the emulator routes in its ASGI app rather than inside the service."""
        if method == "POST" and path == "/WriteGetObjectResponse" and headers.get(
            "x-amz-request-route"
        ):
            from ministack.services import s3_object_lambda

            return s3_object_lambda.write_get_object_response(headers, body)
        if not hasattr(s3, "is_access_point_control_path"):
            return None
        if path.startswith("/v20180820/mrap/") or path.startswith(
            "/v20180820/async-requests/mrap/"
        ):
            return s3.handle_mrap_control(method, path, headers, body, query)
        if s3.is_access_point_control_path(path):
            return s3.handle_access_point_control(method, path, headers, body, query)
        if s3.is_object_lambda_control_path(path):
            return s3.handle_object_lambda_control(method, path, headers, body, query)
        return None

    def drain(streaming) -> bytes:
        """Run a long-lived ASGI runner to completion against a client that reads two frames.

        A shard subscription or a live tail is held open for minutes; the stand-in
        ends it after the opening frames, which is the part a test asserts. The
        handler still sends them, so the wire shape is the emulator's own.
        """
        chunks: list[bytes] = []

        async def send(message):
            if message.get("type") == "http.response.body":
                chunks.append(message.get("body") or b"")

        async def receive():
            if len(chunks) >= 2:
                return {"type": "http.disconnect"}
            await asyncio.sleep(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        asyncio.run(streaming.runner(send, receive))
        return b"".join(chunks)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the test output readable
            pass

        def _serve(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            split = urlsplit(self.path)
            headers = {key.lower(): value for key, value in self.headers.items()}
            query = parse_qs(split.query, keep_blank_values=True)
            module, scope = route(headers, method, split.path, body, query)
            # The ASGI app pins the credential's account and signing region before any handler runs.
            from ministack.core.responses import (
                set_request_account_id,
                set_request_region,
            )

            set_request_account_id(scope["key"])
            set_request_region(scope["region"])
            handled = control(module, method, split.path, headers, body, query)
            if handled is not None:
                status, out_headers, out_body = handled
            else:
                status, out_headers, out_body = asyncio.run(
                    module.handle_request(method, split.path, headers, body, query)
                )
            # Handlers return the body as bytes or as stored text; the ASGI layer encodes, and so does this.
            if isinstance(out_body, str):
                out_body = out_body.encode()
            if out_body.__class__.__name__ == "StreamingResponse":
                out_body = drain(out_body)
            self.send_response(status)
            for key, value in out_headers.items():
                if key.lower() == "content-length":
                    continue
                self.send_header(key, value)
            # A HEAD answers with no body but the same Content-Length the GET would have.
            length = str(len(out_body))
            if method == "HEAD":
                length = (
                    out_headers.get("Content-Length")
                    or out_headers.get("content-length")
                    or "0"
                )
            self.send_header("Content-Length", length)
            self.end_headers()
            if method != "HEAD" and out_body:
                self.wfile.write(out_body)

        def do_GET(self):
            self._serve("GET")

        def do_PUT(self):
            self._serve("PUT")

        def do_POST(self):
            self._serve("POST")

        def do_DELETE(self):
            self._serve("DELETE")

        def do_PATCH(self):
            self._serve("PATCH")

        def do_HEAD(self):
            self._serve("HEAD")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="session")
def endpoint(s3_endpoint):
    """The same surface, named for what it is: one endpoint, and the credential says which service."""
    return s3_endpoint


@pytest.fixture(scope="session")
def s3(s3_endpoint):
    """`buckets.create`'s client shape, over the wire, as the root user; nothing is deleted, so the matrix's buckets stay readable."""

    def build(account: str, region: str):
        def call(method, path, body="", headers=None):
            return signed.request(
                s3_endpoint, "s3", account, region, method, path, body, headers
            )

        return call

    return build


@pytest.fixture
def recorder():
    """A client that records what was asked for and answers 200, for request-shape tests."""

    class Recorded:
        def __init__(self):
            self.calls = []

        def __call__(self, method, path, body="", headers=None):
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "body": body,
                    "headers": dict(headers or {}),
                }
            )
            return 200, ""

    return Recorded()
