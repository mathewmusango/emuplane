#!/usr/bin/env python3
"""Per-node replication agent for the MiniStack federation.

Each agent keeps the full hash-chained ledger of membership and bucket
ownership events and gossips it to its peers (anti-entropy every few seconds).
Agents never hold AWS data: MiniStack stays the source of truth for objects.

Modes are chosen by the control plane (`MINISTACK_CONTROL_MODE`):

  central  agents are ignored; the control plane keeps its own registry
  mesh     accept locally, replicate asynchronously (eventual consistency;
           a partition can register the same name twice, reported as conflict)
  quorum   a reservation is committed only after a majority of agents ack;
           with two nodes a majority is both, so a lost node means no writes

No third-party dependencies: the image is stock `python:3.13-alpine`.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

NODE_NAME = os.environ.get("NODE_NAME", "node")
NODE_REGION = os.environ.get("NODE_REGION", "us-east-1")
ACCOUNT_ID = (
    os.environ.get("MINISTACK_ACCOUNT_ID", "")
    or os.environ.get("NODE_ACCOUNT_ID", "")
).strip()
NODE_ACCOUNT = ACCOUNT_ID
MINISTACK_ENDPOINT = os.environ.get("MINISTACK_ENDPOINT", "")
LEDGER_FILE = os.environ.get("LEDGER_FILE", "/var/lib/ministack/ledger/ledger.json")
AGENT_URL = os.environ.get(
    "AGENT_URL", f"http://core-ministack-agent-{NODE_NAME}:8080"
)
CONTROL_URL = os.environ.get(
    "CONTROL_URL", "http://core-ministack-control:8080"
).rstrip("/")
JOIN_TOKEN = os.environ.get("MINISTACK_JOIN_TOKEN", "").strip()
PEERS = [
    peer.strip()
    for peer in os.environ.get("PEERS", "").split(",")
    if peer.strip()
]
DISCOVERED: list[str] = []
AGENT_PORT = int(os.environ.get("AGENT_PORT", "8080"))
MESH_TOKEN = os.environ.get("MINISTACK_MESH_TOKEN", "").strip()
POLL_SECONDS = int(os.environ.get("AGENT_POLL_SECONDS", "5"))

HOP = {"content-length", "host"}


def canonical(event: dict) -> bytes:
    payload = {key: event[key] for key in event if key != "hash"}
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def digest(event: dict) -> str:
    return hashlib.sha256(canonical(event)).hexdigest()


class Ledger:
    def __init__(self, path: str, origin: str) -> None:
        self.path = path
        self.origin = origin
        self.lock = threading.Lock()
        self.events: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                self.events = json.load(handle).get("events", [])
        except (OSError, json.JSONDecodeError):
            self.events = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"events": self.events}, handle, indent=2)
        os.replace(tmp, self.path)

    def height(self, origin: str) -> int:
        return sum(1 for event in self.events if event["node"] == origin)

    def _tail(self, origin: str) -> dict | None:
        for event in reversed(self.events):
            if event["node"] == origin:
                return event
        return None

    def append(self, kind: str, bucket: str, region: str = "", account: str = "") -> dict:
        with self.lock:
            tail = self._tail(self.origin)
            event = {
                "seq": (tail["seq"] + 1) if tail else 1,
                "prev": tail["hash"] if tail else "GENESIS",
                "node": self.origin,
                "type": kind,
                "bucket": bucket,
                "region": region,
                "account": account,
                "ts": time.time(),
            }
            event["hash"] = digest(event)
            self.events.append(event)
            self._save()
            return event

    def merge(self, incoming: list[dict]) -> int:
        added = 0
        with self.lock:
            known = {(event["node"], event["seq"]) for event in self.events}
            for event in sorted(incoming, key=lambda item: (item["node"], item["seq"])):
                key = (event.get("node"), event.get("seq"))
                if key in known:
                    continue
                if digest(event) != event.get("hash"):
                    continue
                if self.height(key[0]) != key[1] - 1:
                    continue
                tail = self._tail(key[0])
                expected = tail["hash"] if tail else "GENESIS"
                if event.get("prev") != expected:
                    continue
                self.events.append(event)
                known.add(key)
                added += 1
            if added:
                self._save()
        return added

    def state(self) -> dict:
        with self.lock:
            events = sorted(self.events, key=lambda item: (item["ts"], item["node"], item["seq"]))
            buckets: dict[str, dict] = {}
            conflicts: set[str] = set()
            for event in events:
                name = event["bucket"]
                if event["type"] == "bucket.create":
                    if name in buckets:
                        conflicts.add(name)
                    else:
                        buckets[name] = {
                            "region": event.get("region", ""),
                            "node": event["node"],
                            "account_id": event.get("account", ""),
                            "last_seen": time.strftime(
                                "%Y-%m-%d %H:%M:%SZ", time.gmtime(event["ts"])
                            ),
                            "stale": False,
                        }
                elif event["type"] == "bucket.delete":
                    buckets.pop(name, None)
                    conflicts.discard(name)
            heights: dict[str, int] = {}
            for event in self.events:
                heights[event["node"]] = max(heights.get(event["node"], 0), event["seq"])
            return {
                "buckets": buckets,
                "conflicts": sorted(conflicts),
                "heights": heights,
                "events": len(self.events),
            }

    def snapshot(self) -> list[dict]:
        with self.lock:
            return list(self.events)


LEDGER = Ledger(LEDGER_FILE, NODE_NAME)


def peer_request(peer: str, method: str, path: str, payload: dict | None = None):
    url = urlsplit(peer)
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


def control_request(method: str, path: str, payload: dict | None = None):
    url = urlsplit(CONTROL_URL)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=4)
    headers = {"Host": f"{url.hostname}:{url.port or 80}"}
    if JOIN_TOKEN:
        headers["X-Join-Token"] = JOIN_TOKEN
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, response.read()
    except OSError:
        return 0, b""
    finally:
        conn.close()


def register() -> None:
    status, body = control_request(
        "POST",
        "/api/v1/nodes/register",
        {
            "name": NODE_NAME,
            "region": NODE_REGION,
            "account_id": ACCOUNT_ID,
            "endpoint": MINISTACK_ENDPOINT,
            "agent": AGENT_URL,
        },
    )
    if status not in (200, 201):
        detail = body.decode(errors="replace")[:120]
        print(f"register failed: HTTP {status} {detail}", flush=True)


def discover_peers() -> list[str]:
    status, body = control_request("GET", "/api/v1/nodes/discovery")
    if status != 200:
        return []
    try:
        nodes = json.loads(body).get("nodes", [])
    except json.JSONDecodeError:
        return []
    return [
        node["agent"]
        for node in nodes
        if node.get("name") != NODE_NAME and node.get("agent")
    ]


def sync_once() -> None:
    global DISCOVERED
    discovered = discover_peers()
    DISCOVERED = discovered or PEERS
    for peer in DISCOVERED:
        status, body = peer_request(peer, "GET", "/events")
        if status != 200:
            continue
        try:
            events = json.loads(body).get("events", [])
        except json.JSONDecodeError:
            continue
        LEDGER.merge(events)


def sync_loop() -> None:
    while True:
        try:
            register()
            sync_once()
        except Exception as exc:  # keep the loop alive
            print(f"sync error: {exc}", flush=True)
        time.sleep(POLL_SECONDS)


class AgentHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"agent: {fmt % args}", flush=True)

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def _authorized(self) -> bool:
        if not MESH_TOKEN:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {MESH_TOKEN}"

    def do_GET(self):
        if self.path == "/health":
            return self._json(
                200,
                {
                    "node": NODE_NAME,
                    "region": NODE_REGION,
                    "account_id": NODE_ACCOUNT,
                    "endpoint": MINISTACK_ENDPOINT,
                    "peer_count": len(DISCOVERED) or len(PEERS),
                    "events": len(LEDGER.snapshot()),
                },
            )
        if self.path == "/events":
            return self._json(200, {"events": LEDGER.snapshot()})
        if self.path == "/state":
            return self._json(200, LEDGER.state())
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return self._json(401, {"error": "mesh token required"})
        payload = self._body()
        if self.path == "/reserve":
            name = str(payload.get("bucket", "")).strip()
            region = str(payload.get("region", NODE_REGION)).strip()
            if not name:
                return self._json(400, {"error": "bucket required"})
            if name in LEDGER.state()["buckets"]:
                return self._json(409, {"error": "bucket already registered"})
            event = LEDGER.append("bucket.create", name, region, NODE_ACCOUNT)
            return self._json(201, {"event": event})
        if self.path == "/release":
            name = str(payload.get("bucket", "")).strip()
            if not name:
                return self._json(400, {"error": "bucket required"})
            event = LEDGER.append("bucket.delete", name)
            return self._json(200, {"event": event})
        if self.path == "/merge":
            return self._json(200, {"added": LEDGER.merge(payload.get("events", []))})
        self._json(404, {"error": "not found"})


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
    threading.Thread(target=sync_loop, daemon=True).start()
    print(
        f"agent {NODE_NAME} ({NODE_REGION}) on :{AGENT_PORT}, "
        f"{len(DISCOVERED) or len(PEERS)} peers, token {'on' if MESH_TOKEN else 'off'}",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", AGENT_PORT), AgentHandler).serve_forever()


if __name__ == "__main__":
    main()
