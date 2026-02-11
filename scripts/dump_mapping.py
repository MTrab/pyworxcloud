#!/usr/bin/env python3
"""Dump decoded mappings for each fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyworxcloud.utils.devices import DeviceHandler


def _resolve_fixtures() -> list[Path]:
    project_root = Path(__file__).resolve().parents[1]
    fixtures = project_root / "tests" / "fixtures" / "data-samples"
    if not fixtures.exists():
        fixtures = project_root / "code-ref" / "data-samples"
    if not fixtures.exists():
        raise SystemExit("No fixtures directory found")
    return sorted(fixtures.glob("**/http.json"))


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


def _capture_device_snapshot(device: DeviceHandler) -> dict[str, Any]:
    return {
        "status": dict(device.status),
        "error": dict(device.error),
        "rainsensor": dict(device.rainsensor),
        "raindelay_active": device.raindelay_active,
        "module_config": device.module_config,
        "module_status": device.module_status,
        "schedules": device.schedules,
        "statistics": dict(device.statistics),
        "battery": dict(device.battery),
        "raw_cfg": device.raw_cfg,
        "raw_dat": device.raw_dat,
    }


def main() -> None:
    fixtures = _resolve_fixtures()
    for fixture in fixtures:
        payload = json.loads(fixture.read_text(encoding="utf-8"))["payload"]
        protocol = 1 if "slots" in payload.get("cfg", {}).get("sc", {}) else 0
        mower = _build_mower(payload, protocol, fixture.parts[-2])
        device = DeviceHandler(api=object(), mower=mower, tz="UTC")

        snapshot = _capture_device_snapshot(device)
        print(f"\nFixture: {fixture}\n" + "-" * 60)
        print(json.dumps(snapshot, indent=2, default=str))


if __name__ == "__main__":
    main()
