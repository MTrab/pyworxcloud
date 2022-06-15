"""Landroid data classes."""

from ctypes import cast
from enum import IntEnum


class BatteryState(IntEnum):
    """Battery states."""

    UNKNOWN = -1
    CHARGED = 0
    CHARGING = 1
    ERROR_CHARGING = 2


class Blades:
    """Blade information."""

    _total_on: int | None = None  # Total runtime with blades on in minutes
    _distance: int | None = None  # Total distance in meters
    _worktime: int | None = None  # Total worktime in minutes
    _current: int | None = None  # Blade time since last reset

    def __init__(self, data: list = None) -> None:
        """Initialize blade object."""
        self._total_on = data["b"]
        self._distance = data["d"]
        self._worktime = data["wt"]
        self._current = data["bl"]

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
        self._temp = data["t"]
        self._volt = data["v"]
        self._perc = data["p"]
        self._charging = cast(data["c"], BatteryState)
        self._cycles = data["nr"]
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
        3: Charge cycles
        4: Charging state
        5: Maintenence
        """
        return [
            self._temp,
            self._volt,
            self._state,
            self._cycle,
            self._charging,
            self._maint,
        ]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {
            "temperature": self._temp,
            "voltage": self._volt,
            "state": self._state,
            "charge_cycles": self._cycle,
            "charging": self._charging,
            "maintenence": self._maint,
        }


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

    def __init__(self, orientation: list) -> None:
        """Initialize orientation object."""
        self._pitch = orientation[0]
        self._roll = orientation[1]
        self._yaw = orientation[2]

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
