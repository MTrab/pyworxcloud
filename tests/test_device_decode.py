"""Tests for fixture-driven device payload decoding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence, Tuple

import pytest
from zoneinfo import ZoneInfo

from pyworxcloud.utils.capability import DeviceCapability
from pyworxcloud.utils.devices import DeviceHandler
from tests.fixture_utils import fixture_paths, load_fixture_payloads


def _load_payloads(path: Path) -> Sequence[dict[str, Any]]:
    return load_fixture_payloads(path)


def _first_payload(path: Path) -> dict[str, Any]:
    payloads = _load_payloads(path)
    assert payloads
    return payloads[0]


def _protocol_from_payload(payload: dict[str, Any]) -> int:
    sc = payload.get("cfg", {}).get("sc", {})
    return 1 if sc.get("slots") else 0


HTTP_FIXTURES: Tuple[tuple[Path, dict[str, Any]], ...] = tuple(
    (path, _first_payload(path)) for path in fixture_paths("http.json")
)


def _find_http_fixture(predicate) -> tuple[Path, dict[str, Any]]:
    for path, payload in HTTP_FIXTURES:
        if predicate(payload):
            return path, payload
    pytest.skip("No HTTP fixture matches the requested criteria")


def _build_mower(payload: dict[str, Any], protocol: int, name: str) -> dict[str, Any]:
    dat = payload.get("dat", {})
    cfg = payload.get("cfg", {})
    return {
        "name": name,
        "model": {"friendly_name": "Fixture", "code": "FX"},
        "protocol": protocol,
        "serial_number": cfg.get("sn", "SERIAL-FIXTURE"),
        "uuid": dat.get("uuid", "UUID-FIXTURE"),
        "mac_address": dat.get("mac"),
        "time_zone": cfg.get("tz", "UTC"),
        "warranty_expires_at": None,
        "warranty_registered": False,
        "mqtt_topics": {"command_in": "in/topic", "command_out": "out/topic"},
        "last_status": {"payload": payload},
    }


@pytest.mark.parametrize(
    ("path", "payload", "protocol"),
    tuple(
        (path, payload, _protocol_from_payload(payload))
        for path, payload in HTTP_FIXTURES
    ),
)
def test_devicehandler_decodes_fixture_payloads(
    path: Path, payload: dict[str, Any], protocol: int
) -> None:
    """Decode sample payloads and verify core mapped fields."""
    mower = _build_mower(payload, protocol, "Fixture Mower")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.is_decoded is True
    assert device.protocol == protocol
    assert device.status.id == payload["dat"]["ls"]
    assert device.error.id == payload["dat"]["le"]
    assert device.rainsensor.delay == payload["cfg"]["rd"]
    assert device.schedules["active"] is not None


def test_devicehandler_maps_module_capabilities() -> None:
    """Capability flags should be inferred from fixture module payload."""
    _, payload = _find_http_fixture(lambda p: bool(p.get("cfg", {}).get("modules")))
    mower = _build_mower(payload, 1, "Vision Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.capabilities.check(DeviceCapability.CUTTING_HEIGHT) is True
    assert device.capabilities.check(DeviceCapability.ACS) is True


def test_devicehandler_raw_data_setter_redecodes_payload() -> None:
    """Raw payload updates should trigger re-decoding of status fields."""
    _, payload = _find_http_fixture(
        lambda p: isinstance(p.get("dat", {}).get("ls"), int)
    )
    mower = _build_mower(payload, 0, "Classic Fixture")
    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    modified = json.loads(json.dumps(payload))
    modified["dat"]["ls"] = 34
    modified["dat"]["le"] = 5
    device.raw_data = json.dumps(modified)

    assert device.status.id == 34
    assert device.error.id == 5


def test_protocol1_slots_exposed() -> None:
    """All protocol-1 slots should be listed for visual inspection."""
    _, payload = _find_http_fixture(
        lambda p: bool(p.get("cfg", {}).get("sc", {}).get("slots"))
    )
    mower = _build_mower(payload, 1, "Slots Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert isinstance(device.schedules["slots"], list)
    assert len(device.schedules["slots"]) == len(payload["cfg"]["sc"]["slots"])
    assert all(
        slot["source"].startswith("protocol") for slot in device.schedules["slots"]
    )


def test_devicehandler_exposes_raw_cfg_dat() -> None:
    """DeviceHandler keeps cfg/dat structures accessible."""
    _, payload = _find_http_fixture(lambda p: bool(p.get("cfg", {}).get("modules")))
    mower = _build_mower(payload, 1, "Fixture Mower")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.raw_cfg is not None
    assert device.raw_dat is not None
    assert device.raw_cfg["id"] == payload["cfg"]["id"]
    assert device.raw_dat["conn"] == payload["dat"]["conn"]
    assert device.module_config is not None
    assert device.module_status is not None
    assert device.raindelay_active == bool(str(payload["dat"]["rain"]["s"]) == "1")


def test_devicehandler_updates_battery_cycle_current_from_live_nr() -> None:
    """Realtime battery totals should recalculate the current cycle count."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-BATTERY",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "12:00:00",
            "dt": "11/03/2026",
            "tz": "UTC",
        },
        "dat": {
            "uuid": "UUID-BATTERY",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "bt": {"t": 20, "v": 20.1, "p": 95, "c": 0, "nr": 211},
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Battery Fixture")
    mower["battery_charge_cycles"] = 209
    mower["battery_charge_cycles_reset"] = 0
    mower["battery_charge_cycles_reset_at"] = None

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.battery["cycles"] == {
        "total": 211,
        "current": 211,
        "reset_at": 0,
        "reset_time": None,
    }


def test_devicehandler_uses_device_timezone_when_instance_timezone_is_missing() -> None:
    """Schedule timestamps should fall back to device timezone before UTC."""
    _, payload = _find_http_fixture(
        lambda p: bool(p.get("cfg", {}).get("tz"))
        and bool(p.get("cfg", {}).get("sc", {}).get("slots"))
    )
    mower = _build_mower(payload, 1, "Timezone Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz=None)

    next_schedule = device.schedules["next_schedule_start"]
    assert next_schedule is not None
    assert next_schedule.tzinfo == ZoneInfo(payload["cfg"]["tz"])


MQTT_FIXTURES = tuple(fixture_paths("mqtt.json"))


def test_devicehandler_handles_mqtt_payloads() -> None:
    """MQTT fixtures decode the same way as HTTP responses."""
    assert MQTT_FIXTURES, "No MQTT fixtures were discovered"

    for fixture_path in MQTT_FIXTURES:
        payloads = _load_payloads(fixture_path)
        assert payloads

        for index, payload in enumerate(payloads):
            mower = _build_mower(payload, 1, f"MQTT Fixture {index}")
            device = DeviceHandler(api=object(), mower=mower, tz="UTC")

            assert device.is_decoded is True
            assert device.protocol == 1
            expected_mac = payload["dat"].get("mac")
            if expected_mac is not None:
                assert device.raw_dat["mac"] == expected_mac
            else:
                assert payload["dat"].get("uuid")
                assert device.uuid == payload["dat"]["uuid"]
            sc_slots = payload["cfg"]["sc"].get("slots", [])
            slots = device.schedules.get("slots", [])
            assert slots
            if sc_slots:
                assert len(slots) == len(sc_slots)
                assert any(slot["source"].startswith("protocol") for slot in slots)
            else:
                assert any(slot.get("source") for slot in slots)
