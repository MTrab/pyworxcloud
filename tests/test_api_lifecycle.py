"""Tests for API and lifecycle behavior without network access."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pyworxcloud import WorxCloud
from pyworxcloud.api import LandroidCloudAPI
from pyworxcloud.clouds import CloudType
from pyworxcloud.events import LandroidEvent


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
        self.shutdown_called = False

    async def adisconnect(self, _keep_topic: bool = False) -> None:
        self.disconnect_called = True

    async def ashutdown(self) -> None:
        self.shutdown_called = True


class DummyDevice:
    """Simple device stub."""

    time_zone = "UTC"


class CapturingMQTT:
    """MQTT constructor stub capturing provided timeout."""

    last_response_timeout: float | None = None

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
        self.identifier_resolver = identifier_resolver
        self.deduplicate_inflight_commands = deduplicate_inflight_commands
        self.__class__.last_response_timeout = response_timeout

    async def aconnect(self) -> None:
        return None

    async def asubscribe(self, _topic: str, _append: bool = True) -> None:
        return None

    async def adisconnect(self, _keep_topic: bool = False) -> None:
        return None

    async def ashutdown(self) -> None:
        return None


def test_get_token_propagates_unexpected_errors(monkeypatch) -> None:
    """Unexpected token fetch errors should not be swallowed."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)

    async def _raise(*_args: Any, **_kwargs: Any) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("pyworxcloud.api.APOST", _raise)

    with pytest.raises(RuntimeError):
        asyncio.run(api.get_token())


def test_get_mowers_uses_products_cache(monkeypatch) -> None:
    """Repeated mower fetches should not repeatedly load product catalog."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)
    api.access_token = "token"
    api.refresh_token = "refresh"
    api._token_expire = 9999999999

    calls = {"products": 0}

    async def _get(url: str, _headers: dict, session=None) -> list:
        if url.endswith("/api/v2/products"):
            calls["products"] += 1
            assert session is not None
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

    monkeypatch.setattr("pyworxcloud.api.AGET", _get)

    first = asyncio.run(api.get_mowers())
    second = asyncio.run(api.get_mowers())

    assert first[0]["model"]["code"] == "WG123"
    assert second[0]["model"]["friendly_name"] == "Landroid500"
    assert calls["products"] == 1


def test_get_mowers_passes_session_to_request_helper(monkeypatch) -> None:
    """LandroidCloudAPI should reuse its HTTP session when calling GET helper."""
    api = LandroidCloudAPI("user@example.com", "secret", CloudType.WORX)
    api.access_token = "token"
    api.refresh_token = "refresh"
    api._token_expire = 9999999999

    seen = {"session": None}

    async def _get(url: str, _headers: dict, session=None) -> list:
        seen["session"] = session
        if url.endswith("/api/v2/products"):
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
            return [{"name": "My Mower", "product_id": 42}]
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("pyworxcloud.api.AGET", _get)

    asyncio.run(api.get_mowers())

    assert seen["session"] is api._session


def test_disconnect_cancels_timers_and_disconnects_mqtt() -> None:
    """Disconnect should cancel timers, clear timer map, and disconnect MQTT."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    mqtt = DummyMQTT()

    cloud.mqtt = mqtt
    asyncio.run(cloud.disconnect())

    assert mqtt.disconnect_called is True
    assert cloud._disconnecting.is_set() is True
    assert mqtt.shutdown_called is True
    assert cloud.mqtt is None


def test_fetch_skips_api_call_when_disconnecting() -> None:
    """Fetch should do nothing when disconnecting flag is set."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud._disconnecting.set()

    called = {"value": False}

    async def _get_mowers() -> list:
        called["value"] = True
        return []

    cloud._api.get_mowers = _get_mowers
    asyncio.run(cloud._fetch())

    assert called["value"] is False


def test_token_updated_is_noop_without_mqtt() -> None:
    """Token update callback should be safe before MQTT is initialized."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    cloud.mqtt = None
    asyncio.run(cloud._token_updated())


def test_on_api_update_dispatches_api_event_callback() -> None:
    """API update callback should dispatch event payload to registered handler."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    received: list[dict[str, Any]] = []
    cloud.set_callback(LandroidEvent.API, lambda api_data: received.append(api_data))
    cloud._on_api_update({"key": "value"})

    assert received == [{"key": "value"}]


def test_constructor_rejects_non_positive_command_timeout() -> None:
    """WorxCloud should validate command timeout."""
    with pytest.raises(ValueError):
        WorxCloud("user@example.com", "secret", "worx", command_timeout=0)


def test_connect_passes_configured_command_timeout_to_mqtt(monkeypatch) -> None:
    """Configured command timeout should be forwarded to MQTT layer."""
    cloud = WorxCloud(
        "user@example.com",
        "secret",
        "worx",
        command_timeout=12.5,
    )

    async def _fake_fetch() -> None:
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
    monkeypatch.setattr("pyworxcloud.MQTT", CapturingMQTT)
    monkeypatch.setattr("pyworxcloud.convert_to_time", lambda *_args, **_kwargs: None)

    assert asyncio.run(cloud.connect()) is True
    assert CapturingMQTT.last_response_timeout == 12.5


def test_match_mower_uses_identifier_priority() -> None:
    """Matcher should prefer serial, then uuid, then mac."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    mower_serial = {
        "name": "Serial",
        "serial_number": "S1",
        "uuid": "U1",
        "mac_address": "M1",
    }
    mower_uuid = {
        "name": "UUID",
        "serial_number": "S2",
        "uuid": "U2",
        "mac_address": "M2",
    }
    mower_mac = {
        "name": "MAC",
        "serial_number": "S3",
        "uuid": "U3",
        "mac_address": "M3",
    }
    cloud._mowers = [mower_serial, mower_uuid, mower_mac]
    cloud._rebuild_mower_indices()

    assert cloud._match_mower(serial="S1") == mower_serial
    assert cloud._match_mower(uuid="U2") == mower_uuid
    assert cloud._match_mower(mac="M3") == mower_mac
    assert cloud._match_mower(serial="missing", uuid="U2") == mower_uuid
    assert (
        cloud._match_mower(serial="missing", uuid="missing", mac="M1") == mower_serial
    )
    assert cloud._match_mower(serial="missing", uuid="missing", mac="missing") is None


def test_get_mower_uses_rebuilt_serial_index() -> None:
    """get_mower should resolve mowers through serial lookup index."""
    cloud = WorxCloud("user@example.com", "secret", "worx")
    target = {
        "name": "Target",
        "serial_number": "SERIAL-1",
        "uuid": "UUID-1",
        "mac_address": "MAC-1",
    }
    cloud._mowers = [target]
    cloud._rebuild_mower_indices()

    assert cloud.get_mower("SERIAL-1") == target
