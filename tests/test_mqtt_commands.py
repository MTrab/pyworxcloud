"""Tests for MQTT command serialization and response timeouts."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import pytest

from pyworxcloud.exceptions import TimeoutException
from pyworxcloud.utils.mqtt import MQTT


class _ImmediateFuture:
    """Simple future stub with immediate completion."""

    def result(self) -> None:
        return None


class _DummyClient:
    """MQTT client stub that records outgoing payloads."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.publish_events: list[threading.Event] = []

    def publish(
        self, topic: str, payload: str, qos: Any
    ) -> tuple[_ImmediateFuture, int]:
        entry = {"topic": topic, "payload": payload, "qos": qos}
        self.published.append(entry)
        event = threading.Event()
        event.set()
        self.publish_events.append(event)
        return _ImmediateFuture(), 1


def _build_mqtt(
    monkeypatch: pytest.MonkeyPatch,
    response_timeout: float = 30.0,
    identifier_resolver: Any | None = None,
) -> tuple[MQTT, _DummyClient]:
    dummy_client = _DummyClient()
    dummy_api = type("API", (), {"access_token": "a.b.c"})()

    monkeypatch.setattr(MQTT, "_create_mqtt_connection", lambda self: dummy_client)

    mqtt = MQTT(
        api=dummy_api,
        brandprefix="WX",
        endpoint="example.com",
        user_id=42,
        logger=logging.getLogger("test"),
        callback=lambda _payload: None,
        identifier_resolver=identifier_resolver,
        response_timeout=response_timeout,
    )
    mqtt._is_connected = True
    return mqtt, dummy_client


