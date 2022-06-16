"""Battery information."""
from collections import UserDict
from enum import IntEnum


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


class Battery(UserDict):
    """Battery information."""

    def __init__(self, indata: list = None, cycle_info=None) -> None:
        """Initialize a battery object."""
        super(Battery, self).__init__()

        if not indata and not cycle_info:
            return

        if not "cycles" in self.data:
            self.data["cycles"] = {
                "total": 0,
                "current": 0,
                "reset_at": None,
                "reset_time": None,
            }

        if indata:
            self.set_data(indata)
            self._update_cycles()

        if cycle_info:
            self._set_cycles(cycle_info)

    def set_data(self, indata: list):
        """Update data on existing dataset."""
        if "t" in indata:
            self.data["temperature"] = indata["t"]
        if "v" in indata:
            self.data["voltage"] = indata["v"]
        if "p" in indata:
            self.data["percent"] = indata["p"]
        if "c" in indata:
            self.data["charging"] = CHARGE_MAP[indata["c"]]
        if "nr" in indata:
            self.data["cycles"].update({"total": indata["nr"]})

    def _update_cycles(self) -> None:
        """Update cycles info."""
        if self.data["cycles"]["total"] == 0:
            return
        elif (
            isinstance(self.data["cycles"]["reset_at"], type(None))
            and self.data["cycles"]["total"] > 0
        ):
            self.data["cycles"].update({"current": self.data["cycles"]["total"]})
        else:
            self.data["cycles"].update(
                {
                    "current": int(
                        self.data["cycles"]["total"] - self.data["cycles"]["reset_at"]
                    )
                }
            )

    def _set_cycles(self, indata) -> None:
        """Set battery cycles information."""
        if self.data["cycles"]["total"] == 0:
            self.data["cycles"].update({"total": indata.battery_charge_cycles})

        if indata.battery_charge_cycles_reset is not None:
            if self.data["cycles"]["total"] == 0:
                self.data["cycles"].update(
                    {
                        "current": int(
                            self.data["cycles"]["total"]
                            - indata.battery_charge_cycles_reset
                        )
                    }
                )
                if self.data["cycles"]["current"] < 0:
                    self.data["cycles"].update({"current": 0})
            self.data["cycles"].update(
                {
                    "reset_at": int(indata.battery_charge_cycles_reset),
                    "reset_time": indata.battery_charge_cycles_reset_at,
                }
            )
        else:
            if self.data["cycles"]["total"] > 0:
                self.data["cycles"].update({"current": self.data["cycles"]["total"]})
