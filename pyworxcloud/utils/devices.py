"""Class for handling device info and states."""

from __future__ import annotations

import json
from typing import Any

from ..const import UNWANTED_ATTRIBS
from ..exceptions import APIException
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


# class DeviceHandler(LDict, Actions):
class DeviceHandler(LDict):
    """DeviceHandler for Landroid Cloud devices."""

    __is_decoded: bool = True
    __raw_data: str = None
    __json_data: str = None

    def __init__(
        self,
        api: Any = None,
        mower: Any = None,
        tz: str | None = None,
    ) -> dict:
        """Initialize the object."""
        super().__init__()

        self._api = api
        self.mower = mower
        self._tz = tz

        if not isinstance(mower, type(None)) and not isinstance(api, type(None)):
            self.__mapinfo(api, mower)

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
        except:  # pylint: disable=bare-except
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
        self.error = States(StateType.ERROR)
        self.orientation = Orientation([0, 0, 0])
        self.capabilities = Capability(data)
        self.rainsensor = Rainsensor()
        self.status = States()
        self.zone = Zone(data)
        self.warranty = Warranty(data)
        self.firmware = Firmware(data)
        self.schedules = Schedule(data)
        self.in_topic = data["mqtt_topics"]["command_in"]
        self.out_topic = data["mqtt_topics"]["command_out"]

        if data in ["lawn_perimeter", "lawn_size"]:
            self.lawn = Lawn(data["lawn_perimeter"], data["lawn_size"])

        self.name = data["name"]
        self.model = str.format(
            "{} ({})", data["model"]["friendly_name"], data["model"]["code"]
        )

        for attr in UNWANTED_ATTRIBS:
            if hasattr(self, attr):
                delattr(self, attr)

        self.is_decoded = True
