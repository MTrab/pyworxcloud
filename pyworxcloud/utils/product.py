"""Handler for the physical device information."""
from __future__ import annotations

from enum import IntEnum
from typing import Any

from .landroid_class import LDict


class SetupLocation(LDict):
    """Handling setup location."""

    def __init__(self, latitude: float = 0.0, longitude: float = 0.0) -> None:
        """Initialize setup location object."""
        super().__init__()

        self["latitude"] = latitude
        self["longitude"] = longitude


class WarrantyInfo(LDict):
    """Handling warranty information."""


class InfoType(IntEnum):
    MOWER = 0
    BOARD = 1


class ProductInfo(LDict):
    """Handling mainboard information."""

    def __init__(
        self,
        info_type: InfoType,
        api: Any | None = None,
        product_id: int | None = None,
    ) -> dict:
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

    # def __iter__(self) -> Iterator[dict[str, Any]]:
    #     for key, val in self.items():
    #         if key.startswith("_"):
    #             continue

    #         yield (key, val)

    # def __dict__(self) -> dict[str, Any]:
    #     attrs = {}
    #     for key, val in self.items():
    #         if key.startswith("_"):
    #             continue
    #         attrs.update({key:val})
    #         # yield (key, val)
    #     return attrs
