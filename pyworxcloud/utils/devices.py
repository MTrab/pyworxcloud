"""Class for handling device info and states."""
from __future__ import annotations

from typing import Any


from ..const import UNWANTED_ATTRIBS

from .battery import Battery
from .blades import Blades
from .capability import Capability
from .firmware import Firmware
from .landroid_class import LDict
from .lawn import Lawn
from .location import Location
from .mqtt import MQTTTopics
from .orientation import Orientation
from .product import InfoType, ProductInfo
from .rainsensor import Rainsensor
from .schedules import Schedule
from .state import StateType, States
from .warranty import Warranty
from .zone import Zone


class DeviceHandler(LDict):
    """DeviceHandler for Landroid Cloud devices."""

    def __init__(self, api: Any | None = None, product: Any | None = None) -> dict:
        """Initialize the object."""
        super().__init__()

        self._mqtt_data = None
        self._api_data = None

        if not isinstance(product, type(None)) and not isinstance(api, type(None)):
            self.__mapinfo(api, product)

    def __mapinfo(self, api: Any, data: Any) -> None:
        """Map information from API."""

        self._mqtt_data = None

        for attr, val in data.items():
            setattr(self, str(attr), val)

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
        self.schedules = Schedule(
            auto_schedule_settings=data["auto_schedule_settings"],
            auto_schedule_enabled=data["auto_schedule"],
        )
        self.lawn = Lawn(data["lawn_perimeter"], data["lawn_size"])

        self.schedules["auto_schedule"]["settings"] = data["auto_schedule_settings"]
        self.schedules["auto_schedule"]["settings"] = data["auto_schedule_settings"]

        self.name = data["name"]
        self.model = f"{self.chassis.default_name}{self.chassis.meters}"

        for attr in UNWANTED_ATTRIBS:
            if hasattr(self, attr):
                delattr(self, attr)
