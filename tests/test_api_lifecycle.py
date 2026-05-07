"""Tests for API and lifecycle behavior without network access."""

from __future__ import annotations

import asyncio
import threading
import warnings
from datetime import datetime
from typing import Any

import pytest

from pyworxcloud import WorxCloud
from pyworxcloud.api import LandroidCloudAPI
from pyworxcloud.clouds import CloudType
from pyworxcloud.events import LandroidEvent
from pyworxcloud.exceptions import (
    NoFirmwareAvailableError,
    NoFirmwareOtaError,
    NotFoundError,
)
from pyworxcloud.helpers.logger import PACKAGE_LOGGER_NAME, get_logger
from pyworxcloud.utils.schedule_codec import ScheduleEntry, ScheduleModel


class DummyTimer:
    """Simple timer stub."""

    def __init__(self) -> None:
        self.cancel_called = False

    def cancel(self) -> None:
        self.cancel_called = True


class DummyMQTT:
    """Simple MQTT stub."""

    def __init__(self) -> None:
        self.disconnect_called = False
        self.shutdown_called = False

    async def adisconnect(self, _keep_topic: bool = False) -> None:
        self.disconnect_called = True

    async def ashutdown(self) -> None:
        self.shutdown_called = True

    async def apublish(
        self, _serial: str, _topic: str, _message: Any, _protocol: int | None = None
    ) -> None:
        return None


class DummyDevice:
    """Simple device stub."""

    time_zone = "UTC"


class DummySession:
    """Simple session stub that records close calls."""

    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True


class CapturingMQTT:
    """MQTT constructor stub capturing provided timeout."""

    last_response_timeout: float | None = None
    constructor_thread_id: int | None = None

    def __init__(
        self,
        _api: Any,
        _brandprefix: str,
        _endpoint: str,
        _user_id: int,
        _logger: Any,
        _callback: Any,
        response_timeout: float,
        identifier_resolver: Any = None,
        deduplicate_inflight_commands: bool = False,
    ) -> None:
        self.identifier_resolver = identifier_resolver
        self.deduplicate_inflight_commands = deduplicate_inflight_commands
        self.__class__.last_response_timeout = response_timeout
        self.__class__.constructor_thread_id = threading.get_ident()

    async def aconnect(self) -> None:
        return None

    async def asubscribe(self, _topic: str, _append: bool = True) -> None:
        return None

    async def adisconnect(self, _keep_topic: bool = False) -> None:
        return None

    async def ashutdown(self) -> None:
        return None


class TrackingMQTT:
    """MQTT stub that records lifecycle calls per instance."""

    instances: list["TrackingMQTT"] = []

    def __init__(
        self,
        _api: Any,
        _brandprefix: str,
        _endpoint: str,
        _user_id: int,
        _logger: Any,
        _callback: Any,
        response_timeout: float,
        identifier_resolver: Any = None,
        deduplicate_inflight_commands: bool = False,
    ) -> None:
        self.identifier_resolver = identifier_resolver
        self.deduplicate_inflight_commands = deduplicate_inflight_commands
        self.response_timeout = response_timeout
        self.disconnect_calls = 0
        self.shutdown_calls = 0
        self.subscriptions: list[str] = []
        self.__class__.instances.append(self)

    async def aconnect(self) -> None:
        return None

    async def asubscribe(self, topic: str, _append: bool = True) -> None:
        self.subscriptions.append(topic)

    async def adisconnect(self, _keep_topic: bool = False) -> None:
        self.disconnect_calls += 1

    async def ashutdown(self) -> None:
        self.shutdown_calls += 1


def test_get_token_propagates_unexpected_errors(monkeypatch) -> None:
    """Unexpected token fetch errors should not be swallowed."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)

    async def _raise(*_args: Any, **_kwargs: Any) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("pyworxcloud.api.APOST", _raise)

    with pytest.raises(RuntimeError):
        asyncio.run(api.get_token())


def test_get_mowers_uses_products_cache(monkeypatch) -> None:
    """Repeated mower fetches should not repeatedly load product catalog."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)
    api.access_token = "token"
    api.refresh_token = "refresh"
    api._token_expire = 9999999999

    calls = {"products": 0}

    async def _get(url: str, _headers: dict, session=None) -> list:
        if url.endswith("/api/v2/products"):
            calls["products"] += 1
            assert session is not None
            return [
                {
                    "id": 42,
                    "code": "WG123",
                    "default_name": "Landroid",
                    "meters": "500",
                    "product_year": 2024,
                    "cutting_width": 18,
                }
            ]

        if "product-items" in url:
            return [
                {
                    "name": "My Mower",
                    "product_id": 42,
                }
            ]

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("pyworxcloud.api.AGET", _get)

    first = asyncio.run(api.get_mowers())
    second = asyncio.run(api.get_mowers())

    assert first[0]["model"]["code"] == "WG123"
    assert second[0]["model"]["friendly_name"] == "Landroid500"
    assert calls["products"] == 1


def test_get_mowers_passes_session_to_request_helper(monkeypatch) -> None:
    """LandroidCloudAPI should reuse its HTTP session when calling GET helper."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)
    api.access_token = "token"
    api.refresh_token = "refresh"
    api._token_expire = 9999999999

    seen = {"session": None}

    async def _get(url: str, _headers: dict, session=None) -> list:
        seen["session"] = session
        if url.endswith("/api/v2/products"):
            return [
                {
                    "id": 42,
                    "code": "WG123",
                    "default_name": "Landroid",
                    "meters": "500",
                    "product_year": 2024,
                    "cutting_width": 18,
                }
            ]
        if "product-items" in url:
            return [{"name": "My Mower", "product_id": 42}]
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("pyworxcloud.api.AGET", _get)

    asyncio.run(api.get_mowers())

    assert seen["session"] is api._session


def test_disconnect_cancels_timers_and_disconnects_mqtt() -> None:
    """Disconnect should cancel timers, clear timer map, and disconnect MQTT."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    mqtt = DummyMQTT()

    cloud.mqtt = mqtt
    asyncio.run(cloud.disconnect())

    assert mqtt.disconnect_called is True
    assert cloud._disconnecting.is_set() is True
    assert mqtt.shutdown_called is True
    assert cloud.mqtt is None


