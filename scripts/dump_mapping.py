#!/usr/bin/env python3
"""Dump decoded mappings for each fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyworxcloud.utils.devices import DeviceHandler
from tests.fixture_utils import fixture_paths


def _resolve_fixtures() -> list[Path]:
    fixtures = fixture_paths("http.json") + fixture_paths("mqtt.json")
    if not fixtures:
        raise SystemExit("No fixtures directory found")
    seen: set[Path] = set()
    ordered: list[Path] = []
    for fixture in fixtures:
        if fixture in seen:
            continue
        seen.add(fixture)
        ordered.append(fixture)
    return ordered


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


def _iter_payloads(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    payloads: list[dict[str, Any]] = []
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        obj, consumed = decoder.raw_decode(text[index:])
        payloads.append(obj)
        index += consumed
    return payloads


def main() -> None:
    fixtures = _resolve_fixtures()
    for fixture in fixtures:
        content = fixture.read_text(encoding="utf-8")
        entries = _iter_payloads(content)
        for entry_idx, entry in enumerate(entries):
            payload = entry["payload"]
            protocol = 1 if "slots" in payload.get("cfg", {}).get("sc", {}) else 0
            mower_name = (
                f"{fixture.parts[-2]}#{entry_idx}"
                if len(entries) > 1
                else fixture.parts[-2]
            )
            mower = _build_mower(payload, protocol, mower_name)
            device = DeviceHandler(api=object(), mower=mower, tz="UTC")

            snapshot = _capture_device_snapshot(device)
            print(f"\nFixture: {fixture} (entry {entry_idx})\n" + "-" * 60)
            print(json.dumps(snapshot, indent=2, default=str))


if __name__ == "__main__":
    main()
