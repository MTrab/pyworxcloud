"""Landroid data classes."""

from enum import IntEnum
import json


class BatteryState(IntEnum):
    """Battery states."""

    UNKNOWN = -1
    CHARGED = 0
    CHARGING = 1
    ERROR_CHARGING = 2


class DeviceCapability(IntEnum):
    """Available device capabilities."""

    UNKNOWN = -1
    EDGE_CUT = 0
    ONE_TIME_SCHEDULE = 1
    PARTY_MODE = 2
    TORQUE = 3


class Capability:
    """Class for handling device capabilities."""

    _capa: list

    def __init__(self) -> None:
        """Initialize an empty capability list."""
        self._capa = []

    def add(self, capability: DeviceCapability) -> None:
        """Add capability to the list."""
        if not capability in self._capa:
            self._capa.append(capability)

    def remove(self, capability: DeviceCapability) -> None:
        """Delete capability from the list."""
        if capability in self._capa:
            self._capa.pop(capability)

    def get(self, capability: DeviceCapability) -> bool:
        """Check if device has capability."""
        return bool(capability in self._capa)


class Blades:
    """Blade information."""

    _total_on: int | None = None  # Total runtime with blades on in minutes
    _distance: int | None = None  # Total distance in meters
    _worktime: int | None = None  # Total worktime in minutes
    _current: int | None = None  # Blade time since last reset

    def __init__(self, data: list = None) -> None:
        """Initialize blade object."""
        if not data:
            return

        self._total_on = data["b"] if "b" in data else None
        self._distance = data["d"] if "d" in data else None
        self._worktime = data["wt"] if "wt" in data else None
        self._current = data["bl"] if "bl" in data else None

    @property
    def to_list(self) -> list:
        """Return object as a list.

        0: Total on
        1: Distance
        2: Worktime
        3: Current on
        """
        return [
            self._total_on,
            self._distance,
            self._worktime,
            self._current,
        ]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {
            "total_on": self._total_on,
            "distance": self._distance,
            "worktime": self._worktime,
            "current_on": self._current,
        }


class Battery:
    """Battery information."""

    _temp: float | None = None
    _volt: float | None = None
    _perc: int | None = None
    _cycles_total: int | None = None
    _cycles_reset: int | None = None
    _cycles_current: int | None = None
    _charging: BatteryState = BatteryState.UNKNOWN
    _maint: int | None = None

    def __init__(self, data: list = None) -> None:
        """Initialize a battery object."""
        if not data:
            return

        self._temp = data["t"] if "t" in data else None
        self._volt = data["v"] if "v" in data else None
        self._perc = data["p"] if "p" in data else None
        self._charging = data["c"] if "c" in data else None
        self._cycles = data["nr"] if "nr" in data else None
        if self._cycles_reset is not None:
            self._cycles_current = self._cycles_total - self._cycles_reset
            if self._cycles_current < 0:
                self._cycles_current = 0
        else:
            self._cycles_current = self._cycles_total

    @property
    def to_list(self) -> list:
        """Return object as a list.

        0: Temperature
        1: Voltage
        2: State (charge %)
        3: Current charge cycles
        4: Total charge cycles
        5: Reset at charge cycles
        6: Charging state
        7: Maintenence
        """
        return [
            self._temp,
            self._volt,
            self._perc,
            self._cycles_current,
            self._cycles_total,
            self._cycles_reset,
            self._charging,
            self._maint,
        ]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {
            "temperature": self._temp,
            "voltage": self._volt,
            "state": self._perc,
            "current_cycles": self._cycles_current,
            "total_cycles": self._cycles_total,
            "reset_cycles": self._cycles_reset,
            "charging": self._charging,
            "maintenence": self._maint,
        }

    def __repr__(self) -> str:
        return json.dumps(self.to_dict)


class Location:
    """GPS location."""

    _lat: float | None = None
    _lon: float | None = None

    def __init__(self, latitude: float | None = None, longitude: float | None = None):
        """Initialize location object."""
        self._lat = latitude
        self._lon = longitude

    @property
    def to_list(self) -> list:
        """Return object as a list.

        0: Latitude
        1: Longitude
        """
        return [self._lat, self._lon]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {"latitude": self._lat, "longitude": self._lon}

    @property
    def latitude(self):
        """Return latitude."""
        return self._lat

    @property
    def longitude(self):
        """Return longitude."""
        return self._longitude


class Orientation:
    """Device orientation class."""

    _pitch = 0
    _roll = 0
    _yaw = 0

    def __init__(self, data: list) -> None:
        """Initialize orientation object."""
        if not data:
            return

        self._pitch = data[0]
        self._roll = data[1]
        self._yaw = data[2]

    @property
    def to_list(self) -> list:
        """Return object as a list.

        0: Pitch
        1: Roll
        2: Yaw
        """
        return [self._pitch, self._roll, self._yaw]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {"pitch": self._pitch, "roll": self._roll, "yaw": self._yaw}

    @property
    def pitch(self):
        """Return pitch."""
        return self._pitch

    @property
    def roll(self):
        """Return roll."""
        return self._roll

    @property
    def yaw(self):
        """Return yaw."""
        return self._yaw