def test_fetch_skips_api_call_when_disconnecting() -> None:
    """Fetch should do nothing when disconnecting flag is set."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._disconnecting.set()

    called = {"value": False}

    async def _get_mowers() -> list:
        called["value"] = True
        return []

    cloud._api.get_mowers = _get_mowers
    asyncio.run(cloud._fetch())

    assert called["value"] is False


def test_fetch_prefers_newer_cfg_timestamp_over_older_existing_timestamp(
    monkeypatch,
) -> None:
    """API refresh should keep the newer cfg-derived timestamp."""
    cloud = WorxCloud("user@example.com", "secret", "worx", tz="Europe/Copenhagen")
    existing = DummyDevice()
    existing.updated = datetime.fromisoformat("2026-03-12T17:24:22+01:00")
    cloud.devices = {"Jim": existing}

    async def _get_mowers() -> list[dict[str, Any]]:
        return [
            {
                "name": "Jim",
                "model": {"friendly_name": "Fixture", "code": "FX"},
                "protocol": 0,
                "serial_number": "SERIAL-1",
                "uuid": "UUID-1",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "time_zone": "Australia/Perth",
                "warranty_expires_at": None,
                "warranty_registered": False,
                "mqtt_topics": {"command_in": "in/topic", "command_out": "out/topic"},
                "last_status": {
                    "payload": {
                        "cfg": {
                            "id": 21463,
                            "sn": "SERIAL-1",
                            "rd": 0,
                            "tm": "00:24:23",
                            "dt": "13/03/2026",
                            "sc": {"d": [], "dd": False},
                        },
                        "dat": {
                            "uuid": "UUID-1",
                            "mac": "AA:BB:CC:DD:EE:FF",
                            "conn": "online",
                            "ls": 1,
                            "le": 0,
                            "rain": {"s": 0, "cnt": 0},
                        },
                    }
                },
            }
        ]

    monkeypatch.setattr(cloud._api, "get_mowers", _get_mowers)
    asyncio.run(cloud._fetch())

    assert cloud.devices["Jim"].updated == datetime.fromisoformat(
        "2026-03-13T01:24:23+01:00"
    )
    assert cloud.devices["Jim"].updated_origin == "cfg_tm_utc"


def test_token_updated_is_noop_without_mqtt() -> None:
    """Token update callback should be safe before MQTT is initialized."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud.mqtt = None
    asyncio.run(cloud._token_updated())


def test_get_logger_does_not_accumulate_handlers() -> None:
    """Repeated logger setup should not attach output handlers or force levels."""
    get_logger("pyworxcloud.test_handlers")
    package_logger = get_logger(PACKAGE_LOGGER_NAME)
    original_handlers = list(package_logger.handlers)
    original_level = package_logger.level

    try:
        package_logger.handlers.clear()
        package_logger.setLevel(0)

        first = get_logger("pyworxcloud.test_handlers")
        second = get_logger("pyworxcloud.test_handlers")

        assert first is second
        assert first.handlers == []
        assert package_logger.level == 0
        assert len(package_logger.handlers) == 1
        assert package_logger.handlers[0].__class__.__name__ == "NullHandler"
    finally:
        package_logger.handlers.clear()
        package_logger.setLevel(original_level)
        for handler in original_handlers:
            package_logger.addHandler(handler)


def test_on_api_update_dispatches_api_event_callback() -> None:
    """API update callback should dispatch event payload to registered handler."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    received: list[dict[str, Any]] = []
    cloud.set_callback(LandroidEvent.API, lambda api_data: received.append(api_data))
    cloud._on_api_update({"key": "value"})

    assert received == [{"key": "value"}]


def test_constructor_rejects_non_positive_command_timeout() -> None:
    """WorxCloud should validate command timeout."""
    with pytest.raises(ValueError):
        WorxCloud("user@example.com", "secret", "worx", command_timeout=0)


def test_connect_passes_configured_command_timeout_to_mqtt(monkeypatch) -> None:
    """Configured command timeout should be forwarded to MQTT layer."""
    cloud = WorxCloud(
        "user@example.com",
        "secret",
        "worx",
        command_timeout=12.5,
    )

    async def _fake_fetch() -> None:
        cloud._mowers = [
            {
                "name": "My Mower",
                "mqtt_endpoint": "mqtt.example.invalid",
                "user_id": 99,
                "mqtt_topics": {"command_out": "topic/out"},
            }
        ]
        cloud.devices = {"My Mower": DummyDevice()}

    monkeypatch.setattr(cloud, "_fetch", _fake_fetch)
    monkeypatch.setattr("pyworxcloud.MQTT", CapturingMQTT)
    monkeypatch.setattr("pyworxcloud.convert_to_time", lambda *_args, **_kwargs: None)

    assert asyncio.run(cloud.connect()) is True
    assert CapturingMQTT.last_response_timeout == 12.5


def test_connect_constructs_mqtt_off_event_loop_thread(monkeypatch) -> None:
    """MQTT setup performs SSL work, so it should not run on the event loop thread."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    event_loop_thread_id: int | None = None

    async def _fake_fetch() -> None:
        nonlocal event_loop_thread_id
        event_loop_thread_id = threading.get_ident()
        cloud._mowers = [
            {
                "name": "My Mower",
                "mqtt_endpoint": "mqtt.example.invalid",
                "user_id": 99,
                "mqtt_topics": {"command_out": "topic/out"},
            }
        ]
        cloud.devices = {"My Mower": DummyDevice()}

    CapturingMQTT.constructor_thread_id = None

    monkeypatch.setattr(cloud, "_fetch", _fake_fetch)
    monkeypatch.setattr("pyworxcloud.MQTT", CapturingMQTT)
    monkeypatch.setattr("pyworxcloud.convert_to_time", lambda *_args, **_kwargs: None)

    assert asyncio.run(cloud.connect()) is True
    assert CapturingMQTT.constructor_thread_id is not None
    assert CapturingMQTT.constructor_thread_id != event_loop_thread_id


def test_update_passes_optional_timeout_to_mqtt_ping() -> None:
    """Per-call update timeout should be forwarded to MQTT ping."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers_by_serial = {
        "SN-1": {
            "serial_number": "SN-1",
            "uuid": "UUID-1",
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/in"},
        }
    }
    calls: list[tuple[str, str, int, float | None]] = []

    class MQTTStub:
        async def aping(
            self,
            serial_number: str,
            topic: str,
            protocol: int,
            timeout: float | None = None,
        ) -> None:
            calls.append((serial_number, topic, protocol, timeout))

    cloud.mqtt = MQTTStub()

    asyncio.run(cloud.update("SN-1", timeout=3.0))

    assert calls == [("SN-1", "topic/in", 0, 3.0)]


def test_async_context_manager_runs_lifecycle(monkeypatch) -> None:
    """async with should call authenticate/connect on enter and disconnect on exit."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    calls: list[str] = []

    async def _auth() -> bool:
        calls.append("auth")
        return True

    async def _connect() -> bool:
        calls.append("connect")
        return True

    async def _disconnect() -> None:
        calls.append("disconnect")

    monkeypatch.setattr(cloud, "authenticate", _auth)
    monkeypatch.setattr(cloud, "connect", _connect)
    monkeypatch.setattr(cloud, "disconnect", _disconnect)

    async def _run() -> None:
        async with cloud:
            calls.append("inside")

    asyncio.run(_run())
    assert calls == ["auth", "connect", "inside", "disconnect"]


