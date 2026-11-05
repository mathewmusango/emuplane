#!/usr/bin/env python3
"""Control plane for the MiniStack emulator.

One process, two listeners:

  :8080  admin API and HTML dashboard (published as 127.0.0.1:4570)
  :4566  AWS gateway, the single entrypoint for every AWS client
         (published as 127.0.0.1:4571)

Design rules:

  * There is one emulator. MiniStack partitions state by account (a 12-digit
    access key) and by region (the SigV4 scope) inside a single process, so
    regions and accounts are configuration, not containers.
  * The control plane never depends on the emulator being up. It starts first,
    polls it, and renders from a cache — a dead emulator is shown as DOWN, not
    as a missing page.
  * The S3 inventory is cached and persisted. A failed refresh keeps the known
    buckets and marks them stale rather than dropping them.
  * The gateway reads the signing region and the access key and forwards to the
    one emulator. It also keeps **one global bucket-name registry**, because
    AWS keeps S3 names unique across accounts and regions alike: CreateBucket
    is reserved atomically, so a name cannot be claimed twice.

No third-party dependencies: the image is stock `python:3.13-alpine`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import http.client
import json
import os
import queue
import re
import secrets
import smtplib
import sqlite3
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import console  # noqa: E402  (local module: action catalogue)

REGISTRY_FILE = os.environ.get(
    "CONTROL_REGISTRY_FILE", "/var/lib/ministack/control/registry.json"
)
NODES_FILE = os.environ.get(
    "CONTROL_NODES_FILE", "/var/lib/ministack/control/nodes.json"
)
ACCOUNTS_FILE = os.environ.get(
    "CONTROL_ACCOUNTS_FILE", "/var/lib/ministack/control/accounts.json"
)
USERS_DB = os.environ.get(
    "CONTROL_USERS_DB", "/var/lib/ministack/control/users.db"
)
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", "8080"))
GATEWAY_PORT = int(os.environ.get("CONTROL_GATEWAY_PORT", "4566"))
ADMIN_TOKEN = os.environ.get("MC_ADMIN_TOKEN", "").strip()
MODE_RAW = os.environ.get("MINISTACK_CONTROL_MODE", "central").strip().lower()
# Accept a versioned prefix, e.g. v1:central, v1beta1:quorum, v1alpha1:mesh.
MODE = MODE_RAW.split(":")[-1]
if MODE not in {"central", "mesh", "quorum"}:
    MODE = "central"
MESH_TOKEN = os.environ.get("MINISTACK_MESH_TOKEN", "").strip()
# One emulator, many regions and accounts: these are data, not containers.
# MiniStack's own fallback region for unsigned callers. There is no configured
# region list: every region exists, and the one a request uses comes from its
# SigV4 scope. These are just the regions seen so far (for the UI).
DEFAULT_REGION = "us-east-1"
SEEN_REGIONS: set[str] = set()
SEEN_LOCK = threading.Lock()
NODE_NAME = os.environ.get("MINISTACK_NODE_NAME", "ministack").strip() or "ministack"
NODE_URL = os.environ.get(
    "MINISTACK_NODE_URL", "http://core-ministack:4566"
).rstrip("/")
POLL_SECONDS = int(os.environ.get("CONTROL_POLL_SECONDS", "10"))
JOIN_TOKEN = os.environ.get("MINISTACK_JOIN_TOKEN", "").strip()
NODE_TTL_SECONDS = int(os.environ.get("NODE_TTL_SECONDS", "30"))

API_VERSION = "v1"
STARTED_AT = time.time()
# Canonical public addresses shown in the UI (Traefik, lab wildcard cert).
GATEWAY_URL = os.environ.get("MINISTACK_GATEWAY_URL", "https://aws.mus.com")
CONSOLE_URL = os.environ.get("MINISTACK_CONSOLE_URL", "https://ministack.mus.com")
# The optional resource browser (StackPort) running beside the control plane.
# (Retired 2026-11-05; the classic nav links to /resources directly now.)
# Regions offered in the console. MiniStack serves all of them; the list only
# decides what the picker shows, and anything seen at the gateway is added.
REGION_CHOICES = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "ca-central-1", "ca-west-1", "sa-east-1", "mx-central-1",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-central-2",
    "eu-north-1", "eu-south-1", "eu-south-2", "eusc-de-east-1",
    "ap-south-1", "ap-south-2", "ap-east-1", "ap-east-2",
    "ap-southeast-1", "ap-southeast-2", "ap-southeast-3", "ap-southeast-4",
    "ap-southeast-5", "ap-southeast-7",
    "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
    "me-south-1", "me-central-1", "af-south-1", "il-central-1",
]

# Which regions this instance exposes. Unset means `all`: every region exists,
# and the one a request uses comes from its SigV4 scope.
REGION_SETTING = os.environ.get("MC_REGIONS", "all").strip()
if REGION_SETTING.lower() in {"all", "*", ""}:
    ENABLED_REGIONS = list(REGION_CHOICES)
else:
    ENABLED_REGIONS = [
        name.strip()
        for name in REGION_SETTING.split(",")
        if name.strip() in REGION_CHOICES
    ] or [DEFAULT_REGION]

# Optional bootstrap administrator. Only seeded into an empty user store.
# The email matters: `/forgot` can only mail a user that has one.
ADMIN_USER = os.environ.get("MC_ADMIN_USER", "").strip()
ADMIN_EMAIL = os.environ.get("MC_ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.environ.get("MC_ADMIN_PASSWORD", "").strip()

# The React console. Built by `npm run build` in `web/` and mounted here; the
# server-rendered pages stay available under /classic.
STATIC_DIR = os.environ.get("MINISTACK_STATIC_DIR", "/app/static")
PUBLIC_DIR = os.environ.get("MINISTACK_PUBLIC_DIR", "/app/public")
SPA_ROUTES = {"/", "/resources", "/favorites", "/accounts", "/onboarding",
              "/settings", "/about"}
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}
SESSION_SECONDS = int(os.environ.get("MC_SESSION_SECONDS", "28800"))
# AWS allows two access keys per IAM user; the console holds the same line per
# account so a rotation can overlap (create the new key, then delete the old).
MAX_ACCESS_KEYS = 2
MODE_STABILITY = {"central": "stable", "quorum": "beta", "mesh": "alpha"}
SETTINGS_FILE = os.environ.get(
    "CONTROL_SETTINGS_FILE", "/var/lib/ministack/control/settings.json"
)
AUDIT_FILE = os.environ.get(
    "CONTROL_AUDIT_FILE", "/var/lib/ministack/control/audit.jsonl"
)
# Who created a resource from the console. Best-effort provenance: the emulator
# itself records no owner, so anything created with the CLI has none.
OWNERS_FILE = os.environ.get(
    "CONTROL_OWNERS_FILE", "/var/lib/ministack/control/ownership.json"
)
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
OTEL_SERVICE = os.environ.get("OTEL_SERVICE_NAME", "ministack-control")

AUTH_MODE = os.environ.get("MC_AUTH_MODE", "local").strip().lower()
if AUTH_MODE not in {"local", "oidc", "both"}:
    AUTH_MODE = "local"
AUDIT_ENABLED = os.environ.get("MC_AUDIT", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RECENT_LIMIT = int(os.environ.get("MC_RECENT_LIMIT", "5") or 5)
# The canonical public address. Reset links and the OIDC redirect derive from it.
PUBLIC_URL = os.environ.get("MC_PUBLIC_URL", "https://ministack.mus.com").strip().rstrip("/")
OIDC_ENABLED = os.environ.get("MC_OIDC_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}
OIDC_PUBLIC_URL = os.environ.get(
    "MC_OIDC_PUBLIC_URL", "https://keycloak.mus.com"
).rstrip("/")
OIDC_INTERNAL_URL = os.environ.get(
    "MC_OIDC_INTERNAL_URL", "http://security-keycloak:8080"
).rstrip("/")
OIDC_REALM = os.environ.get("MC_OIDC_REALM", "my-labs")
# keycloak  = {public}/realms/{realm}/protocol/openid-connect/...
# provider  = OpenBao-style identity/oidc provider discovery document
OIDC_STYLE = os.environ.get("MC_OIDC_STYLE", "keycloak").strip().lower()
if OIDC_STYLE not in {"keycloak", "openbao", "provider"}:
    OIDC_STYLE = "keycloak"
OIDC_PROVIDER = os.environ.get("MC_OIDC_PROVIDER", "default").strip() or "default"
OIDC_SCOPES = "openid profile email"
OIDC_DISCOVERY_URL = os.environ.get("MC_OIDC_DISCOVERY_URL", "").strip()
OIDC_AUTHORIZE_URL = os.environ.get("MC_OIDC_AUTHORIZE_URL", "").strip()
OIDC_CLIENT_ID = os.environ.get("MC_OIDC_CLIENT_ID", "ministack-control")
OIDC_CLIENT_SECRET = os.environ.get("MC_OIDC_CLIENT_SECRET", "").strip()
OIDC_REDIRECT_URI = os.environ.get(
    "MC_OIDC_REDIRECT_URI", f"{PUBLIC_URL}/oidc/callback"
)
OIDC_PROVIDER_LABEL = "OpenBao" if OIDC_STYLE in {"openbao", "provider"} else "Keycloak"
# Client role that makes an OIDC identity a global admin, like Grafana's roles.
OIDC_ADMIN_ROLE = os.environ.get("MC_OIDC_ADMIN_ROLE", "global-admin").strip()

# --- email (password reset) --------------------------------------------
# StartTLS on 587 by default; `ssl` for 465, `none` only for a local relay.
SMTP_HOST = os.environ.get("MC_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("MC_SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("MC_SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("MC_SMTP_PASSWORD", "").strip()
# An authenticated relay usually insists the From address is the account it
# authenticated as, so fall back to it rather than to a made-up domain.
SMTP_FROM = os.environ.get("MC_SMTP_FROM", "").strip() or SMTP_USER
SMTP_FROM_NAME = os.environ.get("MC_SMTP_FROM_NAME", "MiniStack").strip()
SMTP_TLS = os.environ.get("MC_SMTP_TLS", "starttls").strip().lower()
SMTP_ENABLED = bool(SMTP_HOST)
RESET_TTL_SECONDS = int(os.environ.get("MC_RESET_TTL_SECONDS", "1800"))

GLOBAL_SERVICES = {
    "iam",
    "sts",
    "cloudfront",
    "cloudfront-keyvaluestore",
    "route53",
    "organizations",
}
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "expect",
}

# The upstream catalogue's sections, so the menu and /services read the same way
# as github.com/ministackorg/ministack. Anything not listed lands in "Other".
SERVICE_GROUPS: list[tuple[str, set[str]]] = [
    ("Core", {
        "s3", "sqs", "sns", "dynamodb", "dynamodbstreams", "lambda",
        "lambda-core", "lambda-microvms", "iam", "sts", "imds",
        "ecs-metadata", "secretsmanager", "logs", "monitoring", "ses",
        "acm", "backup", "bedrock", "bedrock-runtime", "bedrock-agent",
        "bedrock-agent-runtime", "bedrock-agentcore", "transcribe",
        "translate", "kafka", "waf", "waf-regional", "wafv2", "states",
        "apigateway", "elasticloadbalancing", "kms", "cloudfront",
        "cloudfront-keyvaluestore", "cloudtrail", "resource-groups",
        "config", "cloudcontrol", "cur", "budgets", "kinesisanalyticsv2",
        "inspector2", "mq", "location", "tagging",
    }),
    ("Extended", {
        "ssm", "events", "kinesis", "appsync", "appsync-events",
        "mediaconnect", "pipes",
    }),
    ("Infrastructure", {
        "ecs", "rds", "rds-data", "documentdb", "dsql", "elasticache",
        "glue", "s3tables", "athena", "firehose", "route53", "ec2",
        "elasticfilesystem", "elasticmapreduce", "cognito-idp",
        "cognito-identity", "ecr", "appconfig", "appconfigdata",
        "servicediscovery", "autoscaling", "codebuild", "scheduler", "iot",
        "iot-data", "iot-jobs-data", "iotwireless", "eks", "opensearch",
        "opensearchserverless", "organizations", "account", "signer",
        "batch", "s3files", "transfer", "airflow",
    }),
    ("CloudFormation", {"cloudformation"}),
]


def grouped_services(services: dict) -> list[tuple[str, list[str]]]:
    """Group the emulator's service map into the upstream sections."""
    groups: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for label, members in SERVICE_GROUPS:
        names = sorted(name for name in services if name in members)
        if names:
            groups.append((label, names))
            seen.update(names)
    other = sorted(name for name in services if name not in seen)
    if other:
        groups.append(("Other", other))
    return groups


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def send_mail(to_address: str, subject: str, body: str) -> str:
    """One plain-text message through the configured relay. Returns "" or an error."""
    if not SMTP_ENABLED:
        return "email is not configured"
    if not SMTP_FROM:
        return "no sender address: set MC_SMTP_FROM or MC_SMTP_USER"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    message["To"] = to_address
    message.set_content(body)
    try:
        if SMTP_TLS == "ssl":
            client = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        else:
            client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        with client:
            if SMTP_TLS == "starttls":
                client.starttls()
            if SMTP_USER:
                client.login(SMTP_USER, SMTP_PASSWORD)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # The exception text can carry the relay's banner, never the password.
        return f"could not send mail: {exc.__class__.__name__}: {exc}"
    return ""


# The emulator entry, refreshed from NodeRegistry. Everything below iterates
# this list; it is replaced in place so module-level readers always see truth.
NODES: list[dict] = []


