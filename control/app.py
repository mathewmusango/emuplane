#!/usr/bin/env python3
"""Control plane for AWS-compatible emulators.

One process, two listeners:

  :8080  admin API and HTML dashboard (published as 127.0.0.1:4570)
  :8081  the gateway, the single entrypoint for every AWS client
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
import re
import secrets
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import console  # noqa: E402  (local module: action catalogue)
import buckets  # noqa: E402  (local module: the console's bucket create)
import signed  # noqa: E402  (local module: the root-signed calls)
import s3extra  # noqa: E402  (local module: S3 Tables / S3 Files listings)
import accesspoints  # noqa: E402  (local module: S3 Control access points)
import mail  # noqa: E402  (local module: the one outbound message)
from dynamo import DynamoError  # noqa: E402
from backends import profile  # noqa: E402
from store import Store, StoreNotProvisioned  # noqa: E402

# No database file: every control-plane document lives in the emulator's
# DynamoDB (control/store.py) — the service this plane manages. Layer 0 creates
# the tables before the API serves.
EP_PORT = int(os.environ.get("EP_PORT", "8080"))
GATEWAY_PORT = int(os.environ.get("EP_GATEWAY_PORT", "8081"))
# The API bearer token is *not* an env setting: a credential in `.env` is a
# credential in every backup and paste. It lives in the settings store as a
# SHA-256 hash (control/token.py mints it and prints the raw value once), so only
# a digest ever reaches the database.
TOKEN_KEY = "admin_token"


def stored_token_hash() -> str:
    """The digest in the settings store, read fresh so a rotation takes effect.

    `control/token.py` rotates the token from another process, so this cannot be
    a boot-time copy held in memory.
    """
    try:
        raw = DB.get("settings", TOKEN_KEY)
    except (OSError, DynamoError):
        return ""
    if not raw:
        return ""
    try:
        return str(json.loads(raw).get("hash") or "")
    except ValueError:
        return ""


def bearer_ok(presented: str) -> bool:
    """True when the presented bearer token matches the stored digest."""
    if not presented:
        return False
    expected = stored_token_hash()
    if not expected:
        return False
    return secrets.compare_digest(
        hashlib.sha256(presented.encode()).hexdigest(), expected
    )
# One emulator, many regions and accounts: these are data, not containers.
# MiniStack's own fallback region for unsigned callers. There is no configured
# region list: every region exists, and the one a request uses comes from its
# SigV4 scope. These are just the regions seen so far (for the UI).
DEFAULT_REGION = "us-east-1"
SEEN_REGIONS: set[str] = set()
SEEN_LOCK = threading.Lock()

# One file in one PutObject. The emulator keeps objects in memory, so a cap is a
# lab decision, not an S3 limit; the page says the same number.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_CONTENT_TYPE_RE = re.compile(r"^[-\w.+/]+\s*(;.*)?$")


def safe_content_type(value: str) -> str:
    """The file's type as S3 should store it, or a neutral one.

    A header is not a place to trust: a CR/LF would split it, and anything odd is
    dropped rather than forwarded to the emulator.
    """
    kind = (value or "").split("\r")[0].split("\n")[0].strip()[:128]
    return kind if kind and _CONTENT_TYPE_RE.match(kind) else "application/octet-stream"
# The endpoint this control fronts. Nothing here names a particular emulator:
# MiniStack, Floci or anything else that answers the same APIs is equally valid,
# and the label in the console comes from the URL unless EP_BACKEND_NAME says it.
NODE_URL = os.environ.get("EP_BACKEND_URL", "").strip().rstrip("/")
BACKEND = profile(os.environ.get("EP_BACKEND"))
NODE_NAME = (
    os.environ.get("EP_BACKEND_NAME", "").strip()
    or BACKEND.title
    or (urlsplit(NODE_URL).hostname or "").strip()
    or "node"
)
POLL_SECONDS = int(os.environ.get("EP_POLL_SECONDS", "10"))

API_VERSION = "v1"
STARTED_AT = time.time()
# Canonical public addresses shown in the UI. A deployment publishes them (a
# reverse proxy, a published port); the console displays whatever is set here.
GATEWAY_URL = os.environ.get("EP_GATEWAY_URL", "").strip().rstrip("/")
CONSOLE_URL = os.environ.get("EP_CONSOLE_URL", "").strip().rstrip("/")

REQUIRED_SETTINGS = {
    # The node name falls back to the URL's host; only the endpoint the node is
    # reached at, and the two public addresses, have to be known.
    "EP_BACKEND_URL": NODE_URL,
    "EP_GATEWAY_URL": GATEWAY_URL,
    "EP_CONSOLE_URL": CONSOLE_URL,
}
MISSING_SETTINGS = [name for name, value in REQUIRED_SETTINGS.items() if not value]
if MISSING_SETTINGS:
    sys.exit(
        "control: missing required .env setting(s): " + ", ".join(MISSING_SETTINGS)
    )
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

# No bootstrap administrator is seeded: a fresh control has **no accounts**, just
# sign-up, the way AWS leaves a new account to the person creating it. The first
# sign-up becomes the platform owner (global + default admin).

# The React console. Built by `npm run build` in `web/` and mounted here; the
# server-rendered pages stay available under /classic.
STATIC_DIR = os.environ.get("MC_STATIC_DIR", "/app/static")
PUBLIC_DIR = os.environ.get("MC_PUBLIC_DIR", "/app/public")
SPA_ROUTES = {"/", "/resources",
              "/settings", "/about"}
# Served to anyone, signed in or not: the sign-in screens themselves. The
# endpoint behind them (`POST /api/auth/login`) mints the session, so this route
# *is* the login page — there is no server-rendered form any more.
PUBLIC_SPA_ROUTES = {"/login", "/signin"}
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

# The icon set `scripts/favicons.sh` writes into `web/public`. They sit at fixed
# names rather than hashed ones, so they must be servable from the root and must
# not be cached as immutable — a new logo has to reach a returning visitor.
ICON_ASSETS = {
    "/favicon.ico",
    "/favicon-32.png",
    "/favicon-192.png",
    "/favicon-512.png",
    "/apple-touch-icon.png",
}

# The same icon declaration in both surfaces — the console's `index.html` and the
# server-rendered auth pages. SVG first (crisp at every size), then the PNG set
# `scripts/favicons.sh` writes, with the `.ico` left to the browser's fallback.
ICON_LINKS = (
    '<link rel="icon" type="image/png" sizes="512x512" href="/favicon-512.png">'
    '<link rel="icon" type="image/png" sizes="192x192" href="/favicon-192.png">'
    '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">'
    '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">'
    '<meta name="theme-color" content="#0f141a">'
)
SESSION_SECONDS = int(os.environ.get("EP_SESSION_SECONDS", "28800"))
# AWS allows two access keys per IAM user; the console holds the same line per
# account so a rotation can overlap (create the new key, then delete the old).
MAX_ACCESS_KEYS = 2
RECENT_LIMIT = int(os.environ.get("EP_RECENT_LIMIT", "5") or 5)

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


# One emulator: it comes from the environment, not from a database or discovery.
NODES: list[dict] = [
    {
        "name": NODE_NAME,
        "region": DEFAULT_REGION,
        "endpoint": NODE_URL,
        "static": True,
    }
]


class Accounts:
    """Accounts are the tenancy boundary.

    Stored as one row per account in the `accounts` store, each carrying this
    shape:

        {"account_id": "111111111111", "alias": "mathewmusango",
         "root": "mathewmusango", "created_at": "...",
         "users": {"mathewmusango": {"username": ..., "role": "root"}}}

    A principal holds its IAM keys in `access_keys` (name, id, secret, created).
    The flat `access_key_id` / `secret_access_key` / `credentials_issued` fields
    mirror the first key: the classic pages and the provision response still read
    them, so they stay as a pointer, never a second copy.

    The pre-2026-11-11 v1 shape (`{username: account_id}`) is converted during
    the one-time SQLite import.
    """

    def __init__(self, db: Store) -> None:
        self.db = db
        self.lock = threading.Lock()
        self.accounts: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        self.accounts = self.db.payloads("accounts")
        if self.accounts:
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
                # Tenancy is AWS-shaped: no account is a global administrator.
                # The flags stay in the document for shape stability, and an old
                # one that granted cross-tenant access is cleared here.
                if account.get("global_admin") or account.get("default_admin"):
                    account["global_admin"] = False
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
            if changed:
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
            # Regions added because a request used them (see enable_region), so
            # the console can say why they are on.
            "auto_regions": [],
            "global_admin": False,
            "default_admin": False,
            "disabled": False,
            "users": {},
        }

    def _save(self) -> None:
        """Persist the accounts this process holds — but never delete by omission.

        This used to replace the whole table, which made an in-memory copy the
        authority: a second writer (a CLI, the bootstrap job, another process)
        could be clobbered back, and a row someone else had just created was
        deleted simply because this process had not loaded it. Writes are
        per-row now; removal is explicit in `delete()`.
        """
        for account_id, account in self.accounts.items():
            self.db.put("accounts", account_id, json.dumps(account))

    def _put(self, account: dict) -> None:
        """Write one account row. Callers change one account, so they save one."""
        self.db.put("accounts", account["account_id"], json.dumps(account))

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
        """Account by ID or alias (case-insensitive on the alias).

        A miss re-reads the table once before answering: the control is the only
        writer in normal operation, but an operator tool (or a probe) can create
        an account out of process, and "no such account" must not be a lie about
        a row that exists.
        """
        ref = (ref or "").strip()
        if not ref:
            return None
        found = self._by_ref(ref)
        if found is not None:
            return found
        self._load()
        return self._by_ref(ref)

    def _by_ref(self, ref: str) -> dict | None:
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

    def create(self, username: str) -> tuple[dict, dict]:
        account_id = self._new_id()
        account = self._blank(account_id, self.unique_alias(username))
        # No account is a global administrator: root owns its own tenancy.
        account["global_admin"] = False
        account["default_admin"] = False
        user = {"username": username, "role": "root"}
        account["users"][username] = user
        self.accounts[account_id] = account
        self._put(account)
        return account, user

    def add_principal(
        self, account_id: str, username: str, role: str = "iam"
    ) -> dict | None:
        """Add an IAM principal to an existing account, or None if it is taken."""
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None or username in account["users"]:
                return None
            principal = {"username": username, "role": role}
            account["users"][username] = principal
            self._put(account)
            return principal

    def set_name(self, account_id: str, name: str) -> dict | None:
        """Record the human-readable account name shown in the console."""
        account = self.accounts.get(account_id)
        if account is None:
            return None
        account["name"] = name
        self._put(account)
        return account

    def ensure_local(self, username: str) -> tuple[dict, dict]:
        """The `.env` admin signs in as the root of its own account."""
        with self.lock:
            for account in self.accounts.values():
                user = account["users"].get(username)
                if user is not None:
                    return account, user
            account = self._blank(self._new_id(), self.unique_alias(username))
            account["global_admin"] = False
            user = {"username": username, "role": "root"}
            account["users"][username] = user
            self.accounts[account["account_id"]] = account
            self._put(account)
            return account, user

    @staticmethod
    def _mirror_primary(user: dict) -> None:
        """Point the legacy flat fields at the principal's first key."""
        keys = user.get("access_keys") or []
        primary = keys[0] if keys else {}
        user["access_key_id"] = primary.get("access_key_id")
        user["secret_access_key"] = primary.get("secret_access_key")
        user["credentials_issued"] = primary.get("created_at")

    def account_for_key(self, key_id: str) -> str:
        """Account that owns an IAM key, from the local store."""
        if not key_id:
            return ""
        for account in self.accounts.values():
            for user in (account.get("users") or {}).values():
                for key in user.get("access_keys") or []:
                    if key.get("access_key_id") == key_id:
                        return account["account_id"]
        return ""

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
            self._put(account)
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
            self._put(account)
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
            # A region that is no longer enabled is no longer "added on first
            # use" either; keep the note only for regions still on.
            if account.get("auto_regions"):
                account["auto_regions"] = [
                    name for name in account["auto_regions"] if name in account["regions"]
                ]
            self._put(account)
            return account

    def enable_region(self, account_id: str, region: str) -> dict | None:
        """Enable one advertised region because a request needed it.

        The gateway calls this when a client signs for a region the account has
        not enabled but is a region MiniStack serves. The region is
        recorded in `auto_regions` so the console can say it was enabled on
        first use rather than by hand.
        """
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None or region in self.regions_of(account):
                return account
            account["regions"] = sorted({DEFAULT_REGION, *account["regions"], region})
            auto = sorted({*(account.get("auto_regions") or []), region})
            account["auto_regions"] = auto
            self._put(account)
            return account

    def set_disabled(self, account_id: str, disabled: bool) -> tuple[dict | None, str]:
        """Disable/enable an account, never the last enabled global admin."""
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None:
                return None, "unknown account"
            account["disabled"] = bool(disabled)
            self._put(account)
            return account, ""

    def delete(self, account_id: str) -> dict | None:
        with self.lock:
            account = self.accounts.pop(account_id, None)
            if account is None:
                return None
            self.db.delete("accounts", account_id)
            return account