def test_async_context_manager_disconnects_on_exception(monkeypatch) -> None:
    """disconnect should still run when async with block raises."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    calls: list[str] = []

    async def _auth() -> bool:
        calls.append("auth")
        return True

    async def _connect() -> bool:
        calls.append("connect")
        return True

    async def _disconnect() -> None:
        calls.append("disconnect")

    monkeypatch.setattr(cloud, "authenticate", _auth)
    monkeypatch.setattr(cloud, "connect", _connect)
    monkeypatch.setattr(cloud, "disconnect", _disconnect)

    async def _run() -> None:
        with pytest.raises(RuntimeError):
            async with cloud:
                raise RuntimeError("boom")

    asyncio.run(_run())
    assert calls == ["auth", "connect", "disconnect"]


def test_repeated_connect_disconnect_closes_resources_each_cycle(monkeypatch) -> None:
    """Repeated lifecycle cycles should not retain MQTT or API resources."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    sessions: list[DummySession] = []
    refresh_tasks = []
    TrackingMQTT.instances = []

    async def _fake_fetch() -> None:
        session = DummySession()
        sessions.append(session)
        cloud._api._session = session
        cloud._mowers = [
            {
                "name": "My Mower",
                "mqtt_endpoint": "mqtt.example.invalid",
                "user_id": 99,
                "mqtt_topics": {"command_out": "topic/out"},
            }
        ]
        cloud.devices = {"My Mower": DummyDevice()}

        async def _never() -> None:
            await asyncio.sleep(3600)

        task = asyncio.create_task(_never())
        refresh_tasks.append(task)
        cloud._api_refresh_task = task

    monkeypatch.setattr(cloud, "_fetch", _fake_fetch)
    monkeypatch.setattr("pyworxcloud.MQTT", TrackingMQTT)
    monkeypatch.setattr("pyworxcloud.convert_to_time", lambda *_args, **_kwargs: None)

    async def _exercise() -> None:
        for _ in range(3):
            assert await cloud.connect() is True
            mqtt_instance = cloud.mqtt
            assert mqtt_instance is not None
            await cloud.disconnect()
            await asyncio.sleep(0)
            assert cloud.mqtt is None
            assert cloud._api_refresh_task is None

    asyncio.run(_exercise())

    assert len(TrackingMQTT.instances) == 3
    assert all(instance.disconnect_calls == 1 for instance in TrackingMQTT.instances)
    assert all(instance.shutdown_calls == 1 for instance in TrackingMQTT.instances)
    assert all(
        instance.subscriptions == ["topic/out"] for instance in TrackingMQTT.instances
    )
    assert len(sessions) == 3
    assert all(session.close_calls == 1 and session.closed for session in sessions)
    assert all(task.cancelled() for task in refresh_tasks)


def test_schedule_api_refresh_replaces_pending_task_without_accumulating() -> None:
    """Scheduling a new API refresh should cancel the previous pending task."""
    cloud = WorxCloud("user@example.com", "secret", "worx", tz="UTC")

    async def _exercise() -> None:
        await cloud._schedule_api_refresh()
        first = cloud._api_refresh_task
        assert first is not None

        await cloud._schedule_api_refresh()
        second = cloud._api_refresh_task
        assert second is not None
        assert second is not first
        await asyncio.sleep(0)
        assert first.cancelled() is True

        second.cancel()
        await asyncio.sleep(0)

    asyncio.run(_exercise())


def test_sync_context_manager_warns_deprecated(monkeypatch) -> None:
    """Sync context manager should emit a deprecation warning."""
    cloud = WorxCloud("user@example.com", "secret", "worx")

    async def _noop_auth() -> bool:
        return True

    async def _noop_connect() -> bool:
        return True

    async def _noop_disconnect() -> None:
        return None

    monkeypatch.setattr(cloud, "authenticate", _noop_auth)
    monkeypatch.setattr(cloud, "connect", _noop_connect)
    monkeypatch.setattr(cloud, "disconnect", _noop_disconnect)

    with pytest.deprecated_call():
        cloud.__enter__()
    cloud.__exit__(None, None, None)


def test_sync_context_manager_fails_inside_running_loop(monkeypatch) -> None:
    """Sync context manager should refuse execution in a running event loop."""
    cloud = WorxCloud("user@example.com", "secret", "worx")

    async def _noop_auth() -> bool:
        return True

    async def _noop_connect() -> bool:
        return True

    monkeypatch.setattr(cloud, "authenticate", _noop_auth)
    monkeypatch.setattr(cloud, "connect", _noop_connect)

    async def _run() -> None:
        with pytest.raises(RuntimeError):
            cloud.__enter__()

    asyncio.run(_run())


def test_match_mower_uses_identifier_priority() -> None:
    """Matcher should prefer serial, then uuid, then mac."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    mower_serial = {
        "name": "Serial",
        "serial_number": "S1",
        "uuid": "U1",
        "mac_address": "M1",
    }
    mower_uuid = {
        "name": "UUID",
        "serial_number": "S2",
        "uuid": "U2",
        "mac_address": "M2",
    }
    mower_mac = {
        "name": "MAC",
        "serial_number": "S3",
        "uuid": "U3",
        "mac_address": "M3",
    }
    cloud._mowers = [mower_serial, mower_uuid, mower_mac]
    cloud._rebuild_mower_indices()

    assert cloud._match_mower(serial="S1") == mower_serial
    assert cloud._match_mower(uuid="U2") == mower_uuid
    assert cloud._match_mower(mac="M3") == mower_mac
    assert cloud._match_mower(serial="missing", uuid="U2") == mower_uuid
    assert (
        cloud._match_mower(serial="missing", uuid="missing", mac="M1") == mower_serial
    )
    assert cloud._match_mower(serial="missing", uuid="missing", mac="missing") is None


def test_get_mower_uses_rebuilt_serial_index() -> None:
    """get_mower should resolve mowers through serial lookup index."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    target = {
        "name": "Target",
        "serial_number": "SERIAL-1",
        "uuid": "UUID-1",
        "mac_address": "MAC-1",
    }
    cloud._mowers = [target]
    cloud._rebuild_mower_indices()

    assert cloud.get_mower("SERIAL-1") == target


