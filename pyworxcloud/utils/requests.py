"""For handling HTTP/HTTPS requests."""

from __future__ import annotations

from typing import Any

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.exceptions import MaxRetryError
from urllib3.util.retry import Retry

from ..exceptions import (
    APIError,
    AuthorizationError,
    ForbiddenError,
    InternalServerError,
    NoConnectionError,
    NotFoundError,
    RequestError,
    ServiceUnavailableError,
    TooManyRequestsError,
)

# pylint: disable=invalid-name

NUM_RETRIES = 5
BACKOFF_FACTOR = 3


def HEADERS(access_token: str | None = None) -> dict:
    """Generate headers dictionary."""
    head = {
        "Accept": "application/json",
    }

    if isinstance(access_token, type(None)):
        head.update({"Content-Type": "application/x-www-form-urlencoded"})
    else:
        head.update({"Authorization": f"Bearer {access_token}"})

    return head


def _build_session() -> requests.Session:
    """Create a session configured with HTTP retry adapters."""
    retry = Retry(
        total=NUM_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def create_session() -> requests.Session:
    """Return a configured session instance."""
    return _build_session()


_DEFAULT_SESSION = _build_session()


def POST(
    URL: str,
    REQUEST_BODY: str,
    HEADER: dict | None = None,
    session: requests.Session | None = None,
) -> str:
    """Perform a POST request."""

    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    client = session if session is not None else _DEFAULT_SESSION
    try:
        req = client.post(
            URL, REQUEST_BODY, headers=HEADER, timeout=60, cookies=None
        )  # 60 seconds timeout

        req.raise_for_status()

        return req.json()
    except requests.exceptions.HTTPError as err:
        code = err.response.status_code
        if code == 400:
            raise RequestError()
        if code == 401:
            raise AuthorizationError()
        if code == 403:
            raise ForbiddenError()
        if code == 404:
            raise NotFoundError()
        if code == 429:
            raise TooManyRequestsError()
        if code == 500:
            raise InternalServerError()
        if code == 503 or code == 504:
            raise ServiceUnavailableError()
        raise APIError(err)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        MaxRetryError,
    ):
        raise NoConnectionError()


def GET(
    URL: str, HEADER: dict | None = None, session: requests.Session | None = None
) -> str:
    """Perform a GET request."""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    client = session if session is not None else _DEFAULT_SESSION
    try:
        req = client.get(
            URL, headers=HEADER, timeout=60, cookies=None
        )  # 60 seconds timeout

        req.raise_for_status()

        return req.json()
    except requests.exceptions.HTTPError as err:
        code = err.response.status_code
        if code == 400:
            raise RequestError()
        if code == 401:
            raise AuthorizationError()
        if code == 403:
            raise ForbiddenError()
        if code == 404:
            raise NotFoundError()
        if code == 429:
            raise TooManyRequestsError()
        if code == 500:
            raise InternalServerError()
        if code == 503 or code == 504:
            raise ServiceUnavailableError()
        raise APIError(err)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        MaxRetryError,
    ):
        raise NoConnectionError()