class NodeRegistry:
    """One configured emulator; seeded at startup, never discovered."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.nodes: dict[str, dict] = {}
        self._load()
        self._sync()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.nodes = {node["name"]: node for node in data.get("nodes", [])}
        except (OSError, json.JSONDecodeError):
            self.nodes = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(
                {"nodes": sorted(self.nodes.values(), key=lambda n: n["name"])},
                handle,
                indent=2,
            )
        os.replace(tmp, self.path)

    def _sync(self) -> None:
        NODES[:] = sorted(self.nodes.values(), key=lambda node: node["name"])

    def ensure_static(
        self, name: str, endpoint: str, region: str
    ) -> None:
        """Seed the emulator entry: it is configured, never discovered.

        MiniStack already serves every region and account from one process, so
        there is nothing to discover and nothing that may expire.
        """
        with self.lock:
            # One emulator is the whole model; entries registered by the retired
            # per-region agents are leftovers and must not linger in the UI.
            self.nodes = {}
            node = {
                "name": name,
                "region": region,
                "endpoint": endpoint,
                "agent": "",
                "static": True,
                "last_seen": time.time(),
            }
            self.nodes[name] = node
            self._save()
            self._sync()

    def register(self, payload: dict, token: str) -> tuple[int, str]:
        name = str(payload.get("name", "")).strip()
        region = str(payload.get("region", "")).strip()
        account = str(payload.get("account_id", "")).strip()
        endpoint = str(payload.get("endpoint", "")).strip()
        agent = str(payload.get("agent", "")).strip()
        if not JOIN_TOKEN or not hmac.compare_digest(token, JOIN_TOKEN):
            return 401, "invalid join token"
        if not name or not region or not endpoint:
            return 400, "name, region and endpoint are required"
        with self.lock:
            for other in self.nodes.values():
                if other["region"] == region and other["name"] != name:
                    return 409, f"region {region} is already registered by {other['name']}"
            existing = self.nodes.get(name)
            if existing and existing["region"] != region:
                return 409, f"node {name} is already registered in {existing['region']}"
            self.nodes[name] = {
                "name": name,
                "region": region,
                "account_id": account,
                "endpoint": endpoint,
                "agent": agent,
                "last_seen": time.time(),
            }
            self._save()
            self._sync()
        return 201 if existing is None else 200, "registered"

    def heartbeat(self, name: str) -> bool:
        with self.lock:
            node = self.nodes.get(name)
            if node is None:
                return False
            node["last_seen"] = time.time()
            self._save()
            self._sync()
            return True

    def expire(self, ttl: int = NODE_TTL_SECONDS) -> None:
        cutoff = time.time() - ttl
        with self.lock:
            stale = [
                name
                for name, node in self.nodes.items()
                if not node.get("static") and node.get("last_seen", 0) < cutoff
            ]
            if not stale:
                return
            for name in stale:
                del self.nodes[name]
            self._save()
            self._sync()

    def snapshot(self) -> list[dict]:
        with self.lock:
            return [dict(node) for node in self.nodes.values()]


class Accounts:
    """Accounts are the tenancy boundary; Keycloak subjects map into them.

    On disk (v2):

        {"accounts": {"111111111111": {
             "account_id": "111111111111", "alias": "mathewmusango",
             "root": "mathewmusango", "created_at": "...",
             "users": {"mathewmusango": {"username": ..., "subject": ..., "role": "root"}}}},
         "subjects": {"<oidc sub>": "111111111111"}}

    A principal holds its IAM keys in `access_keys` (name, id, secret, created).
    The flat `access_key_id` / `secret_access_key` / `credentials_issued` fields
    mirror the first key: the classic pages and the provision response still read
    them, so they stay as a pointer, never a second copy.

    v1 was `{"accounts": {username: account_id}}` — one account per federation.
    It is migrated on load: the username becomes the account alias and its
    unbound root user, so the first Keycloak sign-in claims it.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.accounts: dict[str, dict] = {}
        self.subjects: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        accounts = raw.get("accounts") or {}
        if all(isinstance(value, dict) for value in accounts.values()):
            self.accounts = accounts
            self.subjects = dict(raw.get("subjects") or {})
            changed = False
            for account in self.accounts.values():
                if "global_admin" not in account:
                    account["global_admin"] = False
                    changed = True
                if "disabled" not in account:
                    account["disabled"] = False
                    changed = True
                if "default_admin" not in account:
                    account["default_admin"] = False
                    changed = True
                # Regions are opt-in. Accounts created before that rule carry
                # the whole list; treat it as "untouched" and keep just the
                # home region, so the picker starts from one like AWS.
                regions = account.get("regions")
                if regions is not None and set(regions) == set(REGION_CHOICES):
                    account["regions"] = [DEFAULT_REGION]
                    changed = True
            # One key per principal used to live in the flat fields; fold it
            # into the list so the console has a single shape to render.
            for account in self.accounts.values():
                for user in account.get("users", {}).values():
                    if "access_keys" in user:
                        continue
                    user["access_keys"] = []
                    if user.get("access_key_id"):
                        user["access_keys"].append(
                            {
                                "name": "primary",
                                "access_key_id": user["access_key_id"],
                                "secret_access_key": user.get("secret_access_key", ""),
                                "created_at": user.get("credentials_issued") or now(),
                            }
                        )
                    changed = True
            if self.accounts and not any(
                account.get("global_admin") for account in self.accounts.values()
            ):
                oldest = min(
                    self.accounts.values(),
                    key=lambda account: account.get("created_at", ""),
                )
                oldest["global_admin"] = True
                changed = True
            if self.accounts and not any(
                account.get("default_admin") for account in self.accounts.values()
            ):
                oldest_admin = min(
                    (
                        account
                        for account in self.accounts.values()
                        if account.get("global_admin")
                    ),
                    key=lambda account: account.get("created_at", ""),
                    default=None,
                )
                if oldest_admin is not None:
                    oldest_admin["default_admin"] = True
                    changed = True
            if changed:
                self._save()
            return
        # v1 migration: {username: account_id}
        for username, account_id in accounts.items():
            account = self._blank(account_id, username)
            account["users"][username] = {
                "username": username,
                "subject": None,
                "role": "root",
            }
            self.accounts[account_id] = account
        self._save()

    @staticmethod
    def _blank(account_id: str, alias: str) -> dict:
        return {
            "account_id": account_id,
            "alias": alias,
            "root": alias,
            "created_at": now(),
            # Regions are opt-in per account, like AWS. us-east-1 is always on.
            "regions": [DEFAULT_REGION],
            "global_admin": False,
            "default_admin": False,
            "disabled": False,
            "users": {},
        }

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(
                {"accounts": self.accounts, "subjects": self.subjects},
                handle,
                indent=2,
            )
        os.replace(tmp, self.path)

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
        return slug[:32] or "account"

    def unique_alias(self, wanted: str) -> str:
        base = self._slug(wanted)
        alias, n = base, 1
        while any(a["alias"] == alias for a in self.accounts.values()):
            n += 1
            alias = f"{base}-{n}"
        return alias

    def by_ref(self, ref: str) -> dict | None:
        """Account by ID or alias (case-insensitive on the alias)."""
        ref = (ref or "").strip()
        if not ref:
            return None
        if ref in self.accounts:
            return self.accounts[ref]
        for account in self.accounts.values():
            if account["alias"].lower() == ref.lower():
                return account
        return None

    def _new_id(self) -> str:
        while True:
            candidate = "1" + "".join(
                secrets.choice("0123456789") for _ in range(11)
            )
            if candidate not in self.accounts:
                return candidate

    def create(self, subject: str, username: str) -> tuple[dict, dict]:
        account_id = self._new_id()
        account = self._blank(account_id, self.unique_alias(username))
        # The first account owns the platform; it can promote the next ones.
        account["global_admin"] = not self.accounts
        account["default_admin"] = account["global_admin"]
        user = {"username": username, "subject": subject, "role": "root"}
        account["users"][username] = user
        self.accounts[account_id] = account
        if subject:
            self.subjects[subject] = account_id
        self._save()
        return account, user

    def set_name(self, account_id: str, name: str) -> dict | None:
        """Record the human-readable account name shown in the console."""
        account = self.accounts.get(account_id)
        if account is None:
            return None
        account["name"] = name
        self._save()
        return account

    def _principal(self, account: dict, subject: str) -> dict | None:
        for user in account["users"].values():
            if subject and user.get("subject") == subject:
                return user
        return None

    def resolve(
        self,
        subject: str,
        username: str,
        account_ref: str | None = None,
        create: bool = False,
    ) -> tuple[dict | None, dict | str]:
        """Map an OIDC identity to `(account, principal)` or `(None, error)`."""
        with self.lock:
            if account_ref:
                account = self.by_ref(account_ref)
                if account is None:
                    return None, "unknown account ID or alias"
                user = self._principal(account, subject)
                if user is None:
                    return None, "not a member of that account"
                return account, user

            account_id = self.subjects.get(subject or "")
            if account_id and account_id in self.accounts:
                account = self.accounts[account_id]
                user = self._principal(account, subject)
                if user is not None:
                    return account, user

            # Migration path: a principal created before subjects were keys.
            for candidate in self.accounts.values():
                user = candidate["users"].get(username)
                if user is not None and not user.get("subject"):
                    user["subject"] = subject
                    self.subjects[subject] = candidate["account_id"]
                    self._save()
                    return candidate, user

            if create:
                return self.create(subject, username)
            return None, "no account for this identity; create one"

    def ensure_local(self, username: str) -> tuple[dict, dict]:
        """The `.env` admin signs in as the root of its own account."""
        with self.lock:
            for account in self.accounts.values():
                user = account["users"].get(username)
                if user is not None:
                    return account, user
            account = self._blank(self._new_id(), self.unique_alias(username))
            account["global_admin"] = not self.accounts
            user = {"username": username, "subject": None, "role": "root"}
            account["users"][username] = user
            self.accounts[account["account_id"]] = account
            self._save()
            return account, user

    @staticmethod
    def _mirror_primary(user: dict) -> None:
        """Point the legacy flat fields at the principal's first key."""
        keys = user.get("access_keys") or []
        primary = keys[0] if keys else {}
        user["access_key_id"] = primary.get("access_key_id")
        user["secret_access_key"] = primary.get("secret_access_key")
        user["credentials_issued"] = primary.get("created_at")

    def key_count(self, account: dict) -> int:
        """Every IAM key the account holds, across its principals."""
        return sum(
            len(user.get("access_keys") or [])
            for user in (account.get("users") or {}).values()
        )

    def add_access_key(
        self, account_id: str, username: str, name: str, key_id: str, secret: str
    ) -> tuple[dict | None, str]:
        """Store one issued key. Returns `(entry, error)`; the cap is enforced here."""
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None:
                return None, "unknown account"
            user = account["users"].get(username)
            if user is None:
                return None, "unknown principal"
            if self.key_count(account) >= MAX_ACCESS_KEYS:
                return (
                    None,
                    f"an account may hold at most {MAX_ACCESS_KEYS} access keys",
                )
            taken = {
                key["name"].lower()
                for holder in account["users"].values()
                for key in holder.get("access_keys") or []
            }
            if name.lower() in taken:
                return None, "that key name is already in use"
            entry = {
                "name": name,
                "access_key_id": key_id,
                "secret_access_key": secret,
                "created_at": now(),
            }
            user.setdefault("access_keys", []).append(entry)
            user["iam_user"] = username
            self._mirror_primary(user)
            self._save()
            return entry, ""

    def remove_access_key(
        self, account_id: str, username: str, key_id: str
    ) -> tuple[dict | None, str]:
        """Drop one key from the store. Returns `(entry, error)`."""
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None:
                return None, "unknown account"
            user = account["users"].get(username)
            if user is None:
                return None, "unknown principal"
            keys = user.get("access_keys") or []
            entry = next(
                (key for key in keys if key["access_key_id"] == key_id), None
            )
            if entry is None:
                return None, "no such access key"
            keys.remove(entry)
            user["access_keys"] = keys
            self._mirror_primary(user)
            self._save()
            return entry, ""

    def regions_of(self, account: dict) -> list[str]:
        """Enabled regions for one account; us-east-1 can never be removed."""
        return sorted({DEFAULT_REGION, *(account.get("regions") or [])})

    def set_regions(self, account_id: str, regions: list[str]) -> dict | None:
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None:
                return None
            account["regions"] = sorted({DEFAULT_REGION, *regions})
            self._save()
            return account

    def set_global_admin(self, account_id: str, enabled: bool) -> dict | None:
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None:
                return None
            account["global_admin"] = bool(enabled)
            self._save()
            return account

    def set_disabled(self, account_id: str, disabled: bool) -> tuple[dict | None, str]:
        """Disable/enable an account, never the last enabled global admin."""
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None:
                return None, "unknown account"
            if disabled:
                admins = [
                    item
                    for item in self.accounts.values()
                    if item.get("global_admin") and not item.get("disabled")
                ]
                if account.get("global_admin") and len(admins) <= 1:
                    return None, "cannot disable the last enabled global admin"
            account["disabled"] = bool(disabled)
            self._save()
            return account, ""

    def delete(self, account_id: str) -> dict | None:
        with self.lock:
            account = self.accounts.pop(account_id, None)
            if account is None:
                return None
            self.subjects = {
                subject: bound
                for subject, bound in self.subjects.items()
                if bound != account_id
            }
            self._save()
            return account


class UserStore:
    """Local credentials in SQLite: username -> password hash -> account.

    Tenancy lives in `accounts.json`; this store answers only "is this password
    right, and which account does the username belong to". SQLite is enough for
    one control replica — swapping `_connect` for Postgres is the nod when more
    than one runs.
    """

    ROUNDS = 260_000

    def __init__(self, path: str) -> None:
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.lock = threading.Lock()
        self._run(
            """CREATE TABLE IF NOT EXISTS users (
                   username TEXT PRIMARY KEY COLLATE NOCASE,
                   email TEXT,
                   password_hash TEXT NOT NULL,
                   account_id TEXT NOT NULL,
                   role TEXT NOT NULL DEFAULT 'root',
                   created_at TEXT NOT NULL,
                   last_login TEXT)"""
        )
        # One row per outstanding reset link: only the hash of the token is kept.
        self._run(
            """CREATE TABLE IF NOT EXISTS password_resets (
                   token_hash TEXT PRIMARY KEY,
                   username TEXT NOT NULL COLLATE NOCASE,
                   account_id TEXT NOT NULL DEFAULT '',
                   expires_at INTEGER NOT NULL,
                   used_at TEXT)"""
        )
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: tuple = (), fetch: str = "") -> object:
        conn = self._connect()
        try:
            cursor = conn.execute(sql, params)
            if fetch == "one":
                row = cursor.fetchone()
                conn.commit()
                return dict(row) if row is not None else None
            if fetch == "all":
                rows = [dict(row) for row in cursor.fetchall()]
                conn.commit()
                return rows
            conn.commit()
            return None
        finally:
            conn.close()

    def _hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, self.ROUNDS
        )
        return "pbkdf2_sha256${}${}${}".format(
            self.ROUNDS,
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        )

    @staticmethod
    def _matches(password: str, stored: str) -> bool:
        try:
            algo, rounds, salt, digest = stored.split("$")
            if algo != "pbkdf2_sha256":
                return False
            computed = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                base64.b64decode(salt),
                int(rounds),
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(computed, base64.b64decode(digest))

    def count(self) -> int:
        row = self._run("SELECT COUNT(*) AS n FROM users", fetch="one")
        return int(row["n"]) if row else 0

    def get(self, username: str) -> dict | None:
        return self._run(
            "SELECT * FROM users WHERE username = ?", (username,), fetch="one"
        )

    def exists(self, username: str) -> bool:
        return self.get(username) is not None

    def create(
        self,
        username: str,
        email: str,
        password: str,
        account_id: str,
        role: str = "root",
    ) -> None:
        with self.lock:
            self._run(
                "INSERT INTO users (username, email, password_hash, account_id, "
                "role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (username, email, self._hash(password), account_id, role, now()),
            )

    def verify(self, username: str, password: str) -> dict | None:
        user = self.get(username)
        if user is None or not self._matches(password, user["password_hash"]):
            return None
        with self.lock:
            self._run(
                "UPDATE users SET last_login = ? WHERE username = ?",
                (now(), username),
            )
        return user

    def all(self) -> list[dict]:
        return self._run(
            "SELECT username, email, account_id, role, created_at, last_login "
            "FROM users ORDER BY username",
            fetch="all",
        )

    def delete_account(self, account_id: str) -> None:
        with self.lock:
            self._run("DELETE FROM users WHERE account_id = ?", (account_id,))
            self._run("DELETE FROM password_resets WHERE account_id = ?", (account_id,))

    def by_email(self, email: str) -> dict | None:
        if not email:
            return None
        return self._run(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,), fetch="one"
        )

    def set_password(self, username: str, password: str) -> None:
        with self.lock:
            self._run(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (self._hash(password), username),
            )

    def set_email(self, username: str, email: str) -> None:
        """Fill in a missing address; never overwrite one the user already has."""
        if not email:
            return
        with self.lock:
            self._run(
                "UPDATE users SET email = ? WHERE username = ? "
                "AND (email IS NULL OR email = '')",
                (email, username),
            )

    def create_reset(self, username: str, token_hash: str, expires_at: int) -> None:
        user = self.get(username) or {}
        with self.lock:
            # One live link per user: asking again retires the previous one.
            self._run("DELETE FROM password_resets WHERE username = ?", (username,))
            self._run(
                "INSERT INTO password_resets (token_hash, username, account_id, "
                "expires_at) VALUES (?, ?, ?, ?)",
                (token_hash, username, user.get("account_id", ""), expires_at),
            )

    def peek_reset(self, token_hash: str) -> dict | None:
        """An unused, unexpired reset row, without redeeming it."""
        row = self._run(
            "SELECT * FROM password_resets WHERE token_hash = ?",
            (token_hash,),
            fetch="one",
        )
        if row is None or row.get("used_at"):
            return None
        if int(row.get("expires_at") or 0) < int(time.time()):
            return None
        return row

    def consume_reset(self, token_hash: str) -> dict | None:
        """Redeem a token once; returns its row or None when stale/unknown."""
        with self.lock:
            row = self._run(
                "SELECT * FROM password_resets WHERE token_hash = ?",
                (token_hash,),
                fetch="one",
            )
            if row is None or row.get("used_at"):
                return None
            if int(row.get("expires_at") or 0) < int(time.time()):
                return None
            self._run(
                "UPDATE password_resets SET used_at = ? WHERE token_hash = ?",
                (now(), token_hash),
            )
            return row


class Settings:
    """Small persisted control-plane settings (sign-up toggle, ...)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.values: dict = {}
        try:
            with open(path, encoding="utf-8") as handle:
                self.values = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.values = {}

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set(self, key: str, value) -> None:
        with self.lock:
            self.values[key] = value
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(self.values, handle, indent=2)
                os.replace(tmp, self.path)
            except OSError as exc:
                print(f"control: could not persist settings: {exc}", flush=True)


class Owners:
    """Best-effort provenance: which principal created a named resource.

    The emulator keeps no owner metadata, so this is a control-plane ledger keyed
    by `account/service/name` (names are unique per service inside an account; S3
    is account-scoped upstream anyway). A resource created with the CLI simply has
    no entry — the console shows the account and leaves the user blank.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.entries: dict = {}
        try:
            with open(path, encoding="utf-8") as handle:
                self.entries = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.entries = {}

    @staticmethod
    def _key(account: str, service: str, name: str) -> str:
        return f"{account}/{service}/{name}"

    def record(
        self, account: str, region: str, service: str, name: str, user: str
    ) -> None:
        name = (name or "").strip()
        if not name:
            return
        with self.lock:
            self.entries[self._key(account, service, name)] = {
                "user": user or "token",
                "region": region,
                "at": now(),
            }
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(self.entries, handle, indent=2, sort_keys=True)
                os.replace(tmp, self.path)
            except OSError as exc:
                print(f"control: could not persist ownership: {exc}", flush=True)

    def get(self, account: str, service: str, name: str) -> dict:
        return self.entries.get(self._key(account, service, name)) or {}

    def forget(self, account: str) -> None:
        with self.lock:
            prefix = f"{account}/"
            kept = {k: v for k, v in self.entries.items() if not k.startswith(prefix)}
            if kept != self.entries:
                self.entries = kept
                try:
                    tmp = f"{self.path}.tmp"
                    with open(tmp, "w", encoding="utf-8") as handle:
                        json.dump(self.entries, handle, indent=2, sort_keys=True)
                    os.replace(tmp, self.path)
                except OSError:
                    pass