class UserStore:
    """Local credentials: username -> password hash -> account.

    One document per user in the emulator's DynamoDB, keyed by the lower-cased
    username (the old table used `COLLATE NOCASE`). This store answers only "is
    this password right, and which account does the username belong to".
    """

    ROUNDS = 260_000

    def __init__(self, db: Store) -> None:
        self.db = db
        self.lock = threading.Lock()
        self.users: dict[str, dict] = db.payloads("users")

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

    @staticmethod
    def _key(username: str) -> str:
        return (username or "").lower()

    def _save(self, username: str, record: dict) -> None:
        self.users[self._key(username)] = record
        self.db.put("users", self._key(username), json.dumps(record))

    def _reload(self) -> dict[str, dict]:
        """Read the whole table again.

        Credentials are written by more than one process: this server, and the
        host-side `password.py` that resets a locked-out principal. Serving a
        copy loaded at start-up would leave a reset invisible until a restart,
        so every read goes to the store. The table holds one row per principal,
        which makes this a scan of a handful of rows.
        """
        try:
            self.users = self.db.payloads("users")
        except (OSError, DynamoError) as exc:
            print(f"control: could not read users: {exc}", flush=True)
        return self.users

    def count(self) -> int:
        return len(self._reload())

    def get(self, username: str) -> dict | None:
        return self._reload().get(self._key(username))

    def exists(self, username: str) -> bool:
        return self._key(username) in self._reload()

    def find_by_email(self, email: str) -> dict | None:
        """The user record whose address matches, case-insensitively.

        Root sign-in asks for an email, but the store is keyed by username and
        the address is optional, so a user without one simply has no match.
        """
        wanted = (email or "").strip().lower()
        if not wanted:
            return None
        for user in self._reload().values():
            if (user.get("email") or "").strip().lower() == wanted:
                return user
        return None

    def create(
        self,
        username: str,
        email: str,
        password: str,
        account_id: str,
        role: str = "root",
    ) -> None:
        with self.lock:
            self._save(
                username,
                {
                    "username": username,
                    "email": email,
                    "password_hash": self._hash(password),
                    "account_id": account_id,
                    "role": role,
                    "created_at": now(),
                    "last_login": None,
                },
            )

    def verify(self, username: str, password: str) -> dict | None:
        user = self.get(username)
        if user is None or not self._matches(password, user["password_hash"]):
            return None
        with self.lock:
            user["last_login"] = now()
            self._save(username, user)
        return user

    def matches(self, username: str, password: str) -> bool:
        """Is this already the password on file? Unlike verify, no side effects."""
        user = self.get(username)
        return bool(user and self._matches(password, user.get("password_hash", "")))

    def delete_account(self, account_id: str) -> None:
        with self.lock:
            for key, user in list(self._reload().items()):
                if user.get("account_id") == account_id:
                    del self.users[key]
                    self.db.delete("users", key)

    def set_email(self, username: str, email: str) -> None:
        """Fill in a missing address; never overwrite one the user already has."""
        if not email:
            return
        with self.lock:
            user = self.get(username)
            if user is not None and not user.get("email"):
                user["email"] = email
                self._save(username, user)

    def update_email(self, username: str, email: str) -> None:
        """Set the address from the owner's own request."""
        with self.lock:
            user = self.get(username)
            if user is not None:
                user["email"] = email
                self._save(username, user)

    def set_password(self, username: str, password: str) -> None:
        with self.lock:
            user = self.get(username)
            if user is not None:
                user["password_hash"] = self._hash(password)
                self._save(username, user)


class Settings:
    """Small persisted control-plane settings (sign-up toggle, ...)."""

    def __init__(self, db: Store) -> None:
        self.db = db
        self.lock = threading.Lock()
        self.values: dict = db.payloads("settings")

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set(self, key: str, value) -> None:
        with self.lock:
            self.values[key] = value
            try:
                self.db.put("settings", key, json.dumps(value))
            except (OSError, DynamoError) as exc:
                print(f"control: could not persist setting {key}: {exc}", flush=True)


class Owners:
    """Best-effort provenance: which principal created a named resource.

    The emulator keeps no owner metadata, so this is a control-plane ledger keyed
    by `account/service/name` (names are unique per service inside an account; S3
    is account-scoped upstream anyway). A resource created with the CLI simply has
    no entry — the console shows the account and leaves the user blank.
    """

    def __init__(self, db: Store) -> None:
        self.db = db
        self.lock = threading.Lock()
        self.entries: dict = db.payloads("owners")

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
            key = self._key(account, service, name)
            entry = {"user": user or "token", "region": region, "at": now()}
            self.entries[key] = entry
            try:
                self.db.put("owners", key, json.dumps(entry))
            except (OSError, DynamoError) as exc:
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
                    self.db.delete_prefix("owners", prefix)
                except (OSError, DynamoError):
                    pass


DB = Store()
try:
    DB.verify_tables()
except (OSError, DynamoError) as exc:
    print(f"control: cannot reach the store at {DB.dynamo.endpoint}: {exc}", flush=True)
    raise SystemExit(1)
except StoreNotProvisioned as exc:
    print(f"control: {exc}", flush=True)
    raise SystemExit(1)

ACCOUNTS = Accounts(DB)
USERS = UserStore(DB)
SETTINGS = Settings(DB)
OWNERS = Owners(DB)


def seed_local_admin() -> None:
    """Retired: a fresh control starts with no accounts, only sign-up.

    Kept as a named tombstone so the next reader does not go looking for the
    bootstrap user in `app.py` again — `ensure_local()` already makes the first
    sign-up the platform owner (global and default admin). Removed 2026-11-15
    with the `MC_ADMIN_USER`/`_EMAIL`/`_PASSWORD` settings.
    """


# No seed call on purpose: the database may be empty and that is the design.


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


def ensure_iam_user(account: dict, principal: dict) -> str:
    """Create the IAM user and its admin policy once. Returns "" or an error."""
    account_id = account["account_id"]
    username = principal["username"]
    ok, body = iam_request(account_id, "CreateUser", UserName=username)
    if not ok and "EntityAlreadyExists" not in body:
        return f"CreateUser failed: {body[:120]}"
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}],
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
    return ""


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
    problem = ensure_iam_user(account, principal)
    if problem:
        return None, problem
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

    def __init__(self, db: Store) -> None:
        self.db = db
        self.lock = threading.Lock()
        self.buckets: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        self.buckets = self.db.payloads("buckets")
        self.nodes = self.db.payloads("bucket_nodes")

    def save(self) -> None:
        self.db.replace_all(
            "buckets", {name: json.dumps(e) for name, e in self.buckets.items()}
        )
        self.db.replace_all(
            "bucket_nodes", {name: json.dumps(e) for name, e in self.nodes.items()}
        )

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
        self, node: dict, names: dict[str, str], reachable: bool, account: str = ""
    ) -> list[str]:
        """Merge one account's inventory. Unreachable keeps the last known set.

        ``names`` maps bucket name to the region it was listed in: S3 state is
        account- and region-scoped, so an inventory is assembled one region at
        a time. The listing is per account, so pruning is too: entries
        belonging to other accounts must survive a reconcile of the root
        account.
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
                            "region": names[name],
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


REGISTRY = Registry(DB)

# node health + service availability, refreshed by the poller
HEALTH: dict[str, dict] = {}
HEALTH_LOCK = threading.Lock()

# control-plane sessions (in memory, write-through to the `sessions` store)
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()


def session_key(token: str) -> str:
    """The store key for a session token: a digest, never the token itself.

    A session token is a bearer credential, so a copy of the table must not be
    enough to replay it. The cookie carries the raw token; the store keeps only
    its SHA-256, which is what the lookup hashes again.
    """
    return hashlib.sha256((token or "").encode()).hexdigest()


def save_sessions() -> None:
    """Persist live sessions so a container restart does not sign everyone out."""
    rows = {
        key: json.dumps(info)
        for key, info in list(SESSIONS.items())
        if isinstance(info, dict)
    }
    try:
        DB.replace_all("sessions", rows)
    except (OSError, DynamoError) as exc:
        print(f"control: could not persist sessions: {exc}", flush=True)


def load_sessions() -> None:
    current = time.time()
    restored = 0
    with SESSIONS_LOCK:
        for key, payload in DB.items("sessions"):
            try:
                info = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(info, dict):
                continue
            if info.get("expires", 0) > current:
                # Rows written before sessions were hashed are keyed by the raw
                # token. Re-key them in memory and drop the raw copy, so the
                # table never keeps a usable credential.
                digest = key if re.fullmatch(r"[0-9a-f]{64}", key) else session_key(key)
                SESSIONS[digest] = info
                restored += 1
                if digest != key:
                    DB.delete("sessions", key)
            else:
                DB.delete("sessions", key)
    if restored:
        print(f"control: restored {restored} live session(s)", flush=True)


load_sessions()


def new_session(
    username: str, account: str, role: str = "root", alias: str = "", via: str = "local"
) -> str:
    token = secrets.token_urlsafe(32)
    with SESSIONS_LOCK:
        SESSIONS[session_key(token)] = {
            "expires": time.time() + SESSION_SECONDS,
            "user": username,
            "account": account,
            "role": role,
            "alias": alias,
            "via": via,
        }
        save_sessions()
    return token


def session_info(token: str) -> dict | None:
    with SESSIONS_LOCK:
        info = SESSIONS.get(session_key(token))
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


def session_ok(token: str) -> bool:
    return session_info(token) is not None


def purge_sessions(account_id: str) -> None:
    """Drop every session bound to an account (used when it is disabled)."""
    with SESSIONS_LOCK:
        for key in [
            key
            for key, info in SESSIONS.items()
            if info.get("account") == account_id
        ]:
            SESSIONS.pop(key, None)
        save_sessions()


def purge_user_sessions(account_id: str, username: str) -> None:
    """Drop one principal's sessions (used when its password is reset)."""
    with SESSIONS_LOCK:
        for key in [
            key
            for key, info in SESSIONS.items()
            if info.get("account") == account_id and info.get("user") == username
        ]:
            SESSIONS.pop(key, None)
        save_sessions()