def test_input_helpers_validate_types() -> None:
    """Helper validators should enforce strict bool/int semantics."""
    cloud = WorxCloud("user@example.com", "secret", "worx")

    assert cloud._require_bool(True, "state") is True
    with pytest.raises(ValueError):
        cloud._require_bool("true", "state")

    assert cloud._coerce_int("5", "runtime", minimum=0) == 5
    with pytest.raises(ValueError):
        cloud._coerce_int(True, "runtime")
    with pytest.raises(ValueError):
        cloud._coerce_int("abc", "runtime")
    with pytest.raises(ValueError):
        cloud._coerce_int(-1, "runtime", minimum=0)
    with pytest.raises(ValueError):
        cloud._coerce_int(101, "runtime", maximum=100)
    with pytest.raises(ValueError):
        cloud._require_step(25, "runtime", 10)


def test_set_lock_rejects_non_bool_input_early(monkeypatch) -> None:
    """set_lock should fail fast on invalid bool inputs before mower lookup."""
    cloud = WorxCloud("user@example.com", "secret", "worx")

    def _unexpected_lookup(_serial: str) -> dict:
        raise AssertionError("get_mower should not be called for invalid bool input")

    monkeypatch.setattr(cloud, "get_mower", _unexpected_lookup)

    with pytest.raises(ValueError):
        asyncio.run(cloud.set_lock("SERIAL-1", "true"))


def test_set_time_extension_rejects_out_of_range_input_early(monkeypatch) -> None:
    """set_time_extension should validate the percentage before mower lookup."""
    cloud = WorxCloud("user@example.com", "secret", "worx")

    def _unexpected_lookup(_serial: str) -> dict:
        raise AssertionError("get_mower should not be called for invalid int input")

    monkeypatch.setattr(cloud, "get_mower", _unexpected_lookup)

    with pytest.raises(ValueError):
        asyncio.run(cloud.set_time_extension("SERIAL-1", -101))
    with pytest.raises(ValueError):
        asyncio.run(cloud.set_time_extension("SERIAL-1", 101))
    with pytest.raises(ValueError):
        asyncio.run(cloud.set_time_extension("SERIAL-1", 25))


def test_set_torque_rejects_out_of_range_input_early(monkeypatch) -> None:
    """set_torque should validate the percentage before mower lookup."""
    cloud = WorxCloud("user@example.com", "secret", "worx")

    def _unexpected_lookup(_serial: str) -> dict:
        raise AssertionError("get_mower should not be called for invalid int input")

    monkeypatch.setattr(cloud, "get_mower", _unexpected_lookup)

    with pytest.raises(ValueError):
        asyncio.run(cloud.set_torque("SERIAL-1", -51))
    with pytest.raises(ValueError):
        asyncio.run(cloud.set_torque("SERIAL-1", 51))


def test_set_time_extension_publishes_schedule_payload() -> None:
    """set_time_extension should publish the documented sc.p payload."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []

    class CapturingMQTT(DummyMQTT):
        async def apublish(
            self,
            serial: str,
            topic: str,
            message: Any,
            protocol: int | None = None,
        ) -> None:
            calls.append(
                {
                    "serial": serial,
                    "topic": topic,
                    "message": message,
                    "protocol": protocol,
                }
            )

    cloud.mqtt = CapturingMQTT()

    async def _record_refresh(is_err: bool = False) -> None:
        refreshes.append(is_err)

    cloud._schedule_api_refresh = _record_refresh  # type: ignore[method-assign]
    cloud._mowers = [
        {
            "name": "Target",
            "serial_number": "SERIAL-1",
            "uuid": "UUID-1",
            "mac_address": "MAC-1",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/in"},
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()

    asyncio.run(cloud.set_time_extension("SERIAL-1", 20))

    assert calls == [
        {
            "serial": "SERIAL-1",
            "topic": "topic/in",
            "message": {"sc": {"m": 1, "d": [], "p": 20}},
            "protocol": 0,
        }
    ]
    assert refreshes == [False]


def test_set_time_extension_rejects_protocol1() -> None:
    """Protocol 1 devices should reject schedule time extension writes."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud.mqtt = DummyMQTT()
    cloud._mowers = [
        {
            "name": "Target",
            "serial_number": "SERIAL-1",
            "uuid": "UUID-1",
            "mac_address": "MAC-1",
            "online": True,
            "protocol": 1,
            "mqtt_topics": {"command_in": "topic/in"},
            "last_status": {"payload": {"cfg": {"sc": {"enabled": 1, "slots": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()

    with pytest.raises(ValueError):
        asyncio.run(cloud.set_time_extension("SERIAL-1", 20))


def test_toggle_schedule_uses_protocol_specific_payloads() -> None:
    """toggle_schedule should publish m for protocol 0 and enabled for protocol 1."""
    calls: list[dict[str, Any]] = []

    class CapturingMQTT(DummyMQTT):
        async def apublish(
            self,
            serial: str,
            topic: str,
            message: Any,
            protocol: int | None = None,
        ) -> None:
            calls.append(
                {
                    "serial": serial,
                    "topic": topic,
                    "message": message,
                    "protocol": protocol,
                }
            )

    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud.mqtt = CapturingMQTT()

    async def _noop_refresh(is_err: bool = False) -> None:
        return None

    cloud._schedule_api_refresh = _noop_refresh  # type: ignore[method-assign]
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "last_status": {"payload": {"cfg": {"sc": {"m": 0, "d": []}}}},
        },
        {
            "name": "Proto1",
            "serial_number": "SERIAL-1",
            "uuid": "UUID-1",
            "mac_address": "MAC-1",
            "online": True,
            "protocol": 1,
            "mqtt_topics": {"command_in": "topic/p1"},
            "last_status": {"payload": {"cfg": {"sc": {"enabled": 0, "slots": []}}}},
        },
    ]
    cloud._rebuild_mower_indices()

    asyncio.run(cloud.toggle_schedule("SERIAL-0", True))
    asyncio.run(cloud.toggle_schedule("SERIAL-1", True))

    assert calls == [
        {
            "serial": "SERIAL-0",
            "topic": "topic/p0",
            "message": {"sc": {"m": 1, "d": []}},
            "protocol": 0,
        },
        {
            "serial": "UUID-1",
            "topic": "topic/p1",
            "message": {"sc": {"enabled": 1, "slots": []}},
            "protocol": 1,
        },
    ]


def test_toggle_auto_schedule_puts_top_level_flag_and_refreshes(monkeypatch) -> None:
    """toggle_auto_schedule should PUT the observed auto_schedule field."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": False,
            "auto_schedule_settings": {"boost": 1},
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        },
        {
            "name": "Proto1",
            "serial_number": "SERIAL-1",
            "uuid": "UUID-1",
            "mac_address": "MAC-1",
            "online": True,
            "protocol": 1,
            "mqtt_topics": {"command_in": "topic/p1"},
            "auto_schedule": False,
            "auto_schedule_settings": {"boost": 2},
            "last_status": {"payload": {"cfg": {"sc": {"enabled": 1, "slots": []}}}},
        },
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {"enabled": False, "settings": {"boost": 1}}
                }
            },
        )(),
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule": True}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.toggle_auto_schedule("SERIAL-0", True))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {"auto_schedule": True}
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["auto_schedule"] is True
    assert cloud.devices["Proto0"].schedules["auto_schedule"]["enabled"] is True
    assert refreshes == [True]


def test_set_firmware_auto_upgrade_puts_top_level_flag_and_refreshes(
    monkeypatch,
) -> None:
    """set_firmware_auto_upgrade should PUT the top-level firmware flag."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "firmware_auto_upgrade": False,
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {"firmware": {"auto_upgrade": False, "version": 3.52}},
        )(),
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"firmware_auto_upgrade": True}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_firmware_auto_upgrade("SERIAL-0", True))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {"firmware_auto_upgrade": True}
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["firmware_auto_upgrade"] is True
    assert cloud.devices["Proto0"].firmware["auto_upgrade"] is True
    assert refreshes == [True]


def test_get_firmware_upgrade_info_fetches_and_caches_normalized_payload(
    monkeypatch,
) -> None:
    """get_firmware_upgrade_info should normalize firmware endpoint payload."""
    calls: list[dict[str, Any]] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "firmware_version": "3.52",
            "firmware_auto_upgrade": False,
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {"firmware": {"auto_upgrade": False, "version": "3.52"}},
        )(),
    }

    async def _get(url: str, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "headers": headers, "session": session})
        return {
            "mandatory": False,
            "has_ota_upgrade": True,
            "upgrade_failed": False,
            "product": {
                "uuid": "fw-product-1",
                "version": "3.60",
                "releasedAt": "2026-03-01",
                "changelog": {
                    "en": "• Bug fixes\n• Better battery life\n\nThanks for testing"
                },
            },
            "head": None,
        }

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.AGET", _get)

    result = asyncio.run(cloud.get_firmware_upgrade_info("SERIAL-0"))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0/firmware-upgrade")
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert result == {
        "mandatory": False,
        "current_version": "3.52",
        "latest_version": "3.60",
        "update_available": True,
        "ota_supported": True,
        "auto_upgrade": False,
        "upgrade_failed": False,
        "product": {
            "uuid": "fw-product-1",
            "version": "3.60",
            "released_at": "2026-03-01",
            "changelog": {
                "en": "• Bug fixes\n• Better battery life\n\nThanks for testing"
            },
            "changelog_markdown": {
                "en": "- Bug fixes\n- Better battery life\n\nThanks for testing"
            },
        },
        "head": None,
    }
    assert cloud.get_mower("SERIAL-0")["firmware_upgrade"]["latest_version"] == "3.60"
    assert cloud.devices["Proto0"].firmware["latest_version"] == "3.60"
    assert cloud.devices["Proto0"].firmware["update_available"] is True