class AuditLog:
    """Append-only JSONL audit trail for identity and tenancy changes."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()

    def record(self, actor: str, action: str, target: str = "", detail: dict | None = None) -> None:
        entry = {
            "at": now(),
            "actor": actor or "system",
            "action": action,
            "target": target,
            "detail": detail or {},
        }
        with self.lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry) + "\n")
            except OSError as exc:
                print(f"control: could not write audit log: {exc}", flush=True)

    def recent(self, limit: int = 100) -> list[dict]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()[-limit:]
        except OSError:
            return []
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(entries))


class Telemetry:
    """OTLP/HTTP JSON spans. A no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set."""

    def __init__(self) -> None:
        self.enabled = bool(OTEL_ENDPOINT)
        self.queue: queue.Queue = queue.Queue(maxsize=512)
        if self.enabled:
            threading.Thread(target=self._run, daemon=True).start()

    def start(self, method: str, path: str, headers) -> dict | None:
        if not self.enabled:
            return None
        trace = (headers.get("traceparent") or "").split("-")
        trace_id = trace[1] if len(trace) >= 3 and len(trace[1]) == 32 else secrets.token_hex(16)
        parent_id = trace[2] if len(trace) >= 3 and len(trace[2]) == 16 else ""
        span = {
            "traceId": trace_id,
            "spanId": secrets.token_hex(8),
            "name": f"{method} {path.split('?')[0]}",
            "kind": 2,
            "startTimeUnixNano": str(time.time_ns()),
            "attributes": [
                {"key": "http.request.method", "value": {"stringValue": method}},
                {"key": "url.path", "value": {"stringValue": path.split('?')[0]}},
            ],
        }
        if parent_id:
            span["parentSpanId"] = parent_id
        return span

    def finish(self, span: dict | None, status: int) -> None:
        if span is None:
            return
        span["endTimeUnixNano"] = str(time.time_ns())
        span["attributes"].append(
            {"key": "http.response.status_code", "value": {"intValue": int(status or 0)}}
        )
        span["status"] = {"code": 2 if int(status or 0) >= 500 else 1}
        try:
            self.queue.put_nowait(span)
        except queue.Full:
            pass

    def _run(self) -> None:
        while True:
            batch = []
            try:
                batch.append(self.queue.get(timeout=2))
                while len(batch) < 64:
                    batch.append(self.queue.get_nowait())
            except queue.Empty:
                pass
            if not batch:
                continue
            payload = {
                "resourceSpans": [
                    {
                        "resource": {
                            "attributes": [
                                {"key": "service.name", "value": {"stringValue": OTEL_SERVICE}}
                            ]
                        },
                        "scopeSpans": [{"spans": batch}],
                    }
                ]
            }
            try:
                request = urllib.request.Request(
                    f"{OTEL_ENDPOINT}/v1/traces",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(request, timeout=3).read()
            except OSError:
                pass


NODE_REGISTRY = NodeRegistry(NODES_FILE)
NODE_REGISTRY.ensure_static(NODE_NAME, NODE_URL, DEFAULT_REGION)
ACCOUNTS = Accounts(ACCOUNTS_FILE)
USERS = UserStore(USERS_DB)
SETTINGS = Settings(SETTINGS_FILE)
AUDIT = AuditLog(AUDIT_FILE)
OWNERS = Owners(OWNERS_FILE)
TELEMETRY = Telemetry()


def seed_local_admin() -> None:
    """Seed the optional `.env` administrator into an empty user store.

    On a fresh deployment this is the known first login; it is marked global and
    default admin so the console can prompt to retire it once other admins exist.
    The address matters: `/forgot` can only mail a user that has one, so an
    existing seeded admin gets `MC_ADMIN_EMAIL` backfilled when it had none.
    """
    if not ADMIN_USER or not ADMIN_PASSWORD:
        return
    if USERS.count():
        if ADMIN_EMAIL:
            USERS.set_email(ADMIN_USER, ADMIN_EMAIL)
        return
    account, _principal = ACCOUNTS.ensure_local(ADMIN_USER)
    account["global_admin"] = True
    account["default_admin"] = True
    ACCOUNTS._save()
    USERS.create(
        ADMIN_USER, ADMIN_EMAIL, ADMIN_PASSWORD, account["account_id"], "root"
    )
    AUDIT.record(
        "system",
        "account.seeded",
        account["account_id"],
        {"alias": account["alias"], "via": "env", "global_admin": True},
    )
    print("control: seeded the .env administrator into users.db", flush=True)


seed_local_admin()


# --------------------------------------------------------------------------
# IAM provisioning
#
# A 12-digit access key is an account **root**: MiniStack skips secret
# verification for root keys, so the control can drive IAM for any account by
# presenting its ID. The issued IAM user key is a real, verified credential.


def iam_request(account_id: str, action: str, **params) -> tuple[bool, str]:
    node = primary_node()
    if node is None:
        return False, "emulator is not registered"
    form = urlencode({"Action": action, "Version": "2010-05-08", **params}).encode()
    url = urlsplit(node["endpoint"])
    host = f"{url.hostname}:{url.port or 80}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    headers = {
        "Host": host,
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(form)),
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={account_id}/{stamp}/{DEFAULT_REGION}"
            "/iam/aws4_request, SignedHeaders=host, Signature=local"
        ),
    }
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=10)
    try:
        conn.request("POST", "/", body=form, headers=headers)
        response = conn.getresponse()
        return response.status == 200, response.read().decode(errors="replace")
    except OSError as exc:
        return False, str(exc)
    finally:
        conn.close()


def issue_credentials(account: dict, principal: dict) -> str:
    """Create the IAM user + first access key once. Returns an error string or ""."""
    if principal.get("access_keys"):
        return ""
    account_id = account["account_id"]
    username = principal["username"]
    ok, body = iam_request(account_id, "CreateUser", UserName=username)
    if not ok and "EntityAlreadyExists" not in body:
        return f"CreateUser failed: {body[:120]}"
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": "*", "Resource": "*"}
            ],
        }
    )
    ok, body = iam_request(
        account_id,
        "PutUserPolicy",
        UserName=username,
        PolicyName="ministack-admin",
        PolicyDocument=policy,
    )
    if not ok:
        return f"PutUserPolicy failed: {body[:120]}"
    return create_access_key(account, principal, "primary")


def create_access_key(
    account: dict, principal: dict, name: str
) -> tuple[dict | None, str]:
    """Issue one more IAM key and record it. Returns `(key, error)`.

    The cap is checked against the store first so a refused request never leaves
    an orphan key at the emulator; if the store rejects it afterwards (a racing
    delete), the key we just made is removed again.
    """
    account_id = account["account_id"]
    username = principal["username"]
    if ACCOUNTS.key_count(account) >= MAX_ACCESS_KEYS:
        return None, f"an account may hold at most {MAX_ACCESS_KEYS} access keys"
    ok, body = iam_request(account_id, "CreateAccessKey", UserName=username)
    if not ok:
        return None, f"CreateAccessKey failed: {body[:120]}"
    key = re.search(r"<AccessKeyId>([^<]+)</AccessKeyId>", body)
    secret = re.search(r"<SecretAccessKey>([^<]+)</SecretAccessKey>", body)
    if not key or not secret:
        return None, "CreateAccessKey returned no credentials"
    entry, problem = ACCOUNTS.add_access_key(
        account_id, username, name, key.group(1), secret.group(1)
    )
    if problem:
        iam_request(
            account_id,
            "DeleteAccessKey",
            UserName=username,
            AccessKeyId=key.group(1),
        )
        return None, problem
    return entry, ""


def delete_access_key(
    account: dict, principal: dict, key_id: str
) -> str:
    """Delete one IAM key and forget it. Returns an error string or ""."""
    account_id = account["account_id"]
    username = principal["username"]
    entry = next(
        (
            key
            for key in principal.get("access_keys") or []
            if key["access_key_id"] == key_id
        ),
        None,
    )
    if entry is None:
        return "no such access key"
    ok, body = iam_request(
        account_id, "DeleteAccessKey", UserName=username, AccessKeyId=key_id
    )
    if not ok and "NoSuchEntity" not in body:
        return f"DeleteAccessKey failed: {body[:120]}"
    _, problem = ACCOUNTS.remove_access_key(account_id, username, key_id)
    return problem


def rotate_credentials(account_id: str, username: str) -> tuple[dict | None, str]:
    """Replace every key with one fresh `primary`. Returns `(key, error)`."""
    account = ACCOUNTS.accounts.get(account_id) or {}
    principal = (account.get("users") or {}).get(username) or {}
    if not principal:
        return None, "unknown principal"
    for key in list(principal.get("access_keys") or []):
        problem = delete_access_key(account, principal, key["access_key_id"])
        if problem:
            return None, problem
    return create_access_key(account, principal, "primary")


def public_keys(principal: dict) -> list[dict]:
    """The console's view of a principal's keys: no secret, ever."""
    return [
        {
            "name": key.get("name", ""),
            "access_key_id": key.get("access_key_id", ""),
            "masked": mask(key.get("access_key_id", "")),
            "masked_secret": "•" * 12,
            "created_at": key.get("created_at", ""),
        }
        for key in principal.get("access_keys") or []
    ]


def delete_account(account: dict) -> None:
    """Remove an account, its IAM principals and its bucket-name claims."""
    account_id = account["account_id"]
    for principal in list(account.get("users", {}).values()):
        name = principal.get("iam_user") or principal.get("username")
        _, body = iam_request(account_id, "ListAccessKeys", UserName=name)
        for key in re.findall(r"<AccessKeyId>([^<]+)</AccessKeyId>", body):
            iam_request(
                account_id, "DeleteAccessKey", UserName=name, AccessKeyId=key
            )
        _, body = iam_request(account_id, "ListUserPolicies", UserName=name)
        for policy in xml_members(body, "PolicyNames") or re.findall(
            r"<PolicyName>([^<]+)</PolicyName>", body
        ):
            iam_request(
                account_id, "DeleteUserPolicy", UserName=name, PolicyName=policy
            )
        iam_request(account_id, "DeleteUser", UserName=name)
    USERS.delete_account(account_id)
    ACCOUNTS.delete(account_id)
    OWNERS.forget(account_id)
    with REGISTRY.lock:
        for bucket in [
            name
            for name, entry in REGISTRY.buckets.items()
            if entry.get("account") == account_id
        ]:
            REGISTRY.buckets.pop(bucket, None)
        REGISTRY.save()


OIDC_CACHE: dict[str, dict] = {}
OIDC_LOCK = threading.Lock()


def oidc_available() -> bool:
    """OIDC is optional: env toggle, a configured client and a matching mode."""
    return OIDC_ENABLED and AUTH_MODE in {"oidc", "both"} and bool(OIDC_CLIENT_ID)


def oidc_is_provider() -> bool:
    return OIDC_STYLE in {"openbao", "provider"}


def oidc_roles(profile: dict) -> set[str]:
    """Realm and client roles from a Keycloak-style profile.

    Grafana reads its roles the same way: the client roles live under
    `resource_access.<client>.roles`, so this works without a custom mapper.
    """
    roles: set[str] = set()
    realm = profile.get("realm_access") or {}
    roles.update(str(name) for name in realm.get("roles") or [])
    for client in (profile.get("resource_access") or {}).values():
        roles.update(str(name) for name in (client or {}).get("roles") or [])
    return roles


def oidc_discovery_url() -> str:
    if OIDC_DISCOVERY_URL:
        return OIDC_DISCOVERY_URL
    if oidc_is_provider():
        return (
            f"{OIDC_INTERNAL_URL}/v1/identity/oidc/provider/{OIDC_PROVIDER}"
            "/.well-known/openid-configuration"
        )
    return (
        f"{OIDC_INTERNAL_URL}/realms/{OIDC_REALM}"
        "/.well-known/openid-configuration"
    )


def oidc_internal(url: str) -> str:
    """Point a public endpoint at the address the control container can reach."""
    if OIDC_PUBLIC_URL and url.startswith(OIDC_PUBLIC_URL):
        return OIDC_INTERNAL_URL + url[len(OIDC_PUBLIC_URL):]
    return url


def oidc_public(url: str) -> str:
    """The browser must use the public address, never a container name."""
    if OIDC_INTERNAL_URL and url.startswith(OIDC_INTERNAL_URL):
        return OIDC_PUBLIC_URL + url[len(OIDC_INTERNAL_URL):]
    return url


def oidc_discovery() -> dict:
    with OIDC_LOCK:
        if OIDC_CACHE.get("config"):
            return OIDC_CACHE["config"]
    with urllib.request.urlopen(oidc_discovery_url(), timeout=5) as response:
        config = json.loads(response.read())
    with OIDC_LOCK:
        OIDC_CACHE["config"] = config
    return config


def oidc_endpoint(kind: str) -> str:
    """Token/userinfo (and other) endpoints on the internal network."""
    keys = {
        "auth": "authorization_endpoint",
        "token": "token_endpoint",
        "userinfo": "userinfo_endpoint",
        "jwks": "jwks_uri",
    }
    url = ""
    try:
        url = oidc_discovery().get(keys.get(kind, f"{kind}_endpoint"), "")
    except (OSError, ValueError):
        url = ""
    if not url:
        if oidc_is_provider():
            url = f"{OIDC_PUBLIC_URL}/v1/identity/oidc/provider/{OIDC_PROVIDER}/{kind}"
        else:
            url = f"{OIDC_PUBLIC_URL}/realms/{OIDC_REALM}/protocol/openid-connect/{kind}"
    return oidc_internal(url)


def oidc_authorization_url(query: str) -> str:
    """The authorize endpoint the browser is sent to."""
    if OIDC_AUTHORIZE_URL:
        return f"{OIDC_AUTHORIZE_URL}?{query}"
    base = ""
    try:
        base = oidc_discovery().get("authorization_endpoint", "")
    except (OSError, ValueError):
        base = ""
    if base:
        base = oidc_public(base)
    elif oidc_is_provider():
        # OpenBao serves the authorize endpoint through its UI so an
        # unauthenticated browser is asked to sign in first.
        base = (
            f"{OIDC_PUBLIC_URL}/ui/vault/identity/oidc/provider/{OIDC_PROVIDER}/authorize"
        )
    else:
        base = f"{OIDC_PUBLIC_URL}/realms/{OIDC_REALM}/protocol/openid-connect/auth"
    return f"{base}?{query}"


def primary_node() -> dict | None:
    for node in NODES:
        if node["region"] == DEFAULT_REGION:
            return node
    return NODES[0] if NODES else None


def node_by_region(region: str) -> dict | None:
    for node in NODES:
        if node["region"] == region:
            return node
    return primary_node()


def node_by_name(name: str) -> dict | None:
    for node in NODES:
        if node["name"] == name:
            return node
    return None


# --------------------------------------------------------------------------
# persistent registry + node cache


class Registry:
    """Bucket ownership plus the last known inventory of every node."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.buckets: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.buckets = data.get("buckets", {})
            self.nodes = data.get("nodes", {})
        except (OSError, json.JSONDecodeError):
            self.buckets = {}
            self.nodes = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(
                {"buckets": self.buckets, "nodes": self.nodes},
                handle,
                indent=2,
                sort_keys=True,
            )
        os.replace(tmp, self.path)

    def reserve(
        self, bucket: str, region: str, node: dict, account: str = ""
    ) -> dict | None:
        with self.lock:
            if bucket in self.buckets:
                return None
            self.buckets[bucket] = {
                "region": region,
                "node": node["name"],
                "account_id": account or node.get("account_id", ""),
                "last_seen": now(),
                "stale": False,
            }
            self.save()
            return self.buckets[bucket]

    def adopt(self, bucket: str, node: dict, account: str = "") -> dict:
        with self.lock:
            self.buckets[bucket] = {
                "region": node["region"],
                "node": node["name"],
                "account_id": account or node.get("account_id", ""),
                "last_seen": now(),
                "stale": False,
            }
            self.save()
            return self.buckets[bucket]

    def release(self, bucket: str) -> None:
        with self.lock:
            if self.buckets.pop(bucket, None) is not None:
                self.save()

    def owner(self, bucket: str) -> dict | None:
        with self.lock:
            return self.buckets.get(bucket)

    def snapshot(self) -> dict[str, dict]:
        with self.lock:
            return dict(self.buckets)

    def node_snapshot(self) -> dict[str, dict]:
        with self.lock:
            return dict(self.nodes)

    def reconcile(
        self, node: dict, names: list[str], reachable: bool, account: str = ""
    ) -> list[str]:
        """Merge one account's inventory. Unreachable keeps the last known set.

        The listing is per account, so pruning is too: entries belonging to
        other accounts must survive a reconcile of the root account.
        """
        conflicts: list[str] = []
        checked = now()
        owner = account or node.get("account_id", "")
        with self.lock:
            if reachable:
                for bucket in [
                    name
                    for name, entry in self.buckets.items()
                    if entry["node"] == node["name"]
                    and entry.get("account_id") == owner
                    and name not in names
                ]:
                    del self.buckets[bucket]
                for name in names:
                    entry = self.buckets.get(name)
                    if entry is None:
                        self.buckets[name] = {
                            "region": node["region"],
                            "node": node["name"],
                            "account_id": owner,
                            "last_seen": checked,
                            "stale": False,
                        }
                    elif entry.get("account_id") == owner:
                        entry["last_seen"] = checked
                        entry["stale"] = False
                    else:
                        conflicts.append(name)
                self.nodes[node["name"]] = {
                    "reachable": True,
                    "last_seen": checked,
                    "buckets": sorted(names),
                }
            else:
                previous = self.nodes.get(node["name"], {})
                for entry in self.buckets.values():
                    if entry["node"] == node["name"]:
                        entry["stale"] = True
                self.nodes[node["name"]] = {
                    "reachable": False,
                    "last_seen": previous.get("last_seen", ""),
                    "buckets": previous.get("buckets", []),
                }
            self.save()
        return conflicts


REGISTRY = Registry(REGISTRY_FILE)

# node health + service availability, refreshed by the poller
HEALTH: dict[str, dict] = {}
HEALTH_LOCK = threading.Lock()

# control-plane sessions (in memory: a restart signs everyone out)
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()
SESSIONS_FILE = os.environ.get(
    "CONTROL_SESSIONS_FILE", "/var/lib/ministack/control/sessions.json"
)


def save_sessions() -> None:
    """Persist live sessions so a container restart does not sign everyone out."""
    try:
        directory = os.path.dirname(SESSIONS_FILE)
        os.makedirs(directory, exist_ok=True)
        tmp = f"{SESSIONS_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(SESSIONS, handle)
        os.chmod(tmp, 0o600)
        os.replace(tmp, SESSIONS_FILE)
    except OSError as exc:
        print(f"control: could not persist sessions: {exc}", flush=True)


def load_sessions() -> None:
    try:
        with open(SESSIONS_FILE, encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return
    current = time.time()
    with SESSIONS_LOCK:
        for token, info in stored.items():
            if isinstance(info, dict) and info.get("expires", 0) > current:
                SESSIONS[token] = info


load_sessions()


def new_session(
    username: str, account: str, role: str = "root", alias: str = "", via: str = "local"
) -> str:
    token = secrets.token_urlsafe(32)
    with SESSIONS_LOCK:
        SESSIONS[token] = {
            "expires": time.time() + SESSION_SECONDS,
            "user": username,
            "account": account,
            "role": role,
            "alias": alias,
            "via": via,
        }
        save_sessions()
    AUDIT.record(username, "session.started", account)
    return token


def session_info(token: str) -> dict | None:
    with SESSIONS_LOCK:
        info = SESSIONS.get(token)
        if info is None:
            return None
        if info["expires"] < time.time():
            SESSIONS.pop(token, None)
            save_sessions()
            return None
        account = ACCOUNTS.by_ref(info.get("account", ""))
        if account and account.get("disabled"):
            SESSIONS.pop(token, None)
            save_sessions()
            return None
        # Sliding expiry: an active session does not time out.
        extended = time.time() + SESSION_SECONDS
        if extended - info["expires"] > 60:
            info["expires"] = extended
            save_sessions()
        return info


def login_label(info: dict | None) -> str:
    """How this caller signed in: `local`, or `oidc(<provider>)`."""
    via = (info or {}).get("via")
    if via == "oidc" or (via is None and AUTH_MODE == "oidc"):
        return f"oidc({OIDC_PROVIDER_LABEL})" if OIDC_PROVIDER_LABEL else "oidc"
    if via == "local":
        return "local"
    if AUTH_MODE == "both":
        return "local | oidc"
    return "local"


def session_ok(token: str) -> bool:
    return session_info(token) is not None


def purge_sessions(account_id: str) -> None:
    """Drop every session bound to an account (used when it is disabled)."""
    with SESSIONS_LOCK:
        for token in [
            token
            for token, info in SESSIONS.items()
            if info.get("account") == account_id
        ]:
            SESSIONS.pop(token, None)
        save_sessions()


# --------------------------------------------------------------------------
# node calls


def node_request(
    node: dict,
    method: str,
    path: str,
    body: bytes | None = None,
    timeout: float = 15,
    extra_headers: dict | None = None,
) -> tuple[int, bytes]:
    url = urlsplit(node["endpoint"])
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout)
    headers = {"Host": f"{url.hostname}:{url.port or 80}"}
    if node.get("token"):
        headers["Authorization"] = f"Bearer {node['token']}"
    if extra_headers:
        headers.update(extra_headers)
    if body is not None:
        headers["Content-Length"] = str(len(body))
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, response.read()
    except OSError as exc:
        return 0, str(exc).encode()
    finally:
        conn.close()


def read_health(node: dict) -> tuple[dict, dict]:
    """Return (node health, {service: state}) from one live call."""
    status, body = node_request(node, "GET", "/_ministack/health", timeout=4)
    if status != 200:
        return (
            {
                "reachable": False,
                "error": body.decode(errors="replace")[:120] or f"HTTP {status}",
                "checked_at": now(),
                "joined": "no",
            },
            {},
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}
    return (
        {
            "reachable": True,
            "version": payload.get("version", "?"),
            "edition": payload.get("edition", "?"),
            "auth": payload.get("auth", "?"),
            "checked_at": now(),
            "joined": "yes",
        },
        payload.get("services", {}),
    )


def poll_health() -> None:
    nodes: dict[str, dict] = {}
    services: dict[str, dict] = {}
    for node in NODES:
        health, node_services = read_health(node)
        nodes[node["name"]] = health
        for service, state in node_services.items():
            services.setdefault(service, {})[node["name"]] = state
    with HEALTH_LOCK:
        HEALTH.clear()
        HEALTH["nodes"] = nodes
        HEALTH["services"] = services
        HEALTH["checked_at"] = now()


def health_snapshot() -> dict:
    with HEALTH_LOCK:
        return json.loads(json.dumps(HEALTH)) if HEALTH else {
            "nodes": {},
            "services": {},
            "checked_at": "",
        }