def test_publish_times_out_when_no_response(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Publish should raise TimeoutException when no matching response arrives."""
    mqtt, _dummy = _build_mqtt(monkeypatch)

    with pytest.raises(TimeoutException):
        with caplog.at_level("WARNING", logger="pyworxcloud.utils.mqtt"):
            mqtt.publish(
                serial_number="SN-1",
                topic="topic/in",
                message={"cmd": 1},
                protocol=0,
                timeout=0.05,
            )
    assert "Timeout waiting for device response" in caplog.text


def test_publish_uses_default_response_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publish without explicit timeout should use MQTT default response timeout."""
    mqtt, _dummy = _build_mqtt(monkeypatch, response_timeout=0.05)

    with pytest.raises(TimeoutException):
        mqtt.publish(
            serial_number="SN-1",
            topic="topic/in",
            message={"cmd": 1},
            protocol=0,
        )


def test_mqtt_rejects_non_positive_default_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MQTT constructor should validate response timeout input."""
    with pytest.raises(ValueError):
        _build_mqtt(monkeypatch, response_timeout=0.0)


def test_publish_waits_for_matching_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publish should complete only after receiving matching mower response."""
    mqtt, dummy = _build_mqtt(monkeypatch)
    finished = threading.Event()
    errors: list[Exception] = []

    def _run_publish() -> None:
        try:
            mqtt.publish(
                serial_number="SN-1",
                topic="topic/in",
                message={"cmd": 1},
                protocol=0,
                timeout=1.0,
            )
            finished.set()
        except Exception as exc:  # pragma: no cover - defensive for thread failures
            errors.append(exc)

    thread = threading.Thread(target=_run_publish)
    thread.start()

    deadline = time.time() + 1.0
    while len(dummy.published) < 1 and time.time() < deadline:
        time.sleep(0.01)
    assert dummy.published, "Expected at least one published message"

    payload = json.loads(dummy.published[0]["payload"])
    command_id = payload["id"]
    assert finished.is_set() is False

    mqtt._on_message_received(
        "topic/out",
        json.dumps({"cfg": {"sn": "SN-other", "id": command_id}}).encode("utf-8"),
    )
    time.sleep(0.05)
    assert finished.is_set() is False

    mqtt._on_message_received(
        "topic/out",
        json.dumps({"cfg": {"sn": "SN-1", "id": command_id}}).encode("utf-8"),
    )

    thread.join(timeout=1.0)
    assert thread.is_alive() is False
    assert errors == []
    assert finished.is_set() is True


def test_publish_serializes_concurrent_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second command should wait until first command completes."""
    mqtt, dummy = _build_mqtt(monkeypatch)
    failures: list[str] = []

    def _publish(serial: str) -> None:
        try:
            mqtt.publish(
                serial_number=serial,
                topic="topic/in",
                message={"cmd": 1},
                protocol=0,
                timeout=1.0,
            )
        except Exception as exc:  # pragma: no cover - defensive for thread failures
            failures.append(f"{serial}:{exc}")

    first = threading.Thread(target=_publish, args=("SN-1",))
    second = threading.Thread(target=_publish, args=("SN-2",))
    first.start()

    deadline = time.time() + 1.0
    while len(dummy.published) < 1 and time.time() < deadline:
        time.sleep(0.01)
    assert len(dummy.published) == 1

    second.start()
    time.sleep(0.1)
    assert len(dummy.published) == 1

    first_payload = json.loads(dummy.published[0]["payload"])
    mqtt._on_message_received(
        "topic/out",
        json.dumps({"cfg": {"sn": "SN-1", "id": first_payload["id"]}}).encode("utf-8"),
    )

    deadline = time.time() + 1.0
    while len(dummy.published) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert len(dummy.published) == 2

    second_payload = json.loads(dummy.published[1]["payload"])
    mqtt._on_message_received(
        "topic/out",
        json.dumps({"cfg": {"sn": "SN-2", "id": second_payload["id"]}}).encode("utf-8"),
    )

    first.join(timeout=1.0)
    second.join(timeout=1.0)
    assert first.is_alive() is False
    assert second.is_alive() is False
    assert failures == []


def test_publish_matches_response_via_identifier_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response should match when payload uses serial alias for UUID target."""
    def resolver(identifier: str) -> set[str]:
        if identifier in {"UUID-1", "SN-1"}:
            return {"UUID-1", "SN-1"}
        return {identifier}

    mqtt, dummy = _build_mqtt(monkeypatch, identifier_resolver=resolver)
    finished = threading.Event()
    errors: list[Exception] = []

    def _run_publish() -> None:
        try:
            mqtt.publish(
                serial_number="UUID-1",
                topic="topic/in",
                message={"cmd": 1},
                protocol=1,
                timeout=1.0,
            )
            finished.set()
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    thread = threading.Thread(target=_run_publish)
    thread.start()

    deadline = time.time() + 1.0
    while len(dummy.published) < 1 and time.time() < deadline:
        time.sleep(0.01)
    assert dummy.published

    payload = json.loads(dummy.published[0]["payload"])
    command_id = payload["id"]
    mqtt._on_message_received(
        "topic/out",
        json.dumps({"cfg": {"sn": "SN-1", "id": command_id}}).encode("utf-8"),
    )

    thread.join(timeout=1.0)
    assert thread.is_alive() is False
    assert errors == []
    assert finished.is_set() is True


def test_format_message_uses_protocol_specific_identifier_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Formatted command payload should use sn for protocol 0 and uuid for protocol 1."""
    mqtt, _dummy = _build_mqtt(monkeypatch)

    proto0 = json.loads(mqtt.format_message("SN-1", {"cmd": 1}, 0))
    assert "sn" in proto0
    assert proto0["sn"] == "SN-1"
    assert "uuid" not in proto0
    assert "dt" in proto0

    proto1 = json.loads(mqtt.format_message("UUID-1", {"cmd": 1}, 1))
    assert "uuid" in proto1
    assert proto1["uuid"] == "UUID-1"
    assert "sn" not in proto1
    assert proto1["tm"].endswith("Z")


def test_format_message_rejects_unsupported_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown protocol should raise an explicit ValueError."""
    mqtt, _dummy = _build_mqtt(monkeypatch)

    with pytest.raises(ValueError):
        mqtt.format_message("SN-1", {"cmd": 1}, 99)
