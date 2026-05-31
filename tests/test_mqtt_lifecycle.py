"""Tests for MQTT lifecycle teardown safety."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from pyworxcloud.const import (
    PAHO_MQTT_RECONNECT_MAX_DELAY_SECONDS,
    PAHO_MQTT_RECONNECT_MIN_DELAY_SECONDS,
)
from pyworxcloud.events import EventHandler
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


class _PahoConfigStub:
    """Client stub that records setup calls."""

    def __init__(self) -> None:
        self.reconnect_delay: tuple[int, int] | None = None

    def username_pw_set(self, username: str, password: str | None = None) -> None:
        self.username = username
        self.password = password

    def tls_set(self, **_kwargs: Any) -> None:
        return None

    def ws_set_options(self, **_kwargs: Any) -> None:
        return None

    def reconnect_delay_set(self, min_delay: int, max_delay: int) -> None:
        self.reconnect_delay = (min_delay, max_delay)


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
    mqtt._disconnect_timeout = 5.0
    mqtt._topic = ["topic/out"]
    mqtt._response_lock = threading.Lock()
    mqtt._response_event = threading.Event()
    mqtt._pending_response_target = None
    mqtt._pending_response_message_id = None
    mqtt._pending_response_accepts_any_message_id = False
    mqtt._pending_command_signature = None
    mqtt.client = client
    return mqtt


def test_create_mqtt_connection_uses_conservative_paho_reconnect_backoff() -> None:
    """Paho reconnect backoff should not hammer the broker."""
    mqtt = MQTT.__new__(MQTT)
    mqtt._api = type("API", (), {"access_token": "aaa.bbb.ccc"})()
    mqtt._client_generation = 0
    mqtt._active_generation = 0
    mqtt._client_id = "client-id"
    mqtt._log = logging.getLogger("test")
    client = _PahoConfigStub()
    mqtt._create_paho_client = lambda: client

    assert mqtt._create_mqtt_connection() is client
    assert client.reconnect_delay == (
        PAHO_MQTT_RECONNECT_MIN_DELAY_SECONDS,
        PAHO_MQTT_RECONNECT_MAX_DELAY_SECONDS,
    )


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


def test_disconnect_releases_pending_command_waiter() -> None:
    """Disconnect should wake command waits so shutdown is not delayed by timeout."""
    mqtt = _build_mqtt_lifecycle_fixture(client=_ClientStub())
    mqtt._pending_response_target = "SN-1"
    mqtt._pending_response_message_id = 1234
    mqtt._pending_response_accepts_any_message_id = True
    mqtt._pending_command_signature = ("SN-1", "topic/in", 0, "{}")

    mqtt.disconnect()

    assert mqtt._response_event.is_set() is True
    assert mqtt._pending_response_target is None
    assert mqtt._pending_response_message_id is None
    assert mqtt._pending_response_accepts_any_message_id is False
    assert mqtt._pending_command_signature is None


def test_disconnect_does_not_hang_when_loop_stop_blocks() -> None:
    """Disconnect should not wait forever for paho loop_stop."""
    loop_stop_started = threading.Event()
    release_loop_stop = threading.Event()

    class BlockingLoopStopClient(_ClientStub):
        def loop_stop(self) -> None:
            loop_stop_started.set()
            release_loop_stop.wait()

    mqtt = _build_mqtt_lifecycle_fixture(client=BlockingLoopStopClient())

    started = time.perf_counter()
    try:
        mqtt.disconnect()
    finally:
        release_loop_stop.set()

    assert loop_stop_started.is_set() is True
    assert time.perf_counter() - started < 1.0
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


def test_disconnect_before_initial_connect_unblocks_connect_wait() -> None:
    """A broker hangup during initial connect should fail the attempt immediately."""
    mqtt = _build_mqtt_lifecycle_fixture(connected=False, client=_ClientStub())
    mqtt._events = EventHandler()
    mqtt._connect_error = None
    connect_event = mqtt._get_connect_event()
    connect_event.clear()

    mqtt._on_paho_disconnect(mqtt.client, None, 1)

    assert connect_event.is_set() is True
    assert mqtt._connect_error is not None
    assert "before ready" in str(mqtt._connect_error)
