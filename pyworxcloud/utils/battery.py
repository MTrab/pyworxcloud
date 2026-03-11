"""Battery information."""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from .landroid_class import LDict


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


class Battery(LDict):
    """Battery information."""

    @staticmethod
    def _read_value(indata: Any, key: str) -> Any | None:
        """Read a battery counter field from either a dict or object."""
        if isinstance(indata, dict):
            return indata.get(key)
        return getattr(indata, key, None)

    def __init__(
        self, indata: list | None = None, cycle_info: Any | None = None
    ) -> None:
        """Initialize a battery object."""
        super().__init__()

        if not indata and not cycle_info:
            return

        if not "cycles" in self:
            self["cycles"] = {
                "total": 0,
                "current": 0,
                "reset_at": None,
                "reset_time": None,
            }

        if not "temperature" in self:
            self["temperature"] = None

        if not "voltage" in self:
            self["voltage"] = None

        if not "percent" in self:
            self["percent"] = None

        if not "charging" in self:
            self["charging"] = None

        if indata:
            self.set_data(indata)
            self._update_cycles()

        if cycle_info:
            self._set_cycles(cycle_info)

    def set_data(self, indata: list):
        """Update data on existing dataset."""
        if "t" in indata:
            self["temperature"] = indata["t"]
        if "v" in indata:
            self["voltage"] = indata["v"]
        if "p" in indata:
            self["percent"] = indata["p"]
        if "c" in indata:
            self["charging"] = CHARGE_MAP[indata["c"]]
        if "nr" in indata:
            self["cycles"].update({"total": indata["nr"]})
            self._update_cycles()

    def _update_cycles(self) -> None:
        """Update cycles info."""
        if self["cycles"]["total"] == 0:
            return
        elif (
            isinstance(self["cycles"]["reset_at"], type(None))
            and self["cycles"]["total"] > 0
        ):
            self["cycles"].update({"current": self["cycles"]["total"]})
        else:
            self["cycles"].update(
                {"current": int(self["cycles"]["total"] - self["cycles"]["reset_at"])}
            )

    def _set_cycles(self, indata) -> None:
        """Set battery cycles information."""
        from ..helpers import string_to_time

        total_cycles = self._read_value(indata, "battery_charge_cycles")
        if total_cycles is not None and self["cycles"]["total"] == 0:
            self["cycles"].update({"total": int(total_cycles)})

        reset_at = self._read_value(indata, "battery_charge_cycles_reset")
        reset_time = self._read_value(indata, "battery_charge_cycles_reset_at")
        time_zone = self._read_value(indata, "time_zone")

        if reset_at is not None:
            self["cycles"].update(
                {
                    "reset_at": int(reset_at),
                    "reset_time": (
                        string_to_time(reset_time, time_zone)
                        if not isinstance(reset_time, type(None))
                        else None
                    ),
                }
            )

        self._update_cycles()
