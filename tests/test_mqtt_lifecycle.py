"""Tests for MQTT lifecycle teardown safety."""

from __future__ import annotations

import logging
import threading
from typing import Any

from pyworxcloud.utils.mqtt import MQTT


class _ImmediateFuture:
    """Simple future stub with immediate completion."""

    def result(self) -> None:
        return None


class _ClientStub:
    """Client stub that records disconnect attempts."""

    def __init__(self, should_raise: bool = False) -> None:
        self.disconnect_calls = 0
        self.should_raise = should_raise

    def disconnect(self) -> _ImmediateFuture:
        self.disconnect_calls += 1
        if self.should_raise:
            raise RuntimeError("disconnect failed")
        return _ImmediateFuture()


class _ShutdownEventStub:
    """Stub exposing a wait() method used by AWS CRT resources."""

    def __init__(self) -> None:
        self.wait_calls = 0

    def wait(self, _timeout: float) -> bool:
        self.wait_calls += 1
        return True


class _ShutdownResourceStub:
    """Resource stub with shutdown_event attribute."""

    def __init__(self) -> None:
        self.shutdown_event = _ShutdownEventStub()


def _build_mqtt_lifecycle_fixture(
    *, connected: bool = True, client: Any | None = None
) -> MQTT:
    mqtt = MQTT.__new__(MQTT)
    mqtt._log = logging.getLogger("test")
    mqtt._lifecycle_lock = threading.RLock()
    mqtt._shutdown_event = False
    mqtt._is_connected = connected
    mqtt._topic = ["topic/out"]
    mqtt.client = client
    mqtt._host_resolver = _ShutdownResourceStub()
    mqtt._client_bootstrap = _ShutdownResourceStub()
    mqtt._event_loop_group = _ShutdownResourceStub()
    return mqtt


def test_disconnect_is_idempotent_and_safe_with_missing_client() -> None:
    """Disconnect should be safe to call repeatedly and with no client."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.disconnect()
    mqtt.client = None
    mqtt.disconnect()

    assert client.disconnect_calls == 1
    assert mqtt._is_connected is False


def test_disconnect_swallows_teardown_disconnect_errors() -> None:
    """Disconnect should keep teardown stable even when client disconnect fails."""
    mqtt = _build_mqtt_lifecycle_fixture(client=_ClientStub(should_raise=True))

    mqtt.disconnect()

    assert mqtt._is_connected is False


def test_shutdown_is_idempotent_and_detaches_resources() -> None:
    """Shutdown should execute cleanup once and detach all AWS CRT resources."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.shutdown()
    mqtt.shutdown()

    assert client.disconnect_calls == 1
    assert mqtt.client is None
    assert mqtt._host_resolver is None
    assert mqtt._client_bootstrap is None
    assert mqtt._event_loop_group is None
    assert mqtt._shutdown_event is True
    assert mqtt._is_connected is False
