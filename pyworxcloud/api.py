"""Landroid Cloud API implementation"""
# pylint: disable=unnecessary-lambda
from __future__ import annotations

import logging
import time

from .clouds import CloudType
from .utils.requests import GET, HEADERS, POST

_LOGGER = logging.getLogger(__name__)


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
        self.access_token = None
        self.refresh_token = None
        self._token_expire = 0
        self.uuid = None
        self._api_host = None
        self.api_data = None
        self._tz = tz

        self.username = username
        self.password = password

    def get_token(self) -> None:
        """Get the access and refresh tokens."""
        url = f"https://{self.cloud.AUTH_ENDPOINT}/oauth/token"
        request_body = {
            "grant_type": "password",
            "client_id": self.cloud.AUTH_CLIENT_ID,
            "scope": "*",
            "username": self.username,
            "password": self.password,
        }

        resp = POST(url, request_body, HEADERS())
        self.access_token = resp["access_token"]
        self.refresh_token = resp["refresh_token"]
        now = int(time.time())
        self._token_expire = now + int(resp["expires_in"])

    def update_token(self) -> None:
        """Refresh the tokens."""
        url = f"https://{self.cloud.AUTH_ENDPOINT}/oauth/token"
        request_body = {
            "grant_type": "refresh_token",
            "client_id": self.cloud.AUTH_CLIENT_ID,
            "scope": "*",
            "refresh_token": self.refresh_token,
        }

        resp = POST(url, request_body, HEADERS())
        self.access_token = resp["access_token"]
        self.refresh_token = resp["refresh_token"]
        now = int(time.time())
        self._token_expire = now + int(resp["expires_in"])

    def _get_headers(self, tokenheaders: bool = False) -> dict:
        """Create header object for communication packets."""
        header_data = {}
        if tokenheaders:
            header_data["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            header_data["Content-Type"] = "application/json"
            header_data["Authorization"] = self._token_type + " " + self.access_token

        return header_data

    def authenticate(self) -> bool:
        """Check tokens."""
        if isinstance(self.access_token, type(None)) or isinstance(
            self.refresh_token, type(None)
        ):
            return False
        return True

    def get_mowers(self) -> str:
        """Get mowers associated with the account.

        Returns:
            str: JSON object containing available mowers associated with the account.
        """
        mowers = GET(
            f"https://{self.cloud.ENDPOINT}/api/v2/product-items?status=1",
            HEADERS(self.access_token),
        )
        for mower in mowers:
            mower["firmware_version"] = "{:.2f}".format(mower["firmware_version"])

        return mowers

    @property
    def data(self) -> str:
        """Return the latest dataset of information and states from the API."""
        return self.api_data
