"""Amazon Location (trackers) on the wire: every advertised operation, driven through REST.

The client is named ``location`` but signs with the ``geo`` credential scope, which is what
the emulator routes on. A tracker created here is left in place, with its device positions —
a write is proven by a read. DeleteTracker creates a tracker of its own and removes that.

Creates are name-addressed, so a lab sweep that re-runs finds what an earlier sweep left.
The shared tracker is created with ``AccuracyBased`` filtering and every update carries a
horizontal accuracy of 0: the documented default threshold then keeps every sample, so
"the latest" is this run's sample however soon a second sweep lands.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON = {"Content-Type": "application/json"}

# Stable names, so a second sweep finds the trackers the first one deliberately left.
SHARED = "ops-location-shared"
SECOND = "ops-location-second"
DELETED = "ops-location-deleted"
DESCRIPTION = "updated by the emuplane operations suite"

BATCH_DEVICE = "ops-location-batch"
LATEST_DEVICE = "ops-location-latest"
DEVICE_A = "ops-location-a"
DEVICE_B = "ops-location-b"
ABSENT_DEVICE = "ops-location-absent"
HISTORY_DEVICE = "ops-location-history"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, method: str, path: str, body: dict | None = None):
    payload = json.dumps(body) if body is not None else ""
    return signed.request(endpoint, "geo", ACCOUNT, REGION, method, path, payload, JSON)


def ok(endpoint, method: str, path: str, body: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, body)
    assert status == 200, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def tracker_path(name: str) -> str:
    return "/tracking/v0/trackers/" + quote(name, safe="")


def device_path(name: str, device_id: str, tail: str) -> str:
    return f"{tracker_path(name)}/devices/{quote(device_id, safe='')}/{tail}"


def new_tracker(name: str) -> dict:
    return {
        "TrackerName": name,
        "Description": "emuplane operations suite",
        "PositionFiltering": "AccuracyBased",
        "Tags": {"suite": "control"},
    }


def tracker_names(endpoint, max_results: int | None = None) -> list[str]:
    """Every page of ListTrackers, following NextToken to the end."""
    names: list[str] = []
    token = None
    for _ in range(200):
        body: dict = {}
        if max_results is not None:
            body["MaxResults"] = max_results
        if token:
            body["NextToken"] = token
        page = ok(endpoint, "POST", "/tracking/v0/list-trackers", body)
        names.extend(entry["TrackerName"] for entry in page["Entries"])
        token = page.get("NextToken")
        if not token:
            return names
    raise AssertionError("ListTrackers did not end within 200 pages")


def ensure_tracker(endpoint, name: str) -> None:
    """Find-or-create: the name is the address, so a re-run meets the tracker it left."""
    if name in tracker_names(endpoint):
        return
    status, text = call(endpoint, "POST", "/tracking/v0/trackers", new_tracker(name))
    # A concurrent sweep's create is the tracker we want.
    assert status == 200 or "ConflictException" in text, (
        f"CreateTracker answered {status}: {text[:400]}"
    )
    assert name in tracker_names(endpoint)


def describe(endpoint, name: str) -> dict:
    return ok(endpoint, "GET", tracker_path(name))


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    """The model's iso8601 wire form — millisecond precision with `Z`, which is what
    Location stores and emits, so a sample read back compares equal to the one sent."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def parsed(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def sample(device_id: str, moment: datetime, position: list[float], **extra) -> dict:
    """One DevicePositionUpdate. An accuracy of 0 keeps it under AccuracyBased."""
    return dict(
        {
            "DeviceId": device_id,
            "SampleTime": iso(moment),
            "Position": position,
            "Accuracy": {"Horizontal": 0},
        },
        **extra,
    )


def push(endpoint, tracker: str, *updates: dict) -> dict:
    return ok(
        endpoint, "POST", f"{tracker_path(tracker)}/positions", {"Updates": list(updates)}
    )


# ---------------------------------------------------------------------------
# Tracker control plane
# ---------------------------------------------------------------------------


