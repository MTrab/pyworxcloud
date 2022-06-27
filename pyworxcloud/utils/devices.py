"""Class for handling device info and states."""
from __future__ import annotations

from typing import Any

from .actions import Actions
from .battery import Battery
from .blades import Blades
from .capability import Capability
from .landroid_class import LDict
from .location import Location
from .mqtt import MQTTTopics
from .orientation import Orientation
from .product import ProductInfo
from .rainsensor import Rainsensor
from .state import StateType, States
from .zone import Zone

MQTT_IN = "{}/{}/commandIn"
MQTT_OUT = "{}/{}/commandOut"


class DeviceHandler(LDict):
    """DeviceHandler for Landroid Cloud devices."""

    def __init__(self, api: Any | None = None, product: Any | None = None) -> dict:
        """Initialize the object."""
        super().__init__()

        self._mqtt_data = None

        if not isinstance(product, type(None)) and not isinstance(api, type(None)):
            self.__mapinfo(api, product)

    def __mapinfo(self, api: Any, data: Any) -> None:
        """Map information from API."""

        self._mqtt_data = None

        for attr, val in data.items():
            setattr(self, str(attr), val)

        self.battery = Battery(data)
        self.blades = Blades(data)
        self.device = ProductInfo(api, data["product_id"])
        self.error = States(StateType.ERROR)
        self.orientation = Orientation([0, 0, 0])
        self.capabilities = Capability()
        self.rainsensor = Rainsensor()
        self.status = States()
        self.zone = Zone()

        self.name = data["name"]

        self.mac_address = data["mac_address"]
        topic_in = MQTT_IN.format(self.device.mainboard.code, data["mac_address"])
        topic_out = MQTT_OUT.format(self.device.mainboard.code, data["mac_address"])
        self.mqtt_topics = MQTTTopics(topic_in, topic_out)

        del data["mqtt_topics"]

        if "dat" in data:
            self["gps"] = Location(
                data["dat"]["modules"]["4G"]["gps"]["coo"][0],
                data["dat"]["modules"]["4G"]["gps"]["coo"][1],
            )

        self.schedules: dict[str, Any] = {"time_extension": 0, "active": True}

    # def __dict__(self):
    #     for key, value in self:
    #         if key.startswith("_"):
    #             continue

    #         self.update({key: value})

    # def __dict__(self):
    #     # return super().__iter__()

    #     for key in self:
    #         if key.startswith("_"):
    #             continue

    #         yield key, getattr(self, key)
