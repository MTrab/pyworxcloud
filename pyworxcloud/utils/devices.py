"""Class for handling device info and states."""
from __future__ import annotations

import json
from typing import Any

from ..const import UNWANTED_ATTRIBS
from ..exceptions import APIException
from .actions import Actions
from .battery import Battery
from .blades import Blades
from .capability import Capability
from .firmware import Firmware
from .landroid_class import LDict
from .lawn import Lawn
from .orientation import Orientation
from .product import InfoType, ProductInfo
from .rainsensor import Rainsensor
from .schedules import Schedule
from .state import States, StateType
from .warranty import Warranty
from .zone import Zone


class DeviceHandler(LDict, Actions):
    """DeviceHandler for Landroid Cloud devices."""

    __is_decoded: bool = True
    __raw_data: str = None
    __json_data: str = None

    def __init__(
        self, api: Any = None, product: Any = None, tz: str | None = None
    ) -> dict:
        """Initialize the object."""
        super().__init__()

        self._tz = tz
        if not isinstance(product, type(None)) and not isinstance(api, type(None)):
            self.__mapinfo(api, product)

    @property
    def raw_data(self) -> str:
        """Returns current raw dataset."""
        return self.__raw_data

    @property
    def json_data(self) -> str:
        """Returns current dataset as JSON."""
        return self.__json_data

    @raw_data.setter
    def raw_data(self, value: str) -> None:
        """Set new MQTT data."""
        self.__is_decoded = False
        self.__raw_data = value
        try:
            self.__json_data = json.loads(value)
        except:
            pass  # Just continue if we couldn't decode the data

    @property
    def is_decoded(self) -> bool:
        """Returns true if latest dataset was decoded and handled."""
        return self.__is_decoded

    @is_decoded.setter
    def is_decoded(self, value: bool) -> None:
        """Set decoded flag when dataset was decoded and handled."""
        self.__is_decoded = value

    def __mapinfo(self, api: Any, data: Any) -> None:
        """Map information from API."""

        if isinstance(data, type(None)) or isinstance(api, type(None)):
            raise APIException(
                "Either 'data' or 'api' object was missing, no data was mapped!"
            )

        for attr, val in data.items():
            setattr(self, str(attr), val)

        if not "time_zone" in data:
            data["time_zone"] = "UTC"

        self.battery = Battery(data)
        self.blades = Blades(data)
        self.chassis = ProductInfo(InfoType.MOWER, api, data["product_id"])
        self.mainboard = ProductInfo(InfoType.BOARD, api, self.chassis.board_id)
        self.error = States(StateType.ERROR)
        self.orientation = Orientation([0, 0, 0])
        self.capabilities = Capability()
        self.rainsensor = Rainsensor()
        self.status = States()
        self.zone = Zone()
        self.warranty = Warranty(data)
        self.firmware = Firmware(data)
        self.schedules = Schedule()

        if data in ["lawn_perimeter", "lawn_size"]:
            self.lawn = Lawn(data["lawn_perimeter"], data["lawn_size"])

        if data in ["auto_schedule_settings", "auto_schedule"]:
            self.schedules["auto_schedule"]["settings"] = data["auto_schedule_settings"]
            self.schedules["auto_schedule"]["enabled"] = data["auto_schedule"]

        self.name = data["name"]
        self.model = f"{self.chassis.default_name}{self.chassis.meters}"

        for attr in UNWANTED_ATTRIBS:
            if hasattr(self, attr):
                delattr(self, attr)

        self.is_decoded = True
