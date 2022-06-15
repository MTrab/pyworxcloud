"""Device capabilities."""


import json


class DeviceCapability:
    """Available device capabilities."""

    EDGE_CUT = 1
    ONE_TIME_SCHEDULE = 2
    PARTY_MODE = 4
    TORQUE = 8


class Capability:
    """Class for handling device capabilities."""

    _capa: int

    def __init__(self) -> None:
        """Initialize an empty capability list."""
        self._capa = 0

    def add(self, capability: DeviceCapability) -> None:
        """Add capability to the list."""
        if capability & self._capa == 0:
            self._capa = self._capa | capability

    def check(self, capability: DeviceCapability) -> bool:
        """Check if device has capability."""
        if capability & self._capa == 0:
            return False
        else:
            return True

    def __repr__(self) -> str:
        return json.dumps(self.to_dict, skipkeys=True)