def test_create_tracker_is_read_back_by_list_and_describe(s3_endpoint):
    status, text = call(
        s3_endpoint, "POST", "/tracking/v0/trackers", new_tracker(SHARED)
    )
    if status == 200:
        answer = json.loads(text)
        assert answer["TrackerName"] == SHARED
        assert answer["TrackerArn"].endswith(f"tracker/{SHARED}")
        assert answer["CreateTime"].endswith("Z")
    else:
        # A re-run meets the tracker it created before, addressed by its own name.
        assert status == 409 and "ConflictException" in text, text[:400]
    assert SHARED in tracker_names(s3_endpoint)
    assert describe(s3_endpoint, SHARED)["TrackerName"] == SHARED


def test_describe_tracker_reports_the_stored_settings(s3_endpoint):
    ensure_tracker(s3_endpoint, SHARED)
    answer = describe(s3_endpoint, SHARED)
    assert answer["TrackerArn"] == f"arn:aws:geo:{REGION}:{ACCOUNT}:tracker/{SHARED}"
    assert answer["PricingPlan"] == "RequestBasedUsage"
    assert answer["PositionFiltering"] == "AccuracyBased"
    assert answer["Tags"] == {"suite": "control"}
    assert isinstance(answer["Description"], str)
    assert isinstance(answer["EventBridgeEnabled"], bool)
    assert answer["CreateTime"].endswith("Z") and answer["UpdateTime"].endswith("Z")


def test_update_tracker_is_read_back_by_describe(s3_endpoint):
    ensure_tracker(s3_endpoint, SHARED)
    before = describe(s3_endpoint, SHARED)
    answer = ok(
        s3_endpoint,
        "PATCH",
        tracker_path(SHARED),
        {"Description": DESCRIPTION, "EventBridgeEnabled": True},
    )
    assert answer["TrackerName"] == SHARED
    assert answer["TrackerArn"] == before["TrackerArn"]
    after = describe(s3_endpoint, SHARED)
    assert after["Description"] == DESCRIPTION
    assert after["EventBridgeEnabled"] is True
    assert after["TrackerArn"] == before["TrackerArn"]
    assert parsed(after["UpdateTime"]) >= parsed(before["UpdateTime"])


def test_list_trackers_pages_through_every_entry(s3_endpoint):
    ensure_tracker(s3_endpoint, SHARED)
    # A second tracker is what makes MaxResults 1 a real second page.
    ensure_tracker(s3_endpoint, SECOND)
    names = tracker_names(s3_endpoint)
    assert SHARED in names and SECOND in names
    assert names == sorted(names)
    assert len(names) == len(set(names))
    # MaxResults 1 walks the same total order a page at a time.
    paged = tracker_names(s3_endpoint, max_results=1)
    assert len(paged) >= 2
    assert paged == names
    entry = next(
        row
        for row in ok(s3_endpoint, "POST", "/tracking/v0/list-trackers")["Entries"]
        if row["TrackerName"] == SHARED
    )
    assert entry["PricingPlan"] == "RequestBasedUsage"
    assert isinstance(entry["Description"], str)
    assert entry["CreateTime"].endswith("Z")


def test_delete_tracker_removes_the_tracker_it_created(s3_endpoint):
    status, text = call(
        s3_endpoint, "POST", "/tracking/v0/trackers", new_tracker(DELETED)
    )
    # A sweep that stopped before its delete left the target behind.
    assert status == 200 or "ConflictException" in text, (
        f"CreateTracker answered {status}: {text[:400]}"
    )
    assert ok(s3_endpoint, "DELETE", tracker_path(DELETED)) == {}
    status, text = call(s3_endpoint, "GET", tracker_path(DELETED))
    assert status == 404, text[:300]
    assert "ResourceNotFoundException" in text
    assert DELETED not in tracker_names(s3_endpoint)


# ---------------------------------------------------------------------------
# Device positions
# ---------------------------------------------------------------------------


