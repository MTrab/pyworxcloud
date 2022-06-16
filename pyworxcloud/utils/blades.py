"""Blade information."""

from .landroid_class import LDict


class Blades(LDict):
    """Blade information."""

    def __init__(
        self,
        indata=None,
    ) -> None:
        """Initialize blade object."""
        super().__init__()
        if not indata:
            return

        if hasattr(indata, "blade_work_time"):
            # Total time with blades on in minutes
            self["total_on"] = int(indata.blade_work_time)
        else:
            self["total_on"] = None

        if hasattr(indata, "blade_work_time_reset"):
            # Blade time reset at minutes
            self["reset_at"] = int(indata.blade_work_time_reset)
        else:
            self["reset_at"] = None

        if hasattr(indata, "blade_work_time_reset_at"):
            # Blade time reset time and date
            self["reset_time"] = indata.blade_work_time_reset_at
        else:
            self["reset_time"] = None

        # Calculate blade indata since reset, if possible
        if self["reset_at"] and self["total_on"]:
            # Blade time since last reset
            self["current_on"] = int(self["total_on"] - self["reset_at"])
        else:
            self["current_on"] = self["total_on"]
