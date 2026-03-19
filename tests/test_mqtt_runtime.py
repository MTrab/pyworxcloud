"""Tests for MQTT runtime safety during reconnect and token refresh."""

from __future__ import annotations

import logging
import threading
import time

import awscrt.mqtt
import pytest

from pyworxcloud.events import EventHandler
from pyworxcloud.exceptions import TimeoutException
from pyworxcloud.utils.mqtt import MQTT


def _build_mqtt() -> MQTT:
    """Create a bare MQTT instance without AWS CRT setup."""
    mqtt = MQTT.__new__(MQTT)
    mqtt._log = logging.getLogger("pyworxcloud.test.mqtt")
    mqtt._events = EventHandler()
    mqtt._topic = ["topic/out"]
    mqtt._is_connected = False
    mqtt._ready_event = threading.Event()
    mqtt._token_update_lock = threading.Lock()
    mqtt._lifecycle_lock = threading.RLock()
    mqtt._active_generation = 2
    mqtt._client_generation = 2
    mqtt._response_timeout = 0.2
    mqtt._shutdown_event = False
    mqtt._connection_future = None
    mqtt._reconnected = False
    mqtt.client = object()
    return mqtt


def test_connection_resumed_ignores_stale_generation() -> None:
    """Stale AWS callbacks must not flip connection state back to ready."""
    mqtt = _build_mqtt()
    subscribe_calls: list[tuple[str, bool, int | None]] = []

    mqtt.subscribe = lambda topic, append, generation=None: subscribe_calls.append(
        (topic, append, generation)
    )

    mqtt._on_connection_resumed(
        object(),
        awscrt.mqtt.ConnectReturnCode.ACCEPTED,
        True,
        generation=1,
    )

    assert mqtt.connected is False
    assert mqtt._ready_event.is_set() is False
    assert subscribe_calls == []


def test_connection_resumed_marks_active_generation_ready() -> None:
    """Active resume callbacks should trigger a forced reconnect instead."""
    mqtt = _build_mqtt()
    reconnect_calls: list[str] = []
    mqtt._schedule_reconnect_after_resume = lambda: reconnect_calls.append("called")

    mqtt._on_connection_resumed(
        object(),
        awscrt.mqtt.ConnectReturnCode.ACCEPTED,
        True,
        generation=2,
    )

    assert mqtt.connected is False
    assert mqtt._ready_event.is_set() is False
    assert reconnect_calls == ["called"]


def test_ensure_connection_ready_waits_for_parallel_refresh() -> None:
    """Publish callers should wait for an in-flight token refresh to finish."""
    mqtt = _build_mqtt()
    mqtt._token_update_lock.acquire()

    def _finish_refresh() -> None:
        time.sleep(0.05)
        mqtt._is_connected = True
        mqtt._ready_event.set()
        mqtt._token_update_lock.release()

    worker = threading.Thread(target=_finish_refresh)
    worker.start()
    try:
        mqtt._ensure_connection_ready(timeout=0.2)
    finally:
        worker.join()

    assert mqtt.connected is True


def test_ensure_connection_ready_times_out_during_stuck_refresh() -> None:
    """A stuck token refresh should fail clearly instead of using a bad client."""
    mqtt = _build_mqtt()
    mqtt._token_update_lock.acquire()

    try:
        with pytest.raises(
            TimeoutException, match="MQTT connection unavailable during token refresh"
        ):
            mqtt._ensure_connection_ready(timeout=0.01)
    finally:
        mqtt._token_update_lock.release()
