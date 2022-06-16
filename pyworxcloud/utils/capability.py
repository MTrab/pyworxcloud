"""Device capabilities."""


class DeviceCapability:
    """Available device capabilities."""

    EDGE_CUT = 1
    ONE_TIME_SCHEDULE = 2
    PARTY_MODE = 4
    TORQUE = 8


class Capability(int):
    """Class for handling device capabilities."""

    def __init__(self) -> None:
        """Initialize an empty capability list."""
        super(Capability, self).__init__()
        self.__int__ = 0

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