def list_bucket_names(node: dict, account: str = "") -> tuple[bool, list[str]]:
    """List one account's buckets. A 12-digit key is that account's root."""
    extra = {}
    if account:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        extra["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={account}/{stamp}/{DEFAULT_REGION}"
            "/s3/aws4_request, SignedHeaders=host, Signature=local"
        )
    status, body = node_request(
        node, "GET", "/?x-id=ListBuckets", timeout=10, extra_headers=extra
    )
    if status != 200:
        return False, []
    return True, re.findall(r"<Bucket>.*?<Name>([^<]+)</Name>", body.decode(), re.S)


def live_bucket_owner(bucket: str) -> dict | None:
    """Ask every reachable node directly, in case the cache drifted."""
    for node in NODES:
        status, _ = node_request(node, "HEAD", f"/{bucket}", timeout=3)
        if status == 200:
            return node
    return None


def refresh_registry() -> dict:
    """Rebuild the name registry from every known account's inventory.

    The listing is per account (each with that account's root key), so a
    reconcile never sees — or prunes — another account's buckets.
    """
    conflicts: list[str] = []
    for account_id in list(ACCOUNTS.accounts):
        for node in NODES:
            reachable, names = list_bucket_names(node, account_id)
            conflicts.extend(
                REGISTRY.reconcile(node, names, reachable, account_id)
            )
    return {
        "buckets": len(REGISTRY.snapshot()),
        "conflicts": conflicts,
        "nodes": REGISTRY.node_snapshot(),
    }


# --------------------------------------------------------------------------
# replication backends


def agent_call(node: dict, method: str, path: str, payload: dict | None = None):
    url = urlsplit(node.get("agent", ""))
    if not url.hostname:
        return 0, b""
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=4)
    body = None
    headers = {"Host": f"{url.hostname}:{url.port or 80}"}
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    if MESH_TOKEN:
        headers["Authorization"] = f"Bearer {MESH_TOKEN}"
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, response.read()
    except OSError:
        return 0, b""
    finally:
        conn.close()


def agent_state() -> dict:
    for node in NODES:
        status, body = agent_call(node, "GET", "/state")
        if status == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                continue
    return {"buckets": {}, "conflicts": [], "heights": {}, "events": 0}


def agent_status() -> list[dict]:
    rows = []
    for node in NODES:
        status, body = agent_call(node, "GET", "/health")
        entry = {"node": node["name"], "reachable": status == 200}
        if status == 200:
            try:
                entry.update(json.loads(body))
            except json.JSONDecodeError:
                pass
        rows.append(entry)
    return rows


def current_buckets() -> dict:
    if MODE == "central":
        return REGISTRY.snapshot()
    return agent_state().get("buckets", {})


def bucket_owner(bucket: str) -> dict | None:
    if MODE == "central":
        return REGISTRY.owner(bucket)
    return agent_state().get("buckets", {}).get(bucket)


def reserve_across(
    bucket: str, region: str, account: str = ""
) -> tuple[bool, str, int]:
    """Reserve a name according to the active mode. Returns (ok, code, status)."""
    if MODE == "central":
        node = node_by_region(region)
        if node is None:
            return False, "no emulator is registered", 503
        if REGISTRY.reserve(bucket, region, node, account) is None:
            return False, "already registered", 409
        return True, "", 0

    if bucket_owner(bucket):
        return False, "already registered in the federation", 409
    live = live_bucket_owner(bucket)
    if live is not None:
        agent_call(
            live, "POST", "/reserve", {"bucket": bucket, "region": live["region"]}
        )
        return False, f"already exists in {live['region']}", 409

    owner = node_by_region(region)
    if owner is None:
        return False, "no nodes have joined the federation", 503
    reachable = {
        node["name"]
        for node in NODES
        if agent_call(node, "GET", "/health")[0] == 200
    }
    if MODE == "quorum":
        needed = len(NODES) // 2 + 1
        if len(reachable) < needed:
            return (
                False,
                f"quorum not met: {len(reachable)}/{needed} agents reachable",
                503,
            )
    if owner["name"] not in reachable:
        return False, f"agent for {owner['name']} is unreachable", 503
    status, _ = agent_call(
        owner, "POST", "/reserve", {"bucket": bucket, "region": region}
    )
    if status in (200, 201):
        return True, "", 0
    if status == 409:
        return False, "already registered in the federation", 409
    return False, f"reservation failed on {owner['name']} (HTTP {status})", 503


def release_across(bucket: str) -> None:
    if MODE == "central":
        REGISTRY.release(bucket)
        return
    entry = bucket_owner(bucket)
    if entry:
        node = node_by_name(entry["node"])
        if node is not None:
            status, _ = agent_call(node, "POST", "/release", {"bucket": bucket})
            if status in (200, 201):
                return
    for node in NODES:
        agent_call(node, "POST", "/release", {"bucket": bucket})


# --------------------------------------------------------------------------
# gateway


def detect_region_service(headers, query: str) -> tuple[str, str]:
    auth = headers.get("Authorization", "")
    match = re.search(r"Credential=[^/]+/\d{8}/([^/]+)/([^/]+)/aws4_request", auth)
    if match:
        region, service = match.group(1), match.group(2)
    else:
        params = parse_qs(query)
        presigned = (params.get("X-Amz-Credential") or [""])[0]
        match = re.match(r"[^/]+/\d{8}/([^/]+)/([^/]+)/aws4_request", presigned)
        if match:
            region, service = match.group(1), match.group(2)
        else:
            region = headers.get("X-Ministack-Region", DEFAULT_REGION)
            target = headers.get("X-Amz-Target", "")
            service = target.split(".")[0].split("_")[0].lower() if target else "s3"
    with SEEN_LOCK:
        SEEN_REGIONS.add(region)
    return region, service


def request_account(headers, query: str) -> str:
    """The account a request belongs to: a 12-digit access key, else the root
    fallback. This is also what selects the account inside the emulator."""
    auth = headers.get("Authorization", "")
    match = re.search(r"Credential=([^/]+)/\d{8}/", auth)
    if not match:
        params = parse_qs(query)
        match = re.match(
            r"([^/]+)/\d{8}/", (params.get("X-Amz-Credential") or [""])[0]
        )
    if match and re.fullmatch(r"\d{12}", match.group(1)):
        return match.group(1)
    return ""


def s3_target(path: str, host: str) -> tuple[str | None, str, str, bool]:
    parts = urlsplit(path)
    match = re.match(r"^([a-z0-9.-]+)\.s3[.-]", host)
    if match:
        return match.group(1), parts.path.lstrip("/"), parts.query, True
    segments = parts.path.lstrip("/").split("/", 1)
    bucket = segments[0] if segments and segments[0] else None
    key = segments[1] if len(segments) > 1 else ""
    return bucket, key, parts.query, False


def proxy(
    node: dict, method: str, path: str, headers, body: bytes
) -> tuple[int, list, bytes]:
    url = urlsplit(node["endpoint"])
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=120)
    forwarded = {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP
    }
    # Keep the client's Host: with AUTH=true MiniStack verifies the SigV4
    # signature, which covers the Host header. Rewriting it would make every
    # signed request fail with SignatureDoesNotMatch.
    forwarded.setdefault("Host", f"{url.hostname}:{url.port or 80}")
    if body is not None:
        forwarded["Content-Length"] = str(len(body))
    try:
        conn.request(method, path, body=body, headers=forwarded)
        response = conn.getresponse()
        return response.status, response.getheaders(), response.read()
    finally:
        conn.close()


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"gateway: {fmt % args}", flush=True)

    def do_GET(self):
        self._handle()

    do_HEAD = do_GET
    do_PUT = do_GET
    do_POST = do_GET
    do_DELETE = do_GET
    do_PATCH = do_GET
    do_OPTIONS = do_GET

    def _read_body(self) -> bytes:
        if self.headers.get("Expect", "").lower() == "100-continue":
            self.send_response_only(100)
            self.end_headers()
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            chunks = []
            while True:
                line = self.rfile.readline().strip()
                size = int(line.split(b";")[0] or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.read(2)
            return b"".join(chunks)
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _send(self, status: int, headers: list, body: bytes) -> None:
        self.send_response(status)
        for key, value in headers:
            if key.lower() in HOP_BY_HOP or key.lower() == "content-length":
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Error><Code>{code}</Code><Message>{html.escape(message)}</Message></Error>"
        ).encode()
        self._send(status, [("Content-Type", "application/xml")], body)

    def _forward(self, node: dict, region: str, body: bytes) -> None:
        try:
            status, headers, payload = proxy(
                node, self.command, self.path, self.headers, body
            )
        except OSError as exc:
            self._error(
                503,
                "ServiceUnavailable",
                f"region {region} is served by {node['name']}, which is "
                f"unreachable: {exc}",
            )
            return
        self._send(status, headers, payload)

    def _handle(self) -> None:
        body = self._read_body()
        region, service = detect_region_service(self.headers, urlsplit(self.path).query)
        account = request_account(self.headers, urlsplit(self.path).query)

        if service in GLOBAL_SERVICES:
            node = primary_node()
            if node is None:
                self._error(503, "ServiceUnavailable", "no nodes have joined the federation")
                return
            self._forward(node, node["region"], body)
            return
        if service != "s3":
            node = node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no nodes have joined the federation")
                return
            self._forward(node, region, body)
            return

        bucket, key, query, _ = s3_target(self.path, self.headers.get("Host", ""))
        if not bucket:
            node = node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no nodes have joined the federation")
                return
            self._forward(node, region, body)
            return

        params = parse_qs(query, keep_blank_values=True)
        keys = set(params) - {"x-id"}
        request_id = (params.get("x-id") or [""])[0]
        create = (
            self.command == "PUT"
            and not key
            and not keys
            and request_id in ("", "CreateBucket")
        )
        destroy = (
            self.command == "DELETE"
            and not key
            and not keys
            and request_id in ("", "DeleteBucket")
        )

        if create:
            ok, message, code = reserve_across(bucket, region, account)
            if not ok:
                self._error(
                    code,
                    "BucketAlreadyExists" if code == 409 else "ServiceUnavailable",
                    message,
                )
                return
            node = node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no nodes have joined the federation")
                return
            try:
                status, headers, payload = proxy(
                    node, self.command, self.path, self.headers, body
                )
            except OSError as exc:
                release_across(bucket)
                self._error(503, "ServiceUnavailable", f"{node['name']} unreachable: {exc}")
                return
            if not 200 <= status < 300:
                release_across(bucket)
            self._send(status, headers, payload)
            return

        if destroy:
            entry = bucket_owner(bucket)
            node = node_by_name(entry["node"]) if entry else node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no nodes have joined the federation")
                return
            try:
                status, headers, payload = proxy(
                    node, self.command, self.path, self.headers, body
                )
            except OSError as exc:
                self._error(503, "ServiceUnavailable", f"{node['name']} unreachable: {exc}")
                return
            if 200 <= status < 300:
                release_across(bucket)
            self._send(status, headers, payload)
            return

        entry = bucket_owner(bucket)
        node = node_by_name(entry["node"]) if entry else node_by_region(region)
        if node is None:
            self._error(503, "ServiceUnavailable", "no nodes have joined the federation")
            return
        self._forward(node, region, body)


# --------------------------------------------------------------------------
# control API + dashboard


def state_badge(state: str | None) -> str:
    if state == "available":
        return '<span class="up">available</span>'
    if state:
        return f'<span class="down">{html.escape(state)}</span>'
    return '<span class="muted">—</span>'


PAGE_STYLE = """
 body { font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 64rem;
        background: #11151c; color: #e6edf3; }
 h1 { font-size: 1.4rem; } h2 { font-size: 1.05rem; margin-top: 2rem; }
 h3 { font-size: .95rem; margin-top: 1.5rem; color: #9aa7b8; }
 table { width: 100%; border-collapse: collapse; }
 th, td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #2b3442; }
 th { color: #9aa7b8; font-weight: 600; }
 code { background: #1b2230; padding: .1rem .3rem; border-radius: 4px; }
 a { color: #6cb6ff; }
 .muted { color: #7d8a9c; }
 .up { color: #4ade80; } .down { color: #f87171; }
 .badge { display: inline-block; padding: .1rem .45rem; border-radius: 999px;
          background: #1b2230; border: 1px solid #2b3442; }
 form { display: flex; gap: .5rem; margin: 1rem 0; flex-wrap: wrap; }
 input, button { font: inherit; padding: .35rem .55rem; border-radius: 6px;
   border: 1px solid #2b3442; background: #1b2230; color: #e6edf3; }
 button { cursor: pointer; }
 nav { margin-bottom: 1rem; display: flex; gap: 1rem; align-items: center; }
 nav details.user { position: relative; }
 nav details.user summary { cursor: pointer; list-style: none; }
 nav details.user summary::-webkit-details-marker { display: none; }
 nav details.user summary::after { content: " ▾"; color: #7d8a9c; }
 nav details.user .panel { position: absolute; right: 0; top: 1.7rem; z-index: 10;
   background: #161c26; border: 1px solid #2b3442; border-radius: 8px;
   padding: .75rem 1rem; min-width: 17rem; box-shadow: 0 12px 30px #0008; }
 nav details.user .panel p { margin: 0 0 .55rem; }
 nav details.user .panel a { display: block; padding: .2rem 0; }
 nav details.menu { position: relative; }
 nav details.menu summary { cursor: pointer; list-style: none; color: #6cb6ff; }
 nav details.menu summary::-webkit-details-marker { display: none; }
 nav details.menu summary::after { content: " ▾"; color: #7d8a9c; }
 nav details.menu .panel { position: absolute; left: 0; top: 1.7rem; z-index: 10;
   background: #161c26; border: 1px solid #2b3442; border-radius: 8px;
   padding: 1rem 1.25rem; box-shadow: 0 12px 30px #0008; max-height: 70vh;
   overflow: auto; columns: 3; column-gap: 2rem; }
 nav details.menu .panel h3 { font-size: .72rem; text-transform: uppercase;
   letter-spacing: .08em; color: #9aa7b8; margin: .6rem 0 .35rem;
   break-after: avoid; }
 nav details.menu .panel h3:first-child { margin-top: 0; }
 nav details.menu .panel a { display: block; padding: .1rem 0; font-size: .85rem;
   color: #c9d4e0; text-decoration: none; break-inside: avoid; }
 nav details.menu .panel a:hover { color: #6cb6ff; }
 .frame iframe { width: 100%; height: calc(100vh - 16rem); min-height: 30rem;
   border: 1px solid #2b3442; border-radius: 8px; background: #0b0c0e; }
 select { font: inherit; padding: .35rem .55rem; border-radius: 6px;
   border: 1px solid #2b3442; background: #1b2230; color: #e6edf3; }
"""


def mask(value: str) -> str:
    """Enough to recognise a credential, never enough to use it."""
    if not value:
        return "—"
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 8}{value[-4:]}"


AUTH_STYLE = """
  :root {
    --bg: #f7f8f8; --panel: #ffffff; --fg: #16191f; --muted: #5f6b7a;
    --border: #d5dbdb; --input: #ffffff; --primary: #0972d3;
    --primary-hover: #085ea8; --link: #0972d3;
    --error-bg: #fdf3f3; --error-border: #e07979; --error-fg: #8b1a1a;
    --ok-bg: #f1f8f3; --ok-border: #7fb98a; --ok-fg: #1d5b2c;
    color-scheme: light;
  }
  [data-theme="dark"] {
    --bg: #0f141a; --panel: #161d26; --fg: #e9ecef; --muted: #9aa4b2;
    --border: #2b3540; --input: #0f141a; --primary: #3d9bf0;
    --primary-hover: #60b0f5; --link: #6cb6ff;
    --error-bg: #2a1215; --error-border: #6e2b2b; --error-fg: #ff8f8f;
    --ok-bg: #10241a; --ok-border: #2f6b45; --ok-fg: #7fe0a0;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: var(--bg); color: var(--fg);
         font: 15px/1.5 "Open Sans", system-ui, -apple-system, sans-serif; }
  .auth-card { width: 100%; max-width: 26rem; padding: 2.25rem 2rem;
               background: var(--panel); border: 1px solid var(--border);
               border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.08);
               position: relative; }
  .theme { position: absolute; top: .75rem; right: .75rem; display: inline-flex;
           align-items: center; margin: 0; background: transparent; }
  .theme button { display: inline-flex; align-items: center; justify-content: center;
                  width: 24px; height: 24px; padding: 0; border: none;
                  border-radius: 0; background: transparent; color: inherit;
                  cursor: pointer; opacity: .8; }
  .theme button:hover { opacity: 1; }
  .theme button span[hidden] { display: none !important; }
  .theme button span { display: inline-flex; align-items: center; }
  .brand { display: flex; align-items: center; justify-content: center; gap: .6rem;
           margin-bottom: 1.75rem; font-weight: 600; letter-spacing: .02em; }
  .brand .logo { height: 3.6rem; width: auto; }
  [data-theme="dark"] .brand .logo { background: #fff; padding: .25rem .5rem;
                                     border-radius: 8px; }
  h1 { font-size: 1.45rem; text-align: center; margin: 0 0 .4rem; font-weight: 600; }
  p.sub { text-align: center; color: var(--muted); margin: 0 0 1.6rem; font-size: .9rem; }
  .field { margin-bottom: 1rem; }
  label { display: block; font-size: .85rem; margin: 0 0 .35rem; }
  label .opt { color: var(--muted); font-weight: normal; }
  input { width: 100%; padding: .62rem .7rem; border-radius: 6px;
          border: 1px solid var(--border); background: var(--input);
          color: var(--fg); font: inherit; }
  input:focus { outline: 2px solid var(--primary); outline-offset: 0;
                border-color: transparent; }
  input::placeholder { color: var(--muted); opacity: .8; }
  button { width: 100%; margin-top: 1rem; padding: .65rem; border: 0;
           border-radius: 6px; background: var(--primary); color: #fff;
           font: inherit; font-weight: 600; cursor: pointer; }
  button:hover { background: var(--primary-hover); }
  .divider { display: flex; align-items: center; gap: .75rem; margin: 1.4rem 0;
             color: var(--muted); font-size: .8rem; }
  .divider::before, .divider::after { content: ""; flex: 1; height: 1px;
                                      background: var(--border); }
  a.secondary { display: block; text-align: center; padding: .58rem;
                border-radius: 6px; border: 1px solid var(--border);
                color: var(--fg); text-decoration: none; }
  a.secondary:hover { background: var(--bg); }
  .error { background: var(--error-bg); border: 1px solid var(--error-border);
           color: var(--error-fg); padding: .6rem .75rem; border-radius: 6px;
           font-size: .85rem; margin-bottom: 1rem; }
  .ok { background: var(--ok-bg); border: 1px solid var(--ok-border);
        color: var(--ok-fg); padding: .6rem .75rem; border-radius: 6px;
        font-size: .85rem; margin-bottom: 1rem; }
  .links { margin-top: 1.4rem; text-align: center; font-size: .85rem;
           color: var(--muted); }
  .links a { color: var(--link); text-decoration: none; }
  .links a:hover { text-decoration: underline; }
"""


