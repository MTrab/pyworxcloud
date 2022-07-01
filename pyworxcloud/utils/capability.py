"""Device capabilities."""
from __future__ import annotations

from enum import IntEnum
import logging


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

_LOGGER = logging.getLogger("pyworxcloud.capability_handler")


class Capability(int):
    """Class for handling device capabilities."""

    def __init__(self) -> None:
        """Initialize an empty capability list."""
        super().__init__()
        self.__int__ = 0

    def add(self, capability: DeviceCapability) -> None:
        """Add capability to the list."""
        _LOGGER.debug("Testing %s: %s",CAPABILITY_TO_TEXT[capability],capability & self.__int__)
        if capability & self.__int__ == 0:
            _LOGGER.debug("Adding %s to capabilities", CAPABILITY_TO_TEXT[capability])
            self.__int__ = self.__int__ | capability

    def check(self, capability: DeviceCapability) -> bool:
        """Check if device has capability."""
        if capability & self.__int__ == 0:
            return False
        else:
            return True
