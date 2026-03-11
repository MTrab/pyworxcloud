"""Tests for API and lifecycle behavior without network access."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from pyworxcloud import WorxCloud
from pyworxcloud.api import LandroidCloudAPI
from pyworxcloud.clouds import CloudType
from pyworxcloud.events import LandroidEvent
from pyworxcloud.helpers.logger import get_logger


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


def test_token_updated_is_noop_without_mqtt() -> None:
    """Token update callback should be safe before MQTT is initialized."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud.mqtt = None
    asyncio.run(cloud._token_updated())


def test_get_logger_does_not_accumulate_handlers() -> None:
    """Repeated logger setup should reuse the existing handler."""
    logger = logging.getLogger("pyworxcloud.test_handlers")
    original_handlers = list(logger.handlers)
    original_level = logger.level

    try:
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)

        first = get_logger("pyworxcloud.test_handlers")
        second = get_logger("pyworxcloud.test_handlers")

        assert first is second
        assert len(first.handlers) == 1
        assert isinstance(first.handlers[0], logging.StreamHandler)
    finally:
        logger.handlers.clear()
        logger.setLevel(original_level)
        for handler in original_handlers:
            logger.addHandler(handler)


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
    assert all(instance.subscriptions == ["topic/out"] for instance in TrackingMQTT.instances)
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


def test_set_time_extension_publishes_schedule_payload() -> None:
    """set_time_extension should publish the documented sc.p payload."""
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

    asyncio.run(cloud.set_time_extension("SERIAL-1", 20))

    assert calls == [
        {
            "serial": "UUID-1",
            "topic": "topic/in",
            "message": {"sc": {"p": 20}},
            "protocol": 1,
        }
    ]
