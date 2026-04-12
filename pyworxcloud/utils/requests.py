"""HTTP helpers for sync and async API access."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import requests
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
REQUEST_TIMEOUT = 60


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
    """Create a sync session configured with HTTP retry adapters."""
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
    """Return a configured sync session instance."""
    return _build_session()


def _raise_http_status(code: int, err: Exception) -> None:
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
    if code in (503, 504):
        raise ServiceUnavailableError()
    raise APIError(err)


async def create_async_session() -> aiohttp.ClientSession:
    """Create aiohttp client session for async API calls."""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    return aiohttp.ClientSession(timeout=timeout)


async def APOST(
    URL: str,
    REQUEST_BODY: Any,
    HEADER: dict | None = None,
    session: aiohttp.ClientSession | None = None,
) -> Any:
    """Perform an async POST request."""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    owns_session = session is None
    client = session or await create_async_session()
    try:
        async with client.post(URL, data=REQUEST_BODY, headers=HEADER) as resp:
            if resp.status >= 400:
                _raise_http_status(resp.status, Exception(f"HTTP {resp.status}"))
            return await resp.json()
    except aiohttp.ClientError as err:
        raise NoConnectionError() from err
    except asyncio.TimeoutError as err:
        raise NoConnectionError() from err
    finally:
        if owns_session:
            await client.close()


async def AGET(
    URL: str,
    HEADER: dict | None = None,
    session: aiohttp.ClientSession | None = None,
) -> Any:
    """Perform an async GET request."""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    owns_session = session is None
    client = session or await create_async_session()
    try:
        async with client.get(URL, headers=HEADER) as resp:
            if resp.status >= 400:
                _raise_http_status(resp.status, Exception(f"HTTP {resp.status}"))
            return await resp.json()
    except aiohttp.ClientError as err:
        raise NoConnectionError() from err
    except asyncio.TimeoutError as err:
        raise NoConnectionError() from err
    finally:
        if owns_session:
            await client.close()


async def APUT(
    URL: str,
    REQUEST_BODY: Any,
    HEADER: dict | None = None,
    session: aiohttp.ClientSession | None = None,
) -> Any:
    """Perform an async PUT request."""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    owns_session = session is None
    client = session or await create_async_session()
    try:
        async with client.put(URL, json=REQUEST_BODY, headers=HEADER) as resp:
            if resp.status >= 400:
                _raise_http_status(resp.status, Exception(f"HTTP {resp.status}"))
            return await resp.json()
    except aiohttp.ClientError as err:
        raise NoConnectionError() from err
    except asyncio.TimeoutError as err:
        raise NoConnectionError() from err
    finally:
        if owns_session:
            await client.close()


_DEFAULT_SESSION = _build_session()


def POST(
    URL: str,
    REQUEST_BODY: Any,
    HEADER: dict | None = None,
    session: requests.Session | None = None,
) -> Any:
    """Perform a sync POST request (legacy interface)."""

    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    client = session if session is not None else _DEFAULT_SESSION
    try:
        req = client.post(URL, REQUEST_BODY, headers=HEADER, timeout=REQUEST_TIMEOUT)
        req.raise_for_status()
        return req.json()
    except requests.exceptions.HTTPError as err:
        _raise_http_status(err.response.status_code, err)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        MaxRetryError,
    ) as err:
        raise NoConnectionError() from err


def GET(
    URL: str, HEADER: dict | None = None, session: requests.Session | None = None
) -> Any:
    """Perform a sync GET request (legacy interface)."""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    client = session if session is not None else _DEFAULT_SESSION
    try:
        req = client.get(URL, headers=HEADER, timeout=REQUEST_TIMEOUT)
        req.raise_for_status()
        return req.json()
    except requests.exceptions.HTTPError as err:
        _raise_http_status(err.response.status_code, err)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        MaxRetryError,
    ) as err:
        raise NoConnectionError() from err


def PUT(
    URL: str,
    REQUEST_BODY: Any,
    HEADER: dict | None = None,
    session: requests.Session | None = None,
) -> Any:
    """Perform a sync PUT request (legacy interface)."""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    client = session if session is not None else _DEFAULT_SESSION
    try:
        req = client.put(
            URL, json=REQUEST_BODY, headers=HEADER, timeout=REQUEST_TIMEOUT
        )
        req.raise_for_status()
        return req.json()
    except requests.exceptions.HTTPError as err:
        _raise_http_status(err.response.status_code, err)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        MaxRetryError,
    ) as err:
        raise NoConnectionError() from err
