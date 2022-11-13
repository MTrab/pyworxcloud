"""Login and get tokens."""
from __future__ import annotations

from .handlers.requests import POST, HEADERS

from .endpoints import CloudType


class Token:
    """Class for handling login to the cloud."""

    def __init__(
        self,
        email: str,
        password: str,
        cloud: CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE,
    ) -> None:
        """Initialize login object."""
        self._email = email
        self._password = password
        self._cloud = cloud
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.expires_in: int = 0

        self._auth()

    def _auth(self) -> None:
        """Authenticate."""
        URL = f"https://{self._cloud.AUTH_ENDPOINT}/oauth/token"
        REQUEST_BODY = {
            "grant_type": "password",
            "client_id": self._cloud.AUTH_CLIENT_ID,
            "scope": "*",
            "username": self._email,
            "password": self._password,
        }

        resp = POST(URL, REQUEST_BODY, HEADERS())
        self.access_token = resp["access_token"]
        self.refresh_token = resp["refresh_token"]
        self.expires_in = resp["expires_in"]

    def refresh(self) -> None:
        """Refresh the tokens."""
        URL = f"https://{self._cloud.AUTH_ENDPOINT}/oauth/token"
        REQUEST_BODY = {
            "grant_type": "refresh_token",
            "client_id": self._cloud.AUTH_CLIENT_ID,
            "scope": "*",
            "refresh_token": self.refresh_token,
        }

        resp = POST(URL, REQUEST_BODY, HEADERS())
        self.access_token = resp["access_token"]
        self.refresh_token = resp["refresh_token"]
        self.expires_in = resp["expires_in"]