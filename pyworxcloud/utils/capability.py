"""Device capabilities."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

_LOGGER = logging.getLogger(__name__)


class DeviceCapability(IntEnum):
    """Available device capabilities."""

    EDGE_CUT = 1
    ONE_TIME_SCHEDULE = 2
    PARTY_MODE = 4
    TORQUE = 8
    OFF_LIMITS = 16
    CUTTING_HEIGHT = 32
    ACS = 64


CAPABILITY_TO_TEXT = {
    DeviceCapability.EDGE_CUT: "Edge Cut",
    DeviceCapability.ONE_TIME_SCHEDULE: "One-Time-Schedule",
    DeviceCapability.PARTY_MODE: "Party Mode",
    DeviceCapability.TORQUE: "Motor Torque",
    DeviceCapability.OFF_LIMITS: "Off Limits",
    DeviceCapability.CUTTING_HEIGHT: "Cutting Height",
    DeviceCapability.ACS: "ACS",
}


class Capability:
    """Class for handling device capabilities."""

    def __init__(self, device_data: Any | None = None) -> int:
        """Initialize the capability list."""
        # super().__init__()
        self.__int__: int = 0
        self.ready: bool = False
        if isinstance(device_data, type(None)):
            return

        cfg = (
            device_data["cfg"]
            if "cfg" in device_data
            else device_data["last_status"]["payload"]["cfg"]
        )
        dat = (
            device_data["dat"]
            if "dat" in device_data
            else device_data["last_status"]["payload"]["dat"]
        )

        try:
            if "sc" in cfg:
                if "ots" in cfg["sc"] or "once" in cfg["sc"]:
                    self.add(DeviceCapability.ONE_TIME_SCHEDULE)
                    self.add(DeviceCapability.EDGE_CUT)

                if "distm" in cfg["sc"] or "enabled" in cfg["sc"]:
                    self.add(DeviceCapability.PARTY_MODE)

        except TypeError:
            pass

        try:
            if "modules" in dat:
                # Offlimits module
                if "DF" in dat["modules"]:
                    self.add(DeviceCapability.OFF_LIMITS)

                # Set cutting height
                if "EA" in dat["modules"]:
                    self.add(DeviceCapability.CUTTING_HEIGHT)

                # ACS module
                if "US" in dat["modules"]:
                    self.add(DeviceCapability.ACS)
        except TypeError:
            pass

        try:
            if "tq" in cfg:
                self.add(DeviceCapability.TORQUE)
        except TypeError:
            pass

    def add(self, capability: DeviceCapability) -> None:
        """Add capability to the list."""
        if capability & self.__int__ == 0:
            self.__int__ = self.__int__ | capability

    def check(self, capability: DeviceCapability) -> bool:
        """Check if device has capability."""
        if capability & self.__int__ == 0:
            return False
        else:
            return True