AUTH_THEME_SCRIPT = """
(function () {
  // One button toggles light and dark; it shows the mode it will switch to.
  var authKey = 'ministack:auth-theme';
  var consoleKey = 'ministack:theme';
  var toggle = document.querySelector('#theme-toggle button');
  var sun = toggle.querySelector('.icon-sun');
  var moon = toggle.querySelector('.icon-moon');
  function apply(pref) {
    var dark = pref === 'dark' ||
      (pref === 'system' &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    sun.hidden = !dark;
    moon.hidden = dark;
    toggle.setAttribute('aria-label',
      dark ? 'Switch to light mode' : 'Switch to dark mode');
    toggle.title = toggle.getAttribute('aria-label');
  }
  var stored = null;
  try {
    stored = localStorage.getItem(authKey) || localStorage.getItem(consoleKey);
  } catch (e) {}
  apply(stored || 'system');
  toggle.addEventListener('click', function () {
    var next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(authKey, next); } catch (e) {}
    apply(next);
  });
})();
"""


BROWSE_SERVICES = [
    "iam", "s3", "dynamodb", "sqs", "sns", "lambda", "logs",
    "secretsmanager", "ssm", "kinesis", "stepfunctions",
]


# --------------------------------------------------------------------------
# resource browser
#
# A 12-digit access key is an account root and needs no verified signature, so
# the control can read every account's resources without holding any secret.


def aws_call(
    account: str,
    region: str,
    service: str,
    action: str = "",
    target: str = "",
    params: dict | None = None,
    version: str = "2010-05-08",
    body: dict | None = None,
) -> tuple[int, str]:
    node = primary_node()
    if node is None:
        return 0, "emulator is not registered"
    url = urlsplit(node["endpoint"])
    host = f"{url.hostname}:{url.port or 80}"
    now_utc = datetime.now(timezone.utc)
    stamp = now_utc.strftime("%Y%m%d")
    headers = {
        "Host": host,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={account}/{stamp}/{region}/{service}"
            "/aws4_request, SignedHeaders=host, Signature=local"
        ),
        "x-amz-date": now_utc.strftime("%Y%m%dT%H%M%SZ"),
    }
    if target:
        data = json.dumps(body or {}).encode()
        headers["X-Amz-Target"] = target
        headers["Content-Type"] = "application/x-amz-json-1.0"
    else:
        data = urlencode(
            {"Action": action, "Version": version, **(params or {})}
        ).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    headers["Content-Length"] = str(len(data))
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=10)
    try:
        conn.request("POST", "/", body=data, headers=headers)
        response = conn.getresponse()
        return response.status, response.read().decode(errors="replace")
    except OSError as exc:
        return 0, str(exc)
    finally:
        conn.close()


def signed_rest(
    service: str, account: str, region: str, method: str, path: str, body: str = ""
) -> tuple[int, str]:
    """Generic REST-JSON call (Lambda, API Gateway, ...) as the account root."""
    node = primary_node()
    if node is None:
        return 0, "emulator is not registered"
    url = urlsplit(node["endpoint"])
    host = f"{url.hostname}:{url.port or 80}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    data = (body or "").encode()
    headers = {
        "Host": host,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={account}/{stamp}/{region}/{service}"
            "/aws4_request, SignedHeaders=host, Signature=local"
        ),
        "x-amz-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "Content-Length": str(len(data)),
    }
    if data:
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=10)
    try:
        conn.request(method, path, body=data or None, headers=headers)
        response = conn.getresponse()
        return response.status, response.read().decode(errors="replace")
    except OSError as exc:
        return 0, str(exc)
    finally:
        conn.close()


def signed_s3(
    account: str, region: str, method: str, path: str, body: str = ""
) -> tuple[int, str]:
    """Path-style S3 call signed as the account root, so no secret is held."""
    return signed_rest("s3", account, region, method, path, body)


def static_asset(url_path: str) -> tuple[bytes, str] | None:
    """One built asset from `web/dist`, or None. Traversal-safe."""
    if not (url_path.startswith("/assets/") or url_path == "/ministack-logo.png"):
        return None
    # The logo also ships in `web/public`, so the sign-in pages keep their brand
    # mark before `web/dist` has ever been built.
    for root in (PUBLIC_DIR, STATIC_DIR):
        base = os.path.realpath(root)
        target = os.path.realpath(os.path.join(base, url_path.lstrip("/")))
        if not target.startswith(base + os.sep) or not os.path.isfile(target):
            continue
        with open(target, "rb") as handle:
            payload = handle.read()
        return payload, MIME.get(
            os.path.splitext(target)[1].lower(), "application/octet-stream"
        )
    return None


def spa_index() -> bytes | None:
    try:
        with open(os.path.join(STATIC_DIR, "index.html"), "rb") as handle:
            return handle.read()
    except OSError:
        return None