def test_batch_update_device_position_is_read_back_by_get_device_position(s3_endpoint):
    ensure_tracker(s3_endpoint, SHARED)
    moment = now()
    position = [-0.1276, 51.5072]
    answer = push(
        s3_endpoint,
        SHARED,
        sample(
            BATCH_DEVICE, moment, position, PositionProperties={"source": "control-suite"}
        ),
    )
    assert answer["Errors"] == []
    latest = ok(s3_endpoint, "GET", device_path(SHARED, BATCH_DEVICE, "positions/latest"))
    assert latest["DeviceId"] == BATCH_DEVICE
    assert latest["SampleTime"] == iso(moment)
    assert latest["Position"] == position
    assert latest["PositionProperties"] == {"source": "control-suite"}


def test_get_device_position_returns_the_latest_sample(s3_endpoint):
    ensure_tracker(s3_endpoint, SHARED)
    moment = now()
    position = [-1.5, 52.0]
    assert push(s3_endpoint, SHARED, sample(LATEST_DEVICE, moment, position))["Errors"] == []
    latest = ok(s3_endpoint, "GET", device_path(SHARED, LATEST_DEVICE, "positions/latest"))
    assert latest["DeviceId"] == LATEST_DEVICE
    assert latest["SampleTime"] == iso(moment)
    assert latest["Position"] == position
    assert latest["ReceivedTime"].endswith("Z")
    # A device that has never reported is a 404, not a position with no sample.
    status, text = call(
        s3_endpoint, "GET", device_path(SHARED, ABSENT_DEVICE, "positions/latest")
    )
    assert status == 404, text[:300]
    assert "ResourceNotFoundException" in text
    assert "records not found" in text


def test_batch_get_device_position_returns_the_devices_it_found(s3_endpoint):
    ensure_tracker(s3_endpoint, SHARED)
    moment = now()
    assert push(
        s3_endpoint,
        SHARED,
        sample(DEVICE_A, moment, [10.0, 60.0]),
        sample(DEVICE_B, moment, [11.0, 61.0]),
    )["Errors"] == []
    answer = ok(
        s3_endpoint,
        "POST",
        f"{tracker_path(SHARED)}/get-positions",
        {"DeviceIds": [DEVICE_A, DEVICE_B, ABSENT_DEVICE]},
    )
    # Request order, and a device without a position is left out rather than errored.
    assert [row["DeviceId"] for row in answer["DevicePositions"]] == [DEVICE_A, DEVICE_B]
    assert [row["SampleTime"] for row in answer["DevicePositions"]] == [iso(moment)] * 2
    assert [row["Position"] for row in answer["DevicePositions"]] == [
        [10.0, 60.0],
        [11.0, 61.0],
    ]
    assert answer["Errors"] == []


def test_get_device_position_history_returns_the_window_in_order(s3_endpoint):
    ensure_tracker(s3_endpoint, SHARED)
    # Three samples one second apart, so the window names this run's data and not an
    # earlier sweep's: history accumulates for the life of the tracker.
    base = now()
    moments = [base + timedelta(seconds=offset) for offset in range(3)]
    positions = [[10.0 + step * 0.001, 60.0 + step * 0.001] for step in range(3)]
    updates = [
        sample(HISTORY_DEVICE, moment, position)
        for moment, position in zip(moments, positions)
    ]
    assert push(s3_endpoint, SHARED, *updates)["Errors"] == []
    end = iso(base + timedelta(seconds=3))
    answer = ok(
        s3_endpoint,
        "POST",
        device_path(SHARED, HISTORY_DEVICE, "list-positions"),
        {"StartTimeInclusive": iso(base), "EndTimeExclusive": end},
    )
    rows = answer["DevicePositions"]
    times = [row["SampleTime"] for row in rows]
    expected = [iso(moment) for moment in moments]
    assert times == sorted(times)
    assert all(iso(base) <= text < end for text in times)
    ours = [row for row in rows if row["SampleTime"] in expected]
    assert [row["SampleTime"] for row in ours] == expected
    assert [row["Position"] for row in ours] == positions
    assert rows[-1]["SampleTime"] == expected[-1]
    assert rows[-1]["Position"] == positions[-1]
