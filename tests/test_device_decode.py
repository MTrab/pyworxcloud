"""Tests for fixture-driven device payload decoding."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, Tuple
from zoneinfo import ZoneInfo

import pytest

import pyworxcloud.utils.devices as devices_module
import pyworxcloud.utils.schedules as schedules_module
from pyworxcloud.utils.capability import DeviceCapability
from pyworxcloud.utils.devices import DeviceHandler
from pyworxcloud.utils.schedules import Schedule
from pyworxcloud.utils.zone import Zone
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


def test_devicehandler_maps_lawn_from_top_level_api_fields() -> None:
    """Top-level API lawn fields should populate device.lawn."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-LAWN",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "12:00:00",
            "dt": "11/03/2026",
            "tz": "UTC",
        },
        "dat": {
            "uuid": "UUID-LAWN",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Lawn Fixture")
    mower["lawn_size"] = 250
    mower["lawn_perimeter"] = 115

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.lawn["size"] == 250
    assert device.lawn["perimeter"] == 115


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


def test_zone_defaults_exist_without_input_data() -> None:
    """Zone should expose safe defaults even before payload data is mapped."""
    zone = Zone()

    assert zone.index == 0
    assert zone.current == 0
    assert zone.indicies == [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    assert zone.starting_point == [0, 0, 0, 0]
    assert zone.ids == []


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


def test_devicehandler_prefers_dat_tm_over_cfg_date_time_for_updated() -> None:
    """UTC dat.tm should win and be represented in the effective timezone."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-UPDATED",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "21:30:00",
            "dt": "12/03/2026",
            "tz": "Australia/Perth",
        },
        "dat": {
            "uuid": "UUID-UPDATED",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "tm": "2026-03-12T13:30:00.000Z",
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Updated Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.updated == datetime.fromisoformat("2026-03-12T13:30:00+00:00")


def test_devicehandler_converts_dat_tm_to_configured_timezone() -> None:
    """Realtime UTC timestamps should not switch display timezone after MQTT updates."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-UPDATED-TZ",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "21:30:00",
            "dt": "12/03/2026",
            "tz": "Australia/Perth",
        },
        "dat": {
            "uuid": "UUID-UPDATED-TZ",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "tm": "2026-03-12T13:30:00.000Z",
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Updated TZ Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="Europe/Copenhagen")

    assert device.updated == datetime.fromisoformat("2026-03-12T14:30:00+01:00")


def test_devicehandler_falls_back_to_cfg_date_time_when_dat_tm_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy cfg date/time should still be used when realtime timestamp is missing."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-CFG-UPDATED",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "12:00:00",
            "dt": "11/03/2026",
            "tz": "Australia/Perth",
        },
        "dat": {
            "uuid": "UUID-CFG-UPDATED",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "CFG Updated Fixture")

    frozen_now = datetime.fromisoformat("2026-03-12T16:19:22+00:00")
    real_datetime = devices_module.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return frozen_now.replace(tzinfo=None)
            return frozen_now.astimezone(tz)

    monkeypatch.setattr(devices_module, "datetime", FrozenDateTime)
    device = DeviceHandler(api=object(), mower=mower, tz="Europe/Copenhagen")

    assert device.updated == datetime.fromisoformat("2026-03-11T13:00:00+01:00")


def test_devicehandler_treats_cfg_date_time_as_utc_before_display_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API cfg timestamps should not be interpreted in the host-local timezone."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-CFG-UTC",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "09:03:31",
            "dt": "05/05/2026",
        },
        "dat": {
            "uuid": "UUID-CFG-UTC",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "CFG UTC Fixture")
    mower["time_zone"] = "Europe/Copenhagen"

    frozen_now = datetime.fromisoformat("2026-05-05T09:04:00+00:00")
    real_datetime = devices_module.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return frozen_now.replace(tzinfo=None)
            return frozen_now.astimezone(tz)

    monkeypatch.setattr(devices_module, "datetime", FrozenDateTime)
    device = DeviceHandler(api=object(), mower=mower, tz=None)

    assert device.updated == datetime.fromisoformat("2026-05-05T11:03:31+02:00")
    assert device.updated_origin == "cfg_tm_utc"