def test_firmware_changelog_markdown_conversion_preserves_paragraphs() -> None:
    """Firmware changelog conversion should map bullets into Markdown lists."""
    result = WorxCloud._firmware_changelog_to_markdown(
        {
            "en": "• First item\n• Second item\n\nClosing note",
            "de": "",
        }
    )

    assert result == {
        "en": "- First item\n- Second item\n\nClosing note",
    }


def test_get_firmware_upgrade_info_maps_not_found_to_no_available_upgrade(
    monkeypatch,
) -> None:
    """get_firmware_upgrade_info should treat 404 as no current OTA upgrade."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "capabilities": ["mqtt", "ota_upgrade"],
            "mqtt_topics": {"command_in": "topic/p0"},
            "firmware_version": "3.52",
            "firmware_auto_upgrade": True,
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {"firmware": {"auto_upgrade": True, "version": "3.52"}},
        )(),
    }

    async def _get(url: str, headers: dict, session=None) -> dict[str, Any]:
        raise NotFoundError()

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.AGET", _get)

    result = asyncio.run(cloud.get_firmware_upgrade_info("SERIAL-0"))

    assert result == {
        "mandatory": False,
        "current_version": "3.52",
        "latest_version": None,
        "update_available": False,
        "ota_supported": True,
        "auto_upgrade": True,
        "upgrade_failed": False,
        "product": None,
        "head": None,
    }
    assert cloud.get_mower("SERIAL-0")["firmware_upgrade"]["update_available"] is False
    assert cloud.devices["Proto0"].firmware["update_available"] is False
    assert cloud.devices["Proto0"].firmware["latest_version"] is None


def test_start_firmware_upgrade_posts_to_firmware_endpoint_and_refreshes(
    monkeypatch,
) -> None:
    """start_firmware_upgrade should queue OTA updates through the REST endpoint."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "capabilities": ["mqtt", "ota_upgrade"],
            "firmware_upgrade": {
                "ota_supported": True,
                "latest_version": "3.60",
                "update_available": True,
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "firmware": {
                    "upgrade": {
                        "ota_supported": True,
                        "latest_version": "3.60",
                        "update_available": True,
                    }
                }
            },
        )(),
    }

    async def _post(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"queued": True}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APOST", _post)

    result = asyncio.run(cloud.start_firmware_upgrade("SERIAL-0"))

    assert result == {"queued": True}
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0/firmware-upgrade")
    assert calls[0]["body"] == ""
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["firmware_upgrade"]["command_queued"] is True
    assert cloud.devices["Proto0"].firmware["upgrade"]["command_queued"] is True
    assert refreshes == [True]


