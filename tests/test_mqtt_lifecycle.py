"""Tests for MQTT lifecycle teardown safety."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from pyworxcloud.utils.mqtt import MQTT, MQTT_CONNECT_ACCEPTED


class _ImmediateFuture:
    """Simple future stub with immediate completion."""

    def result(self, timeout: float | None = None) -> None:
        return None


class _TimeoutFuture:
    """Future stub that always times out."""

    def result(self, timeout: float | None = None) -> None:
        raise FutureTimeoutError(f"timed out after {timeout}")


class _ClientStub:
    """Client stub that records disconnect attempts."""

    def __init__(self, should_raise: bool = False) -> None:
        self.disconnect_calls = 0
        self.should_raise = should_raise
        self.future: Any = _ImmediateFuture()

    def disconnect(self) -> _ImmediateFuture:
        self.disconnect_calls += 1
        if self.should_raise:
            raise RuntimeError("disconnect failed")
        return self.future


def _build_mqtt_lifecycle_fixture(
    *, connected: bool = True, client: Any | None = None
) -> MQTT:
    mqtt = MQTT.__new__(MQTT)
    mqtt._log = logging.getLogger("test")
    mqtt._lifecycle_lock = threading.RLock()
    mqtt._shutdown_event = False
    mqtt._is_connected = connected
    mqtt._connection_future = object()
    mqtt._shutdown_timeout = 5.0
    mqtt._topic = ["topic/out"]
    mqtt.client = client
    return mqtt


def test_disconnect_is_idempotent_and_safe_with_missing_client() -> None:
    """Disconnect should be safe to call repeatedly and with no client."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.disconnect()
    mqtt.client = None
    mqtt.disconnect()

    assert client.disconnect_calls == 1
    assert mqtt._connection_future is None
    assert mqtt._is_connected is False


def test_disconnect_swallows_teardown_disconnect_errors() -> None:
    """Disconnect should keep teardown stable even when client disconnect fails."""
    mqtt = _build_mqtt_lifecycle_fixture(client=_ClientStub(should_raise=True))

    mqtt.disconnect()

    assert mqtt._is_connected is False


def test_disconnect_swallows_disconnect_future_timeout() -> None:
    """Disconnect should not block indefinitely on disconnect futures."""
    client = _ClientStub()
    client.future = _TimeoutFuture()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.disconnect()

    assert client.disconnect_calls == 1
    assert mqtt._connection_future is None
    assert mqtt._is_connected is False


def test_shutdown_is_idempotent_and_detaches_resources() -> None:
    """Shutdown should execute cleanup once and detach the paho client."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.shutdown()
    mqtt.shutdown()

    assert client.disconnect_calls == 1
    assert mqtt.client is None
    assert mqtt._connection_future is None
    assert mqtt._shutdown_event is True
    assert mqtt._is_connected is False


def test_shutdown_skips_second_disconnect_after_prior_disconnect() -> None:
    """Shutdown should not disconnect again after a clean disconnect."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.disconnect()
    mqtt.shutdown()

    assert client.disconnect_calls == 1


def test_shutdown_swallows_disconnect_future_timeout() -> None:
    """Shutdown should not block indefinitely on disconnect futures."""
    client = _ClientStub()
    client.future = _TimeoutFuture()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.shutdown()

    assert client.disconnect_calls == 1
    assert mqtt._shutdown_event is True


def test_connection_resumed_resubscribes_even_when_session_persists() -> None:
    """Resume should trigger a full reconnect even when session_present is true."""
    mqtt = _build_mqtt_lifecycle_fixture(connected=False, client=_ClientStub())
    mqtt._topic = ["topic/a", "topic/b"]
    mqtt._awaiting_post_resume_message = False
    reconnect_calls: list[str] = []
    mqtt._schedule_reconnect_after_resume = lambda: reconnect_calls.append("called")

    mqtt._on_connection_resumed(
        None,
        MQTT_CONNECT_ACCEPTED,
        True,
    )

    assert mqtt._is_connected is False
    assert mqtt._get_ready_event().is_set() is False
    assert mqtt._awaiting_post_resume_message is False
    assert reconnect_calls == ["called"]


def test_connection_resumed_resubscribes_when_session_is_not_present() -> None:
    """Resume should trigger a full reconnect when the session is lost."""
    mqtt = _build_mqtt_lifecycle_fixture(connected=False, client=_ClientStub())
    mqtt._topic = ["topic/out"]
    mqtt._awaiting_post_resume_message = False
    reconnect_calls: list[str] = []
    mqtt._schedule_reconnect_after_resume = lambda: reconnect_calls.append("called")

    mqtt._on_connection_resumed(
        None,
        MQTT_CONNECT_ACCEPTED,
        False,
    )

    assert mqtt._is_connected is False
    assert mqtt._awaiting_post_resume_message is False
    assert reconnect_calls == ["called"]