# --------------------------------------------------------------------------
# password-reset links
#
# There is no mail transport here, so a reset link is minted by an administrator
# and handed over out of band — the user still chooses their own password, which
# is the point of a link rather than an admin-typed password. The token follows
# the same contract as a session: only its SHA-256 is stored, the raw value
# appears once in the link, it expires, and it is deleted when it is used.

RESET_SECONDS = int(os.environ.get("EP_RESET_SECONDS", "1800"))


def reset_key(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def mint_reset(username: str, account_id: str) -> str:
    """Create a one-time reset token and return the raw value (shown once)."""
    token = secrets.token_urlsafe(32)
    DB.put(
        "resets",
        reset_key(token),
        json.dumps(
            {
                "user": username,
                "account": account_id,
                "expires": time.time() + RESET_SECONDS,
                "created": now(),
            }
        ),
    )
    return token


def read_reset(token: str) -> dict | None:
    """The live reset record for a token, or None when it is spent/expired."""
    if not token:
        return None
    try:
        raw = DB.get("resets", reset_key(token))
    except (OSError, DynamoError):
        return None
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    if record.get("expires", 0) < time.time():
        DB.delete("resets", reset_key(token))
        return None
    return record


def consume_reset(token: str) -> dict | None:
    """Read a reset record and burn it, so a link works exactly once."""
    record = read_reset(token)
    if record is not None:
        DB.delete("resets", reset_key(token))
    return record


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


def list_bucket_names(
    node: dict, account: str = "", region: str = ""
) -> tuple[bool, dict[str, str]]:
    """List one account's buckets in one region. A 12-digit key is that
    account's root.

    ListBuckets is regional: the signing region decides what is enumerated, so
    an account's inventory is the union of the listings over its enabled
    regions.
    """
    region = region or DEFAULT_REGION
    extra = {}
    if account:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        extra["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={account}/{stamp}/{region}"
            "/s3/aws4_request, SignedHeaders=host, Signature=local"
        )
    status, body = node_request(
        node, "GET", "/?x-id=ListBuckets", timeout=10, extra_headers=extra
    )
    if status != 200:
        return False, {}
    found = re.findall(r"<Bucket>.*?<Name>([^<]+)</Name>", body.decode(), re.S)
    return True, {name: region for name in found}


def refresh_registry() -> dict:
    """Rebuild the name registry from every known account's inventory.

    The listing is per account (each with that account's root key), so a
    reconcile never sees — or prunes — another account's buckets.
    """
    conflicts: list[str] = []
    for account_id, account in list(ACCOUNTS.accounts.items()):
        regions = ACCOUNTS.regions_of(account)
        for node in NODES:
            reachable, names = False, {}
            for region in regions:
                ok, found = list_bucket_names(node, account_id, region)
                reachable = reachable or ok
                names.update(found)
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


def current_buckets() -> dict:
    return REGISTRY.snapshot()


def bucket_owner(bucket: str) -> dict | None:
    return REGISTRY.owner(bucket)


BUCKET_TAKEN = "Bucket {name} already exists"


def bucket_taken(name: str) -> str:
    """The one message for a name that is already taken.

    The emulator sends the same sentence, so the answer does not depend on which
    layer caught it.
    """
    return BUCKET_TAKEN.format(name=name)


def reserve_across(
    bucket: str, region: str, account: str = ""
) -> tuple[bool, str, int]:
    """Claim a bucket name for this create; an existing name is refused.

    One answer for every duplicate — this account's or another's, this region's
    or another's — with the same ``409`` and message the emulator gives.
    """
    node = node_by_region(region)
    if node is None:
        return False, "no emulator is configured", 503
    if REGISTRY.reserve(bucket, region, node, account) is None:
        return False, bucket_taken(bucket), 409
    return True, "", 0

def release_across(bucket: str) -> None:
    REGISTRY.release(bucket)


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
    if match:
        ref = match.group(1)
        if re.fullmatch(r"\d{12}", ref):
            return ref
        return ACCOUNTS.account_for_key(ref)
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

        if account and service not in GLOBAL_SERVICES:
            owner = ACCOUNTS.accounts.get(account)
            if owner is not None and region not in ACCOUNTS.regions_of(owner):
                if region not in REGION_CHOICES:
                    self._error(
                        403,
                        "AccessDenied",
                        f"region {region} is not enabled for this account",
                    )
                    return
                # A region MiniStack serves, so the reference is
                # honoured and recorded as enabled on first use instead of being
                # refused. A region outside the catalogue stays refused.
                ACCOUNTS.enable_region(account, region)
                print(
                    f"gateway: enabled {region} for {owner.get('alias', account)} on first use",
                    flush=True,
                )

        if service in GLOBAL_SERVICES:
            node = primary_node()
            if node is None:
                self._error(503, "ServiceUnavailable", "no emulator is configured")
                return
            self._forward(node, node["region"], body)
            return
        if service != "s3":
            node = node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no emulator is configured")
                return
            self._forward(node, region, body)
            return

        bucket, key, query, _ = s3_target(self.path, self.headers.get("Host", ""))
        if not bucket:
            node = node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no emulator is configured")
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
            entry = bucket_owner(bucket)
            reserved = entry is None
            if entry is None:
                ok, message, code = reserve_across(bucket, region, account)
                if not ok:
                    self._error(
                        code,
                        "BucketAlreadyExists" if code == 409 else "ServiceUnavailable",
                        message,
                    )
                    return
            elif entry.get("account_id") != account or entry.get("region") != region:
                # Another account's name, or this account's bucket in another
                # region: one answer, whichever account or region asks.
                self._error(409, "BucketAlreadyExists", bucket_taken(bucket))
                return
            # The owner re-creating in the bucket's own region is forwarded: the
            # emulator answers AWS's 200-and-reset (us-east-1) or
            # BucketAlreadyOwnedByYou, and either way the reservation stays.
            node = node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no emulator is configured")
                return
            try:
                status, headers, payload = proxy(
                    node, self.command, self.path, self.headers, body
                )
            except OSError as exc:
                if reserved:
                    release_across(bucket)
                self._error(503, "ServiceUnavailable", f"{node['name']} unreachable: {exc}")
                return
            if not 200 <= status < 300 and reserved:
                release_across(bucket)
            self._send(status, headers, payload)
            return

        if destroy:
            entry = bucket_owner(bucket)
            node = node_by_name(entry["node"]) if entry else node_by_region(region)
            if node is None:
                self._error(503, "ServiceUnavailable", "no emulator is configured")
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
            self._error(503, "ServiceUnavailable", "no emulator is configured")
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
    --bg: #f3f6fc; --panel: #ffffff; --fg: #0b1b3f; --muted: #5a6b8c;
    --border: #d7e0f5; --input: #ffffff; --primary: #ff8a1f;
    --primary-hover: #ef700a; --link: #1b4fd8;
    --error-bg: #fdf3f3; --error-border: #e07979; --error-fg: #8b1a1a;
    --ok-bg: #f1f8f3; --ok-border: #7fb98a; --ok-fg: #1d5b2c;
    color-scheme: light;
  }
  [data-theme="dark"] {
    --bg: #0a1220; --panel: #111c31; --fg: #e8eefb; --muted: #93a4c4;
    --border: #23324f; --input: #0a1220; --primary: #ff8a1f;
    --primary-hover: #ef700a; --link: #6cb6ff;
    --error-bg: #2a1215; --error-border: #6e2b2b; --error-fg: #ff8f8f;
    --ok-bg: #10241a; --ok-border: #2f6b45; --ok-fg: #7fe0a0;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: var(--bg); color: var(--fg);
         font: 15px/1.5 "Open Sans", system-ui, -apple-system, sans-serif; }
  .auth-card { width: 100%; max-width: 25rem; padding: 2.25rem 2rem;
               background: var(--panel); border: 1px solid var(--border);
               border-radius: 8px;
               position: relative; }
  .theme { position: absolute; top: .75rem; right: .75rem; display: inline-flex;
           align-items: center; margin: 0; background: transparent; }
  .theme button { display: inline-flex; align-items: center; justify-content: center;
                  width: 34px; height: 34px; padding: 0; border: none;
                  border-radius: 50%; background: transparent; color: inherit;
                  cursor: pointer; opacity: .85; }
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
  input { width: 100%; padding: .3rem .55rem; border-radius: 6px;
          border: 1px solid var(--border); background: var(--input);
          color: var(--fg); font: inherit; font-size: .875rem; }
  input:focus { outline: 2px solid var(--primary); outline-offset: 0;
                border-color: transparent; }
  input::placeholder { color: var(--muted); opacity: .8; }
  button { width: 100%; margin-top: 1rem; padding: .65rem; border: 0;
           border-radius: 8px; background: var(--primary); color: #0b1b3f;
           font: inherit; font-weight: 700; cursor: pointer; }
  button:hover { background: var(--primary-hover); }
  .brand-mark { display: block; height: 4.5rem; width: auto;
                margin: 0 auto 1.25rem; }
  .auth-title { text-align: left; font-size: 1.75rem; line-height: 1.25;
                margin: 0 0 1.6rem; font-weight: 700; }
  .hint { color: var(--muted); font-size: .85rem; margin: -.05rem 0 .5rem; }
  .field-error { display: flex; gap: .4rem; align-items: flex-start;
                 margin: .4rem 0 0; color: #d91515; font-size: .85rem; }
  [data-theme="dark"] .field-error { color: #ff8f8f; }
  .field-error .dot { flex: 0 0 auto; width: 1rem; height: 1rem; border-radius: 50%;
                      background: #d91515; color: #fff; font-size: .7rem;
                      font-weight: 700; display: inline-flex; align-items: center;
                      justify-content: center; }
  /* The reveal control lives inside the field, the way the console's sign-in
     pages show it, so the eye lines up with the input it acts on. */
  .pwd { position: relative; }
  .pwd input { padding-inline-end: 2.1rem; }
  .reveal { position: absolute; top: 50%; inset-inline-end: .3rem;
            transform: translateY(-50%); width: 1.75rem; height: 1.75rem;
            margin: 0; padding: 0; border: 0; border-radius: 6px;
            background: transparent; color: var(--muted); cursor: pointer;
            display: inline-flex; align-items: center; justify-content: center; }
  .reveal:hover { background: transparent; color: var(--fg); }
  .reveal .eye-shut { display: none; }
  .reveal[aria-pressed="true"] .eye-open { display: none; }
  .reveal[aria-pressed="true"] .eye-shut { display: inline-flex; }
  .actions { display: flex; align-items: center; gap: .6rem; margin-top: 1.25rem; }
  .actions > button { flex: 1 1 0; margin-top: 0; }
  .actions > a { flex: 1 1 0; margin-top: 0; }
  .actions .or { flex: 0 0 auto; color: var(--muted); font-size: .72rem;
                 font-weight: 600; letter-spacing: .06em; }
  .secondary { display: flex; align-items: center; justify-content: center;
               width: 100%; padding: .6rem .75rem; border: 1px solid var(--link);
               border-radius: 8px; color: var(--link); text-decoration: none;
               font-weight: 600; text-align: center; line-height: 1.25; }
  .secondary:hover { background: rgba(9, 114, 211, .08); }
  .divider { display: flex; align-items: center; gap: .75rem; margin: 1.4rem 0;
             color: var(--muted); font-size: .8rem; }
  .divider::before, .divider::after { content: ""; flex: 1; height: 1px;
                                      background: var(--border); }
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
  pre.code { margin: .55rem 0 0; padding: .55rem .7rem; border-radius: 6px;
             background: rgba(0, 0, 0, .06); font-size: .8rem;
             overflow-x: auto; }
  [data-theme="dark"] pre.code { background: rgba(255, 255, 255, .07); }
"""


AUTH_THEME_SCRIPT = """
(function () {
  // One button toggles light and dark; it shows the mode it will switch to.
  var authKey = 'emuplane:auth-theme';
  var consoleKey = 'emuplane:theme';
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


def brand_logo_path() -> str:
    """The small mark embedded in mail, from the built assets or the source."""
    for candidate in (
        os.path.join(STATIC_DIR, "email-logo.png"),
        os.path.join(PUBLIC_DIR, "email-logo.png"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return ""


def reset_email_html(link: str, username: str, minutes: int) -> str:
    """The HTML alternative: inline styles only, because mail clients ignore
    stylesheets. The mark is referenced by `cid:`, which `mail.py` attaches."""
    safe_link = html.escape(link, quote=True)
    safe_user = html.escape(username)
    return f"""<!doctype html><html><body style="margin:0;padding:24px;background:#f3f6fc;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0b1b3f">
<div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #d7e0f5;border-radius:8px;padding:28px">
  <img src="cid:emuplane-logo" width="72" height="72" alt="Emuplane" style="display:block;margin:0 0 20px;border:0">
  <h1 style="font-size:20px;line-height:1.3;margin:0 0 12px">Reset your password</h1>
  <p style="font-size:15px;line-height:1.55;margin:0 0 20px">Someone asked to reset the password for <strong>{safe_user}</strong>. Choose a new one here:</p>
  <p style="margin:0 0 20px"><a href="{safe_link}" style="display:inline-block;background:#ff8a1f;color:#0b1b3f;font-weight:700;text-decoration:none;padding:12px 22px;border-radius:8px">Choose a new password</a></p>
  <p style="font-size:13px;line-height:1.5;color:#5a6b8c;margin:0 0 8px">The link works once and expires in {minutes} minutes.</p>
  <p style="font-size:13px;line-height:1.5;color:#5a6b8c;margin:0;word-break:break-all">Or paste this address: {safe_link}</p>
  <p style="font-size:13px;line-height:1.5;color:#5a6b8c;margin:16px 0 0">If you did not ask for this, ignore the message &mdash; your password has not changed.</p>
</div>
</body></html>"""


def reveal_control(field: str) -> str:
    """The in-field reveal button; AUTH_REVEAL_SCRIPT flips the input's type."""
    return (
        f'<button type="button" class="reveal" data-target="{field}"'
        ' aria-pressed="false" aria-label="Show password"'
        ' title="Show password">'
        '<svg class="eye-open" width="16" height="16" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round"'
        ' aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7'
        '-10-7-10-7z"></path><circle cx="12" cy="12" r="3"></circle></svg>'
        '<svg class="eye-shut" width="16" height="16" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c6.4 0 10 7 10 7a18 18 0 0'
        ' 1-2.2 3.1M6.6 6.6A18 18 0 0 0 2 12s3.6 7 10 7a10.7 10.7 0 0 0'
        ' 4.1-.8"></path><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"></path>'
        '<path d="M2 2l20 20"></path></svg>'
        '</button>'
    )

AUTH_REVEAL_SCRIPT = """
(function () {
  // The in-field eye: flip the input between password and text. Nothing else on
  // the page is touched, so a page with no reveal control costs one query.
  var buttons = document.querySelectorAll('.reveal[data-target]');
  Array.prototype.forEach.call(buttons, function (button) {
    var input = document.getElementById(button.dataset.target);
    if (!input) { return; }
    button.addEventListener('click', function () {
      var shown = input.type === 'text';
      input.type = shown ? 'password' : 'text';
      button.setAttribute('aria-pressed', String(!shown));
      var label = shown ? 'Show password' : 'Hide password';
      button.setAttribute('aria-label', label);
      button.setAttribute('title', label);
    });
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
    service: str,
    account: str,
    region: str,
    method: str,
    path: str,
    body="",
    extra_headers: dict | None = None,
) -> tuple[int, str]:
    """A generic REST call (S3, Lambda, API Gateway, ...) as the account root.

    The signing itself lives in `signed.py`, so the S3 create sequence can be
    exercised on a real socket without a store behind it.
    """
    node = primary_node()
    if node is None:
        return 0, "emulator is not registered"
    return signed.request(
        node["endpoint"], service, account, region, method, path, body, extra_headers
    )


def signed_rest_raw(
    service: str,
    account: str,
    region: str,
    method: str,
    path: str,
    body=b"",
    extra_headers: dict | None = None,
) -> tuple[int, dict, bytes]:
    """The same call, answering headers and bytes — for an object download."""
    node = primary_node()
    if node is None:
        return 0, {}, b"emulator is not registered"
    return signed.request_bytes(
        node["endpoint"], service, account, region, method, path, body, extra_headers
    )


def signed_s3(
    account: str,
    region: str,
    method: str,
    path: str,
    body: str = "",
    extra_headers: dict | None = None,
) -> tuple[int, str]:
    """Path-style S3 call signed as the account root, so no secret is held."""
    return signed_rest("s3", account, region, method, path, body, extra_headers)


def s3control(account: str, region: str):
    """An S3 Control call, as `rest(region, method, path, body)`.

    S3 Control names the account in `x-amz-account-id`, and the region is an
    argument rather than the page's: Multi-Region access point management is
    served from us-west-2 whichever region the page is showing.
    """

    def rest(target_region, method, path, body=""):
        return signed_rest(
            "s3",
            account,
            target_region or region,
            method,
            path,
            body,
            {"x-amz-account-id": account},
        )

    return rest


def is_console_route(path: str) -> bool:
    """The console's own paths beyond the flat `SPA_ROUTES`.

    A service's home (`/<service>/home`) and the pages that sit beside it
    (`/<service>/create`), plus every page S3 hangs off its own nav — the create
    forms, a bucket's own page and the access point pages — which the client
    router resolves and whose unknown names it redirects away from. Any depth is
    SPA territory: a page you cannot open by its URL is a page you cannot
    bookmark.
    """
    parts = [part for part in path.split("/") if part]
    if not parts:
        return False
    if parts[0] == "s3":
        return True
    return len(parts) == 2 and parts[1] in ("home", "create")


def static_asset(url_path: str) -> tuple[bytes, str] | None:
    """One built asset from `web/dist`, or None. Traversal-safe."""
    if not (
        url_path.startswith("/assets/")
        or url_path.startswith("/backends/")
        or url_path in ICON_ASSETS
        or url_path == "/emuplane.png"
    ):
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


def _bucket_location(account: str, region: str, name: str) -> str:
    """Where a bucket really lives, asked of S3 itself.

    `ListBuckets` is account-global and says nothing about a bucket's region, and
    a bucket created straight on the emulator has no claim either. `GetBucketLocation`
    answers whatever region it is signed for, and an empty constraint is us-east-1
    — which is what AWS returns for it, not a guess.
    """
    status, body = signed_s3(account, region, "GET", "/" + quote(name) + "?location")
    if not 200 <= status < 300:
        return ""
    found = re.search(
        r"<LocationConstraint[^>]*>([^<]+)</LocationConstraint>", body or ""
    )
    return found.group(1).strip() if found else "us-east-1"


def _annotate(
    service: str, account: str, region: str, rows: list[dict]
) -> list[dict]:
    """Attach the region and owner metadata every row carries.

    The registry is the only thing that knows where a bucket this console created
    lives: the fork's ``ListBuckets`` is account-global, as AWS's is, so every
    enabled region answers with every bucket and the queried region says nothing
    about a bucket's own. A bucket with no claim — one made straight on the
    emulator — is located by asking S3 (`GetBucketLocation`); the queried region
    stays the fallback for a name even that cannot answer for.
    """
    for row in rows:
        claim = _bucket_claim(row["name"]) if service == "s3" else {}
        entry = OWNERS.get(account, service, row["name"])
        owner = {"account": claim.get("account_id") or account}
        if entry.get("user"):
            owner["user"] = entry["user"]
            owner["at"] = entry.get("at", "")
        row["region"] = claim.get("region") or region
        if service == "s3" and not claim.get("region"):
            row["region"] = _bucket_location(account, region, row["name"]) or row["region"]
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
    """Every region at once: one row per resource.

    A bucket name is unique partition-wide, so S3 rows dedupe by name alone;
    every other service may reuse a name in another region.
    """
    rows: list[dict] = []
    seen: set[tuple] = set()
    for region in regions:
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

    def _json(self, status: int, payload, cookie: str = "") -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _page(self, body: str, status: int = 200) -> None:
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # These pages carry a form and change with every build; a cached copy is
        # how a reworked screen looks "unchanged" to a returning browser.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _bytes(
        self,
        payload: bytes,
        content_type: str,
        status: int = 200,
        filename: str = "",
    ) -> None:
        """One object's bytes, as an attachment when `filename` is given."""
        self.send_response(status)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        if filename:
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''" + quote(filename, safe=""),
            )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _spa(self) -> None:
        payload = spa_index()
        if payload is None:
            return self._page(
                "<!doctype html><meta charset=utf-8><title>Emuplane</title>"
                "<body style='font:15px system-ui;padding:2rem;background:#0f1b2d;color:#e6edf7'>"
                "<h1>Console not built</h1><p>Run <code>npm install &amp;&amp; npm run build</code>"
                " in <code>services/ministack-control/web</code>, then restart this container.</p>"
                "<p>The server-rendered pages are still at <a style='color:#7cc4ff' href='/classic'>/classic</a>.</p>",
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
        # Hashed build output never changes under a name; the brand files (icons
        # and the marks) keep their name across releases, so they revalidate.
        brand = url_path in ICON_ASSETS or url_path.startswith("/backends/")
        cache = (
            "public, max-age=86400"
            if brand or url_path == "/emuplane.png"
            else "public, max-age=31536000, immutable"
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(payload)

    def _cookies(self) -> dict[str, str]:
        cookies = {}
        for part in self.headers.get("Cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key:
                cookies[key] = value
        return cookies

    def _session_token(self) -> str:
        for part in self.headers.get("Cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == "emuplane_session":
                return value
        return ""

    def _authenticated(self) -> bool:
        token = self._session_token()
        if token and session_ok(token):
            return True
        header = self.headers.get("Authorization", "")
        if not header.lower().startswith("bearer "):
            return False
        return bearer_ok(header[7:].strip())

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
        """Cross-tenant access belongs to the deployment, never to a login.

        The AWS model has no global administrator: a root user owns its account
        and nothing else, and IAM users live inside that boundary. The only
        principal that may cross tenancies is the bearer token — a deployment
        credential held by the operator, not somebody's login.
        """
        return not info

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
        if token:
            with SESSIONS_LOCK:
                SESSIONS.pop(session_key(token), None)
                save_sessions()
        self.send_response(302)
        self.send_header("Location", "/login")
        self.send_header(
            "Set-Cookie",
            "emuplane_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _auth_login(self) -> None:
        """JSON sign-in for the console's own screens.

        Root takes an email (or username) and a password; IAM takes an account
        reference, a username and a password. Success mints the same HttpOnly
        session cookie the server-rendered form used to, so every later request
        is unchanged. The answer says whether this principal still owes an MFA
        code; enrolment does not exist yet (slice 3b), so it is false for every
        account and the code screen is not reached.
        """
        payload = self._body()
        mode = str(payload.get("mode") or "root").strip().lower()
        password = str(payload.get("password") or "")
        if mode not in {"root", "iam"}:
            return self._json(400, {"error": "user type must be root or iam"})
        if not password:
            return self._json(400, {"error": "Enter your password."})

        if mode == "root":
            identifier = str(payload.get("email") or "").strip()
            if not identifier:
                return self._json(
                    400, {"error": "Enter the email address for the account."}
                )
            user = USERS.find_by_email(identifier) or USERS.get(identifier)
            if user is None:
                time.sleep(0.4)
                return self._json(
                    401, {"error": "That email address and password do not match."}
                )
            username = user["username"]
        else:
            reference = str(payload.get("account") or "").strip()
            username = str(payload.get("username") or "").strip()
            if not reference or not username:
                return self._json(
                    400, {"error": "Enter the account and the IAM username."}
                )
            account = ACCOUNTS.by_ref(reference)
            user = USERS.get(username)
            if (
                account is None
                or user is None
                or user.get("account_id") != account["account_id"]
            ):
                time.sleep(0.4)
                return self._json(
                    401, {"error": "That account, username and password do not match."}
                )

        record = USERS.verify(username, password)
        if record is None:
            time.sleep(0.4)
            return self._json(401, {"error": "That password does not match."})
        account = ACCOUNTS.by_ref(record["account_id"])
        principal = ((account or {}).get("users") or {}).get(username)
        if account is not None and principal is None:
            # The account was cached before this principal existed (an operator
            # tool added it out of process). Read the table once more.
            ACCOUNTS._load()
            account = ACCOUNTS.by_ref(record["account_id"])
            principal = ((account or {}).get("users") or {}).get(username)
        if account is None or principal is None:
            return self._json(
                500, {"error": "This user has no account record; sign up again."}
            )
        if account.get("disabled"):
            return self._json(403, {"error": "This account is disabled."})
        if principal.get("role") == "root" and not account.get(
            "root_credentials_enabled", True
        ):
            return self._json(
                403, {"error": "Root credentials for this account are disabled."}
            )
        if principal.get("mfa_enabled"):
            # The contract is in place; the enrolment flow is not (slice 3b).
            return self._json(
                501, {"error": "MFA enrolment is not implemented yet."}
            )

        token = new_session(
            username, account["account_id"], principal["role"], account["alias"]
        )
        answer = {
            "ok": True,
            "mfa_required": False,
            "user": username,
            "account": account["account_id"],
            "alias": account["alias"],
            "role": principal["role"],
        }
        if payload.get("multi"):
            # Opt-in: the browser keeps this to switch back without a password.
            # It is a session token, so it is only ever returned on request.
            answer["token"] = token
        self._json(
            200,
            answer,
            cookie=(
                f"emuplane_session={token}; Path=/; Max-Age={SESSION_SECONDS}; "
                "HttpOnly; SameSite=Lax"
            ),
        )

    def _auth_switch(self) -> None:
        """Adopt an identity the browser already holds a session token for.

        Multi-session is opt-in and client-side: the token sits in
        `localStorage` only after the account menu turned it on. The server
        merely re-mints the cookie for a token that is still live — a dead one
        is refused, so signing out everywhere also ends the switch list.
        """
        payload = self._body()
        token = str(payload.get("token") or "").strip()
        info = session_info(token) if token else None
        if info is None:
            return self._json(401, {"error": "that identity is no longer signed in"})
        return self._json(
            200,
            {
                "ok": True,
                "user": info.get("user"),
                "account": info.get("account"),
                "alias": info.get("alias"),
                "role": info.get("role"),
            },
            cookie=(
                f"emuplane_session={token}; Path=/; Max-Age={SESSION_SECONDS}; "
                "HttpOnly; SameSite=Lax"
            ),
        )

    def _signup(self) -> None:
        """Create an account and sign in; the first one becomes the platform owner."""
        if not SETTINGS.get("signup_enabled", True):
            return self._page(
                self._signup_page({"form": "Sign-up is disabled on this lab."}), 403
            )
        form = self._form()
        username = (form.get("username") or "").strip()
        email = (form.get("email") or "").strip()
        password = form.get("password") or ""
        confirm = form.get("confirm") or ""
        errors: dict[str, str] = {}
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
            errors["username"] = (
                "An account name is required: 3-32 characters, letters, digits, "
                "dot, dash or underscore."
            )
        elif USERS.exists(username):
            errors["username"] = "That account name is already taken."
        if not email:
            errors["email"] = "An email address is required."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors["email"] = "That email address does not look right."
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        elif password != confirm:
            errors["confirm"] = "The passwords do not match."
        if errors:
            return self._page(self._signup_page(errors, username, email), 400)

        account, principal = ACCOUNTS.ensure_local(username)
        USERS.create(
            username,
            email,
            password,
            account["account_id"],
            principal.get("role", "root"),
        )
        session = new_session(
            username, account["account_id"], principal["role"], account["alias"]
        )
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"emuplane_session={session}; Path=/; Max-Age={SESSION_SECONDS}; "
            "HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _auth_layout(
        self, title: str, body: str, logo: bool | None = None
    ) -> str:
        """The shell every server-rendered auth page sits in.

        `logo` defaults to on for /reset — the one auth page a link lands on, so
        it has to look like the product that sent the mail.
        """
        if logo is None:
            logo = urlsplit(self.path).path == "/reset"
        mark = (
            '<img class="brand-mark" src="/emuplane.png" alt="Emuplane" '
            'width="72" height="72">'
            if logo
            else ""
        )
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Emuplane</title>{ICON_LINKS}<style>{AUTH_STYLE}</style>
</head><body><main class="auth-card">
<div class="theme" id="theme-toggle">
  <button type="button" aria-label="Toggle colour theme" title="Toggle colour theme">
    <span class="icon-sun">
      <svg width="21" height="21" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <circle cx="12" cy="12" r="4"></circle>
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>
      </svg>
    </span>
    <span class="icon-moon">
      <svg width="21" height="21" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round"
           stroke-linejoin="round">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path>
      </svg>
    </span>
  </button>
</div>
{mark}
{body}</main><script>{AUTH_THEME_SCRIPT}</script><script>{AUTH_REVEAL_SCRIPT}</script></body></html>"""

    def _signup_page(
        self,
        errors: dict[str, str] | None = None,
        username: str = "",
        email: str = "",
    ) -> str:
        """Step one: the address the code goes to, and the account name."""
        errors = errors or {}

        def problem(field: str) -> str:
            message = errors.get(field, "")
            if not message:
                return ""
            return (
                '<p class="field-error"><span class="dot" aria-hidden="true">!</span>'
                f"{html.escape(message)}</p>"
            )

        reveal = reveal_control

        notice = errors.get("form", "")
        notice_html = f'<div class="error">{html.escape(notice)}</div>' if notice else ""
        return self._auth_layout(
            "Create account",
            f"""
    <h1 class="auth-title">Create your account</h1>
    {notice_html}
    <form method="post" action="/signup">
      <div class="field">
        <label for="email">Email address</label>
        <input id="email" name="email" type="email" value="{html.escape(email)}"
               placeholder="username@example.com" autocomplete="email" required autofocus>
        {problem("email")}
      </div>
      <div class="field">
        <label for="username">Account name</label>
        <p class="hint">Choose a name for your account.</p>
        <input id="username" name="username" value="{html.escape(username)}"
               placeholder="username" autocomplete="username" required>
        {problem("username")}
      </div>
      <div class="field">
        <label for="password">Password</label>
        <p class="hint">At least 8 characters.</p>
        <div class="pwd">
          <input id="password" name="password" type="password"
                 autocomplete="new-password" required>
          {reveal("password")}
        </div>
        {problem("password")}
      </div>
      <div class="field">
        <label for="confirm">Confirm password</label>
        <p class="hint">The same password again.</p>
        <div class="pwd">
          <input id="confirm" name="confirm" type="password"
                 autocomplete="new-password" required>
          {reveal("confirm")}
        </div>
        {problem("confirm")}
      </div>
      <div class="actions">
        <button type="submit">Create Account</button>
        <span class="or">OR</span>
        <a class="secondary" href="/login">Sign in to an existing account</a>
      </div>
    </form>
""",
        )

    def _forgot_page(self, sent: bool = False, problem: str = "") -> str:
        """Ask for the address: we send the link when a relay is configured."""
        minutes = RESET_SECONDS // 60
        notice = f'<div class="error">{html.escape(problem)}</div>' if problem else ""
        if sent:
            return self._auth_layout(
                "Reset password",
                f"""
    <h1 class="auth-title">Check your mail</h1>
    <div class="ok">If that address belongs to an account, a reset link is on its
      way. It expires in {minutes} minutes and works once.</div>
    <p class="hint">Nothing arrived? An administrator can mint a link instead
      with <code>./scripts/reset-link.sh &lt;username&gt;</code>.</p>
    <div class="actions">
      <a class="secondary" href="/login">Back to sign in</a>
    </div>
""",
            )

        if not mail.configured():
            return self._auth_layout(
                "Reset password",
                """
    <h1 class="auth-title">Reset your password</h1>
    <p class="hint">This server has no mail relay configured, so a reset link
      cannot be emailed. Ask an administrator: they mint a single-use link that
      opens <code>/reset</code>, where you choose the password yourself. It
      expires after 30 minutes and stops working once used.</p>
    <div class="field">
      <label>If you can still sign in</label>
      <p class="hint">Change the password yourself under Settings &rarr; Account.
        It asks for the current password first.</p>
    </div>
    <div class="field">
      <label>If you are the platform owner</label>
      <p class="hint">Mint a link from the host, in the service directory:</p>
      <pre class="code">./scripts/reset-link.sh &lt;username&gt;</pre>
    </div>
    <div class="actions">
      <a class="secondary" href="/login">Back to sign in</a>
    </div>
""",
            )

        return self._auth_layout(
            "Reset password",
            f"""
    <h1 class="auth-title">Reset your password</h1>
    <p class="hint">Enter the address on the account and we will email a link.
      It expires in {minutes} minutes and can be used once.</p>
    {notice}
    <form method="post" action="/forgot">
      <div class="field">
        <label for="email">Email address</label>
        <input id="email" name="email" type="email"
               placeholder="username@example.com" autocomplete="email"
               required autofocus>
      </div>
      <div class="actions">
        <button type="submit">Send reset link</button>
        <a class="secondary" href="/login">Sign in</a>
      </div>
    </form>
""",
        )

    def _forgot_submit(self) -> None:
        """Mail a reset link. The answer is identical whether or not it exists."""
        form = self._form()
        email = (form.get("email") or "").strip()
        if not mail.configured():
            return self._page(
                self._forgot_page(
                    problem="No mail relay is configured on this server."
                ),
                400,
            )
        if not email:
            return self._page(
                self._forgot_page(problem="An email address is required."), 400
            )
        user = USERS.find_by_email(email)
        if user is not None:
            token = mint_reset(user["username"], user.get("account_id", ""))
            link = f"{CONSOLE_URL}/reset?token={token}"
            body = (
                f"A password reset was requested for {user['username']} "
                f"at {CONSOLE_URL}.\n\n"
                "Open this link to choose a new password. It is single use and "
                f"expires in {RESET_SECONDS // 60} minutes:\n\n"
                f"{link}\n\n"
                "If you did not ask for this, ignore this message - your "
                "password has not changed.\n"
            )
            try:
                mail.send(
                    user.get("email") or email,
                    "Reset your Emuplane password",
                    body,
                    html_body=reset_email_html(
                        link, user["username"], RESET_SECONDS // 60
                    ),
                    logo=brand_logo_path(),
                )
            except mail.MailError as exc:
                print(f"control: could not send a reset mail: {exc}", flush=True)
                return self._page(
                    self._forgot_page(
                        problem="The mail relay refused the message. Ask an "
                        "administrator for a reset link."
                    ),
                    502,
                )
        return self._page(self._forgot_page(sent=True))

    def _reset_page(
        self, token: str = "", errors: dict[str, str] | None = None
    ) -> str:
        """The page a reset link opens: choose a new password."""
        errors = errors or {}
        if not token:
            token = (parse_qs(urlsplit(self.path).query).get("token") or [""])[0]
        notice = errors.get("form", "")
        notice_html = f'<div class="error">{html.escape(notice)}</div>' if notice else ""
        record = read_reset(token) if token else None
        if record is None:
            return self._auth_layout(
                "Reset password",
                f"""
    <h1 class="auth-title">Reset your password</h1>
    {notice_html or '<div class="error">This reset link is not valid any more. Ask an administrator for a new one.</div>'}
    <div class="actions">
      <a class="secondary" href="/login">Back to sign in</a>
    </div>
""",
            )

        def problem(field: str) -> str:
            message = errors.get(field, "")
            if not message:
                return ""
            return (
                '<p class="field-error"><span class="dot" aria-hidden="true">!</span>'
                f"{html.escape(message)}</p>"
            )

        return self._auth_layout(
            "Choose a password",
            f"""
    <h1 class="auth-title">Choose a password</h1>
    <p class="hint">Setting a new password for
      <strong>{html.escape(record.get("user", ""))}</strong>.</p>
    {notice_html}
    <form method="post" action="/reset">
      <input type="hidden" name="token" value="{html.escape(token)}">
      <div class="field">
        <label for="password">New password</label>
        <p class="hint">At least 8 characters.</p>
        <div class="pwd">
          <input id="password" name="password" type="password"
                 autocomplete="new-password" required autofocus>
          {reveal_control("password")}
        </div>
        {problem("password")}
      </div>
      <div class="field">
        <label for="confirm">Confirm password</label>
        <div class="pwd">
          <input id="confirm" name="confirm" type="password"
                 autocomplete="new-password" required>
          {reveal_control("confirm")}
        </div>
        {problem("confirm")}
      </div>
      <div class="actions">
        <button type="submit">Set password</button>
      </div>
    </form>
""",
        )

    def _read_body(self) -> bytes:
        """The request body as bytes — a file upload is not JSON."""
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

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
            # Public and unauthenticated: liveness only. Counts, uptime, mode and
            # seen regions are in `/api/meta`, behind a session.
            return self._json(200, {"status": "ok"})
        if path == "/signup":
            return self._page(self._signup_page())
        if path == "/forgot":
            return self._page(self._forgot_page())
        if path == "/reset":
            token = (parse_qs(urlsplit(self.path).query).get("token") or [""])[0]
            live = bool(token) and read_reset(token) is not None
            return self._page(self._reset_page(), 200 if live else 400)
        if path in ("/accounts", "/onboarding"):
            # Retired console pages. The account view is Settings now.
            return self._redirect("/settings")
        if path == "/favorites":
            # Favourites as a page is gone; it pins services on All services.
            return self._redirect("/services")
        if path in PUBLIC_SPA_ROUTES:
            return self._spa()
        if path in SPA_ROUTES or path.startswith("/resources/") or is_console_route(path):
            if not self._authenticated():
                return self._redirect("/login?next=" + quote(path))
            return self._spa()
        if path.startswith("/assets/"):
            return self._asset(path)
        if path == "/emuplane.png" or path.startswith("/backends/"):
            # Public brand marks: the sign-in pages carry Emuplane's, the console
            # carries the backend profile's.
            return self._asset(path)
        if path in ICON_ASSETS:
            return self._asset(path)
        if path == "/logout":
            return self._logout()
        if path.startswith("/api"):
            if not self._authenticated():
                return self._json(401, {"error": "authentication required"})
            path = self._api_path(path)
        elif not self._authenticated():
            return self._redirect("/login?next=" + quote(path))

        if path == "/api/accounts/me":
            info = session_info(self._session_token()) or {}
            account = ACCOUNTS.by_ref(info.get("account", "")) if info else None
            record = USERS.get(info.get("user", "")) if info else None
            return self._json(
                200,
                {
                    **{
                        key: info.get(key)
                        for key in ("user", "account", "alias", "role", "expires")
                    },
                    "name": (account or {}).get("name", ""),
                    "email": (record or {}).get("email") or "",
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
        if path == "/api/s3/bucket-head":
            # HeadBucket: the page asks where this bucket really is before it
            # reads anything, so a bookmarked link works from any region.
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            bucket = (params.get("bucket") or [""])[0].strip()
            info = self._caller()
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
            if not bucket:
                return self._json(400, {"error": "a bucket is required"})
            result = buckets.head_bucket(
                bucket,
                lambda method, target_path: signed_rest_raw(
                    "s3", target["account_id"], region, method, target_path
                ),
            )
            return self._json(
                200 if result.get("ok") else 502,
                # `region` is the bucket's own answer; the one the page asked with
                # is echoed separately so the two cannot be confused.
                dict(result, account=target["account_id"], requested_region=region),
            )
        if path in ("/api/s3/bucket-documents", "/api/s3/object", "/api/s3/object-download"):
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            bucket = (params.get("bucket") or [""])[0].strip()
            key = (params.get("key") or [""])[0]
            info = self._caller()
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
            if not bucket:
                return self._json(400, {"error": "a bucket is required"})
            if path.endswith("bucket-documents"):
                result = buckets.read_documents(
                    bucket,
                    lambda method, target_path: signed_rest(
                        "s3", target["account_id"], region, method, target_path
                    ),
                )
                return self._json(
                    200 if result.get("ok") else 404,
                    dict(result, account=target["account_id"], region=region),
                )
            if not key:
                return self._json(400, {"error": "a key is required"})
            if path.endswith("object-download"):
                # The object as a file: the console shows text inline and offers
                # this for everything else, so a PNG is not a page of mojibake.
                status, headers, data = signed_rest_raw(
                    "s3",
                    target["account_id"],
                    region,
                    "GET",
                    "/" + quote(bucket) + "/" + quote(key, safe="/"),
                )
                if not 200 <= status < 300:
                    return self._json(
                        status if status in (403, 404) else 502,
                        {"error": data.decode(errors="replace")[:300]},
                    )
                return self._bytes(
                    data,
                    safe_content_type(headers.get("content-type", "")),
                    filename=key.rsplit("/", 1)[-1],
                )
            result = buckets.read_object(
                bucket,
                key,
                lambda method, target_path: signed_rest_raw(
                    "s3", target["account_id"], region, method, target_path
                ),
            )
            return self._json(
                200 if result.get("ok") else 404,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/bucket-settings":
            # The create page's "copy settings from an existing bucket".
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            bucket = (params.get("bucket") or [""])[0].strip()
            info = self._caller()
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
            if not bucket:
                return self._json(400, {"error": "a bucket name is required"})
            result = buckets.read_settings(
                bucket,
                lambda method, target_path: signed_rest(
                    "s3", target["account_id"], region, method, target_path
                ),
            )
            return self._json(
                200, dict(result, account=target["account_id"], region=region)
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
            # A bucket is read in its own region; asking elsewhere is a 301 on the
            # wire, and saying which region saves the caller the round trip.
            claim = _bucket_claim(bucket)
            if claim.get("region") and claim["region"] != region:
                return self._json(
                    301,
                    {
                        "error": (
                            f"bucket {bucket} is in {claim['region']}, not {region}"
                        ),
                        "bucket": bucket,
                        "region": claim["region"],
                    },
                )
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
        if path in ("/api/s3/table-buckets", "/api/s3/file-systems"):
            # S3's other tabs are other APIs; the console asks them directly.
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            section = (
                "table-buckets" if path.endswith("table-buckets") else "file-systems"
            )
            info = self._caller()
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
            result = s3extra.list_items(
                section,
                lambda service, method, target_path: signed_rest(
                    service, target["account_id"], region, method, target_path
                ),
            )
            return self._json(
                200 if result.get("ok") else 502,
                dict(
                    result,
                    account=target["account_id"],
                    region=region,
                    service=section,
                ),
            )
        if path == "/api/s3/access-points":
            # Access points are S3 Control, not bucket subresources: each section
            # is read from the region S3 Control serves it from.
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            section = (params.get("section") or ["general"])[0]
            bucket = (params.get("bucket") or [""])[0].strip()
            info = self._caller()
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
            if section not in accesspoints.SECTIONS:
                return self._json(
                    400, {"error": f"unknown access point section: {section}"}
                )
            result = accesspoints.listing(
                section, region, s3control(target["account_id"], region), bucket
            )
            failure = result.get("status") or 0
            return self._json(
                200
                if result.get("ok")
                else (failure if 400 <= failure < 500 else 502),
                dict(
                    result,
                    account=target["account_id"],
                    section=section,
                ),
            )
        if path == "/api/s3/access-point-policy":
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            name = (params.get("name") or [""])[0].strip()
            info = self._caller()
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
            if not name:
                return self._json(400, {"error": "an access point name is required"})
            result = accesspoints.read_policy(
                region, name, s3control(target["account_id"], region)
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
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
                },
            )
        if path == "/api/meta":
            info = self._caller()
            platform = self._platform(info)
            operator = next(iter(ACCOUNTS.accounts.values()), {})
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
            auto_regions = sorted((current or {}).get("auto_regions") or [])
            visible = [
                account
                for account in ACCOUNTS.accounts.values()
                if platform or account["account_id"] == info.get("account")
            ]
            return self._json(
                200,
                {
                    "product": "Emuplane",
                    "backend": BACKEND.title,
                    "backend_id": BACKEND.id,
                    "backend_logo": BACKEND.logo,
                    "api_version": API_VERSION,
                    "recent_limit": RECENT_LIMIT,
                    "emulator_version": version or "unknown",
                    "me": {
                        key: display.get(key)
                        for key in ("user", "account", "alias", "role")
                    },
                    "accounts": [
                        {
                            "account_id": account["account_id"],
                            "alias": account["alias"],
                            "name": account.get("name") or "",
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
                    # Selectable regions are the ones this account enabled.
                    "regions": enabled,
                    "auto_regions": auto_regions,
                    "all_regions": list(REGION_CHOICES),
                    "platform_admin": platform,
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
            return self._json(
                200,
                [
                    dict(
                        node,
                        health=health_snapshot()["nodes"].get(node["name"], {}),
                    )
                    for node in NODES
                ],
            )
        if path == "/api/services":
            return self._json(200, health_snapshot().get("services", {}))
        if path == "/api/buckets":
            return self._json(200, current_buckets())
        if path == "/api/s3":
            return self._json(
                200,
                {"buckets": current_buckets(), "nodes": REGISTRY.node_snapshot()},
            )
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

    def _reset_submit(self) -> None:
        """Set the password a reset link was issued for, then burn the link."""
        form = self._form()
        token = (form.get("token") or "").strip()
        password = form.get("password") or ""
        confirm = form.get("confirm") or ""
        if not token:
            return self._page(
                self._reset_page(errors={"form": "The link is incomplete."}), 400
            )
        if len(password) < 8:
            return self._page(
                self._reset_page(
                    token,
                    {"password": "Password must be at least 8 characters."},
                ),
                400,
            )
        if password != confirm:
            return self._page(
                self._reset_page(token, {"confirm": "The passwords do not match."}),
                400,
            )
        # Read, validate, then burn: a rejected attempt must not spend the link.
        record = read_reset(token)
        if record is None:
            return self._page(
                self._reset_page(
                    errors={"form": "That reset link has expired or was already used."}
                ),
                400,
            )
        user = USERS.get(record.get("user", ""))
        if user is None:
            return self._page(
                self._reset_page(errors={"form": "That account no longer exists."}),
                400,
            )
        if USERS.matches(user["username"], password):
            return self._page(
                self._reset_page(
                    token,
                    {
                        "password": "That is already the password on this account. "
                        "Choose a different one."
                    },
                ),
                400,
            )
        consume_reset(token)
        USERS.set_password(user["username"], password)
        purge_user_sessions(record.get("account", ""), user["username"])
        self.send_response(302)
        self.send_header("Location", "/login?reset=1")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _issue_reset_link(self, username: str) -> None:
        """Mint a one-time reset link for a principal (platform admin only).

        The link is the whole credential, so the raw token is returned here and
        nowhere else — the store keeps only its digest.
        """
        record = USERS.get(username)
        if record is None:
            return self._json(404, {"error": "unknown user"})
        account_id = record.get("account_id", "")
        if not self._can_touch(self._caller(), account_id):
            return self._json(
                403, {"error": "this user belongs to a different account"}
            )
        token = mint_reset(record["username"], account_id)
        base = CONSOLE_URL or ""
        return self._json(
            200,
            {
                "user": record["username"],
                "account": account_id,
                "expires_in": RESET_SECONDS,
                "link": f"{base}/reset?token={token}",
            },
        )

    def _reset_user_password(self, username: str) -> None:
        """Set a new password for a principal who cannot sign in.

        There is no mail transport on this server, so recovery is a local act: a
        platform administrator (or the account's own root user) issues the new
        password here, and every session that principal holds is dropped.
        """
        payload = self._body()
        password = str(payload.get("password") or "")
        if len(password) < 8:
            return self._json(
                400, {"error": "the new password must be at least 8 characters"}
            )
        record = USERS.get(username)
        if record is None:
            return self._json(404, {"error": "unknown user"})
        account_id = record.get("account_id", "")
        if not self._can_touch(self._caller(), account_id):
            return self._json(
                403, {"error": "this user belongs to a different account"}
            )
        if USERS.matches(record["username"], password):
            return self._json(
                400, {"error": "that is already the password on this account"}
            )
        USERS.set_password(record["username"], password)
        purge_user_sessions(account_id, record["username"])
        return self._json(
            200,
            {
                "user": record["username"],
                "account": account_id,
                "sessions_revoked": True,
            },
        )

    def _update_me(self) -> None:
        """Let a signed-in principal change its own name, email and password."""
        info = session_info(self._session_token())
        if not info:
            return self._json(400, {"error": "sign in to change your own account"})
        payload = self._body()
        account = ACCOUNTS.by_ref(info.get("account", "")) or {}
        username = info.get("user", "")
        if not account or username not in (account.get("users") or {}):
            return self._json(400, {"error": "this session has no local account"})
        name = payload.get("name")
        email = payload.get("email")
        current = str(payload.get("current_password") or "")
        new = str(payload.get("new_password") or "")
        if new:
            if len(new) < 8:
                return self._json(
                    400, {"error": "the new password must be at least 8 characters"}
                )
            if USERS.verify(username, current) is None:
                return self._json(
                    403, {"error": "the current password is not correct"}
                )
        if email is not None:
            email = str(email).strip()
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return self._json(
                    400, {"error": "that email address does not look right"}
                )
            USERS.update_email(username, email)
        if name is not None:
            ACCOUNTS.set_name(account["account_id"], str(name).strip())
        if new:
            USERS.set_password(username, new)
        updated = ACCOUNTS.by_ref(account["account_id"]) or {}
        record = USERS.get(username) or {}
        return self._json(
            200,
            {
                "user": username,
                "account": account["account_id"],
                "name": updated.get("name", ""),
                "email": record.get("email") or "",
            },
        )

    def _route_post(self):
        path = urlsplit(self.path).path
        if path == "/signup":
            return self._signup()
        if path == "/forgot":
            return self._forgot_submit()
        if path == "/reset":
            return self._reset_submit()
        if path.startswith("/api"):
            path = self._api_path(path)
        if path == "/api/auth/login":
            return self._auth_login()
        if path == "/api/auth/switch":
            return self._auth_switch()
        if path == "/api/auth/mfa":
            return self._json(
                501, {"error": "MFA enrolment is not implemented yet."}
            )
        if path == "/api/auth/remember":
            # Multi-session opt-in: hand this session's own token to its holder so
            # the browser can switch back to it later. The cookie is the same
            # token; nothing else is disclosed.
            token = self._session_token()
            info = session_info(token) if token else None
            if info is None:
                return self._json(401, {"error": "sign in first"})
            return self._json(
                200,
                {
                    "token": token,
                    "user": info.get("user"),
                    "alias": info.get("alias"),
                    "account": info.get("account"),
                    "role": info.get("role"),
                },
            )
        if path == "/api/me":
            return self._update_me()
        if not self._require_admin():
            return
        if path == "/api/users":
            payload = self._body()
            info = self._caller()
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            role = str(payload.get("role") or "iam").strip().lower()
            email = str(payload.get("email") or "").strip()
            target = ACCOUNTS.by_ref(str(payload.get("account") or info.get("account") or ""))
            if role not in {"root", "iam"}:
                return self._json(400, {"error": "role must be root or iam"})
            if not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
                return self._json(
                    400,
                    {
                        "error": "a username is required: 3-32 letters, digits, "
                        "dot, dash or underscore"
                    },
                )
            if len(password) < 8:
                return self._json(
                    400, {"error": "the password must be at least 8 characters"}
                )
            if target is None or not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "you can only add users to your own account"}
                )
            if USERS.exists(username):
                return self._json(409, {"error": "that username is already taken"})
            principal = ACCOUNTS.add_principal(target["account_id"], username, role)
            if principal is None:
                return self._json(409, {"error": "that username is already taken"})
            USERS.create(username, email, password, target["account_id"], role)
            return self._json(
                200,
                {
                    "user": username,
                    "role": role,
                    "account": target["account_id"],
                    "alias": target["alias"],
                },
            )
        reset = re.fullmatch(r"/api/users/([^/]+)/password", path)
        if reset:
            return self._reset_user_password(unquote(reset.group(1)))
        reset_link = re.fullmatch(r"/api/users/([^/]+)/reset-link", path)
        if reset_link:
            return self._issue_reset_link(unquote(reset_link.group(1)))
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
            elif action == "rotate":
                key, problem = rotate_credentials(
                    account_obj["account_id"], principal["username"]
                )
            else:
                return self._json(400, {"error": f"unknown action: {action}"})
            if problem:
                return self._json(502, {"error": problem})
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
        if path == "/api/s3/object":
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            bucket = str(payload.get("bucket") or "").strip()
            key = str(payload.get("key") or "").strip()
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            if not bucket or not key:
                return self._json(400, {"error": "a bucket and a key are required"})
            result = buckets.put_object(
                bucket,
                key,
                str(payload.get("body") or ""),
                lambda method, target_path, body, headers=None: signed_rest(
                    "s3", target["account_id"], region, method, target_path, body, headers
                ),
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/object-upload":
            # A file from the operator's machine, sent as its own bytes: the body
            # is the object, not base64 inside JSON. S3 stores the Content-Type it
            # is given, which is why the browser's file type is passed through.
            params = parse_qs(urlsplit(self.path).query)
            account = (params.get("account") or [""])[0].strip()
            region = (params.get("region") or [DEFAULT_REGION])[0]
            bucket = (params.get("bucket") or [""])[0].strip()
            key = (params.get("key") or [""])[0]
            info = self._caller()
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
            # Read the body before answering anything: an early return would leave
            # the file in the socket for the next keep-alive request to choke on.
            data = self._read_body()
            if not bucket or not key:
                return self._json(400, {"error": "a bucket and a key are required"})
            if len(data) > MAX_UPLOAD_BYTES:
                return self._json(
                    413,
                    {
                        "error": (
                            f"that file is {len(data)} bytes; this console uploads up to "
                            f"{MAX_UPLOAD_BYTES} in one request"
                        )
                    },
                )
            result = buckets.put_object(
                bucket,
                key,
                data,
                lambda method, target_path, body, headers=None: signed_rest(
                    "s3", target["account_id"], region, method, target_path, body, headers
                ),
                content_type=safe_content_type(self.headers.get("Content-Type", "")),
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region, bucket=bucket),
            )
        if path == "/api/s3/object-copy":
            # CopyObject is a PUT to the destination, so the call is signed where
            # the destination lives - HeadBucket says where that is.
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            bucket = str(payload.get("bucket") or "").strip()
            key = str(payload.get("key") or "").strip()
            destination = str(payload.get("destination") or "").strip()
            destination_key = str(payload.get("destination_key") or "").strip()
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
            if not bucket or not key or not destination:
                return self._json(
                    400, {"error": "a source bucket and key, and a destination bucket, are required"}
                )
            destination_key = destination_key or key
            where = buckets.head_bucket(
                destination,
                lambda method, target_path: signed_rest_raw(
                    "s3", target["account_id"], region, method, target_path
                ),
            )
            if not where.get("ok"):
                return self._json(502, {"error": where.get("error", "could not place the destination")})
            if not where.get("exists"):
                return self._json(
                    400, {"error": f"BucketNotFound: {destination} does not exist"}
                )
            destination_region = where.get("region") or region
            result = buckets.copy_object(
                bucket,
                key,
                destination,
                destination_key,
                lambda method, target_path, body, headers=None: signed_rest(
                    "s3",
                    target["account_id"],
                    destination_region,
                    method,
                    target_path,
                    body,
                    headers,
                ),
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(
                    result,
                    account=target["account_id"],
                    region=destination_region,
                ),
            )
        if path == "/api/s3/empty":
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            bucket = str(payload.get("bucket") or "").strip()
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            if not bucket:
                return self._json(400, {"error": "a bucket is required"})
            result = buckets.empty_bucket(
                bucket,
                lambda method, target_path, body="": signed_rest(
                    "s3", target["account_id"], region, method, target_path, body
                ),
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/bucket-document":
            # One configuration document: save it, or clear it. Clearing is a
            # DELETE where S3 has one and an empty document where it has not,
            # which is knowledge the control owns, not the page.
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            bucket = str(payload.get("bucket") or "").strip()
            document = str(payload.get("document") or "").strip()
            action = str(payload.get("action") or "save").strip()
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
            if not bucket:
                return self._json(400, {"error": "a bucket is required"})
            if document not in buckets.EDITABLE:
                return self._json(
                    400, {"error": f"{document} is not a document this page writes"}
                )
            client = lambda method, target_path, body="", headers=None: signed_rest(  # noqa: E731
                "s3", target["account_id"], region, method, target_path, body, headers
            )
            if action == "clear":
                result = buckets.clear_document(bucket, document, client)
            else:
                text = str(payload.get("body") or "")
                if not text.strip():
                    return self._json(400, {"error": "the document is empty"})
                result = buckets.write_document(bucket, document, text, client)
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/bucket-settings-edit":
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            bucket = str(payload.get("bucket") or "").strip()
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            if not bucket:
                return self._json(400, {"error": "a bucket is required"})
            result = buckets.update_settings(
                bucket,
                payload,
                lambda method, target_path, body="": signed_rest(
                    "s3", target["account_id"], region, method, target_path, body
                ),
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/access-points":
            # The create form, applied as one request: CreateAccessPoint, then the
            # policy the form carries.
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
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
            result = accesspoints.create(
                region, payload, s3control(target["account_id"], region)
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/access-point-delete":
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            name = str(payload.get("name") or "").strip()
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            if not name:
                return self._json(400, {"error": "an access point name is required"})
            result = accesspoints.delete(
                region, name, s3control(target["account_id"], region)
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/access-point-policy-edit":
            # An empty policy deletes it, which is what the console's editor does
            # when you remove the statement.
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            name = str(payload.get("name") or "").strip()
            target = ACCOUNTS.by_ref(account)
            if target is None:
                return self._json(404, {"error": "unknown account"})
            if not self._can_touch(info, target["account_id"]):
                return self._json(
                    403, {"error": "this account is not signed in to that tenancy"}
                )
            if not name:
                return self._json(400, {"error": "an access point name is required"})
            result = accesspoints.write_policy(
                region, name, payload.get("policy"), s3control(target["account_id"], region)
            )
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=target["account_id"], region=region),
            )
        if path == "/api/s3/buckets":
            # The console's create page: one request that applies the whole form.
            payload = self._body()
            info = self._caller()
            account = str(payload.get("account") or info.get("account") or "").strip()
            region = str(payload.get("region") or DEFAULT_REGION).strip()
            name = str(payload.get("bucket") or "").strip()
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
            if not name:
                return self._json(400, {"error": "a bucket name is required"})
            # The suffix of the Account Regional namespace is added server-side,
            # so the name the registry claims is the name the bucket gets.
            name, problem = buckets.resolve_name(payload, region)
            if problem:
                return self._json(400, {"error": problem})
            # The name is claimed before the emulator sees it, exactly as the
            # gateway claims it, so a taken name gets one answer from both paths.
            entry = bucket_owner(name)
            reserved = entry is None
            if entry is None:
                ok, message, code = reserve_across(name, region, target["account_id"])
                if not ok:
                    return self._json(code, {"error": message})
            elif (
                entry.get("account_id") != target["account_id"]
                or entry.get("region") != region
            ):
                return self._json(409, {"error": bucket_taken(name)})
            result = buckets.create(
                region,
                payload,
                lambda method, target_path, body, headers=None: signed_s3(
                    target["account_id"], region, method, target_path, body, headers
                ),
            )
            if result.get("created"):
                OWNERS.record(
                    target["account_id"],
                    region,
                    "s3",
                    name,
                    info.get("user") or "token",
                )
            elif reserved:
                # Nothing was created, so the claim goes back.
                release_across(name)
            return self._json(
                200 if result.get("ok") else 400,
                dict(result, account=account, region=region, service="s3"),
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
            account, principal = ACCOUNTS.create(username)
            if display_name:
                ACCOUNTS.set_name(account["account_id"], display_name)
            USERS.create(
                username, email, password, account["account_id"],
                principal.get("role", "root"),
            )
            _key, problem = create_access_key(account, principal, "primary")
            if problem:
                return self._json(502, {"error": problem})
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
                    403, {"error": "only the platform administrator can disable accounts"}
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
            return self._json(
                200,
                {"account": account["account_id"], "disabled": disabled},
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
            if region not in REGION_CHOICES:
                return self._json(400, {"error": "unknown region"})
            enabled = bool(payload.get("enabled", True))
            current = set(ACCOUNTS.regions_of(target))
            if enabled:
                current.add(region)
            elif region != DEFAULT_REGION:
                current.discard(region)
            account = ACCOUNTS.set_regions(target["account_id"], sorted(current))
            return self._json(
                200,
                {
                    "account": account["account_id"],
                    "regions": ACCOUNTS.regions_of(account),
                },
            )
        if path == "/api/refresh":
            self._body()
            return self._json(200, refresh_registry())
        if path == "/api/reserve":
            payload = self._body()
            name = str(payload.get("name", "")).strip()
            region = str(payload.get("region", DEFAULT_REGION)).strip()
            if not name:
                return self._json(400, {"error": "name required"})
            ok, message, code = reserve_across(name, region)
            if not ok:
                return self._json(code, {"error": message})
            return self._json(201, {"bucket": name, "region": region})
        match = re.fullmatch(r"/api/nodes/([^/]+)/reset", path)
        if match:
            node = node_by_name(match.group(1))
            if not node:
                return self._json(404, {"error": "unknown node"})
            status, _ = node_request(node, "POST", "/_ministack/reset", timeout=30)
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
            return self._json(
                200 if status == 200 else 502, {"node": node["name"], "upstream": status}
            )
        self._json(404, {"error": "not found"})

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
            return self._json(
                200,
                {"deleted": account["account_id"], "alias": account["alias"]},
            )
        match = re.fullmatch(r"/api/buckets/([^/]+)", path)
        if match:
            REGISTRY.release(match.group(1))
            return self._json(200, {"removed": match.group(1)})
        self._json(404, {"error": "not found"})

    def do_GET(self):
        return self._route_get()

    def do_POST(self):
        return self._route_post()

    def do_DELETE(self):
        return self._route_delete()

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
            for region in sorted(set(REGION_CHOICES) | SEEN_REGIONS)
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
        return self._layout("Emuplane federation", body)

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
            for choice in sorted(set(REGION_CHOICES) | SEEN_REGIONS)
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
                    f"<td><code>{html.escape(user.get('access_key_id') or '—')}</code></td>"
                    f"<td>{html.escape(str(user.get('credentials_issued') or '—'))}</td>"
                    "</tr>"
                )
        body = f"""
<h1>Users</h1>
<p class="muted">An account is the tenancy boundary; a principal is an identity
inside one. The account ID lives here as data — it is never configuration.</p>
<table><thead><tr><th>Account ID</th><th>Alias</th><th>Principal</th><th>Role</th>
<th>Access key</th><th>Issued</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="6" class="muted">no accounts yet</td></tr>'}</tbody></table>
<p class="muted">Secrets are not shown here; the signed-in principal sees its own
on the <a href="/">overview</a>.</p>
"""
        return self._layout("Users", body)

    def _s3_page(self) -> str:
        registry = current_buckets()
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
            for name, entry in sorted(registry.items())
        ) or '<tr><td colspan="6" class="muted">no buckets registered</td></tr>'
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
        inventory_title = "Cached inventory"
        inventory_header = (
            "<th>Node</th><th>Health</th><th>Inventory from</th>"
            "<th>Buckets</th><th>Names</th>"
        )
        inventory_note = (
            "An unreachable emulator keeps its last successful inventory; "
            "those rows are marked stale instead of disappearing."
        )
        body = f"""
<h1>S3</h1>
<p class="muted">Bucket names are reserved globally: one registry, one
emulator. The home region is where the bucket was created.</p>
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
    control = ThreadingHTTPServer(("0.0.0.0", EP_PORT), ControlHandler)
    gateway = ThreadingHTTPServer(("0.0.0.0", GATEWAY_PORT), GatewayHandler)
    threading.Thread(target=gateway.serve_forever, daemon=True).start()

    def poller() -> None:
        while True:
            try:
                poll_health()
                refresh_registry()
            except Exception as exc:  # keep the poller alive
                print(f"poller error: {exc}", flush=True)
            time.sleep(POLL_SECONDS)

    threading.Thread(target=poller, daemon=True).start()
    print(
        f"control on :{EP_PORT}, gateway on :{GATEWAY_PORT}, "
        f"{len(NODES)} nodes, bearer token {'set' if stored_token_hash() else 'unset'}",
        flush=True,
    )
    control.serve_forever()


if __name__ == "__main__":
    main()
