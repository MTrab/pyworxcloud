"""Handler for the physical device information."""
from __future__ import annotations
from enum import IntEnum
from typing import Any

from .landroid_class import LDict


class SetupLocation(dict):
    """Handling setup location."""

    def __init__(self, latitude: float = 0.0, longitude: float = 0.0) -> None:
        """Initialize setup location object."""
        super().__init__()

        self["latitude"] = latitude
        self["longitude"] = longitude


class WarrantyInfo(dict):
    """Handling warranty information."""


class InfoType(IntEnum):
    MOWER = 0
    BOARD = 1


class Info(dict):
    """Handling mainboard information."""

    def __init__(
        self,
        info_type: InfoType,
        api: Any | None = None,
        product_id: int | None = None,
    ):
        """Initialize mower infor object."""
        super().__init__()

        if product_id and api:
            self.get_information_from_id(info_type, api, product_id)

    def get_information_from_id(
        self, info_type: InfoType, api: Any, product_id: int
    ) -> None:
        """Get the device information based on ID."""

        api_prod = None
        if info_type == InfoType.MOWER:
            api_prod = api.get_product_info(product_id)
        elif info_type == InfoType.BOARD:
            api_prod = api.get_board(product_id)

        for attr, val in api_prod.items():
            setattr(self, str(attr), val)


class ProductInfo(LDict):
    """Class definition for handling physical device information."""

    def __init__(self, api: Any | None = None, product_id: int | None = None):
        """Initialize a device object."""
        super().__init__()

        self.mower = Info(InfoType.MOWER, api, product_id)
        self.mainboard = Info(
            InfoType.BOARD,
            api,
            self.mower.board_id if hasattr(self.mower, "board_id") else None,
        )
