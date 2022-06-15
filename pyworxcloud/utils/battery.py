"""Battery information."""
from enum import IntEnum
from typing import Any


class BatteryState(IntEnum):
    """Battery states."""

    UNKNOWN = -1
    CHARGED = 0
    CHARGING = 1
    ERROR_CHARGING = 2


class Battery(dict):
    """Battery information."""

    temperature: float | None = None
    voltage: float | None = None
    state: int | None = None
    cycles: dict[str, Any]
    _cycles_total: int | None = None
    _cycles_reset: int | None = None
    _cycles_current: int | None = None
    charging: BatteryState = BatteryState.UNKNOWN
    maintenence: int | None = None

    _dict: dict[str, Any]

    def __init__(self, data: list = None) -> None:
        """Initialize a battery object."""
        super(Battery, self).__init__()
        self.cycles = {}
        if not data:
            return

        self.temperature = data["t"] if "t" in data else None
        self.voltage = data["v"] if "v" in data else None
        self.state = data["p"] if "p" in data else None
        self.charging = data["c"] if "c" in data else None
        self.cycles.update({"total": data["nr"] if "nr" in data else None})
        if self._cycles_reset is not None:
            self._cycles_current = self._cycles_total - self._cycles_reset
            if self._cycles_current < 0:
                self._cycles_current = 0
        else:
            self.cycles.update({"current": self.cycles["total"]})

    def __repr__(self) -> str:
        return repr(self.__dict__)

    # @property
    # def temperature(self) -> int:
    #     """Return battery temperature."""
    #     return self._temp

    # @property
    # def voltage(self) -> int:
    #     """Return battery voltage."""
    #     return self._volt

    # @property
    # def percent(self) -> int:
    #     """Return battery charge state in percent."""
    #     return self._perc

    # @property
    # def cycles(self) -> int:
    #     """Contains charge cycle information."""

    #     @property
    #     def current() -> int:
    #         """Return current cycles."""
    #         return self._cycles_current

    #     @property
    #     def total() -> int:
    #         """Return total cycles."""
    #         return self._cycles_total

    #     @property
    #     def reset_at() -> int:
    #         """Return cycles for last reset."""
    #         return self._cycles_reset

    #     return {"current": current(), "total": total(), "reset_at": reset_at()}

    # @property
    # def charging(self) -> BatteryState:
    #     """Return current cycles."""
    #     return self._charging

    # @property
    # def maintenence(self) -> int:
    #     """Return current cycles."""
    #     return self._maint