def xml_value(block: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    return match.group(1) if match else ""


def xml_members(text: str, container: str) -> list[str]:
    match = re.search(rf"<{container}>(.*?)</{container}>", text, re.S)
    if not match:
        return []
    return re.findall(r"<member>(.*?)</member>", match.group(1), re.S)


def xml_all(text: str, tag: str) -> list[str]:
    return re.findall(rf"<{tag}>([^<]+)</{tag}>", text)


def _browse_region(service: str, account: str, region: str) -> list[dict]:
    """Return `[{name, kind, detail}]` for one service in one account/region."""
    rows: list[dict] = []

    if service == "iam":
        spec = [
            ("ListUsers", "Users", "UserName", "user"),
            ("ListRoles", "Roles", "RoleName", "role"),
            ("ListGroups", "Groups", "GroupName", "group"),
            ("ListPolicies", "Policies", "PolicyName", "policy"),
        ]
        for action, container, name_tag, kind in spec:
            _, body = aws_call(account, region, "iam", action=action)
            for member in xml_members(body, container):
                rows.append(
                    {
                        "name": xml_value(member, name_tag),
                        "kind": kind,
                        "detail": {
                            "arn": xml_value(member, "Arn"),
                            "created": xml_value(member, "CreateDate"),
                        },
                    }
                )
        return rows

    if service == "s3":
        # ListBuckets is a REST GET; a query-protocol POST returns MethodNotAllowed.
        status, body = signed_s3(account, region, "GET", "/?x-id=ListBuckets")
        if status != 200:
            return rows
        for name, created in re.findall(
            r"<Bucket>.*?<Name>([^<]+)</Name>.*?<CreationDate>([^<]*)</CreationDate>",
            body,
            re.S,
        ):
            rows.append({"name": name, "kind": "bucket", "detail": {"created": created}})
        for name in re.findall(r"<Bucket>\s*<Name>([^<]+)</Name>", body):
            if not any(row["name"] == name for row in rows):
                rows.append({"name": name, "kind": "bucket", "detail": {}})
        return rows

    if service == "ec2":
        _, body = aws_call(account, region, "ec2", action="DescribeInstances")
        for name, state in re.findall(
            r"<instanceId>([^<]+)</instanceId>.*?<instanceState>\s*<code>[^<]*</code>\s*"
            r"<name>([^<]+)</name>",
            body,
            re.S,
        ):
            rows.append({"name": name, "kind": "instance", "detail": {"state": state}})
        _, groups = aws_call(account, region, "ec2", action="DescribeSecurityGroups")
        for group_id, group_name in re.findall(
            r"<groupId>([^<]+)</groupId>\s*<groupName>([^<]+)</groupName>", groups
        ):
            rows.append(
                {
                    "name": group_name,
                    "kind": "security group",
                    "detail": {"id": group_id},
                }
            )
        _, pairs = aws_call(account, region, "ec2", action="DescribeKeyPairs")
        for key_name in re.findall(r"<keyName>([^<]+)</keyName>", pairs):
            rows.append({"name": key_name, "kind": "key pair", "detail": {}})
        return rows

    if service == "dynamodb":
        _, body = aws_call(
            account, region, "dynamodb",
            target="DynamoDB_20120810.ListTables", body={},
        )
        tables = json.loads(body).get("TableNames", []) if body.startswith("{") else []
        return [{"name": name, "kind": "table", "detail": {}} for name in tables]

    if service == "sqs":
        _, body = aws_call(
            account, region, "sqs", action="ListQueues", version="2012-11-05"
        )
        return [
            {"name": url.rstrip("/").rsplit("/", 1)[-1], "kind": "queue", "detail": {"url": url}}
            for url in xml_all(body, "QueueUrl")
        ]

    if service == "sns":
        _, body = aws_call(account, region, "sns", action="ListTopics")
        return [
            {
                "name": arn.rsplit(":", 1)[-1],
                "kind": "topic",
                "detail": {"arn": arn},
            }
            for arn in xml_all(body, "TopicArn")
        ]

    if service == "lambda":
        _, body = signed_rest(
            "lambda", account, region, "GET", "/2015-03-31/functions/"
        )
        functions = json.loads(body).get("Functions", []) if body.startswith("{") else []
        return [
            {
                "name": fn.get("FunctionName", ""),
                "kind": "function",
                "detail": {
                    "runtime": fn.get("Runtime", ""),
                    "memory": fn.get("MemorySize", ""),
                    "modified": fn.get("LastModified", ""),
                },
            }
            for fn in functions
        ]

    if service == "logs":
        _, body = aws_call(
            account, region, "logs",
            target="Logs_20140328.DescribeLogGroups", body={},
        )
        groups = json.loads(body).get("logGroups", []) if body.startswith("{") else []
        return [
            {
                "name": group.get("logGroupName", ""),
                "kind": "log group",
                "detail": {
                    "storedBytes": group.get("storedBytes", ""),
                    "retention": group.get("retentionInDays", ""),
                },
            }
            for group in groups
        ]

    if service == "secretsmanager":
        _, body = aws_call(
            account, region, "secretsmanager",
            target="secretsmanager.ListSecrets", body={},
        )
        secrets = json.loads(body).get("SecretList", []) if body.startswith("{") else []
        return [
            {
                "name": secret.get("Name", ""),
                "kind": "secret",
                "detail": {"changed": secret.get("LastChangedDate", "")},
            }
            for secret in secrets
        ]

    if service == "ssm":
        _, body = aws_call(
            account, region, "ssm",
            target="AmazonSSM.DescribeParameters", body={},
        )
        parameters = json.loads(body).get("Parameters", []) if body.startswith("{") else []
        return [
            {
                "name": parameter.get("Name", ""),
                "kind": parameter.get("Type", "parameter"),
                "detail": {"modified": parameter.get("LastModifiedDate", "")},
            }
            for parameter in parameters
        ]

    if service == "kinesis":
        _, body = aws_call(
            account, region, "kinesis",
            target="Kinesis_20131202.ListStreams", body={},
        )
        streams = json.loads(body).get("StreamNames", []) if body.startswith("{") else []
        return [{"name": name, "kind": "stream", "detail": {}} for name in streams]

    if service == "stepfunctions":
        _, body = aws_call(
            account, region, "states",
            target="AWSStepFunctions.ListStateMachines", body={},
        )
        machines = json.loads(body).get("stateMachines", []) if body.startswith("{") else []
        return [
            {
                "name": machine.get("name", ""),
                "kind": "state machine",
                "detail": {"status": machine.get("status", "")},
            }
            for machine in machines
        ]

    return rows


# Parameters that name the resource an action creates or touches. The emulator
# records no owner, so this is how the control learns who made what.
OWNER_PARAMS = (
    "Bucket", "QueueName", "TopicArn", "TableName", "UserName", "RoleName",
    "FunctionName", "ParameterName", "SecretId", "StreamName", "logGroupName",
    "stateMachineArn", "Name",
)
# Those whose row name is the last ARN segment.
OWNER_ARN_PARAMS = {"TopicArn", "stateMachineArn", "SecretId"}


def owner_name(params: dict) -> str:
    """The resource name a successful action created/updated, or ""."""
    for key in OWNER_PARAMS:
        value = params.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if key in OWNER_ARN_PARAMS and value.startswith("arn:"):
            return value.rsplit(":", 1)[-1]
        return value
    return ""


def _bucket_claim(name: str) -> dict:
    with REGISTRY.lock:
        return dict(REGISTRY.buckets.get(name) or {})


def _annotate(
    service: str, account: str, region: str, rows: list[dict]
) -> list[dict]:
    """Attach the region and owner metadata every row carries.

    S3 is account-scoped but not region-isolated upstream, so a bucket's region
    is the one recorded when its name was claimed, not the region being queried.
    """
    for row in rows:
        claim = _bucket_claim(row["name"]) if service == "s3" else {}
        entry = OWNERS.get(account, service, row["name"])
        owner = {"account": claim.get("account_id") or account}
        if entry.get("user"):
            owner["user"] = entry["user"]
            owner["at"] = entry.get("at", "")
        row["region"] = claim.get("region") or region
        row["owner"] = owner
        row["detail"] = dict(row.get("detail") or {})
    return rows


def browse(service: str, account: str, region: str) -> list[dict]:
    """Rows for one service in one account/region, with region + owner."""
    return _annotate(service, account, region, _browse_region(service, account, region))


def served_regions(account: dict) -> list[str]:
    """The account's enabled regions that the registered emulator serves."""
    known = {node.get("region") for node in NODES if node.get("region")}
    regions = [
        name for name in ACCOUNTS.regions_of(account) if not known or name in known
    ]
    return regions or [DEFAULT_REGION]


def browse_all(service: str, account: str, regions: list[str]) -> list[dict]:
    """Every region at once; S3 is listed once because it is not region-isolated."""
    rows: list[dict] = []
    seen: set[tuple] = set()
    for region in regions[:1] if service == "s3" else regions:
        for row in browse(service, account, region):
            key = (
                row["kind"],
                row["name"],
                "" if service == "s3" else row.get("region", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def identity(account: str, region: str) -> dict:
    status, body = aws_call(
        account, region, "sts", action="GetCallerIdentity", version="2011-06-15"
    )
    if status != 200:
        return {"error": body[:160]}
    return {"arn": xml_value(body, "Arn"), "account": xml_value(body, "Account")}


class ControlHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"control: {fmt % args}", flush=True)

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _page(self, body: str, status: int = 200) -> None:
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _spa(self) -> None:
        payload = spa_index()
        if payload is None:
            return self._page(
                "<!doctype html><meta charset=utf-8><title>MiniStack</title>"
                "<body style='font:15px system-ui;padding:2rem;background:#0f1b2d;color:#e6edf7'>"
                "<h1>Console not built</h1><p>Run <code>npm install &amp;&amp; npm run build</code>"
                " in <code>services/ministack-control/web</code>, then restart this container.</p>"
                f"<p>The server-rendered pages are still at <a style='color:#7cc4ff' href='/classic'>/classic</a>.</p>",
                503,
            )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _asset(self, url_path: str) -> None:
        found = static_asset(url_path)
        if found is None:
            return self._json(404, {"error": "asset not found"})
        payload, content_type = found
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(payload)

    def _cookies(self) -> dict[str, str]:
        cookies = {}
        for part in self.headers.get("Cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key:
                cookies[key] = value
        return cookies

    def _oidc_start(self) -> None:
        if AUTH_MODE not in {"oidc", "both"}:
            return self._page(self._login_page("OIDC sign-in is disabled."), 404)
        if not oidc_is_provider() and not OIDC_CLIENT_SECRET:
            return self._page(
                self._login_page("OIDC is not configured (OIDC_CLIENT_SECRET)."), 500
            )
        query = parse_qs(urlsplit(self.path).query)
        intent = (query.get("intent") or ["root"])[0].strip().lower()
        if intent not in {"root", "signup", "user"}:
            intent = "root"
        account_ref = re.sub(
            r"[^A-Za-z0-9-]", "", (query.get("account") or [""])[0]
        )[:64]
        if intent == "user" and not account_ref:
            return self._page(
                self._login_page("Enter the account ID or alias to sign in to."), 400
            )
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        params = urlencode(
            {
                "client_id": OIDC_CLIENT_ID,
                "response_type": "code",
                "scope": OIDC_SCOPES,
                "redirect_uri": OIDC_REDIRECT_URI,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        location = oidc_authorization_url(params)
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header(
            "Set-Cookie", f"oidc_state={state}; Path=/; Max-Age=300; HttpOnly; SameSite=Lax"
        )
        self.send_header(
            "Set-Cookie",
            f"oidc_verifier={verifier}; Path=/; Max-Age=300; HttpOnly; SameSite=Lax",
        )
        self.send_header(
            "Set-Cookie",
            f"oidc_intent={intent}; Path=/; Max-Age=300; HttpOnly; SameSite=Lax",
        )
        self.send_header(
            "Set-Cookie",
            f"oidc_account={account_ref}; Path=/; Max-Age=300; HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _oidc_callback(self, query: str) -> None:
        params = parse_qs(query)
        code = (params.get("code") or [""])[0]
        state = (params.get("state") or [""])[0]
        cookies = self._cookies()
        if not code or not state or state != cookies.get("oidc_state"):
            return self._page(self._login_page("Invalid OIDC state; try again."), 400)
        try:
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OIDC_REDIRECT_URI,
                "client_id": OIDC_CLIENT_ID,
                "code_verifier": cookies.get("oidc_verifier", ""),
            }
            # A public client has no secret: OpenBao's `none` auth method.
            if OIDC_CLIENT_SECRET:
                payload["client_secret"] = OIDC_CLIENT_SECRET
            data = urlencode(payload).encode()
            request = urllib.request.Request(
                oidc_endpoint("token"),
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                tokens = json.loads(response.read())
            request = urllib.request.Request(
                oidc_endpoint("userinfo"),
                headers={"Authorization": f"Bearer {tokens.get('access_token', '')}"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                profile = json.loads(response.read())
        except (OSError, ValueError) as exc:
            return self._page(self._login_page(f"OIDC sign-in failed: {exc}"), 502)
        subject = str(profile.get("sub") or "").strip()
        username = str(
            profile.get("preferred_username")
            or profile.get("email")
            or subject
            or "oidc-user"
        ).strip()
        if not subject:
            return self._page(
                self._login_page("The identity provider returned no subject."), 502
            )
        intent = cookies.get("oidc_intent", "root")
        account_ref = cookies.get("oidc_account", "")
        account, principal = ACCOUNTS.resolve(
            subject, username, account_ref or None, create=(intent == "signup")
        )
        if account is None:
            return self._page(self._login_page(str(principal)), 403)
        if account.get("disabled"):
            return self._page(self._login_page("This account is disabled."), 403)
        # Keycloak is the source of truth for who is a global admin: the client
        # role `global-admin` (OIDC_ADMIN_ROLE) elevates, and the console role
        # mirrors it. Removing the role in Keycloak does not demote by itself,
        # a global admin can still do that from Accounts.
        roles = oidc_roles(profile)
        if OIDC_ADMIN_ROLE and OIDC_ADMIN_ROLE in roles and not account.get("global_admin"):
            updated = ACCOUNTS.set_global_admin(account["account_id"], True)
            if updated is not None:
                account = updated
            AUDIT.record(
                username,
                "account.global_admin_granted",
                account["account_id"],
                {"via": "oidc", "role": OIDC_ADMIN_ROLE},
            )
        problem = issue_credentials(account, principal)
        if problem:
            print(f"control: IAM credentials for {principal['username']}: {problem}", flush=True)
        token = new_session(
            principal["username"],
            account["account_id"],
            principal["role"],
            account["alias"],
        )
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"ministack_session={token}; Path=/; Max-Age={SESSION_SECONDS}; "
            "HttpOnly; SameSite=Lax",
        )
        self.send_header(
            "Set-Cookie", "oidc_state=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
        )
        self.send_header(
            "Set-Cookie", "oidc_verifier=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
        )
        self.send_header(
            "Set-Cookie", "oidc_intent=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
        )
        self.send_header(
            "Set-Cookie", "oidc_account=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _session_token(self) -> str:
        for part in self.headers.get("Cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == "ministack_session":
                return value
        return ""

    def _authenticated(self) -> bool:
        token = self._session_token()
        if token and session_ok(token):
            return True
        return bool(ADMIN_TOKEN) and self.headers.get(
            "Authorization", ""
        ) == f"Bearer {ADMIN_TOKEN}"

    def _require_admin(self) -> bool:
        if self._authenticated():
            return True
        self._json(401, {"error": "authentication required"})
        return False

    def _caller(self) -> dict:
        """The signed-in principal, or {} for a bearer-token caller."""
        return session_info(self._session_token()) or {}

    @staticmethod
    def _platform(info: dict) -> bool:
        """Bearer clients and global-admin accounts may cross tenants."""
        if not info:
            return True
        account = ACCOUNTS.by_ref(info.get("account", ""))
        return bool(account and account.get("global_admin"))

    def _can_touch(self, info: dict, account: str) -> bool:
        return self._platform(info) or account == info.get("account")

    @staticmethod
    def _api_path(path: str) -> str:
        prefix = f"/api/{API_VERSION}"
        if path.startswith(prefix):
            return "/api" + path[len(prefix) :]
        return path

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _logout(self) -> None:
        token = self._session_token()
        info = session_info(token) if token else None
        if token:
            with SESSIONS_LOCK:
                SESSIONS.pop(token, None)
                save_sessions()
        if info:
            AUDIT.record(info.get("user", "user"), "session.ended", info.get("account", ""))
        self.send_response(302)
        self.send_header("Location", "/login")
        self.send_header(
            "Set-Cookie",
            "ministack_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _login(self) -> None:
        if AUTH_MODE == "oidc":
            return self._page(
                self._login_page(
                    f"Local sign-in is disabled; use {OIDC_PROVIDER_LABEL}."
                ),
                403,
            )
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode() if length else ""
        form = parse_qs(raw)
        username = (form.get("username") or [""])[0]
        password = (form.get("password") or [""])[0]
        next_path = (form.get("next") or ["/"])[0]
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/"
        record = USERS.verify(username, password)
        if record is None:
            time.sleep(0.4)
            return self._page(
                self._login_page("Invalid username or password.", next_path),
                status=401,
            )
        account = ACCOUNTS.by_ref(record["account_id"])
        principal = ((account or {}).get("users") or {}).get(record["username"])
        if account is None or principal is None:
            return self._page(
                self._login_page("This user has no account record; sign up again."),
                500,
            )
        if account.get("disabled"):
            return self._page(
                self._login_page("This account is disabled.", next_path), 403
            )
        problem = issue_credentials(account, principal)
        if problem:
            print(f"control: IAM credentials for {username}: {problem}", flush=True)
        token = new_session(
            record["username"],
            account["account_id"],
            principal["role"],
            account["alias"],
            via="oidc",
        )
        self.send_response(302)
        self.send_header("Location", next_path)
        self.send_header(
            "Set-Cookie",
            f"ministack_session={token}; Path=/; Max-Age={SESSION_SECONDS}; "
            "HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _signup(self) -> None:
        if not SETTINGS.get("signup_enabled", True):
            return self._page(self._signup_page("Sign-up is disabled on this lab."), 403)
        if AUTH_MODE == "oidc":
            return self._page(
                self._signup_page(
                    f"Local sign-up is disabled; use {OIDC_PROVIDER_LABEL}."
                ),
                403,
            )
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode() if length else ""
        form = parse_qs(raw)
        username = (form.get("username") or [""])[0].strip()
        email = (form.get("email") or [""])[0].strip()
        password = (form.get("password") or [""])[0]
        confirm = (form.get("confirm") or [""])[0]
        error = ""
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
            error = (
                "Username must be 3-32 characters: letters, digits, dot, dash "
                "or underscore."
            )
        elif email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            error = "That email address does not look right."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "The passwords do not match."
        elif USERS.exists(username):
            error = "That username is already taken."
        if error:
            return self._page(
                self._signup_page(error, username, email), status=400
            )
        account, principal = ACCOUNTS.ensure_local(username)
        USERS.create(
            username,
            email,
            password,
            account["account_id"],
            principal.get("role", "root"),
        )
        AUDIT.record(
            username,
            "account.created",
            account["account_id"],
            {
                "alias": account["alias"],
                "via": "local-signup",
                "global_admin": bool(account.get("global_admin")),
            },
        )
        problem = issue_credentials(account, principal)
        if problem:
            print(f"control: IAM credentials for {username}: {problem}", flush=True)
        token = new_session(
            username, account["account_id"], principal["role"], account["alias"],
            via="oidc",
        )
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"ministack_session={token}; Path=/; Max-Age={SESSION_SECONDS}; "
            "HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _forgot(self) -> None:
        if AUTH_MODE == "oidc":
            return self._page(
                self._forgot_page(
                    f"Local accounts are disabled; use {OIDC_PROVIDER_LABEL}."
                ),
                403,
            )
        if not SMTP_ENABLED:
            return self._page(
                self._forgot_page("Email is not configured on this instance."), 503
            )
        form = self._form()
        address = str(form.get("email") or "").strip()
        # Same answer whether or not the address exists: no account enumeration.
        generic = "If that address belongs to an account, a reset link is on its way."
        user = USERS.by_email(address) or USERS.get(address)
        if user and (user.get("email") or ""):
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            USERS.create_reset(
                user["username"], digest, int(time.time()) + RESET_TTL_SECONDS
            )
            link = f"{PUBLIC_URL}/reset?token={quote(token)}"
            body = (
                f"Hello {user['username']},\n\n"
                "Someone asked to reset the password for your MiniStack account.\n"
                f"Open this link within {RESET_TTL_SECONDS // 60} minutes:\n\n"
                f"{link}\n\n"
                "If this was not you, ignore this message; the password is "
                "unchanged.\n"
            )
            problem = send_mail(user["email"], "Reset your MiniStack password", body)
            if problem:
                print(f"control: password reset mail: {problem}", flush=True)
            AUDIT.record(
                user["username"],
                "password.reset_requested",
                user.get("account_id", ""),
            )
        elif user:
            # Same response either way (no enumeration); the log tells an admin why
            # nothing was sent.
            print(
                f"control: reset requested for {user['username']} but the account "
                "has no email; set MC_ADMIN_EMAIL (seeded admin) or update the user",
                flush=True,
            )
        return self._page(self._forgot_page(message=generic))

    def _reset_submit(self) -> None:
        form = self._form()
        token = str(form.get("token") or "").strip()
        password = str(form.get("password") or "")
        confirm = str(form.get("confirm") or "")
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = USERS.peek_reset(digest) if token else None
        if row is None:
            return self._page(
                self._reset_page(token, "That reset link is no longer valid."), 400
            )
        if len(password) < 8:
            return self._page(
                self._reset_page(
                    token, "Password must be at least 8 characters."
                ),
                400,
            )
        if password != confirm:
            return self._page(
                self._reset_page(token, "The passwords do not match."), 400
            )
        consumed = USERS.consume_reset(digest)
        if consumed is None:
            return self._page(
                self._reset_page(token, "That reset link is no longer valid."), 400
            )
        USERS.set_password(consumed["username"], password)
        purge_sessions(consumed.get("account_id", ""))
        AUDIT.record(
            consumed["username"], "password.reset", consumed.get("account_id", "")
        )
        self._redirect("/login?reset=1")

    def _auth_layout(self, title: str, body: str) -> str:
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · MiniStack</title><style>{AUTH_STYLE}</style>
</head><body><main class="auth-card">
<div class="theme" id="theme-toggle">
  <button type="button" aria-label="Toggle colour theme" title="Toggle colour theme">
    <span class="icon-sun">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <circle cx="12" cy="12" r="4"></circle>
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>
      </svg>
    </span>
    <span class="icon-moon">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round"
           stroke-linejoin="round">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path>
      </svg>
    </span>
  </button>
</div>
{body}</main><script>{AUTH_THEME_SCRIPT}</script></body></html>"""

    def _login_page(
        self, error: str = "", next_path: str = "/", message: str = ""
    ) -> str:
        notice = f'<div class="error">{html.escape(error)}</div>' if error else ""
        if message:
            notice += f'<div class="ok">{html.escape(message)}</div>'
        oidc = oidc_available()
        provider = html.escape(OIDC_PROVIDER_LABEL)
        divider = (
            '<div class="divider">or</div>'
            f'<a class="secondary" href="/oidc/start?intent=root">'
            f"Sign in with {provider}</a>"
            if oidc
            else ""
        )
        if AUTH_MODE == "oidc":
            local = ""
        elif not USERS.count():
            local = (
                '<div class="error">No local users yet. A global admin can '
                "provision the first one.</div>"
            )
        else:
            local = f"""
        <form method="post" action="/login">
          <input type="hidden" name="next" value="{html.escape(next_path)}">
          <div class="field"><label for="username">Email or username</label>
            <input id="username" name="username" autocomplete="username"
                   placeholder="email or username" required autofocus></div>
          <div class="field"><label for="password">Password</label>
            <input id="password" name="password" type="password"
                   autocomplete="current-password" placeholder="password"
                   required></div>
          <button type="submit">Sign in</button>
        </form>"""
        forgot = (
            '<div class="links"><a href="/forgot">Forgot password?</a></div>'
            if AUTH_MODE != "oidc"
            else ""
        )
        return self._auth_layout(
            "Sign in",
            f"""
    <div class="brand"><img class="logo" src="/ministack-logo.png"
         alt="MiniStack"></div>
    <h1>Welcome to MiniStack CP</h1>
    <p class="sub">Sign in to your account</p>
    {notice}
    {local}
    {divider}
    {forgot}
""",
        )

    def _forgot_page(self, error: str = "", message: str = "") -> str:
        notice = f'<div class="error">{html.escape(error)}</div>' if error else ""
        if message:
            notice += f'<div class="ok">{html.escape(message)}</div>'
        if not SMTP_ENABLED:
            form = (
                '<p class="sub">Email is not configured on this instance, so a '
                "reset link cannot be sent. Ask a global admin to reset your "
                "password.</p>"
            )
        else:
            form = """
        <form method="post" action="/forgot">
          <div class="field"><label for="email">Email address</label>
            <input id="email" name="email" type="email"
                   autocomplete="email" placeholder="email" required autofocus></div>
          <button type="submit">Send reset link</button>
        </form>"""
        return self._auth_layout(
            "Forgot password",
            f"""
    <div class="brand"><img class="logo" src="/ministack-logo.png"
         alt="MiniStack"></div>
    <h1>Forgot password?</h1>
    <p class="sub">We will email you a link to set a new password</p>
    {notice}
    {form}
    <div class="links"><a href="/login">Back to sign in</a></div>
""",
        )

    def _reset_page(self, token: str, error: str = "") -> str:
        notice = f'<div class="error">{html.escape(error)}</div>' if error else ""
        return self._auth_layout(
            "Set a new password",
            f"""
    <div class="brand"><img class="logo" src="/ministack-logo.png"
         alt="MiniStack"></div>
    <h1>Set a new password</h1>
    <p class="sub">This link can be used once</p>
    {notice}
    <form method="post" action="/reset">
      <input type="hidden" name="token" value="{html.escape(token)}">
      <div class="field"><label for="password">New password</label>
        <input id="password" name="password" type="password"
               autocomplete="new-password" placeholder="new password"
               required autofocus></div>
      <div class="field"><label for="confirm">Confirm password</label>
        <input id="confirm" name="confirm" type="password"
               autocomplete="new-password" placeholder="repeat new password"
               required></div>
      <button type="submit">Update password</button>
    </form>
    <div class="links"><a href="/login">Back to sign in</a></div>
""",
        )

    def _signup_page(self, error: str = "", username: str = "", email: str = "") -> str:
        notice = f'<div class="error">{html.escape(error)}</div>' if error else ""
        oidc = oidc_available()
        alternate = (
            '<div class="divider">or</div>'
            f'<a class="secondary" href="/oidc/start?intent=signup">'
            f"Continue with {html.escape(OIDC_PROVIDER_LABEL)}</a>"
            if oidc
            else ""
        )
        return self._auth_layout(
            "Create account",
            f"""
    <div class="brand"><img class="logo" src="/ministack-logo.png"
         alt="MiniStack"></div>
    <h1>Create your account</h1>
    <p class="sub">A new account gets its own ID and IAM credentials</p>
    {notice}
    <form method="post" action="/signup">
      <div class="field"><label for="username">Username</label>
        <input id="username" name="username" value="{html.escape(username)}"
               autocomplete="username" required autofocus></div>
      <div class="field"><label for="email">Email <span class="opt">(optional)</span></label>
        <input id="email" name="email" type="email" value="{html.escape(email)}"
               autocomplete="email"></div>
      <div class="field"><label for="password">Password</label>
        <input id="password" name="password" type="password"
               autocomplete="new-password" required></div>
      <div class="field"><label for="confirm">Confirm password</label>
        <input id="confirm" name="confirm" type="password"
               autocomplete="new-password" required></div>
      <button type="submit">Create account</button>
    </form>
    {alternate}
    <div class="links">Already have an account? <a href="/login">Sign in</a></div>
""",
        )

    def _iam_page(self, error: str = "") -> str:
        notice = f'<div class="error">{html.escape(error)}</div>' if error else ""
        if AUTH_MODE not in {"oidc", "both"}:
            form = '<p class="sub">OIDC sign-in is disabled.</p>'
        else:
            form = f"""
    <form method="get" action="/oidc/start">
      <input type="hidden" name="intent" value="user">
      <div class="field"><label for="account">Account ID or alias</label>
        <input id="account" name="account" autocomplete="off" required autofocus></div>
      <button type="submit">Sign in with {html.escape(OIDC_PROVIDER_LABEL)}</button>
    </form>"""
        return self._auth_layout(
            "Service account",
            f"""
    <div class="brand"><img class="logo" src="/ministack-logo.png"
         alt="MiniStack"></div>
    <h1>Sign in with an account ID</h1>
    <p class="sub">Your identity must already be a principal in that account</p>
    {notice}
    {form}
    <div class="links"><a href="/login">Back to sign in</a></div>
""",
        )

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def _form(self) -> dict:
        """The request body as a flat form dict (last value wins)."""
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode()
        return {key: values[0] for key, values in parse_qs(raw).items()}

    def _route_get(self):
        path = urlsplit(self.path).path
        if path == "/health":
            return self._json(
                200,
                {
                    "status": "ok",
                    "api_version": API_VERSION,
                    "uptime_seconds": int(time.time() - STARTED_AT),
                    "mode": MODE,
                    "stability": MODE_STABILITY.get(MODE, "unknown"),
                    "auth": AUTH_MODE,
                    "accounts": len(ACCOUNTS.accounts),
                    "regions_seen": sorted(SEEN_REGIONS),
                },
            )
        if path == "/login":
            params = parse_qs(urlsplit(self.path).query)
            message = (
                "Password updated. Sign in with the new one."
                if (params.get("reset") or [""])[0] == "1"
                else ""
            )
            return self._page(self._login_page(message=message))
        if path == "/forgot":
            return self._page(self._forgot_page())
        if path == "/reset":
            params = parse_qs(urlsplit(self.path).query)
            token = (params.get("token") or [""])[0].strip()
            digest = hashlib.sha256(token.encode()).hexdigest()
            if not token or USERS.peek_reset(digest) is None:
                return self._page(
                    self._forgot_page(
                        error="That reset link is no longer valid. Ask for a new one."
                    ),
                    400,
                )
            return self._page(self._reset_page(token))
        if path == "/login/iam":
            return self._page(self._iam_page())
        if path == "/signup":
            return self._page(self._signup_page())
        if path in SPA_ROUTES or path.startswith("/resources/"):
            if not self._authenticated():
                return self._redirect("/login?next=" + quote(path))
            return self._spa()
        if path.startswith("/assets/"):
            return self._asset(path)
        if path == "/ministack-logo.png":
            return self._asset(path)
        if path == "/oidc/start":
            return self._oidc_start()
        if path == "/oidc/callback":
            return self._oidc_callback(urlsplit(self.path).query)
        if path == "/logout":
            return self._logout()
        if path in ("/api/nodes/discovery", "/api/v1/nodes/discovery"):
            token = self.headers.get("X-Join-Token", "")
            if not JOIN_TOKEN or not hmac.compare_digest(token, JOIN_TOKEN):
                return self._json(401, {"error": "invalid join token"})
            return self._json(200, {"nodes": NODE_REGISTRY.snapshot()})
        if path.startswith("/api"):
            if not self._authenticated():
                return self._json(401, {"error": "authentication required"})
            path = self._api_path(path)
        elif not self._authenticated():
            return self._redirect("/login?next=" + quote(path))

        if path == "/api/accounts/me":
            info = session_info(self._session_token()) or {}
            return self._json(
                200,
                {
                    key: info.get(key)
                    for key in ("user", "account", "alias", "role", "expires")
                },
            )
        if path == "/api/credentials":
            info = session_info(self._session_token()) or {}
            account_obj = ACCOUNTS.by_ref(info.get("account", ""))
            principal = ((account_obj or {}).get("users") or {}).get(
                info.get("user", "")
            )
            if account_obj is None or principal is None:
                return self._json(
                    400, {"error": "sign in as an account principal first"}
                )
            return self._json(
                200,
                {
                    "account": account_obj["account_id"],
                    "user": principal["username"],
                    "iam_user": principal.get("iam_user") or principal["username"],
                    "max_keys": MAX_ACCESS_KEYS,
                    "keys": public_keys(principal),
                },
            )
        if path == "/api/counts":
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            info = self._caller()
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(403, {"error": "account is not in this tenancy"})
            if region not in ACCOUNTS.regions_of(target):
                return self._json(403, {"error": "region is not enabled"})
            counts = {
                service: len(browse(service, target["account_id"], region))
                for service in console.CATALOGUE
            }
            return self._json(
                200,
                {"account": target["account_id"], "region": region, "counts": counts},
            )
        if path == "/api/s3/objects":
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            bucket = (params.get("bucket") or [""])[0].strip()
            prefix = (params.get("prefix") or [""])[0]
            info = self._caller()
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(403, {"error": "account is not in this tenancy"})
            if region not in ACCOUNTS.regions_of(target):
                return self._json(403, {"error": "region is not enabled"})
            if not bucket:
                return self._json(400, {"error": "bucket is required"})
            query = "/" + quote(bucket) + "?list-type=2"
            if prefix:
                query += "&prefix=" + quote(prefix)
            status, body = signed_s3(account, region, "GET", query)
            if status != 200:
                return self._json(
                    status if status >= 400 else 502, {"error": body[:200]}
                )
            objects = [
                {
                    "key": xml_value(block, "Key"),
                    "size": xml_value(block, "Size"),
                    "modified": xml_value(block, "LastModified"),
                    "storage": xml_value(block, "StorageClass"),
                }
                for block in re.findall(r"<Contents>(.*?)</Contents>", body, re.S)
            ]
            return self._json(
                200,
                {
                    "account": target["account_id"],
                    "region": region,
                    "bucket": bucket,
                    "prefix": prefix,
                    "objects": objects,
                },
            )
        if path == "/api/browse":
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0].strip()
            service = (params.get("service") or ["iam"])[0]
            info = self._caller()
            if service not in BROWSE_SERVICES:
                return self._json(400, {"error": "unknown service"})
            if not account:
                return self._json(400, {"error": "account is required"})
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            every = region.lower() in {"all", "*", "any"}
            regions = served_regions(target)
            if not every and region not in ACCOUNTS.regions_of(target):
                return self._json(
                    403, {"error": f"region {region} is not enabled for this account"}
                )
            resources = (
                browse_all(service, account, regions)
                if every
                else browse(service, account, region)
            )
            return self._json(
                200,
                {
                    "account": target["account_id"],
                    "region": "all" if every else region,
                    "regions": regions,
                    "service": service,
                    "identity": identity(account, region if not every else regions[0]),
                    "resources": resources,
                },
            )
        if path == "/api/settings":
            return self._json(
                200,
                {
                    "signup_enabled": bool(SETTINGS.get("signup_enabled", True)),
                    "instance_regions": list(ENABLED_REGIONS),
                },
            )
        if path == "/api/audit":
            info = self._caller()
            if not AUDIT_ENABLED:
                return self._json(404, {"error": "audit trail is disabled"})
            if not self._platform(info):
                return self._json(
                    403, {"error": "only a global admin can read the audit trail"}
                )
            params = parse_qs(urlsplit(self.path).query)
            try:
                limit = min(int((params.get("limit") or ["100"])[0]), 500)
            except ValueError:
                limit = 100
            return self._json(200, AUDIT.recent(limit))
        if path == "/api/meta":
            info = self._caller()
            platform = self._platform(info)
            operator = next(
                (a for a in ACCOUNTS.accounts.values() if a.get("global_admin")), {}
            )
            # Token clients have no session; present them as the operator.
            display = info or {
                "user": "token",
                "role": "platform-admin",
                "account": operator.get("account_id", ""),
                "alias": "token",
            }
            health = health_snapshot()
            version = next(
                (node.get("version") for node in health.get("nodes", {}).values()
                 if node.get("version")),
                "",
            )
            current = ACCOUNTS.by_ref(info.get("account", "")) if info else None
            enabled = list(ACCOUNTS.regions_of(current)) if current else []
            if not enabled:
                enabled = [DEFAULT_REGION]
            node_regions = sorted(
                {node.get("region") for node in NODES if node.get("region")}
            )
            visible = [
                account
                for account in ACCOUNTS.accounts.values()
                if platform or account["account_id"] == info.get("account")
            ]
            return self._json(
                200,
                {
                    "product": "MiniStack",
                    "api_version": API_VERSION,
                    "mode": MODE,
                    "auth": AUTH_MODE,
                    "login": login_label(info),
                    "recent_limit": RECENT_LIMIT,
                    "audit_enabled": AUDIT_ENABLED,
                    "version": version or "unknown",
                    "me": {
                        key: display.get(key)
                        for key in ("user", "account", "alias", "role")
                    },
                    "accounts": [
                        {
                            "account_id": account["account_id"],
                            "alias": account["alias"],
                            "users": len(account["users"]),
                            "regions": ACCOUNTS.regions_of(account),
                            "global_admin": bool(account.get("global_admin")),
                            "default_admin": bool(account.get("default_admin")),
                            "disabled": bool(account.get("disabled")),
                        }
                        for account in visible
                    ],
                    # Accounts are one global tenancy per identity: the same
                    # account ID works in every region, now and in a future
                    # multi-region cluster. Regions are a data axis only.
                    "accounts_scope": "global",
                    # Selectable regions are the ones this account enabled.
                    "regions": enabled,
                    "all_regions": list(ENABLED_REGIONS),
                    "instance_regions": list(ENABLED_REGIONS),
                    "node_regions": node_regions,
                    "active_regions": sorted(set(enabled) & set(node_regions)),
                    "platform_admin": platform,
                    "signup_enabled": bool(SETTINGS.get("signup_enabled", True)),
                    "default_admin": bool(current and current.get("default_admin")),
                    "other_global_admins": sum(
                        1
                        for account in ACCOUNTS.accounts.values()
                        if account.get("global_admin")
                        and not account.get("disabled")
                        and account["account_id"]
                        != (current or {}).get("account_id")
                    ),
                    "total_accounts": len(ACCOUNTS.accounts),
                    "global_admins": sum(
                        1
                        for account in ACCOUNTS.accounts.values()
                        if account.get("global_admin")
                    ),
                    "gateway": GATEWAY_URL,
                    "console": CONSOLE_URL,
                    "uptime_seconds": int(time.time() - STARTED_AT),
                    "checked_at": health.get("checked_at", ""),
                },
            )
        if path == "/api/actions":
            return self._json(
                200,
                {
                    "services": console.public_catalogue(),
                    "groups": [
                        {"label": label, "services": sorted(members)}
                        for label, members in SERVICE_GROUPS
                    ],
                },
            )
        if path == "/api/users":
            info = self._caller()
            return self._json(
                200,
                [
                    {
                        "account_id": account["account_id"],
                        "alias": account["alias"],
                        "name": account.get("name") or "",
                        "regions": ACCOUNTS.regions_of(account),
                        "global_admin": bool(account.get("global_admin")),
                        "default_admin": bool(account.get("default_admin")),
                        "disabled": bool(account.get("disabled")),
                        "users": [
                            {
                                "username": user["username"],
                                "role": user.get("role"),
                                "subject_bound": bool(user.get("subject")),
                                "access_key_id": user.get("access_key_id"),
                            }
                            for user in account["users"].values()
                        ],
                    }
                    for account in ACCOUNTS.accounts.values()
                    if self._can_touch(info, account["account_id"])
                ],
            )
        if path == "/api/nodes":
            agents = (
                {row["node"]: row for row in agent_status()}
                if MODE != "central"
                else {}
            )
            return self._json(
                200,
                [
                    dict(
                        node,
                        health=health_snapshot()["nodes"].get(node["name"], {}),
                        agent=agents.get(node["name"], {}),
                    )
                    for node in NODES
                ],
            )
        if path == "/api/services":
            return self._json(200, health_snapshot().get("services", {}))
        if path == "/api/buckets":
            return self._json(200, current_buckets())
        if path == "/api/s3":
            payload = {"mode": MODE, "buckets": current_buckets()}
            if MODE == "central":
                payload["nodes"] = REGISTRY.node_snapshot()
            else:
                payload["mesh"] = agent_state()
                payload["agents"] = agent_status()
            return self._json(200, payload)
        if path in ("/classic", "/classic/", "/index.html"):
            return self._page(self._dashboard())
        if path in ("/classic/services", "/classic/services/"):
            return self._page(self._services_page())
        if path in ("/classic/s3", "/classic/s3/"):
            return self._page(self._s3_page())
        if path in ("/classic/users", "/classic/users/", "/users", "/users/"):
            return self._page(self._users_page())
        if path in ("/classic/resources", "/classic/resources/"):
            return self._page(self._resources_page())
        if path in ("/services", "/services/"):
            return self._redirect("/resources")
        if path in ("/s3", "/s3/"):
            return self._redirect("/resources/s3")
        self._json(404, {"error": "not found"})

    def _route_post(self):
        path = urlsplit(self.path).path
        if path == "/login":
            return self._login()
        if path == "/signup":
            return self._signup()
        if path == "/forgot":
            return self._forgot()
        if path == "/reset":
            return self._reset_submit()
        if path.startswith("/api"):
            path = self._api_path(path)
        if path == "/api/nodes/register":
            return self._register_node()
        if path == "/api/nodes/heartbeat":
            return self._heartbeat()
        if not self._require_admin():
            return
        if path == "/api/credentials":
            payload = self._body()
            info = session_info(self._session_token()) or {}
            account_obj = ACCOUNTS.by_ref(info.get("account", ""))
            principal = ((account_obj or {}).get("users") or {}).get(
                info.get("user", "")
            )
            if account_obj is None or principal is None:
                return self._json(
                    400, {"error": "sign in as an account principal first"}
                )
            action = str(payload.get("action", "rotate")).strip().lower()
            key: dict | None = None
            if action == "delete":
                key_id = str(payload.get("access_key_id", "")).strip()
                if not key_id:
                    return self._json(400, {"error": "access_key_id is required"})
                problem = delete_access_key(
                    account_obj, principal, key_id
                )
                audited = "credentials.deleted"
            elif action == "create":
                name = str(payload.get("name", "")).strip()
                if not re.fullmatch(r"[A-Za-z0-9._ -]{1,32}", name):
                    return self._json(
                        400,
                        {
                            "error": "a key name is required: 1-32 letters, "
                            "digits, dot, dash, underscore or space"
                        },
                    )
                key, problem = create_access_key(account_obj, principal, name)
                audited = "credentials.created"
            elif action == "rotate":
                key, problem = rotate_credentials(
                    account_obj["account_id"], principal["username"]
                )
                audited = "credentials.rotated"
            else:
                return self._json(400, {"error": f"unknown action: {action}"})
            if problem:
                return self._json(502, {"error": problem})
            AUDIT.record(
                info.get("user", "token"),
                audited,
                account_obj["account_id"],
                {
                    "user": principal["username"],
                    "key": (key or {}).get("access_key_id")
                    or payload.get("access_key_id"),
                },
            )
            return self._json(
                200,
                {
                    "account": account_obj["account_id"],
                    "user": principal["username"],
                    "max_keys": MAX_ACCESS_KEYS,
                    "keys": public_keys(principal),
                    # The secret is only ever handed back when a key is created,
                    # like the AWS console's "download .csv" step.
                    "key": key,
                    "aws_access_key_id": (key or {}).get("access_key_id"),
                    "aws_secret_access_key": (key or {}).get("secret_access_key"),
                    "region": DEFAULT_REGION,
                    "regions": ACCOUNTS.regions_of(account_obj),
                },
            )
        if path == "/api/exec":
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            service = str(payload.get("service") or "").strip()
            operation = str(payload.get("operation") or "").strip()
            params = payload.get("params") or {}
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            if region not in ACCOUNTS.regions_of(target):
                return self._json(
                    403, {"error": f"region {region} is not enabled for this account"}
                )
            if not isinstance(params, dict):
                return self._json(400, {"error": "params must be an object"})
            result = console.run_action(
                service, operation, params, account, region, aws_call, signed_rest
            )
            if result.get("ok"):
                created = owner_name(params)
                if created:
                    OWNERS.record(
                        account, region, service, created, info.get("user") or "token"
                    )
            return self._json(
                200 if result.get("ok") else 400,
                dict(
                    result,
                    account=account,
                    region=region,
                    service=service,
                    operation=operation,
                ),
            )
        if path == "/api/accounts":
            payload = self._body()
            info = self._caller()
            if not self._platform(info):
                return self._json(
                    403,
                    {"error": "only the platform administrator can provision accounts"},
                )
            username = str(payload.get("username", "")).strip()
            email = str(payload.get("email", "")).strip()
            password = str(payload.get("password", ""))
            display_name = str(payload.get("name", "")).strip()
            if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
                return self._json(
                    400,
                    {
                        "error": "username must be 3-32 characters: letters, "
                        "digits, dot, dash or underscore"
                    },
                )
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return self._json(400, {"error": "that email address does not look right"})
            if len(password) < 8:
                return self._json(
                    400, {"error": "password must be at least 8 characters"}
                )
            if USERS.exists(username):
                return self._json(400, {"error": "that username is already registered"})
            account, principal = ACCOUNTS.create("", username)
            if display_name:
                ACCOUNTS.set_name(account["account_id"], display_name)
            USERS.create(
                username, email, password, account["account_id"],
                principal.get("role", "root"),
            )
            problem = issue_credentials(account, principal)
            if problem:
                return self._json(502, {"error": problem})
            AUDIT.record(
                info.get("user", "token"),
                "account.created",
                account["account_id"],
                {
                    "alias": account["alias"],
                    "via": "api",
                    "global_admin": bool(account.get("global_admin")),
                },
            )
            return self._json(
                201,
                {
                    "username": username,
                    "account_id": account["account_id"],
                    "alias": account["alias"],
                    "iam_user": principal.get("iam_user"),
                    "aws_access_key_id": principal.get("access_key_id"),
                    "aws_secret_access_key": principal.get("secret_access_key"),
                    "region": DEFAULT_REGION,
                    "regions": ACCOUNTS.regions_of(account),
                },
            )
        match = re.fullmatch(r"/api/accounts/([0-9]{12})/disabled", path)
        if match:
            payload = self._body()
            info = self._caller()
            if not self._platform(info):
                return self._json(
                    403, {"error": "only a global admin can disable accounts"}
                )
            account = ACCOUNTS.by_ref(match.group(1))
            if account is None:
                return self._json(404, {"error": "unknown account"})
            disabled = bool(payload.get("disabled", True))
            account, problem = ACCOUNTS.set_disabled(account["account_id"], disabled)
            if problem:
                return self._json(400, {"error": problem})
            if disabled:
                purge_sessions(account["account_id"])
            AUDIT.record(
                info.get("user", "token"),
                "account.disabled" if disabled else "account.enabled",
                account["account_id"],
                {"alias": account["alias"]},
            )
            return self._json(
                200,
                {"account": account["account_id"], "disabled": disabled},
            )
        match = re.fullmatch(r"/api/accounts/([0-9]{12})/admin", path)
        if match:
            payload = self._body()
            info = self._caller()
            if not self._platform(info):
                return self._json(
                    403, {"error": "only a global admin can change global admins"}
                )
            account = ACCOUNTS.by_ref(match.group(1))
            if account is None:
                return self._json(404, {"error": "unknown account"})
            enabled = bool(payload.get("enabled", True))
            if (
                not enabled
                and info
                and account["account_id"] == info.get("account")
            ):
                return self._json(
                    400, {"error": "you cannot remove your own global admin role"}
                )
            ACCOUNTS.set_global_admin(account["account_id"], enabled)
            AUDIT.record(
                info.get("user", "token"),
                "account.global_admin" if enabled else "account.global_admin_removed",
                account["account_id"],
                {"alias": account["alias"]},
            )
            return self._json(
                200,
                {
                    "account": account["account_id"],
                    "global_admin": enabled,
                },
            )
        if path == "/api/settings":
            payload = self._body()
            info = self._caller()
            if not self._platform(info):
                return self._json(
                    403, {"error": "only a global admin can change settings"}
                )
            if "signup_enabled" in payload:
                enabled = bool(payload.get("signup_enabled"))
                SETTINGS.set("signup_enabled", enabled)
                AUDIT.record(
                    info.get("user", "token"),
                    "settings.signup",
                    "signup_enabled",
                    {"enabled": enabled},
                )
            return self._json(
                200,
                {
                    "signup_enabled": bool(SETTINGS.get("signup_enabled", True)),
                    "instance_regions": list(ENABLED_REGIONS),
                },
            )
        if path == "/api/regions":
            payload = self._body()
            info = self._caller()
            target = ACCOUNTS.by_ref(
                str(payload.get("account") or info.get("account") or "").strip()
            )
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            region = str(payload.get("region", "")).strip()
            if region not in ENABLED_REGIONS:
                return self._json(400, {"error": "unknown region"})
            enabled = bool(payload.get("enabled", True))
            current = set(ACCOUNTS.regions_of(target))
            if enabled:
                current.add(region)
            elif region != DEFAULT_REGION:
                current.discard(region)
            account = ACCOUNTS.set_regions(target["account_id"], sorted(current))
            AUDIT.record(
                info.get("user", "token"),
                "region.enabled" if enabled else "region.disabled",
                target["account_id"],
                {"region": region},
            )
            return self._json(
                200,
                {
                    "account": account["account_id"],
                    "regions": ACCOUNTS.regions_of(account),
                },
            )
        if path == "/api/refresh":
            self._body()
            if MODE == "central":
                return self._json(200, refresh_registry())
            return self._json(
                200, {"mode": MODE, **agent_state(), "agents": agent_status()}
            )
        if path == "/api/reserve":
            payload = self._body()
            name = str(payload.get("name", "")).strip()
            region = str(payload.get("region", DEFAULT_REGION)).strip()
            if not name:
                return self._json(400, {"error": "name required"})
            ok, message, code = reserve_across(name, region)
            if not ok:
                return self._json(code, {"error": message})
            return self._json(201, {"bucket": name, "region": region, "mode": MODE})
        match = re.fullmatch(r"/api/nodes/([^/]+)/reset", path)
        if match:
            node = node_by_name(match.group(1))
            if not node:
                return self._json(404, {"error": "unknown node"})
            status, _ = node_request(node, "POST", "/_ministack/reset", timeout=30)
            if MODE == "central":
                with REGISTRY.lock:
                    for bucket in [
                        name
                        for name, entry in REGISTRY.buckets.items()
                        if entry["node"] == node["name"]
                    ]:
                        REGISTRY.buckets.pop(bucket, None)
                    cached = REGISTRY.nodes.get(node["name"], {})
                    if cached:
                        cached["buckets"] = []
                    REGISTRY.save()
            else:
                state = agent_state()
                for bucket, entry in state.get("buckets", {}).items():
                    if entry.get("node") == node["name"]:
                        release_across(bucket)
            return self._json(
                200 if status == 200 else 502, {"node": node["name"], "upstream": status}
            )
        self._json(404, {"error": "not found"})

    def _register_node(self) -> None:
        token = self.headers.get("X-Join-Token", "")
        status, message = NODE_REGISTRY.register(self._body(), token)
        return self._json(
            status, {"status": message, "nodes": NODE_REGISTRY.snapshot()}
        )

    def _heartbeat(self) -> None:
        token = self.headers.get("X-Join-Token", "")
        if not JOIN_TOKEN or not hmac.compare_digest(token, JOIN_TOKEN):
            return self._json(401, {"error": "invalid join token"})
        name = str(self._body().get("name", ""))
        if not NODE_REGISTRY.heartbeat(name):
            return self._json(404, {"error": "unknown node"})
        return self._json(200, {"node": name, "linked": True})

    def _route_delete(self):
        if not self._require_admin():
            return
        path = urlsplit(self.path).path
        if path.startswith("/api"):
            path = self._api_path(path)
        match = re.fullmatch(r"/api/accounts/([0-9]{12})", path)
        if match:
            info = self._caller()
            if not self._platform(info):
                return self._json(
                    403,
                    {"error": "only the platform administrator can delete accounts"},
                )
            account = ACCOUNTS.by_ref(match.group(1))
            if account is None:
                return self._json(404, {"error": "unknown account"})
            if info and account["account_id"] == info.get("account"):
                return self._json(
                    400, {"error": "you cannot delete the account you are signed in to"}
                )
            delete_account(account)
            AUDIT.record(
                info.get("user", "token"),
                "account.deleted",
                account["account_id"],
                {"alias": account["alias"]},
            )
            return self._json(
                200,
                {"deleted": account["account_id"], "alias": account["alias"]},
            )
        match = re.fullmatch(r"/api/buckets/([^/]+)", path)
        if match:
            REGISTRY.release(match.group(1))
            return self._json(200, {"removed": match.group(1)})
        self._json(404, {"error": "not found"})

    def send_response(self, code, message=None):
        self._status = code
        super().send_response(code, message)

    def _instrumented(self, route):
        span = TELEMETRY.start(self.command or "", self.path or "", self.headers)
        try:
            return route()
        finally:
            TELEMETRY.finish(span, getattr(self, "_status", 0))

    def do_GET(self):
        return self._instrumented(self._route_get)

    def do_POST(self):
        return self._instrumented(self._route_post)

    def do_DELETE(self):
        return self._instrumented(self._route_delete)

    # ---------------------------------------------------------------- pages

    def _layout(self, title: str, body: str) -> str:
        info = session_info(self._session_token()) or {}
        if info:
            identity = (
                '<details class="user">'
                f'<summary>{html.escape(info.get("user") or "user")}</summary>'
                '<div class="panel">'
                f'<p class="muted">{html.escape(info.get("role") or "-")} · '
                f'account <code>{html.escape(info.get("account") or "-")}</code> '
                f'({html.escape(info.get("alias") or "-")})</p>'
                '<a href="/users">Users</a>'
                '<a href="/logout">Sign out</a>'
                "</div></details>"
            )
        else:
            identity = ""
        services = health_snapshot().get("services", {})
        groups = grouped_services(services)
        if groups:
            menu = "".join(
                f"<h3>{html.escape(label)}</h3>"
                + "".join(
                    f'<a href="/services#{html.escape(name)}">{html.escape(name)}</a>'
                    for name in names
                )
                for label, names in groups
            )
            services_nav = (
                '<details class="menu"><summary>Services</summary>'
                f'<div class="panel">{menu}</div></details>'
            )
        else:
            services_nav = '<a href="/services">Services</a>'
        resources_nav = '<a href="/resources">Resources</a>'
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{PAGE_STYLE}</style></head>
<body>
<nav><a href="/">Overview</a>{services_nav}<a href="/s3">S3</a>
<a href="/users">Users</a>{resources_nav}<span style="flex:1"></span>{identity}</nav>
{body}
<p class="muted" style="margin-top:2rem">Control <a href="{html.escape(CONSOLE_URL)}">{html.escape(CONSOLE_URL)}</a>
· gateway <a href="{html.escape(GATEWAY_URL)}">{html.escape(GATEWAY_URL)}</a> · API {API_VERSION}</p>
</body></html>"""

    def _dashboard(self) -> str:
        health = health_snapshot()
        node_health = health.get("nodes", {})
        registry = current_buckets()
        nodes = "".join(
            "<tr>"
            f"<td>{html.escape(node['name'])}</td>"
            f"<td>{html.escape(node['region'])}</td>"
            f"<td>{html.escape(node.get('account_id', ''))}</td>"
            f"<td>{'<span class=up>UP</span>' if node_health.get(node['name'], {}).get('reachable') else '<span class=down>DOWN</span>'}</td>"
            f"<td>{html.escape(str(node_health.get(node['name'], {}).get('version', '-')))}</td>"
            f"<td>{html.escape(str(node_health.get(node['name'], {}).get('checked_at', '-')))}</td>"
            f"<td>{html.escape(str(node_health.get(node['name'], {}).get('joined', '-')))}</td>"
            "</tr>"
            for node in NODES
        )
        mesh_html = ""
        if MODE != "central":
            state = agent_state()
            agents = agent_status()
            agent_rows = "".join(
                "<tr>"
                f"<td>{html.escape(row['node'])}</td>"
                f"<td>{'<span class=up>UP</span>' if row['reachable'] else '<span class=down>DOWN</span>'}</td>"
                f"<td>{html.escape(str(row.get('events', '-')))}</td>"
                f"<td>{html.escape(str(row.get('peer_count', '-')))}</td>"
                "</tr>"
                for row in agents
            )
            conflicts = state.get("conflicts", [])
            conflict_text = (
                '<span class=down>' + html.escape(", ".join(conflicts)) + "</span>"
                if conflicts
                else '<span class=up>none</span>'
            )
            mesh_html = f"""<h2>Replication ({html.escape(MODE)})</h2>
<table><thead><tr><th>Agent</th><th>Health</th><th>Events</th><th>Peers</th></tr></thead>
<tbody>{agent_rows}</tbody></table>
<p class="muted">Chain heights: {html.escape(json.dumps(state.get('heights', {}), sort_keys=True))}
 · conflicts: {conflict_text}</p>"""
        info = session_info(self._session_token()) or {}
        account = info.get("account") or "unassigned"
        alias = info.get("alias") or "-"
        role = info.get("role") or "-"
        signed_in_as = info.get("user") or "-"
        regions = ", ".join(sorted(SEEN_REGIONS)) or "none seen yet"
        registered = len(registry)
        account_obj = ACCOUNTS.by_ref(account) if account else None
        principal = ((account_obj or {}).get("users") or {}).get(signed_in_as) or {}
        if principal.get("access_key_id"):
            key_id = principal["access_key_id"]
            creds = f"""
<h2>Credentials</h2>
<p class="muted">IAM user <code>{html.escape(principal.get('iam_user', ''))}</code> ·
access key <code>{html.escape(mask(key_id))}</code></p>
<details><summary>Show access key ID and secret</summary>
<p class="muted">Access key ID <code>{html.escape(key_id)}</code><br>
Secret <code>{html.escape(principal.get('secret_access_key', ''))}</code></p></details>
<p class="muted">Point any AWS client at
<a href="{html.escape(GATEWAY_URL)}">{html.escape(GATEWAY_URL)}</a>.
The account ID alone also works as a root access key (any secret).</p>
<form id="credrotate"><button>Rotate access key</button></form>"""
        else:
            creds = """
<h2>Credentials</h2>
<p class="muted">No IAM access key has been issued for this principal.</p>
<form id="credrotate"><button>Issue access key</button></form>"""
        region_options = "".join(
            f'<option value="{html.escape(region)}"'
            f'{" selected" if region == DEFAULT_REGION else ""}>'
            f"{html.escape(region)}</option>"
            for region in sorted(set(ENABLED_REGIONS) | SEEN_REGIONS)
        )
        body = f"""
<h1>Overview</h1>
<p class="muted">Account <code>{html.escape(account)}</code>
(<code>{html.escape(alias)}</code>) · {html.escape(role)} · regions seen:
{html.escape(regions)}</p>
<p class="muted">Gateway
<a href="{html.escape(GATEWAY_URL)}">{html.escape(GATEWAY_URL)}</a> ·
console <a href="{html.escape(CONSOLE_URL)}">{html.escape(CONSOLE_URL)}</a> ·
checked {html.escape(health.get('checked_at', '-'))}</p>
{creds}
<h2>Emulator</h2>
<table><thead><tr><th>Node</th><th>Home region</th><th>Account</th><th>Health</th>
<th>Version</th><th>Last checked</th><th>Joined</th></tr></thead>
<tbody>{nodes}</tbody></table>
{mesh_html}
<p class="muted">{registered} bucket name(s) registered.
<a href="/services">All services →</a></p>
<h2>Actions</h2>
<form id="reserve">
  <input name="name" placeholder="bucket-name" required>
  <select name="region">{region_options}</select>
  <button>Reserve bucket</button>
</form>
<form id="refresh"><button>Refresh registry from nodes</button></form>
<script>
const token = () => '';
document.getElementById('reserve').onsubmit = async (event) => {{
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  const response = await fetch('/api/reserve', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(data)}});
  alert(response.status + ' ' + await response.text());
  location.reload();
}};
document.getElementById('refresh').onsubmit = async (event) => {{
  event.preventDefault();
  const response = await fetch('/api/refresh', {{method: 'POST'}});
  alert(response.status + ' ' + await response.text());
  location.reload();
}};
document.getElementById('credrotate').onsubmit = async (event) => {{
  event.preventDefault();
  const response = await fetch('/api/credentials', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{action: 'rotate'}})}});
  alert(response.status + ' ' + await response.text());
  location.reload();
}};
</script>"""
        return self._layout("MiniStack federation", body)

    def _resources_page(self) -> str:
        params = parse_qs(urlsplit(self.path).query)
        info = session_info(self._session_token()) or {}
        account = (params.get("account") or [info.get("account") or ""])[0]
        if not account and ACCOUNTS.accounts:
            # Bearer-token sessions carry no account: fall back to the operator's.
            preferred = ACCOUNTS.by_ref(info.get("account", "")) if info else None
            if preferred is None:
                preferred = next(
                    (a for a in ACCOUNTS.accounts.values() if a.get("global_admin")),
                    None,
                )
            if preferred is None:
                preferred = sorted(
                    ACCOUNTS.accounts.values(), key=lambda entry: entry["alias"]
                )[0]
            account = preferred["account_id"]
        region = (params.get("region") or [DEFAULT_REGION])[0]
        service = (params.get("service") or ["iam"])[0]
        if service not in BROWSE_SERVICES:
            service = "iam"
        accounts = "".join(
            f'<option value="{html.escape(account_id)}"'
            f'{" selected" if account_id == account else ""}>'
            f'{html.escape(entry["alias"])} · {html.escape(account_id)}</option>'
            for account_id, entry in sorted(
                ACCOUNTS.accounts.items(), key=lambda item: item[1]["alias"]
            )
        ) or '<option value="">no accounts yet</option>'
        regions = "".join(
            f'<option value="{html.escape(choice)}"'
            f'{" selected" if choice == region else ""}>'
            f"{html.escape(choice)}</option>"
            for choice in sorted(set(ENABLED_REGIONS) | SEEN_REGIONS)
        )
        services = "".join(
            f'<option value="{html.escape(name)}"'
            f'{" selected" if name == service else ""}>'
            f"{html.escape(name)}</option>"
            for name in BROWSE_SERVICES
        )
        who = identity(account, region) if account else {"error": "no account selected"}
        rows = browse(service, account, region) if account else []
        if "error" in who:
            who_html = f'<p class="error">{html.escape(who["error"])}</p>'
        else:
            who_html = (
                f'<p class="muted">Signed as <code>{html.escape(who.get("arn", ""))}</code>'
                f' · account <code>{html.escape(who.get("account", ""))}</code>'
                f' · region <code>{html.escape(region)}</code></p>'
            )
        table = "".join(
            f'<tr><td class="muted">{html.escape(row["kind"])}</td>'
            f'<td><code>{html.escape(row["name"])}</code></td>'
            f'<td class="muted">{html.escape(", ".join(f"{k}={v}" for k, v in row["detail"].items() if v))}</td></tr>'
            for row in rows
        ) or (
            f'<tr><td colspan="3" class="muted">no {html.escape(service)} '
            "resources in this account and region</td></tr>"
        )
        body = f"""
<style>body {{ max-width: none; }}</style>
<h1>Resources</h1>
<p class="muted">Read straight from the emulator, one account at a time. The
account is chosen by the access key, so this reads every account without
holding any secret.</p>
<form method="get" action="/resources">
  <select name="account">{accounts}</select>
  <select name="region">{regions}</select>
  <select name="service">{services}</select>
  <button>Browse</button>
</form>
{who_html}
<table><thead><tr><th>Kind</th><th>Name</th><th>Detail</th></tr></thead>
<tbody>{table}</tbody></table>
<p class="muted">{len(rows)} resource(s) in <code>{html.escape(service)}</code>.
<a href="/s3">Bucket registry</a> · <a href="/users">Accounts</a></p>
"""
        return self._layout("Resources", body)

    def _services_page(self) -> str:
        health = health_snapshot()
        nodes = health.get("nodes", {})
        node_health = nodes.get(NODE_NAME, {})
        version = html.escape(str(node_health.get("version", "-")))
        services = health.get("services", {})
        sections = []
        for label, names in grouped_services(services):
            rows = "".join(
                f'<tr id="{html.escape(name)}"><td><code>{html.escape(name)}</code></td>'
                f"<td>{state_badge((services.get(name) or {}).get(NODE_NAME))}</td>"
                f'<td class="muted">{version}</td></tr>'
                for name in names
            )
            anchor = html.escape(label.lower().replace(" ", "-"))
            sections.append(
                f'<h2 id="{anchor}">{html.escape(label)} '
                f'<span class="muted">({len(names)})</span></h2>'
                "<table><thead><tr><th>Service</th><th>State</th>"
                f"<th>Emulator</th></tr></thead><tbody>{rows}</tbody></table>"
            )
        body = f"""
<h1>Services</h1>
<p class="muted">{len(services)} services reported by <code>{html.escape(NODE_NAME)}</code>,
grouped like the upstream catalogue; checked {html.escape(health.get('checked_at', '-'))}.</p>
{''.join(sections)}
"""
        return self._layout("Services", body)

    def _users_page(self) -> str:
        rows = []
        for account in sorted(ACCOUNTS.accounts.values(), key=lambda a: a["alias"]):
            for name, user in sorted(account["users"].items()):
                rows.append(
                    "<tr>"
                    f"<td><code>{html.escape(account['account_id'])}</code></td>"
                    f"<td>{html.escape(account['alias'])}</td>"
                    f"<td>{html.escape(name)}</td>"
                    f"<td>{html.escape(str(user.get('role', '-')))}</td>"
                    f"<td>{'bound' if user.get('subject') else '—'}</td>"
                    f"<td><code>{html.escape(user.get('access_key_id') or '—')}</code></td>"
                    f"<td>{html.escape(str(user.get('credentials_issued') or '—'))}</td>"
                    "</tr>"
                )
        body = f"""
<h1>Users</h1>
<p class="muted">An account is the tenancy boundary; a principal is an identity
inside one. The account ID lives here as data — it is never configuration.</p>
<table><thead><tr><th>Account ID</th><th>Alias</th><th>Principal</th><th>Role</th>
<th>Keycloak</th><th>Access key</th><th>Issued</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="7" class="muted">no accounts yet</td></tr>'}</tbody></table>
<p class="muted">Secrets are not shown here; the signed-in principal sees its own
on the <a href="/">overview</a>.</p>
"""
        return self._layout("Users", body)

    def _s3_page(self) -> str:
        buckets = current_buckets()
        health = health_snapshot()
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{html.escape(entry['region'])}</td>"
            f"<td>{html.escape(entry['node'])}</td>"
            f"<td>{html.escape(entry.get('account_id', ''))}</td>"
            f"<td>{html.escape(entry.get('last_seen', '-'))}</td>"
            f"<td>{'<span class=down>stale</span>' if entry.get('stale') else '<span class=up>live</span>'}</td>"
            "</tr>"
            for name, entry in sorted(buckets.items())
        ) or '<tr><td colspan="6" class="muted">no buckets registered</td></tr>'
        if MODE == "central":
            node_cache = REGISTRY.node_snapshot()
            inventory = "".join(
                "<tr>"
                f"<td>{html.escape(node['name'])}</td>"
                f"<td>{'<span class=up>UP</span>' if health.get('nodes', {}).get(node['name'], {}).get('reachable') else '<span class=down>DOWN</span>'}</td>"
                f"<td>{html.escape(str(node_cache.get(node['name'], {}).get('last_seen', '-')))}</td>"
                f"<td>{len(node_cache.get(node['name'], {}).get('buckets', []))}</td>"
                f"<td>{html.escape(', '.join(node_cache.get(node['name'], {}).get('buckets', [])) or '-')}</td>"
                "</tr>"
                for node in NODES
            )
            inventory_title = "Per-node cached inventory"
            inventory_header = (
                "<th>Node</th><th>Health</th><th>Inventory from</th>"
                "<th>Buckets</th><th>Names</th>"
            )
            inventory_note = (
                "An unreachable node keeps its last successful inventory; "
                "those rows are marked stale instead of disappearing."
            )
        else:
            state = agent_state()
            inventory = "".join(
                "<tr>"
                f"<td>{html.escape(row['node'])}</td>"
                f"<td>{'<span class=up>UP</span>' if row['reachable'] else '<span class=down>DOWN</span>'}</td>"
                f"<td>{html.escape(str(row.get('events', '-')))}</td>"
                f"<td>{html.escape(str(row.get('peer_count', '-')))}</td>"
                "</tr>"
                for row in agent_status()
            )
            inventory_title = f"Replication agents ({MODE})"
            inventory_header = "<th>Agent</th><th>Health</th><th>Events</th><th>Peers</th>"
            inventory_note = (
                "Chain heights: "
                + json.dumps(state.get("heights", {}), sort_keys=True)
                + " · conflicts: "
                + (", ".join(state.get("conflicts", [])) or "none")
            )
        body = f"""
<h1>S3</h1>
<p class="muted">Mode <code>{html.escape(MODE)}</code>. Bucket names are
reserved across the federation. The home region is where the bucket was
created and stays authoritative even while that node is offline.</p>
<h2>Registered buckets</h2>
<table><thead><tr><th>Bucket</th><th>Home region</th><th>Node</th>
<th>Account</th><th>Last seen</th><th>State</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>{html.escape(inventory_title)}</h2>
<table><thead><tr>{inventory_header}</tr></thead><tbody>{inventory}</tbody></table>
<p class="muted">{html.escape(inventory_note)}</p>
<form id="refresh"><button>Refresh</button></form>
<script>
document.getElementById('refresh').onsubmit = async (event) => {{
  event.preventDefault();
  const response = await fetch('/api/refresh', {{method: 'POST'}});
  alert(response.status + ' ' + await response.text());
  location.reload();
}};
</script>"""
        return self._layout("S3", body)


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
    control = ThreadingHTTPServer(("0.0.0.0", CONTROL_PORT), ControlHandler)
    gateway = ThreadingHTTPServer(("0.0.0.0", GATEWAY_PORT), GatewayHandler)
    threading.Thread(target=gateway.serve_forever, daemon=True).start()

    def poller() -> None:
        while True:
            try:
                NODE_REGISTRY.expire()
                poll_health()
                if MODE == "central":
                    refresh_registry()
            except Exception as exc:  # keep the poller alive
                print(f"poller error: {exc}", flush=True)
            time.sleep(POLL_SECONDS)

    threading.Thread(target=poller, daemon=True).start()
    print(
        f"control on :{CONTROL_PORT}, gateway on :{GATEWAY_PORT}, "
        f"{len(NODES)} nodes, auth {'on' if ADMIN_TOKEN else 'off'}",
        flush=True,
    )
    control.serve_forever()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--test-mail":
        # Run inside the container, where the real settings and network live:
        #   podman exec core-ministack-control python /app/app.py --test-mail you@example.com
        problem = send_mail(
            sys.argv[2],
            "MiniStack control: test message",
            "This message proves the control can reach its SMTP relay.\n",
        )
        print("sent" if not problem else problem, flush=True)
        sys.exit(0 if not problem else 1)
    main()
