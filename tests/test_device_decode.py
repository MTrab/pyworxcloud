"""Tests for fixture-driven device payload decoding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pyworxcloud.utils.capability import DeviceCapability
from pyworxcloud.utils.devices import DeviceHandler


def _load_payload(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["payload"]


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
    ("fixture_path", "protocol"),
    [
        ("52461d2e-918b-4dd6-a04f-b3120f46dfb3/http.json", 1),
        ("9066087f-8591-456c-a75c-43e434b23164/http.json", 0),
        ("9c3a0295-36eb-415f-9bc1-4d41466d4a95/http.json", 0),
        ("e2703c73-4811-4756-a389-bfdc6bbedca9/http.json", 0),
    ],
)
def test_devicehandler_decodes_fixture_payloads(
    fixtures_dir: Path, fixture_path: str, protocol: int
) -> None:
    """Decode sample payloads and verify core mapped fields."""
    payload = _load_payload(fixtures_dir / "data-samples" / fixture_path)
    mower = _build_mower(payload, protocol, "Fixture Mower")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.is_decoded is True
    assert device.protocol == protocol
    assert device.status.id == payload["dat"]["ls"]
    assert device.error.id == payload["dat"]["le"]
    assert device.rainsensor.delay == payload["cfg"]["rd"]
    assert device.schedules["active"] is not None


def test_devicehandler_maps_module_capabilities(fixtures_dir: Path) -> None:
    """Capability flags should be inferred from fixture module payload."""
    payload = _load_payload(
        fixtures_dir / "data-samples" / "52461d2e-918b-4dd6-a04f-b3120f46dfb3/http.json"
    )
    mower = _build_mower(payload, 1, "Vision Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.capabilities.check(DeviceCapability.CUTTING_HEIGHT) is True
    assert device.capabilities.check(DeviceCapability.ACS) is True


def test_devicehandler_raw_data_setter_redecodes_payload(fixtures_dir: Path) -> None:
    """Raw payload updates should trigger re-decoding of status fields."""
    payload = _load_payload(
        fixtures_dir / "data-samples" / "9c3a0295-36eb-415f-9bc1-4d41466d4a95/http.json"
    )
    mower = _build_mower(payload, 0, "Classic Fixture")
    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    modified = json.loads(json.dumps(payload))
    modified["dat"]["ls"] = 34
    modified["dat"]["le"] = 5
    device.raw_data = json.dumps(modified)

    assert device.status.id == 34
    assert device.error.id == 5


def test_protocol1_slots_exposed(fixtures_dir: Path) -> None:
    """All protocol-1 slots should be listed for visual inspection."""
    payload = _load_payload(
        fixtures_dir / "data-samples" / "52461d2e-918b-4dd6-a04f-b3120f46dfb3/http.json"
    )
    mower = _build_mower(payload, 1, "Slots Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert isinstance(device.schedules["slots"], list)
    assert len(device.schedules["slots"]) == len(payload["cfg"]["sc"]["slots"])
    assert all(slot["source"].startswith("protocol") for slot in device.schedules["slots"])


def test_devicehandler_exposes_raw_cfg_dat(fixtures_dir: Path) -> None:
    """DeviceHandler keeps cfg/dat structures accessible."""
    payload = _load_payload(
        fixtures_dir / "data-samples" / "52461d2e-918b-4dd6-a04f-b3120f46dfb3/http.json"
    )
    mower = _build_mower(payload, 1, "Fixture Mower")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.raw_cfg is not None
    assert device.raw_dat is not None
    assert device.raw_cfg["id"] == payload["cfg"]["id"]
    assert device.raw_dat["conn"] == payload["dat"]["conn"]
    assert device.module_config is not None
    assert device.module_status is not None
    assert device.raindelay_active == bool(str(payload["dat"]["rain"]["s"]) == "1")