def test_start_firmware_upgrade_raises_when_ota_is_not_supported() -> None:
    """start_firmware_upgrade should fail fast when OTA is known unsupported."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "capabilities": ["mqtt"],
            "firmware_upgrade": {"ota_supported": False},
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub", (), {"firmware": {"upgrade": {"ota_supported": False}}}
        )(),
    }

    with pytest.raises(NoFirmwareOtaError, match="does not support OTA"):
        asyncio.run(cloud.start_firmware_upgrade("SERIAL-0"))


def test_start_firmware_upgrade_maps_missing_update_to_domain_error(
    monkeypatch,
) -> None:
    """start_firmware_upgrade should map missing OTA payloads to a clear error."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "capabilities": ["mqtt", "ota_upgrade"],
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {"Proto0": type("DeviceStub", (), {"firmware": {}})()}

    async def _post(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        raise NotFoundError()

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APOST", _post)

    with pytest.raises(NoFirmwareAvailableError, match="No firmware available"):
        asyncio.run(cloud.start_firmware_upgrade("SERIAL-0"))


def test_set_lawn_puts_top_level_fields_and_refreshes(monkeypatch) -> None:
    """set_lawn should PUT both top-level lawn fields and refresh."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "lawn_size": 100,
            "lawn_perimeter": 50,
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type("DeviceStub", (), {"lawn": {"perimeter": 50, "size": 100}})()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {
            "lawn_size": body["lawn_size"],
            "lawn_perimeter": body["lawn_perimeter"],
        }

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_lawn("SERIAL-0", size=250, perimeter=115))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {"lawn_size": 250, "lawn_perimeter": 115}
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    mower = cloud.get_mower("SERIAL-0")
    assert mower["lawn_size"] == 250
    assert mower["lawn_perimeter"] == 115
    assert cloud.devices["Proto0"].lawn["size"] == 250
    assert cloud.devices["Proto0"].lawn["perimeter"] == 115
    assert refreshes == [True]


def test_set_lawn_size_puts_top_level_field_and_refreshes(monkeypatch) -> None:
    """set_lawn_size should PUT the lawn_size field and refresh."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "lawn_size": 100,
            "lawn_perimeter": 50,
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type("DeviceStub", (), {"lawn": {"perimeter": 50, "size": 100}})()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"lawn_size": body["lawn_size"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_lawn_size("SERIAL-0", 250))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {"lawn_size": 250}
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    mower = cloud.get_mower("SERIAL-0")
    assert mower["lawn_size"] == 250
    assert mower["lawn_perimeter"] == 50
    assert cloud.devices["Proto0"].lawn["size"] == 250
    assert cloud.devices["Proto0"].lawn["perimeter"] == 50
    assert refreshes == [True]


def test_set_lawn_perimeter_puts_top_level_field_and_refreshes(monkeypatch) -> None:
    """set_lawn_perimeter should PUT the lawn_perimeter field and refresh."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "lawn_size": 100,
            "lawn_perimeter": 50,
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type("DeviceStub", (), {"lawn": {"perimeter": 50, "size": 100}})()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"lawn_perimeter": body["lawn_perimeter"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_lawn_perimeter("SERIAL-0", 115))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {"lawn_perimeter": 115}
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    mower = cloud.get_mower("SERIAL-0")
    assert mower["lawn_size"] == 100
    assert mower["lawn_perimeter"] == 115
    assert cloud.devices["Proto0"].lawn["size"] == 100
    assert cloud.devices["Proto0"].lawn["perimeter"] == 115
    assert refreshes == [True]


def test_set_auto_schedule_boost_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_boost should PUT merged top-level auto_schedule_settings."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 0,
                "grass_type": "mixed_species",
                "exclusion_scheduler": {"exclude_nights": True, "days": []},
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 0,
                            "grass_type": "mixed_species",
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_auto_schedule_boost("SERIAL-0", 1))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 1,
            "grass_type": "mixed_species",
            "exclusion_scheduler": {"exclude_nights": True, "days": []},
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["boost"] == 1
    assert cloud.devices["Proto0"].schedules["auto_schedule"]["settings"]["boost"] == 1
    assert refreshes == [True]


def test_set_auto_schedule_grass_type_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_grass_type should PUT merged top-level settings."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 1,
                "grass_type": "mixed_species",
                "soil_type": "ignore",
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 1,
                            "grass_type": "mixed_species",
                            "soil_type": "ignore",
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_auto_schedule_grass_type("SERIAL-0", "festuca_arundinacea"))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 1,
            "grass_type": "festuca_arundinacea",
            "soil_type": "ignore",
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert (
        cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["grass_type"]
        == "festuca_arundinacea"
    )
    assert (
        cloud.devices["Proto0"].schedules["auto_schedule"]["settings"]["grass_type"]
        == "festuca_arundinacea"
    )
    assert refreshes == [True]


def test_set_auto_schedule_soil_type_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_soil_type should PUT merged top-level settings."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 2,
                "soil_type": "ignore",
                "grass_type": "mixed_species",
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 2,
                            "soil_type": "ignore",
                            "grass_type": "mixed_species",
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_auto_schedule_soil_type("SERIAL-0", "clay"))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 2,
            "soil_type": "clay",
            "grass_type": "mixed_species",
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["soil_type"] == "clay"
    assert (
        cloud.devices["Proto0"].schedules["auto_schedule"]["settings"]["soil_type"]
        == "clay"
    )
    assert refreshes == [True]


def test_set_auto_schedule_irrigation_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_irrigation should PUT merged top-level settings."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 2,
                "soil_type": "ignore",
                "irrigation": False,
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 2,
                            "soil_type": "ignore",
                            "irrigation": False,
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_auto_schedule_irrigation("SERIAL-0", True))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 2,
            "soil_type": "ignore",
            "irrigation": True,
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["irrigation"] is True
    assert (
        cloud.devices["Proto0"].schedules["auto_schedule"]["settings"]["irrigation"]
        is True
    )
    assert refreshes == [True]


def test_set_auto_schedule_exclude_nights_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_exclude_nights should PUT merged nested settings."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 2,
                "exclusion_scheduler": {
                    "exclude_nights": False,
                    "days": [{"exclude_day": False, "slots": []}] * 7,
                },
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 2,
                            "exclusion_scheduler": {
                                "exclude_nights": False,
                                "days": [{"exclude_day": False, "slots": []}] * 7,
                            },
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_auto_schedule_exclude_nights("SERIAL-0", True))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 2,
            "exclusion_scheduler": {
                "exclude_nights": True,
                "days": [{"exclude_day": False, "slots": []}] * 7,
            },
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert (
        cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["exclusion_scheduler"][
            "exclude_nights"
        ]
        is True
    )
    assert (
        cloud.devices["Proto0"].schedules["auto_schedule"]["settings"][
            "exclusion_scheduler"
        ]["exclude_nights"]
        is True
    )
    assert refreshes == [True]


def test_set_auto_schedule_exclusion_day_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_exclusion_day should PUT a full seven-day list."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    days = [{"exclude_day": False, "slots": []} for _ in range(7)]
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "soil_type": "ignore",
                "exclusion_scheduler": {
                    "exclude_nights": True,
                    "days": days,
                },
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "soil_type": "ignore",
                            "exclusion_scheduler": {
                                "exclude_nights": True,
                                "days": [
                                    {"exclude_day": False, "slots": []}
                                    for _ in range(7)
                                ],
                            },
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_auto_schedule_exclusion_day("SERIAL-0", 2, True))

    expected_days = [{"exclude_day": False, "slots": []} for _ in range(7)]
    expected_days[2]["exclude_day"] = True

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "soil_type": "ignore",
            "exclusion_scheduler": {
                "exclude_nights": True,
                "days": expected_days,
            },
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert (
        cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["exclusion_scheduler"][
            "days"
        ][2]["exclude_day"]
        is True
    )
    assert (
        cloud.devices["Proto0"].schedules["auto_schedule"]["settings"][
            "exclusion_scheduler"
        ]["days"][2]["exclude_day"]
        is True
    )
    assert refreshes == [True]


def test_set_auto_schedule_exclusion_slots_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_exclusion_slots should replace one weekday slot list."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    days = [{"exclude_day": False, "slots": []} for _ in range(7)]
    days[4]["slots"] = [{"start_time": 120, "duration": 30, "reason": "generic"}]
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 2,
                "exclusion_scheduler": {
                    "exclude_nights": False,
                    "days": days,
                },
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 2,
                            "exclusion_scheduler": {
                                "exclude_nights": False,
                                "days": [
                                    {"exclude_day": False, "slots": []}
                                    for _ in range(7)
                                ],
                            },
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    new_slots = [
        {"start_time": 360, "duration": 45, "reason": "generic"},
        {"start_time": 900, "duration": 60, "reason": "irrigation"},
    ]
    asyncio.run(cloud.set_auto_schedule_exclusion_slots("SERIAL-0", 4, new_slots))

    expected_days = [{"exclude_day": False, "slots": []} for _ in range(7)]
    expected_days[4]["slots"] = new_slots

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 2,
            "exclusion_scheduler": {
                "exclude_nights": False,
                "days": expected_days,
            },
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert (
        cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["exclusion_scheduler"][
            "days"
        ][4]["slots"]
        == new_slots
    )
    assert (
        cloud.devices["Proto0"].schedules["auto_schedule"]["settings"][
            "exclusion_scheduler"
        ]["days"][4]["slots"]
        == new_slots
    )
    assert refreshes == [True]


def test_set_auto_schedule_nutrition_puts_merged_settings_and_refreshes(
    monkeypatch,
) -> None:
    """set_auto_schedule_nutrition should PUT merged top-level settings."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 2,
                "soil_type": "ignore",
                "irrigation": False,
                "nutrition": {"n": 18, "p": 24, "k": 6},
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 2,
                            "soil_type": "ignore",
                            "irrigation": False,
                            "nutrition": {"n": 18, "p": 24, "k": 6},
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.set_auto_schedule_nutrition("SERIAL-0", 10, 20, 5))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 2,
            "soil_type": "ignore",
            "irrigation": False,
            "nutrition": {"n": 10, "p": 20, "k": 5},
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["nutrition"] == {
        "n": 10,
        "p": 20,
        "k": 5,
    }
    assert cloud.devices["Proto0"].schedules["auto_schedule"]["settings"][
        "nutrition"
    ] == {"n": 10, "p": 20, "k": 5}
    assert refreshes == [True]


