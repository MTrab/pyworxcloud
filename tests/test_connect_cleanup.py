"""Tests for cleanup when WorxCloud.connect fails mid-lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any

from pyworxcloud import WorxCloud


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


class FailingMQTT:
    """MQTT stub that fails during async connect and records cleanup."""

    instances: list["FailingMQTT"] = []

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
        self.response_timeout = response_timeout
        self.identifier_resolver = identifier_resolver
        self.deduplicate_inflight_commands = deduplicate_inflight_commands
        self.disconnect_calls = 0
        self.shutdown_calls = 0
        self.__class__.instances.append(self)

    async def aconnect(self) -> None:
        raise RuntimeError("connect failed")

    async def asubscribe(self, _topic: str, _append: bool = True) -> None:
        return None

    async def adisconnect(self, _keep_topic: bool = False) -> None:
        self.disconnect_calls += 1

    async def ashutdown(self) -> None:
        self.shutdown_calls += 1


class TransientMQTT(FailingMQTT):
    """MQTT stub that fails once and then reconnects."""

    async def aconnect(self) -> None:
        if len(self.__class__.instances) == 1:
            raise RuntimeError("connect failed")
        self.connected = True

    async def asubscribe(self, topic: str, _append: bool = True) -> None:
        subscriptions = getattr(self, "subscriptions", [])
        subscriptions.append(topic)
        self.subscriptions = subscriptions


def test_mqtt_connect_failure_keeps_api_fallback_running(monkeypatch) -> None:
    """MQTT failure should not prevent API-backed connect from succeeding."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    session = DummySession()
    FailingMQTT.instances = []

    async def _fake_fetch() -> None:
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

    monkeypatch.setattr(cloud, "_fetch", _fake_fetch)
    monkeypatch.setattr("pyworxcloud.MQTT", FailingMQTT)
    monkeypatch.setattr("pyworxcloud.convert_to_time", lambda *_args, **_kwargs: None)

    async def _exercise() -> None:
        assert await cloud.connect() is True
        assert cloud.mqtt is None
        assert cloud._mqtt_retry_task is not None
        assert session.close_calls == 0
        assert session.closed is False
        assert cloud._disconnecting.is_set() is False
        await cloud.disconnect()

    asyncio.run(_exercise())

    assert len(FailingMQTT.instances) == 1
    assert FailingMQTT.instances[0].disconnect_calls == 1
    assert FailingMQTT.instances[0].shutdown_calls == 1
    assert cloud.mqtt is None
    assert session.close_calls == 1
    assert session.closed is True
    assert cloud._disconnecting.is_set() is True


def test_mqtt_background_retry_reconnects_without_api_refetch(monkeypatch) -> None:
    """Background MQTT retry should use existing API data and restore MQTT."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    TransientMQTT.instances = []
    fetch_calls = 0

    async def _fake_fetch() -> None:
        nonlocal fetch_calls
        fetch_calls += 1
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
    monkeypatch.setattr("pyworxcloud.MQTT", TransientMQTT)
    monkeypatch.setattr("pyworxcloud.MQTT_RECONNECT_RETRY_SECONDS", 0)
    monkeypatch.setattr("pyworxcloud.convert_to_time", lambda *_args, **_kwargs: None)

    async def _exercise() -> None:
        assert await cloud.connect() is True
        for _ in range(50):
            await asyncio.sleep(0)
            if cloud.mqtt is not None:
                break
        assert cloud.mqtt is TransientMQTT.instances[1]
        assert cloud.mqtt.subscriptions == ["topic/out"]
        await cloud.disconnect()

    asyncio.run(_exercise())

    assert fetch_calls == 1
    assert len(TransientMQTT.instances) == 2
    assert TransientMQTT.instances[0].disconnect_calls == 1
    assert TransientMQTT.instances[0].shutdown_calls == 1
