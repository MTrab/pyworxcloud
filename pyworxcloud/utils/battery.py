"""Battery information."""
from enum import IntEnum
import json


class BatteryState(IntEnum):
    """Battery states."""

    UNKNOWN = -1
    CHARGED = 0
    CHARGING = 1
    ERROR_CHARGING = 2


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
        2: Charge left as percent
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
            "percent": self._perc,
            "current_cycles": self._cycles_current,
            "total_cycles": self._cycles_total,
            "reset_cycles": self._cycles_reset,
            "charging": self._charging,
            "maintenence": self._maint,
        }

    def __repr__(self) -> str:
        return str(self._perc)

    @property
    def temperature(self) -> int:
        """Return battery temperature."""
        return self._temp

    @property
    def voltage(self) -> int:
        """Return battery voltage."""
        return self._volt

    @property
    def percent(self) -> int:
        """Return battery charge state in percent."""
        return self._perc

    @property
    def cycles(self) -> int:
        """Contains charge cycle information."""

        @property
        def current() -> int:
            """Return current cycles."""
            return self._cycles_current

        @property
        def total() -> int:
            """Return total cycles."""
            return self._cycles_total

        @property
        def reset_at() -> int:
            """Return cycles for last reset."""
            return self._cycles_reset

        return {"current": current(), "total": total(), "reset_at": reset_at()}

    @property
    def charging(self) -> BatteryState:
        """Return current cycles."""
        return self._charging

    @property
    def maintenence(self) -> int:
        """Return current cycles."""
        return self._maint
