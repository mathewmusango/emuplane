"""Amazon OpenSearch Service on the wire: all 13 advertised operations, REST/JSON.

Paths are under `/2021-01-01/`. A domain is keyed by name, so a stable domain
carries the read/update/tag tests while a create or delete test makes its own.
With the dataplane disabled the emulator reports a stub endpoint, so the
management plane is fully exercisable without a container.
"""

from __future__ import annotations

import json
import time
from urllib.parse import quote

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
BASE = "/2021-01-01"
JSON_TYPE = {"Content-Type": "application/json"}
DOMAIN = "ops-search"


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "opensearch", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status == 200, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, method: str, path: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, method, path, payload)
    assert status >= 400, f"{method} {path} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def ensure_domain(endpoint, name: str = DOMAIN) -> dict:
    status, text = call(endpoint, "POST", f"{BASE}/domain", {"DomainName": name})
    assert status == 200 or "ResourceAlreadyExistsException" in text, text[:300]
    return ok(endpoint, "GET", f"{BASE}/domain/{name}")["DomainStatus"]


def tags(endpoint, arn: str) -> list[dict]:
    return ok(endpoint, "GET", f"{BASE}/tags?arn={quote(arn, safe='')}")["TagList"]


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------


def test_create_domain_is_read_back(endpoint):
    name = f"ops{time.time_ns() % 100000000}"
    created = ok(endpoint, "POST", f"{BASE}/domain", {"DomainName": name})["DomainStatus"]
    assert created["DomainName"] == name
    assert created["Created"] is True


def test_describe_domain_reads_the_domain(endpoint):
    described = ensure_domain(endpoint)
    assert described["DomainName"] == DOMAIN
    assert described["Processing"] is False


def test_describe_domains_lists_the_domain(endpoint):
    ensure_domain(endpoint)
    listed = ok(endpoint, "POST", f"{BASE}/domain-info", {"DomainNames": [DOMAIN]})["DomainStatusList"]
    assert DOMAIN in {item["DomainName"] for item in listed}


def test_delete_domain_removes_the_domain_it_created(endpoint):
    name = f"opsdel{time.time_ns() % 10000000}"
    ok(endpoint, "POST", f"{BASE}/domain", {"DomainName": name})
    deleted = ok(endpoint, "DELETE", f"{BASE}/domain/{name}")["DomainStatus"]
    assert deleted["Deleted"] is True
    refused(endpoint, "GET", f"{BASE}/domain/{name}", code="ResourceNotFoundException")


def test_list_domain_names_lists_the_domain(endpoint):
    ensure_domain(endpoint)
    names = [item["DomainName"] for item in ok(endpoint, "GET", f"{BASE}/domain")["DomainNames"]]
    assert DOMAIN in names


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_update_domain_config_changes_the_cluster(endpoint):
    ensure_domain(endpoint)
    cluster = {"InstanceType": "r6g.large.search", "InstanceCount": 3}
    ok(endpoint, "POST", f"{BASE}/domain/{DOMAIN}/config", {"ClusterConfig": cluster})
    config = ok(endpoint, "GET", f"{BASE}/domain/{DOMAIN}/config")["DomainConfig"]
    assert config["ClusterConfig"]["Options"]["InstanceCount"] == 3


def test_describe_domain_config_reads_the_config(endpoint):
    ensure_domain(endpoint)
    config = ok(endpoint, "GET", f"{BASE}/domain/{DOMAIN}/config")["DomainConfig"]
    assert "EngineVersion" in config
    assert config["ClusterConfig"]["Status"]["State"] == "Active"


def test_describe_domain_change_progress_reports_completed(endpoint):
    ensure_domain(endpoint)
    progress = ok(endpoint, "GET", f"{BASE}/domain/{DOMAIN}/progress")["ChangeProgressStatus"]
    assert progress["Status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def test_list_versions_lists_supported_versions(endpoint):
    versions = ok(endpoint, "GET", f"{BASE}/versions")["Versions"]
    assert versions


def test_get_compatible_versions_lists_a_source(endpoint):
    compatible = ok(endpoint, "GET", f"{BASE}/compatibleVersions")["CompatibleVersions"]
    assert compatible
    assert "SourceVersion" in compatible[0]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_add_tags_is_read_back_by_list_tags(endpoint):
    arn = ensure_domain(endpoint)["ARN"]
    ok(endpoint, "POST", f"{BASE}/tags", {"ARN": arn, "TagList": [{"Key": "env", "Value": "ops"}]})
    assert {"Key": "env", "Value": "ops"} in tags(endpoint, arn)


def test_list_tags_lists_the_tag(endpoint):
    arn = ensure_domain(endpoint)["ARN"]
    ok(endpoint, "POST", f"{BASE}/tags", {"ARN": arn, "TagList": [{"Key": "team", "Value": "platform"}]})
    assert {"Key": "team", "Value": "platform"} in tags(endpoint, arn)


def test_remove_tags_removes_the_key_it_names(endpoint):
    arn = ensure_domain(endpoint)["ARN"]
    ok(endpoint, "POST", f"{BASE}/tags", {"ARN": arn, "TagList": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "POST", f"{BASE}/tags-removal", {"ARN": arn, "TagKeys": ["doomed"]})
    assert "doomed" not in {tag["Key"] for tag in tags(endpoint, arn)}
