"""Landroid Cloud API implementation"""
# pylint: disable=unnecessary-lambda
from __future__ import annotations

import json
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
        cloud: CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE,
        tz: str | None = None,  # pylint: disable=invalid-name
    ) -> None:
        """Initialize a new instance of the API broker.

        Args:
            username (str): Email for the user account.
            password (str): Password for the user account.
            cloud (CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE , optional): CloudType representing the device. Defaults to CloudType.WORX.
        """
        self.cloud: CloudType = cloud
        self._token_type = "app"
        self._access_token = None
        self._refresh_token = None
        self._token_expire = 0
        self.uuid = None
        self._api_host = None
        self._data = None
        self._tz = tz

        self.api_url = cloud.URL
        self.api_key = cloud.KEY
        self.token_url = cloud.TOKEN_URL
        self.username = username
        self.password = password

    def set_token(self, access_token: str, expires_in: int, refresh_token: str) -> None:
        """Set the API token to be used

        Args:
            access_token (str): Token from authentication.
            expires_in (int): Seconds to token expire.
            refresh_token (str): Token to use when refreshing access_token
        """
        now = int(time.time())
        self._token_expire = now + expires_in
        self._access_token = access_token
        self._refresh_token = refresh_token

    def set_token_type(self, token_type: str) -> None:
        """Set token type.

        Args:
            token_type (str): Token type
        """
        self._token_type = token_type

    def _get_headers(self, tokenheaders: bool = False) -> dict:
        """Create header object for communication packets."""
        header_data = {}
        if tokenheaders:
            header_data["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            header_data["Content-Type"] = "application/json"
            header_data["Authorization"] = self._token_type + " " + self._access_token

        return header_data

    def auth(self, refresh: bool = False) -> str:
        """Authenticate against API endpoint

        Returns:
            str: JSON object containing authentication token.
        """
        self.uuid = str(uuid.uuid1())
        self._api_host = (API_BASE).format(self.api_url)

        payload_data = {}
        if not refresh:
            payload_data["username"] = self.username
            payload_data["password"] = self.password
        else:
            payload_data["refresh_token"] = self._refresh_token
        payload_data["grant_type"] = "password"
        payload_data["client_id"] = self.api_key
        payload_data["scope"] = "*"

        calldata = self._call(
            "/oauth/token", payload=payload_data, checktoken=False, generatetoken=True
        )

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

    def get_status(self, serial: str) -> str | bool:
        """Get device status

        Args:
            serial (str): Serialnumber for the device to get status for.

        Returns:
            str: JSON object containing the device status if found.
            bool: Returns false if no device was found.
        """
        callstr = f"/product-items?status=1"
        calldata = self._call(callstr)

        for mower in calldata:
            if mower["serial_number"] == serial:
                return json.dumps(mower, indent=4)

        return False

    def _call(
        self,
        path: str | None = None,
        payload: str | None = None,
        checktoken: bool = True,
        generatetoken: bool = False,
        post: bool = False,
    ) -> str:
        """Do the actual call to the device."""
        # Check if token needs refreshing
        now = int(time.time())  # Current time in unix timestamp format
        if checktoken and ((self._token_expire - 300) < now):
            try:
                auth_data = self.auth()

                if "return_code" in auth_data:
                    return

                self.set_token(
                    auth_data["access_token"],
                    auth_data["expires_in"],
                    auth_data["refresh_token"],
                )
                self.set_token_type(auth_data["token_type"])
            except Exception as ex:  # pylint: disable=bare-except
                raise TokenError("Error refreshing authentication token") from ex

        try:
            url = (
                (self._api_host + path)
                if not generatetoken
                else ("https://" + self.token_url + path)
            )
            if payload or post:
                req = requests.post(
                    url,
                    data=payload,
                    headers=self._get_headers(generatetoken),
                    timeout=30,
                )
            else:
                req = requests.get(url, headers=self._get_headers(), timeout=30)

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
