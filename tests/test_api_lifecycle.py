"""Tests for API and lifecycle behavior without network access."""

from __future__ import annotations

from typing import Any

import pytest

from pyworxcloud import WorxCloud
from pyworxcloud.api import LandroidCloudAPI
from pyworxcloud.clouds import CloudType


class DummyTimer:
    """Simple timer stub."""

    def __init__(self) -> None:
        self.cancel_called = False

    def cancel(self) -> None:
        self.cancel_called = True


class DummyMQTT:
    """Simple MQTT stub."""

    def __init__(self) -> None:
        self.disconnect_called = False

    def disconnect(self) -> None:
        self.disconnect_called = True


def test_get_token_propagates_unexpected_errors(monkeypatch) -> None:
    """Unexpected token fetch errors should not be swallowed."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)

    def _raise(*_args: Any, **_kwargs: Any) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("pyworxcloud.api.POST", _raise)

    with pytest.raises(RuntimeError):
        api.get_token()


def test_get_mowers_uses_products_cache(monkeypatch) -> None:
    """Repeated mower fetches should not repeatedly load product catalog."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)
    api.access_token = "token"
    api.refresh_token = "refresh"
    api._token_expire = 9999999999

    calls = {"products": 0}

    def _get(url: str, _headers: dict) -> list:
        if url.endswith("/api/v2/products"):
            calls["products"] += 1
            return [
                {
                    "id": 42,
                    "code": "WG123",
                    "default_name": "Landroid",
                    "meters": "500",
                    "product_year": 2024,
                    "cutting_width": 18,
                }
            ]

        if "product-items" in url:
            return [
                {
                    "name": "My Mower",
                    "product_id": 42,
                }
            ]

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("pyworxcloud.api.GET", _get)

    first = api.get_mowers()
    second = api.get_mowers()

    assert first[0]["model"]["code"] == "WG123"
    assert second[0]["model"]["friendly_name"] == "Landroid500"
    assert calls["products"] == 1


def test_disconnect_cancels_timers_and_disconnects_mqtt() -> None:
    """Disconnect should cancel timers, clear timer map, and disconnect MQTT."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    timer_a = DummyTimer()
    timer_b = DummyTimer()
    mqtt = DummyMQTT()

    cloud._timers = {"a": timer_a, "b": timer_b}
    cloud.mqtt = mqtt
    cloud.disconnect()

    assert timer_a.cancel_called is True
    assert timer_b.cancel_called is True
    assert cloud._timers == {}
    assert mqtt.disconnect_called is True
    assert cloud._disconnecting.is_set() is True


def test_fetch_skips_api_call_when_disconnecting() -> None:
    """Fetch should do nothing when disconnecting flag is set."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._disconnecting.set()

    called = {"value": False}

    def _get_mowers() -> list:
        called["value"] = True
        return []

    cloud._api.get_mowers = _get_mowers
    cloud._fetch()

    assert called["value"] is False


def test_token_updated_is_noop_without_mqtt() -> None:
    """Token update callback should be safe before MQTT is initialized."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud.mqtt = None
    cloud._token_updated()
