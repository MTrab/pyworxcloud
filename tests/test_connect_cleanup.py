"""Tests for cleanup when WorxCloud.connect fails mid-lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

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


def test_connect_failure_cleans_up_mqtt_and_api_session(monkeypatch) -> None:
    """A failed connect should not leave partial MQTT or API resources behind."""
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

    with pytest.raises(RuntimeError, match="connect failed"):
        asyncio.run(cloud.connect())

    assert len(FailingMQTT.instances) == 1
    assert FailingMQTT.instances[0].disconnect_calls == 1
    assert FailingMQTT.instances[0].shutdown_calls == 1
    assert cloud.mqtt is None
    assert session.close_calls == 1
    assert session.closed is True
    assert cloud._disconnecting.is_set() is True
