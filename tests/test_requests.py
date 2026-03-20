"""Tests for HTTP request utility module."""

from __future__ import annotations

from typing import Any

import requests
import urllib3

from pyworxcloud.exceptions import NoConnectionError
from pyworxcloud.utils import requests as req_utils


class DummyResponse:
    """Simple response stub for request utility tests."""

    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FailingSession:
    def get(self, *args: Any, **kwargs: Any) -> None:
        raise requests.exceptions.ConnectionError()

    def post(self, *args: Any, **kwargs: Any) -> None:
        raise urllib3.exceptions.MaxRetryError(None, None, "max retries exceeded")

    def put(self, *args: Any, **kwargs: Any) -> None:
        raise requests.exceptions.ConnectionError()


def test_get_retries_connection_errors_and_fails(monkeypatch) -> None:
    """GET should retry and raise NoConnectionError on repeated transport failures."""
    monkeypatch.setattr(req_utils, "_DEFAULT_SESSION", _FailingSession())

    try:
        req_utils.GET("https://example.invalid")
    except NoConnectionError:
        return

    raise AssertionError("Expected NoConnectionError was not raised")


def test_post_retries_max_retry_error_and_fails(monkeypatch) -> None:
    """POST should retry and raise NoConnectionError on repeated MaxRetryError."""
    monkeypatch.setattr(req_utils, "_DEFAULT_SESSION", _FailingSession())

    try:
        req_utils.POST("https://example.invalid", {})
    except NoConnectionError:
        return

    raise AssertionError("Expected NoConnectionError was not raised")


def test_post_returns_json_on_success(monkeypatch) -> None:
    """POST should return JSON payload for successful request."""

    class _SuccessSession:
        def post(self, *args: Any, **kwargs: Any) -> DummyResponse:
            return DummyResponse({"ok": True})

    monkeypatch.setattr(req_utils, "_DEFAULT_SESSION", _SuccessSession())

    payload = req_utils.POST("https://example.invalid", {})
    assert payload["ok"] is True


def test_put_retries_connection_errors_and_fails(monkeypatch) -> None:
    """PUT should retry and raise NoConnectionError on repeated transport failures."""
    monkeypatch.setattr(req_utils, "_DEFAULT_SESSION", _FailingSession())

    try:
        req_utils.PUT("https://example.invalid", {})
    except NoConnectionError:
        return

    raise AssertionError("Expected NoConnectionError was not raised")


def test_put_returns_json_on_success(monkeypatch) -> None:
    """PUT should return JSON payload for successful request."""

    class _SuccessSession:
        def put(self, *args: Any, **kwargs: Any) -> DummyResponse:
            return DummyResponse({"ok": True})

    monkeypatch.setattr(req_utils, "_DEFAULT_SESSION", _SuccessSession())

    payload = req_utils.PUT("https://example.invalid", {})
    assert payload["ok"] is True
