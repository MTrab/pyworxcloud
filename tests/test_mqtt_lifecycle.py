"""Tests for MQTT lifecycle teardown safety."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

import awscrt.mqtt
import pytest

from pyworxcloud.utils.mqtt import MQTT, _connect_with_awscrt_compat


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


class _ConnectMismatchClientStub:
    """Client stub that reproduces the awscrt 17/18-arg connect mismatch."""

    def connect(self) -> None:
        raise TypeError("function takes exactly 18 arguments (17 given)")


class _ConnectTypeErrorClientStub:
    """Client stub that raises an unrelated TypeError."""

    def connect(self) -> None:
        raise TypeError("some other type error")


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
    mqtt._connection_future = object()
    mqtt._shutdown_timeout = 5.0
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
    """Shutdown should execute cleanup once and detach all AWS CRT resources."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.shutdown()
    mqtt.shutdown()

    assert client.disconnect_calls == 1
    assert mqtt.client is None
    assert mqtt._connection_future is None
    assert mqtt._host_resolver is None
    assert mqtt._client_bootstrap is None
    assert mqtt._event_loop_group is None
    assert mqtt._shutdown_event is True
    assert mqtt._is_connected is False


def test_shutdown_skips_second_disconnect_after_prior_disconnect() -> None:
    """Shutdown should not disconnect again after a clean disconnect."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.disconnect()
    mqtt.shutdown()

    assert client.disconnect_calls == 1


def test_shutdown_waits_for_resource_shutdown_events() -> None:
    """Shutdown should give CRT resources a bounded chance to tear down cleanly."""
    client = _ClientStub()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)
    host_resolver = mqtt._host_resolver
    client_bootstrap = mqtt._client_bootstrap
    event_loop_group = mqtt._event_loop_group

    mqtt.shutdown()

    assert (
        host_resolver.shutdown_event.wait_calls,
        client_bootstrap.shutdown_event.wait_calls,
        event_loop_group.shutdown_event.wait_calls,
    ) == (1, 1, 1)


def test_shutdown_swallows_disconnect_future_timeout() -> None:
    """Shutdown should not block indefinitely on disconnect futures."""
    client = _ClientStub()
    client.future = _TimeoutFuture()
    mqtt = _build_mqtt_lifecycle_fixture(client=client)

    mqtt.shutdown()

    assert client.disconnect_calls == 1
    assert mqtt._shutdown_event is True


def test_connect_with_awscrt_compat_retries_known_arg_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known mixed awscrt installs should use the legacy compatibility path."""
    fallback_future = _ImmediateFuture()
    fallback_calls: list[Any] = []

    def _legacy(client: Any) -> _ImmediateFuture:
        fallback_calls.append(client)
        return fallback_future

    monkeypatch.setattr(
        "pyworxcloud.utils.mqtt._legacy_connect_without_metrics", _legacy
    )

    result = _connect_with_awscrt_compat(
        _ConnectMismatchClientStub(),
        logging.getLogger("test"),
    )

    assert result is fallback_future
    assert len(fallback_calls) == 1


def test_connect_with_awscrt_compat_preserves_unrelated_type_errors() -> None:
    """Only the known awscrt mismatch should trigger the compatibility path."""
    with pytest.raises(TypeError, match="some other type error"):
        _connect_with_awscrt_compat(
            _ConnectTypeErrorClientStub(),
            logging.getLogger("test"),
        )


def test_connection_resumed_resubscribes_even_when_session_persists() -> None:
    """Resume should trigger a full reconnect even when session_present is true."""
    mqtt = _build_mqtt_lifecycle_fixture(connected=False, client=_ClientStub())
    mqtt._topic = ["topic/a", "topic/b"]
    mqtt._awaiting_post_resume_message = False
    reconnect_calls: list[str] = []
    mqtt._schedule_reconnect_after_resume = lambda: reconnect_calls.append("called")

    mqtt._on_connection_resumed(
        None,
        awscrt.mqtt.ConnectReturnCode.ACCEPTED,
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
        awscrt.mqtt.ConnectReturnCode.ACCEPTED,
        False,
    )

    assert mqtt._is_connected is False
    assert mqtt._awaiting_post_resume_message is False
    assert reconnect_calls == ["called"]
