"""For handling HTTP/HTTPS requests."""

from __future__ import annotations

from time import sleep

import requests

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
MAX_BACKOFF = 120
BACKOFF_FACTOR = 3


def backoff(retry: int) -> float:
    """Calculate backoff time."""
    val: float = BACKOFF_FACTOR * (2 ** (retry - 1))

    return val if val <= MAX_BACKOFF else MAX_BACKOFF


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


def POST(URL: str, REQUEST_BODY: str, HEADER: dict | None = None) -> str:
    """A request POST"""

    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    for retry in range(NUM_RETRIES):
        try:
            req = requests.post(
                URL, REQUEST_BODY, headers=HEADER, timeout=60, cookies=None
            )  # 60 seconds timeout

            req.raise_for_status()

            return req.json()
        except requests.exceptions.HTTPError as err:
            code = err.response.status_code
            if code == 400:
                raise RequestError()
            elif code == 401:
                raise AuthorizationError()
            elif code == 403:
                raise ForbiddenError()
            elif code == 404:
                raise NotFoundError()
            elif code == 429:
                raise TooManyRequestsError()
            elif code == 500:
                raise InternalServerError()
            elif code == 503:
                raise ServiceUnavailableError()
            elif code == 504:
                sleep(backoff(retry))
                pass
            else:
                raise APIError(err)

    raise NoConnectionError()


def GET(URL: str, HEADER: dict | None = None) -> str:
    """A request GET"""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    for retry in range(NUM_RETRIES):
        try:
            req = requests.get(
                URL, headers=HEADER, timeout=60, cookies=None
            )  # 60 seconds timeout

            req.raise_for_status()

            return req.json()
        except requests.exceptions.HTTPError as err:
            code = err.response.status_code
            if code == 400:
                raise RequestError()
            elif code == 401:
                raise AuthorizationError()
            elif code == 403:
                raise ForbiddenError()
            elif code == 404:
                raise NotFoundError()
            elif code == 429:
                raise TooManyRequestsError()
            elif code == 500:
                raise InternalServerError()
            elif code == 503:
                raise ServiceUnavailableError()
            elif code == 504:
                sleep(backoff(retry))
                pass
            else:
                raise APIError(err)

    raise NoConnectionError()
