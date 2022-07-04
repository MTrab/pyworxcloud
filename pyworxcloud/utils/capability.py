"""Device capabilities."""
from __future__ import annotations

import logging
from enum import IntEnum

from ..events import EventHandler, LandroidEvent


class DeviceCapability(IntEnum):
    """Available device capabilities."""

    EDGE_CUT = 1
    ONE_TIME_SCHEDULE = 2
    PARTY_MODE = 4
    TORQUE = 8


CAPABILITY_TO_TEXT = {
    DeviceCapability.EDGE_CUT: "Edge Cut",
    DeviceCapability.ONE_TIME_SCHEDULE: "One-Time-Schedule",
    DeviceCapability.PARTY_MODE: "Party Mode",
    DeviceCapability.TORQUE: "Motor Torque",
}


class Capability(int):
    """Class for handling device capabilities."""

    def __init__(self) -> None:
        """Initialize an empty capability list."""
        super().__init__()
        self.__int__ = 0
        self.ready = False

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
