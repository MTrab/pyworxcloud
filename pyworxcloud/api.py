"""Landroid Cloud API implementation"""
# pylint: disable=unnecessary-lambda
from __future__ import annotations

import functools
import json
import operator
import re
import time
import uuid
from typing import Any

import requests

from .clouds import CloudType
from .const import API_BASE
from .exceptions import (
    APIException,
    AuthorizationError,
    ForbiddenError,
    InternalServerError,
    NotFoundError,
    RequestError,
    RequestException,
    ServiceUnavailableError,
    TimeoutException,
    TokenError,
    TooManyRequestsError,
)


class LandroidCloudAPI:
    """Landroid Cloud API definition."""

    def __init__(
        self,
        username: str,
        password: str,
        cloud: CloudType.WORX
        | CloudType.KRESS
        | CloudType.LANDXCAPE
        | CloudType.FERREX = CloudType.WORX,
        tz: str | None = None,  # pylint: disable=invalid-name
    ) -> None:
        """Initialize a new instance of the API broker.

        Args:
            username (str): Email for the user account.
            password (str): Password for the user account.
            cloud (CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE | CloudType.FERREX, optional): CloudType representing the device. Defaults to CloudType.WORX.
        """
        self.cloud: CloudType = cloud
        self._token_type = "app"
        self._token = None
        self._tokenrefresh = 0
        self.uuid = None
        self._api_host = None
        self._data = None
        self._tz = tz

        self.api_url = cloud.URL
        self.api_key = cloud.KEY
        self.username = username
        self.password = password

    def set_token(self, token: str, now: int = -1) -> None:
        """Set the API token to be used

        Args:
            token (str): Token from authentication.
            now (int, optional): When was the token last refreshed. Defaults to -1 which will force a token refresh.
        """
        if now == -1:
            now = int(time.time())

        self._tokenrefresh = now
        self._token = token

    def set_token_type(self, token_type: str) -> None:
        """Set token type.

        Args:
            token_type (str): Token type
        """
        self._token_type = token_type

    def _generate_identify_token(self, seed_token: str) -> str:
        """Generate identify token."""
        text_to_char = [ord(c) for c in self.api_url]

        step_one = re.findall(r".{1,2}", seed_token)
        step_two = list(map((lambda hex: int(hex, 16)), step_one))

        step_three = list(
            map(
                (
                    lambda foo: functools.reduce(
                        (lambda x, y: operator.xor(x, y)),
                        text_to_char,
                        foo,
                    )
                ),
                step_two,
            )
        )
        step_four = list(map(chr, step_three))

        final = "".join(step_four)
        return final

    def _get_headers(self) -> dict:
        """Create header object for communication packets."""
        header_data = {}
        header_data["Content-Type"] = "application/json"
        header_data["Authorization"] = self._token_type + " " + self._token

        return header_data

    def auth(self) -> str:
        """Authenticate against API endpoint

        Returns:
            str: JSON object containing authentication token.
        """
        self.uuid = str(uuid.uuid1())
        self._api_host = (API_BASE).format(self.api_url)

        self._token = self._generate_identify_token(self.api_key)

        payload_data = {}
        payload_data["username"] = self.username
        payload_data["password"] = self.password
        payload_data["grant_type"] = "password"
        payload_data["client_id"] = 1
        payload_data["type"] = "app"
        payload_data["client_secret"] = self._token
        payload_data["scope"] = "*"

        payload = json.dumps(payload_data)

        calldata = self._call("/oauth/token", payload, checktoken=False)

        return calldata

    def get_profile(self) -> str:
        """Get user profile.

        Returns:
            str: JSON object with user data.
        """
        calldata = self._call("/users/me")
        self._data = calldata
        return calldata

    def get_cert(self) -> str:
        """Get the user certificate.

        Returns:
            str: JSON object with certificate info.
        """
        calldata = self._call("/users/certificate")
        self._data = calldata
        return calldata

    def get_products(self) -> str:
        """Get products associated with the account.

        Returns:
            str: JSON object containing available devices associated with the account.
        """
        calldata = self._call("/product-items")
        self._data = calldata
        return calldata

    def get_product_info(self, product_id: int) -> dict[str, Any]:
        """Get product info and features for a given device model.

        Args:
            product_id (int): Product_id to get information for.

        Returns:
            list | None: A list of attributes with the product information.
        """
        products = self._call("/products")
        try:
            return [x for x in products if x["id"] == product_id][0]
        except:
            return None

    def get_board(self, board_id: int) -> list:
        """Get board info and features for a given baseboard.

        Args:
            board_code (str): Board_id to get information for.

        Returns:
            list | None: A list of attributes with board information.
        """
        boards = self._call("/boards")
        try:
            return [x for x in boards if x["id"] == board_id][0]
        except:
            return None

    def get_status(self, serial: str) -> str:
        """Get device status

        Args:
            serial (str): Serialnumber for the device to get status for.

        Returns:
            str: JSON object containing the device status.
        """
        callstr = f"/product-items/{serial}/status"
        calldata = self._call(callstr)
        return calldata

    def _call(
        self, path: str, payload: str | None = None, checktoken: bool = True
    ) -> str:
        """Do the actual call to the device."""
        # Check if token needs refreshing
        now = int(time.time())  # Current time in unix timestamp format
        if checktoken and ((self._tokenrefresh + 3000) < now):
            try:
                auth_data = self.auth()

                if "return_code" in auth_data:
                    return

                self.set_token(auth_data["access_token"], now)
                self.set_token_type(auth_data["token_type"])
            except Exception as ex:  # pylint: disable=bare-except
                raise TokenError("Error refreshing authentication token") from ex

        try:
            if payload:
                req = requests.post(
                    self._api_host + path,
                    data=payload,
                    headers=self._get_headers(),
                    timeout=30,
                )
            else:
                req = requests.get(
                    self._api_host + path, headers=self._get_headers(), timeout=30
                )

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
                raise APIException(err)
        except requests.exceptions.Timeout as err:
            raise TimeoutException(err)
        except requests.exceptions.RequestException as err:
            raise RequestException(err)

        return req.json()

    @property
    def data(self) -> str:
        """Return the latest dataset of information and states from the API."""
        return self._data
