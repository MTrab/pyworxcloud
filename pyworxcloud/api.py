"""Landroid Cloud API implementation (async-first)."""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from .clouds import CloudType
from .exceptions import TooManyRequestsError
from .utils.requests import AGET, APOST, HEADERS, create_async_session

_LOGGER = logging.getLogger(__name__)


class LandroidCloudAPI:
    """Landroid Cloud API definition."""

    def __init__(
        self,
        username: str,
        password: str,
        cloud: CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE,
        tz: str | None = None,  # pylint: disable=invalid-name
        token_callback: callable | None = None,
    ) -> None:
        self.cloud: CloudType = cloud
        self._token_type = "app"
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self._token_expire = 0
        self.uuid = None
        self._api_host = None
        self.api_data = None
        self._products_cache = None
        self._session: aiohttp.ClientSession | None = None
        self._tz = tz
        self._callback = token_callback

        self.username = username
        self.password = password

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = await create_async_session()
        return self._session

    async def close(self) -> None:
        """Close underlying aiohttp session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def get_token(self) -> None:
        """Get the access and refresh tokens."""
        url = f"https://{self.cloud.AUTH_ENDPOINT}/oauth/token"
        request_body = {
            "grant_type": "password",
            "client_id": self.cloud.AUTH_CLIENT_ID,
            "scope": "*",
            "username": self.username,
            "password": self.password,
        }

        try:
            resp = await APOST(
                url,
                request_body,
                HEADERS(),
                session=await self._ensure_session(),
            )
            self.access_token = resp["access_token"]
            self.refresh_token = resp["refresh_token"]
            now = int(time.time())
            self._token_expire = now + int(resp["expires_in"])
        except TooManyRequestsError:
            raise TooManyRequestsError from None

    async def _update_token(self) -> None:
        """Refresh the tokens."""
        url = f"https://{self.cloud.AUTH_ENDPOINT}/oauth/token"
        request_body = {
            "grant_type": "refresh_token",
            "client_id": self.cloud.AUTH_CLIENT_ID,
            "scope": "*",
            "refresh_token": self.refresh_token,
        }

        resp = await APOST(
            url,
            request_body,
            HEADERS(),
            session=await self._ensure_session(),
        )
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
            header_data["Authorization"] = (
                self._token_type + " " + str(self.access_token)
            )

        return header_data

    def authenticate(self) -> bool:
        """Check tokens."""
        if isinstance(self.access_token, type(None)) or isinstance(
            self.refresh_token, type(None)
        ):
            return False
        return True

    async def check_token(self) -> None:
        """Check token and refresh if needed."""
        now = int(time.time())

        if (now + 1800) >= self._token_expire:
            _LOGGER.debug("Updating access_token")
            await self._update_token()
            if self._callback:
                callback_res = self._callback()
                if hasattr(callback_res, "__await__"):
                    await callback_res

    async def get_mowers(self) -> list[dict[str, Any]]:
        """Get mowers associated with the account."""
        await self.check_token()

        mowers = await AGET(
            f"https://{self.cloud.ENDPOINT}/api/v2/product-items?status=1",
            HEADERS(self.access_token),
            session=await self._ensure_session(),
        )
        products = await self._get_products()
        product_map = {item["id"]: item for item in products}

        for mower in mowers:
            if mower["name"] is None:
                mower["name"] = "No Name"

            _LOGGER.debug("Matching models for mower '%s'", mower["name"])
            model = product_map.get(mower["product_id"])
            if model is None:
                _LOGGER.debug(
                    "Could not match model for mower '%s' (product_id=%s)",
                    mower["name"],
                    mower["product_id"],
                )
                continue

            mower["model"] = {
                "code": model["code"],
                "friendly_name": str.format(
                    "{}{}", model["default_name"], model["meters"]
                ),
                "model_year": model["product_year"],
                "cutting_width": model["cutting_width"],
            }

        return mowers

    async def get_model(self, product_id: int) -> dict[str, Any] | None:
        """Get model from product_id."""
        await self.check_token()

        products = await self._get_products()

        product_info = None
        for product in products:
            if product["id"] == product_id:
                product_info = product
                break

        return product_info

    async def _get_products(self) -> list[dict[str, Any]]:
        """Get product list from cache or API."""
        await self.check_token()
        if self._products_cache is None:
            self._products_cache = await AGET(
                f"https://{self.cloud.ENDPOINT}/api/v2/products",
                HEADERS(self.access_token),
                session=await self._ensure_session(),
            )

        return self._products_cache

    @property
    def data(self) -> Any:
        """Return the latest dataset of information and states from the API."""
        return self.api_data
