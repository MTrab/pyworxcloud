"""Tests for event handler isolation and callback behavior."""

from __future__ import annotations

from pyworxcloud.events import EventHandler, LandroidEvent


def test_event_handlers_are_isolated_per_instance() -> None:
    """Each EventHandler instance should keep its own callbacks."""
    first = EventHandler()
    second = EventHandler()

    calls: list[str] = []

    first.set_handler(
        LandroidEvent.MQTT_CONNECTION,
        lambda state: calls.append(f"first:{state}"),
    )
    second.set_handler(
        LandroidEvent.MQTT_CONNECTION,
        lambda state: calls.append(f"second:{state}"),
    )

    assert first.call(LandroidEvent.MQTT_CONNECTION, state=True) is True
    assert calls == ["first:True"]


def test_deleting_handler_does_not_affect_other_instances() -> None:
    """Removing a callback from one instance must not remove it from another."""
    first = EventHandler()
    second = EventHandler()

    calls: list[bool] = []
    second.set_handler(LandroidEvent.MQTT_CONNECTION, lambda state: calls.append(state))

    first.del_handler(LandroidEvent.MQTT_CONNECTION)
    assert second.call(LandroidEvent.MQTT_CONNECTION, state=False) is True
    assert calls == [False]


def test_api_event_accepts_api_data_payload() -> None:
    """API event should support api_data dict payloads."""
    handler = EventHandler()
    calls: list[dict] = []

    handler.set_handler(LandroidEvent.API, lambda api_data: calls.append(api_data))

    result = handler.call(LandroidEvent.API, api_data={"status": "ok"})

    assert result is True
    assert calls == [{"status": "ok"}]


def test_api_event_rejects_invalid_payload() -> None:
    """API event should reject invalid payload shape."""
    handler = EventHandler()
    handler.set_handler(LandroidEvent.API, lambda **_kwargs: None)

    result = handler.call(LandroidEvent.API, message="invalid")

    assert result is False
