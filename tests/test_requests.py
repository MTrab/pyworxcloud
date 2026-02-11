"""Tests for HTTP request utility module."""

from __future__ import annotations

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


def test_get_retries_connection_errors_and_fails(monkeypatch) -> None:
    """GET should retry and raise NoConnectionError on repeated transport failures."""

    def _fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr(req_utils.requests, "get", _fail)
    monkeypatch.setattr(req_utils, "sleep", lambda *_args, **_kwargs: None)

    try:
        req_utils.GET("https://example.invalid")
    except NoConnectionError:
        return

    raise AssertionError("Expected NoConnectionError was not raised")


def test_post_retries_max_retry_error_and_fails(monkeypatch) -> None:
    """POST should retry and raise NoConnectionError on repeated MaxRetryError."""

    def _fail(*args, **kwargs):
        raise urllib3.exceptions.MaxRetryError(None, None, "max retries exceeded")

    monkeypatch.setattr(req_utils.requests, "post", _fail)
    monkeypatch.setattr(req_utils, "sleep", lambda *_args, **_kwargs: None)

    try:
        req_utils.POST("https://example.invalid", {})
    except NoConnectionError:
        return

    raise AssertionError("Expected NoConnectionError was not raised")


def test_post_returns_json_on_success(monkeypatch) -> None:
    """POST should return JSON payload for successful request."""

    monkeypatch.setattr(
        req_utils.requests,
        "post",
        lambda *_args, **_kwargs: DummyResponse({"ok": True}),
    )

    payload = req_utils.POST("https://example.invalid", {})
    assert payload["ok"] is True
