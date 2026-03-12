"""Tests for event handler isolation and callback behavior."""

from __future__ import annotations

import asyncio

from pyworxcloud.events import EventHandler, LandroidEvent
from pyworxcloud.utils.devices import DeviceHandler


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


def test_api_event_accepts_name_and_device_fallback() -> None:
    """API event should support the legacy name/device callback shape."""
    handler = EventHandler()
    calls: list[tuple[str, DeviceHandler]] = []
    device = DeviceHandler.__new__(DeviceHandler)

    handler.set_handler(
        LandroidEvent.API,
        lambda name, device: calls.append((name, device)),
    )

    result = handler.call(LandroidEvent.API, name="Jim", device=device)

    assert result is True
    assert calls == [("Jim", device)]


def test_event_handler_supports_async_callback_inside_running_loop() -> None:
    """Async callbacks should be scheduled when called from an active loop."""
    handler = EventHandler()
    calls: list[bool] = []

    async def _on_conn(state: bool) -> None:
        calls.append(state)

    handler.set_handler(LandroidEvent.MQTT_CONNECTION, _on_conn)

    async def _run() -> None:
        assert handler.call(LandroidEvent.MQTT_CONNECTION, state=True) is True
        await asyncio.sleep(0)

    asyncio.run(_run())
    assert calls == [True]


def test_event_handler_supports_async_callback_without_running_loop() -> None:
    """Async callbacks should run to completion even without active loop."""
    handler = EventHandler()
    calls: list[dict] = []

    async def _on_api(api_data: dict) -> None:
        calls.append(api_data)

    handler.set_handler(LandroidEvent.API, _on_api)

    assert handler.call(LandroidEvent.API, api_data={"status": "ok"}) is True
    assert calls == [{"status": "ok"}]
