"""IoT Wireless on the wire: the one advertised operation, `GetPositionEstimate`.

The service is REST-JSON under the `iotwireless` credential scope at
`POST /position-estimate`. The response body is the raw GeoJSON payload (the
output shape declares a blob), not a JSON envelope.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PATH = "/position-estimate"
JSON_TYPE = {"Content-Type": "application/json"}


def test_get_position_estimate_resolves_an_ip(endpoint):
    body = json.dumps({"Ip": {"IpAddress": "1.1.1.1"}})
    status, text = signed.request(endpoint, "iotwireless", ACCOUNT, REGION, "POST", PATH, body, JSON_TYPE)
    assert status == 200, text[:400]
    payload = json.loads(text)
    assert payload["type"] == "Point"
    assert len(payload["coordinates"]) == 2
    assert payload["properties"]["horizontalAccuracy"] > 0
    assert payload["properties"]["timestamp"]
