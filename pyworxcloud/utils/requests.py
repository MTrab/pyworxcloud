"""For handling HTTP/HTTPS requests."""
from __future__ import annotations

import requests

from ..exceptions import (
    APIError,
    AuthorizationError,
    ForbiddenError,
    InternalServerError,
    NotFoundError,
    RequestError,
    ServiceUnavailableError,
    TooManyRequestsError,
)

# pylint: disable=invalid-name


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

    try:
        req = requests.post(URL, REQUEST_BODY, headers=HEADER)

        req.raise_for_status()
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
        else:
            raise APIError(err)

    return req.json()


def GET(URL: str, HEADER: dict | None = None) -> str:
    """A request GET"""
    if isinstance(HEADER, type(None)):
        HEADER = HEADERS()

    try:
        req = requests.get(URL, headers=HEADER)

        req.raise_for_status()
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
        else:
            raise APIError(err)

    return req.json()