def test_devicehandler_rejects_implausible_future_cfg_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Future-skewed legacy cfg timestamps should fall back to observed time."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-FUTURE-CFG",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "00:24:23",
            "dt": "13/03/2026",
        },
        "dat": {
            "uuid": "UUID-FUTURE-CFG",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Future CFG Fixture")

    frozen_now = datetime.fromisoformat("2026-03-12T16:24:23+00:00")
    real_datetime = devices_module.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return frozen_now.replace(tzinfo=None)
            return frozen_now.astimezone(tz)

    monkeypatch.setattr(devices_module, "datetime", FrozenDateTime)
    device = DeviceHandler(api=object(), mower=mower, tz="Europe/Copenhagen")

    assert device.updated == frozen_now


def test_devicehandler_keeps_monotonic_updated_when_cfg_timestamp_goes_backwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older legacy cfg timestamps should not overwrite a newer known update time."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-MONOTONIC",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "15:24:22",
            "dt": "12/03/2026",
        },
        "dat": {
            "uuid": "UUID-MONOTONIC",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Monotonic Fixture")
    frozen_now = datetime.fromisoformat("2026-03-12T16:24:23+00:00")
    real_datetime = devices_module.datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return frozen_now.replace(tzinfo=None)
            return frozen_now.astimezone(tz)

    monkeypatch.setattr(devices_module, "datetime", FrozenDateTime)
    device = DeviceHandler(api=object(), mower=mower, tz="Europe/Copenhagen")
    device.updated = FrozenDateTime.fromisoformat("2026-03-12T16:24:22+01:00")

    regressing = json.loads(json.dumps(payload))
    regressing["cfg"]["tm"] = "15:23:22"
    regressing["cfg"]["id"] = 0
    device.raw_data = json.dumps(regressing)

    assert device.updated == FrozenDateTime.fromisoformat("2026-03-12T16:24:22+01:00")


def test_devicehandler_uses_device_timezone_when_instance_timezone_is_missing() -> None:
    """Schedule timestamps should fall back to device timezone before UTC."""
    _, payload = _find_http_fixture(
        lambda p: (
            bool(p.get("cfg", {}).get("tz"))
            and bool(p.get("cfg", {}).get("sc", {}).get("slots"))
        )
    )
    mower = _build_mower(payload, 1, "Timezone Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz=None)

    next_schedule = device.schedules["next_schedule_start"]
    assert next_schedule is not None
    assert next_schedule.tzinfo == ZoneInfo(payload["cfg"]["tz"])


def test_protocol1_next_schedule_prefers_next_same_day_slot(monkeypatch) -> None:
    """Protocol 1 should choose the next same-day slot, not the last slot of the day."""
    real_datetime = schedules_module.datetime

    class FrozenDateTime:
        """Minimal datetime shim returning a fixed current time."""

        @staticmethod
        def now(tz=None) -> Any:
            current = real_datetime(2026, 3, 12, 10, 30, tzinfo=ZoneInfo("UTC"))
            return current if tz is None else current.astimezone(tz)

        strptime = staticmethod(real_datetime.strptime)

    monkeypatch.setattr(schedules_module, "datetime", FrozenDateTime)

    schedule = Schedule()
    schedule["slots"] = [
        {
            "day": "thursday",
            "start": "09:00",
            "end": "09:30",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "protocol1",
        },
        {
            "day": "thursday",
            "start": "11:00",
            "end": "11:30",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "protocol1",
        },
        {
            "day": "thursday",
            "start": "15:00",
            "end": "15:30",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "protocol1",
        },
    ]

    schedule.update_progress_and_next("UTC")

    assert schedule["next_schedule_start"] == "2026-03-12 11:00:00"


def test_protocol0_next_schedule_includes_secondary_same_day_slot(
    monkeypatch,
) -> None:
    """Protocol 0 should include same-day secondary slots when finding next run."""
    real_datetime = schedules_module.datetime

    class FrozenDateTime:
        """Minimal datetime shim returning a fixed current time."""

        @staticmethod
        def now(tz=None) -> Any:
            current = real_datetime(2026, 3, 12, 10, 30, tzinfo=ZoneInfo("UTC"))
            return current if tz is None else current.astimezone(tz)

        strptime = staticmethod(real_datetime.strptime)

    monkeypatch.setattr(schedules_module, "datetime", FrozenDateTime)

    schedule = Schedule()
    schedule["slots"] = [
        {
            "day": "thursday",
            "start": "09:00",
            "end": "10:00",
            "duration": 60,
            "duration_extended": 60,
            "boundary": False,
            "source": "protocol0",
        },
        {
            "day": "thursday",
            "start": "12:00",
            "end": "12:30",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "secondary",
        },
        {
            "day": "friday",
            "start": "08:00",
            "end": "08:30",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "protocol0",
        },
    ]

    schedule.update_progress_and_next("UTC")

    assert schedule["next_schedule_start"] == "2026-03-12 12:00:00"


def test_protocol1_schedule_progress_uses_mower_timezone(monkeypatch) -> None:
    """Protocol 1 schedule progress should use mower timezone, not host local time."""
    real_datetime = schedules_module.datetime
    mower_now = real_datetime(2026, 3, 12, 23, 30, tzinfo=ZoneInfo("UTC"))

    class FrozenDateTime:
        """Datetime shim exposing different host-local and mower-timezone values."""

        @staticmethod
        def now(tz=None) -> Any:
            if tz is None:
                return real_datetime(2026, 3, 13, 0, 30, tzinfo=ZoneInfo("UTC"))
            return mower_now.astimezone(tz)

        strptime = staticmethod(real_datetime.strptime)

    monkeypatch.setattr(schedules_module, "datetime", FrozenDateTime)

    schedule = Schedule()
    schedule["slots"] = [
        {
            "day": "thursday",
            "start": "23:00",
            "end": "23:40",
            "duration": 40,
            "duration_extended": 40,
            "boundary": False,
            "source": "protocol1",
        },
        {
            "day": "friday",
            "start": "00:15",
            "end": "00:45",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "protocol1",
        },
    ]

    schedule.update_progress_and_next("UTC")

    assert schedule["daily_progress"] == 75
    assert schedule["next_schedule_start"] == "2026-03-13 00:15:00"


def test_protocol0_schedule_progress_uses_mower_timezone(monkeypatch) -> None:
    """Protocol 0 schedule progress should use mower timezone, not host local time."""
    real_datetime = schedules_module.datetime
    mower_now = real_datetime(2026, 3, 12, 23, 30, tzinfo=ZoneInfo("UTC"))

    class FrozenDateTime:
        """Datetime shim exposing different host-local and mower-timezone values."""

        @staticmethod
        def now(tz=None) -> Any:
            if tz is None:
                return real_datetime(2026, 3, 13, 0, 30, tzinfo=ZoneInfo("UTC"))
            return mower_now.astimezone(tz)

        strptime = staticmethod(real_datetime.strptime)

    monkeypatch.setattr(schedules_module, "datetime", FrozenDateTime)

    schedule = Schedule()
    schedule["slots"] = [
        {
            "day": "thursday",
            "start": "23:00",
            "end": "23:40",
            "duration": 40,
            "duration_extended": 40,
            "boundary": False,
            "source": "protocol0",
        },
        {
            "day": "friday",
            "start": "00:15",
            "end": "00:45",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "secondary",
        },
    ]

    schedule.update_progress_and_next("UTC")

    assert schedule["daily_progress"] == 75
    assert schedule["next_schedule_start"] == "2026-03-13 00:15:00"


def test_schedule_progress_is_none_without_active_slot_today(monkeypatch) -> None:
    """Daily progress should be None when the current day has no schedule slots."""
    real_datetime = schedules_module.datetime

    class FrozenDateTime:
        """Minimal datetime shim returning a fixed current time."""

        @staticmethod
        def now(tz=None) -> Any:
            current = real_datetime(2026, 3, 12, 10, 30, tzinfo=ZoneInfo("UTC"))
            return current if tz is None else current.astimezone(tz)

        strptime = staticmethod(real_datetime.strptime)

    monkeypatch.setattr(schedules_module, "datetime", FrozenDateTime)

    schedule = Schedule()
    schedule["slots"] = [
        {
            "day": "friday",
            "start": "08:00",
            "end": "08:30",
            "duration": 30,
            "duration_extended": 30,
            "boundary": False,
            "source": "protocol1",
        }
    ]

    schedule.update_progress_and_next("UTC")

    assert schedule["daily_progress"] is None
    assert schedule["next_schedule_start"] == "2026-03-13 08:00:00"


def test_devicehandler_maps_rtk_zone_ids_and_current_zone() -> None:
    """RTK devices should expose current zone and known zone IDs from RTK payloads."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-RTK",
            "rd": 0,
            "tz": "UTC",
            "sc": {"enabled": 1, "slots": []},
            "rtk": {
                "map": "fixture",
                "ck": "fixture",
                "st": 1,
                "zs": [
                    {"id": 1, "cfg": {}},
                    {"id": 2, "cfg": {}},
                    {"id": 4, "cfg": {}},
                    {"id": 5, "cfg": {}},
                ],
            },
        },
        "dat": {
            "uuid": "UUID-RTK",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "4G",
            "ls": 7,
            "le": 0,
            "cut": {"z": 4},
            "sc": {"slot": 0},
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 1, "RTK Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.zone.ids == [1, 2, 4, 5]
    assert device.zone.current == 4
    assert device.zone.index == 2


def test_devicehandler_normalizes_auto_schedule_settings() -> None:
    """Auto schedule settings should be exposed via a stable normalized shape."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-AUTO-SCHEDULE",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "12:00:00",
            "dt": "11/03/2026",
            "tz": "UTC",
        },
        "dat": {
            "uuid": "UUID-AUTO-SCHEDULE",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Auto Schedule Fixture")
    mower["auto_schedule"] = True
    mower["auto_schedule_settings"] = {
        "boost": 0,
        "grass_type": "mixed_species",
        "soil_type": "ignore",
        "irrigation": True,
        "nutrition": {"n": 18, "p": 24, "k": 6},
        "exclusion_scheduler": {
            "exclude_nights": True,
            "days": [
                {"exclude_day": False, "slots": []},
                {"exclude_day": False, "slots": []},
                {"exclude_day": False, "slots": []},
                {
                    "exclude_day": False,
                    "slots": [
                        {
                            "start_time": 540,
                            "duration": 180,
                            "reason": "generic",
                            "ignored": "value",
                        },
                        {
                            "start_time": 60,
                            "duration": 135,
                            "reason": "irrigation",
                        },
                    ],
                },
                {"exclude_day": False, "slots": []},
                {"exclude_day": False, "slots": []},
                {"exclude_day": False, "slots": []},
            ],
        },
    }

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.schedules["auto_schedule"] == {
        "enabled": True,
        "settings": {
            "boost": 0,
            "grass_type": "mixed_species",
            "soil_type": "ignore",
            "irrigation": True,
            "nutrition": {"n": 18, "p": 24, "k": 6},
            "exclusion_scheduler": {
                "exclude_nights": True,
                "days": [
                    {"exclude_day": False, "slots": []},
                    {"exclude_day": False, "slots": []},
                    {"exclude_day": False, "slots": []},
                    {
                        "exclude_day": False,
                        "slots": [
                            {
                                "start_time": 540,
                                "duration": 180,
                                "reason": "generic",
                            },
                            {
                                "start_time": 60,
                                "duration": 135,
                                "reason": "irrigation",
                            },
                        ],
                    },
                    {"exclude_day": False, "slots": []},
                    {"exclude_day": False, "slots": []},
                    {"exclude_day": False, "slots": []},
                ],
            },
        },
    }


@pytest.mark.parametrize("boost", schedules_module.AUTO_SCHEDULE_BOOST_LEVELS)
def test_devicehandler_preserves_observed_auto_schedule_boost_levels(
    boost: int,
) -> None:
    """Observed auto-schedule boost levels should round-trip unchanged."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": f"SERIAL-AUTO-SCHEDULE-BOOST-{boost}",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "12:00:00",
            "dt": "11/03/2026",
            "tz": "UTC",
        },
        "dat": {
            "uuid": f"UUID-AUTO-SCHEDULE-BOOST-{boost}",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Auto Schedule Boost Fixture")
    mower["auto_schedule"] = True
    mower["auto_schedule_settings"] = {"boost": boost}

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.schedules["auto_schedule"]["settings"]["boost"] == boost


def test_devicehandler_fills_missing_auto_schedule_defaults() -> None:
    """Missing auto schedule fields should fall back to safe defaults."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-AUTO-SCHEDULE-DEFAULTS",
            "rd": 0,
            "sc": {"d": [], "dd": False},
            "tm": "12:00:00",
            "dt": "11/03/2026",
            "tz": "UTC",
        },
        "dat": {
            "uuid": "UUID-AUTO-SCHEDULE-DEFAULTS",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Auto Schedule Defaults Fixture")
    mower["auto_schedule"] = False
    mower["auto_schedule_settings"] = {
        "exclusion_scheduler": {
            "days": [
                {"exclude_day": True, "slots": [{"start_time": 15}]},
            ]
        }
    }

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")
    auto_schedule = device.schedules["auto_schedule"]

    assert auto_schedule["enabled"] is False
    assert auto_schedule["settings"]["boost"] is None
    assert auto_schedule["settings"]["grass_type"] is None
    assert auto_schedule["settings"]["soil_type"] is None
    assert auto_schedule["settings"]["irrigation"] is None
    assert auto_schedule["settings"]["nutrition"] is None
    assert auto_schedule["settings"]["exclusion_scheduler"]["exclude_nights"] is False
    assert len(auto_schedule["settings"]["exclusion_scheduler"]["days"]) == 7
    assert auto_schedule["settings"]["exclusion_scheduler"]["days"][0] == {
        "exclude_day": True,
        "slots": [
            {
                "start_time": 15,
                "duration": None,
                "reason": None,
            }
        ],
    }
    assert all(
        day == {"exclude_day": False, "slots": []}
        for day in auto_schedule["settings"]["exclusion_scheduler"]["days"][1:]
    )


def test_vision_mower_detects_ots_from_dat_sc_once() -> None:
    """Vision mowers (protocol 1) expose 'once' in dat.sc, not cfg.sc."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-VISION-OTS",
            "rd": 0,
            "tz": "UTC",
            "sc": {"enabled": 1, "paused": 0, "slots": []},
        },
        "dat": {
            "uuid": "UUID-VISION-OTS",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "sc": {"once": 0, "slot": 0},
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 1, "Vision OTS Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE) is True
    assert device.capabilities.check(DeviceCapability.EDGE_CUT) is True
    assert device.schedules["one_time_schedule"] is True


def test_classic_mower_ots_still_detected_from_cfg_sc() -> None:
    """Protocol 0 mowers with 'ots' in cfg.sc should still work unchanged."""
    payload = {
        "cfg": {
            "id": 1,
            "sn": "SERIAL-CLASSIC-OTS",
            "rd": 0,
            "sc": {
                "d": [],
                "dd": False,
                "ots": {"bc": 0, "wtm": 30},
            },
            "tm": "12:00:00",
            "dt": "11/03/2026",
            "tz": "UTC",
        },
        "dat": {
            "uuid": "UUID-CLASSIC-OTS",
            "mac": "AA:BB:CC:DD:EE:FF",
            "conn": "online",
            "ls": 1,
            "le": 0,
            "rain": {"s": 0, "cnt": 0},
        },
    }
    mower = _build_mower(payload, 0, "Classic OTS Fixture")

    device = DeviceHandler(api=object(), mower=mower, tz="UTC")

    assert device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE) is True
    assert device.capabilities.check(DeviceCapability.EDGE_CUT) is True


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