def test_clear_auto_schedule_nutrition_puts_null_and_refreshes(monkeypatch) -> None:
    """clear_auto_schedule_nutrition should PUT nutrition as null."""
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "auto_schedule": True,
            "auto_schedule_settings": {
                "boost": 2,
                "soil_type": "ignore",
                "irrigation": False,
                "nutrition": {"n": 18, "p": 24, "k": 6},
            },
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}}},
        }
    ]
    cloud._rebuild_mower_indices()
    cloud.devices = {
        "Proto0": type(
            "DeviceStub",
            (),
            {
                "schedules": {
                    "auto_schedule": {
                        "enabled": True,
                        "settings": {
                            "boost": 2,
                            "soil_type": "ignore",
                            "irrigation": False,
                            "nutrition": {"n": 18, "p": 24, "k": 6},
                        },
                    }
                }
            },
        )()
    }

    async def _put(url: str, body: Any, headers: dict, session=None) -> dict[str, Any]:
        calls.append({"url": url, "body": body, "headers": headers, "session": session})
        return {"auto_schedule_settings": body["auto_schedule_settings"]}

    async def _check_token() -> None:
        return None

    session_holder = object()

    async def _ensure_session() -> object:
        return session_holder

    async def _record_fetch(forced: bool = False) -> None:
        refreshes.append(forced)

    cloud._api.access_token = "token"
    cloud._api.check_token = _check_token  # type: ignore[method-assign]
    cloud._api._ensure_session = _ensure_session  # type: ignore[method-assign]
    cloud._fetch = _record_fetch  # type: ignore[method-assign]
    monkeypatch.setattr("pyworxcloud.APUT", _put)

    asyncio.run(cloud.clear_auto_schedule_nutrition("SERIAL-0"))

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/v2/product-items/SERIAL-0")
    assert calls[0]["body"] == {
        "auto_schedule_settings": {
            "boost": 2,
            "soil_type": "ignore",
            "irrigation": False,
            "nutrition": None,
        }
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer token"
    assert calls[0]["session"] is session_holder
    assert cloud.get_mower("SERIAL-0")["auto_schedule_settings"]["nutrition"] is None
    assert (
        cloud.devices["Proto0"].schedules["auto_schedule"]["settings"]["nutrition"]
        is None
    )
    assert refreshes == [True]


def test_schedule_crud_publishes_normalized_payload_and_refreshes() -> None:
    """Schedule CRUD should publish protocol-specific payloads and trigger refresh."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    calls: list[dict[str, Any]] = []
    refreshes: list[bool] = []

    class CapturingMQTT(DummyMQTT):
        async def apublish(
            self,
            serial: str,
            topic: str,
            message: Any,
            protocol: int | None = None,
        ) -> None:
            calls.append(
                {
                    "serial": serial,
                    "topic": topic,
                    "message": message,
                    "protocol": protocol,
                }
            )

    async def _record_refresh(is_err: bool = False) -> None:
        refreshes.append(is_err)

    cloud.mqtt = CapturingMQTT()
    cloud._schedule_api_refresh = _record_refresh  # type: ignore[method-assign]
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "last_status": {
                "payload": {
                    "cfg": {
                        "sc": {
                            "m": 1,
                            "p": 0,
                            "d": [["09:00", 30, 1]] + [["00:00", 0, 0]] * 6,
                            "dd": [["12:00", 20, 0]] + [["00:00", 0, 0]] * 6,
                        }
                    }
                }
            },
        },
        {
            "name": "Proto1",
            "serial_number": "SERIAL-1",
            "uuid": "UUID-1",
            "mac_address": "MAC-1",
            "online": True,
            "protocol": 1,
            "mqtt_topics": {"command_in": "topic/p1"},
            "last_status": {
                "payload": {
                    "cfg": {
                        "sc": {
                            "enabled": 1,
                            "paused": 0,
                            "freq": 0,
                            "slots": [
                                {
                                    "e": 1,
                                    "d": 1,
                                    "s": 600,
                                    "t": 120,
                                    "cfg": {"cut": {"b": 0, "ob": 1, "z": [1, 2]}},
                                }
                            ],
                        }
                    }
                }
            },
        },
    ]
    cloud._rebuild_mower_indices()

    proto0_schedule = cloud.get_schedule("SERIAL-0")
    assert proto0_schedule.entries[0].entry_id == "p0:sunday:primary"

    asyncio.run(cloud.delete_schedule_entry("SERIAL-0", "p0:sunday:primary"))
    asyncio.run(
        cloud.update_schedule_entry(
            "SERIAL-1",
            "p1:0",
            ScheduleEntry(
                entry_id="ignored",
                day="monday",
                start="11:00",
                duration=30,
                boundary=True,
                source="slot",
                secondary=False,
            ),
        )
    )
    asyncio.run(
        cloud.add_schedule_entry(
            "SERIAL-1",
            ScheduleEntry(
                entry_id="",
                day="tuesday",
                start="12:00",
                duration=50,
                boundary=False,
                source="slot",
                secondary=False,
            ),
        )
    )
    asyncio.run(
        cloud.set_schedule(
            "SERIAL-1",
            ScheduleModel(
                enabled=False,
                time_extension=None,
                protocol=1,
                entries=cloud.get_schedule("SERIAL-1").entries,
            ),
        )
    )

    assert calls[0] == {
        "serial": "SERIAL-0",
        "topic": "topic/p0",
        "message": {
            "sc": {
                "m": 1,
                "p": 0,
                "d": [["12:00", 20, 0]] + [["00:00", 0, 0]] * 6,
                "dd": [["00:00", 0, 0]] + [["00:00", 0, 0]] * 6,
            }
        },
        "protocol": 0,
    }
    assert calls[1]["serial"] == "UUID-1"
    assert calls[1]["message"]["sc"]["slots"][0]["s"] == 660
    assert calls[1]["message"]["sc"]["slots"][0]["cfg"]["cut"]["ob"] == 1
    assert len(calls[2]["message"]["sc"]["slots"]) == 2
    assert calls[2]["message"]["sc"]["freq"] == 0
    assert calls[3]["message"]["sc"]["enabled"] == 1
    assert refreshes == [False, False, False, False]


def test_set_torque_publishes_torque_payload() -> None:
    """set_torque should publish the documented tq payload."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    calls: list[dict[str, Any]] = []

    class CapturingMQTT(DummyMQTT):
        async def apublish(
            self,
            serial: str,
            topic: str,
            message: Any,
            protocol: int | None = None,
        ) -> None:
            calls.append(
                {
                    "serial": serial,
                    "topic": topic,
                    "message": message,
                    "protocol": protocol,
                }
            )

    cloud.mqtt = CapturingMQTT()
    cloud._mowers = [
        {
            "name": "Target",
            "serial_number": "SERIAL-1",
            "uuid": "UUID-1",
            "mac_address": "MAC-1",
            "online": True,
            "protocol": 1,
            "mqtt_topics": {"command_in": "topic/in"},
        }
    ]
    cloud._rebuild_mower_indices()

    asyncio.run(cloud.set_torque("SERIAL-1", -13))

    assert calls == [
        {
            "serial": "UUID-1",
            "topic": "topic/in",
            "message": {"cfg": {"tq": -13}},
            "protocol": 1,
        }
    ]


def test_set_pause_mode_warns_and_calls_party_mode(monkeypatch) -> None:
    """Deprecated set_pause_mode should warn and delegate to set_party_mode."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    calls: list[dict[str, Any]] = []

    class CapturingMQTT(DummyMQTT):
        async def apublish(
            self,
            serial: str,
            topic: str,
            message: Any,
            protocol: int | None = None,
        ) -> None:
            calls.append(
                {
                    "serial": serial,
                    "topic": topic,
                    "message": message,
                    "protocol": protocol,
                }
            )

    class DummyCapabilities:
        def check(self, _capability: Any) -> bool:
            return True

    class StubDeviceHandler:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.capabilities = DummyCapabilities()

    monkeypatch.setattr("pyworxcloud.DeviceHandler", StubDeviceHandler)
    cloud.mqtt = CapturingMQTT()
    cloud._mowers = [
        {
            "name": "Proto0",
            "serial_number": "SERIAL-0",
            "uuid": "UUID-0",
            "mac_address": "MAC-0",
            "online": True,
            "protocol": 0,
            "mqtt_topics": {"command_in": "topic/p0"},
            "last_status": {"payload": {"cfg": {"sc": {"m": 1, "d": []}}, "dat": {}}},
        }
    ]
    cloud._rebuild_mower_indices()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        asyncio.run(cloud.set_pause_mode("SERIAL-0", True))

    assert any(
        "set_pause_mode() is deprecated" in str(item.message) for item in captured
    )
    assert calls[0]["message"] == {"sc": {"m": 2, "distm": 0}}


def test_set_party_mode_protocol1_includes_cmd0(monkeypatch) -> None:
    """Protocol 1 party mode writes should include the cmd=0 scheduler envelope."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    calls: list[dict[str, Any]] = []

    class CapturingMQTT(DummyMQTT):
        async def apublish(
            self,
            serial: str,
            topic: str,
            message: Any,
            protocol: int | None = None,
        ) -> None:
            calls.append(
                {
                    "serial": serial,
                    "topic": topic,
                    "message": message,
                    "protocol": protocol,
                }
            )

    class DummyCapabilities:
        def check(self, _capability: Any) -> bool:
            return True

    class StubDeviceHandler:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.capabilities = DummyCapabilities()

    monkeypatch.setattr("pyworxcloud.DeviceHandler", StubDeviceHandler)
    cloud.mqtt = CapturingMQTT()
    cloud._mowers = [
        {
            "name": "Proto1",
            "serial_number": "SERIAL-1",
            "uuid": "UUID-1",
            "mac_address": "MAC-1",
            "online": True,
            "protocol": 1,
            "mqtt_topics": {"command_in": "topic/p1"},
            "last_status": {
                "payload": {"cfg": {"sc": {"enabled": 0, "paused": 0}}, "dat": {}}
            },
        }
    ]
    cloud._rebuild_mower_indices()

    asyncio.run(cloud.set_party_mode("SERIAL-1", False))

    assert calls == [
        {
            "serial": "UUID-1",
            "topic": "topic/p1",
            "message": {"cmd": 0, "sc": {"enabled": 1}},
            "protocol": 1,
        }
    ]
