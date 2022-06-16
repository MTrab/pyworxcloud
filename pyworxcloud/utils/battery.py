"""Battery information."""
from enum import IntEnum
from typing import Any

from .landroid_base import DictBase


class BatteryState(IntEnum):
    """Battery states."""

    UNKNOWN = -1
    NOT_CHARGING = 0
    CHARGING = 1
    ERROR_CHARGING = 2


CHARGE_MAP = {
    BatteryState.UNKNOWN: "unknown",
    BatteryState.NOT_CHARGING: False,
    BatteryState.CHARGING: True,
    BatteryState.ERROR_CHARGING: "error",
}


class Battery(DictBase):
    """Battery information."""

    _dict: dict[str, Any]

    def __init__(self, data: list = None, cycle_info=None) -> None:
        """Initialize a battery object."""
        super(Battery, self).__init__()

        if not data and not cycle_info:
            return

        if not hasattr(self, "cycles"):
            self.cycles = {
                "total": 0,
                "current": 0,
                "reset_at": None,
                "reset_time": None,
            }

        if data:
            self.set_data(data)
            self._update_cycles()

        if cycle_info:
            self._set_cycles(cycle_info)

    def set_data(self, data: list):
        """Update data on existing dataset."""
        if "t" in data:
            self.temperature = data["t"]
        if "v" in data:
            self.voltage = data["v"]
        if "p" in data:
            self.percent = data["p"]
        if "c" in data:
            self.charging = CHARGE_MAP[data["c"]]
        if "nr" in data:
            self.cycles.update({"total": data["nr"]})

    def _update_cycles(self) -> None:
        """Update cycles info."""
        if self.cycles["total"] == 0:
            return
        elif (
            isinstance(self.cycles["reset_at"], type(None)) and self.cycles["total"] > 0
        ):
            self.cycles.update({"current": self.cycles["total"]})
        else:
            self.cycles.update(
                {"current": int(self.cycles["total"] - self.cycles["reset_at"])}
            )

    def _set_cycles(self, data) -> None:
        """Set battery cycles information."""
        if self.cycles["total"] == 0:
            self.cycles.update({"total": data.battery_charge_cycles})

        if data.battery_charge_cycles_reset is not None:
            if self.cycles["total"] == 0:
                self.cycles.update(
                    {
                        "current": int(
                            self.cycles["total"] - data.battery_charge_cycles_reset
                        )
                    }
                )
                if self.cycles["current"] < 0:
                    self.cycles.update({"current": 0})
            self.cycles.update(
                {
                    "reset_at": int(data.battery_charge_cycles_reset),
                    "reset_time": data.battery_charge_cycles_reset_at,
                }
            )
        else:
            if self.cycles["total"] > 0:
                self.cycles.update({"current": self.cycles["total"]})
