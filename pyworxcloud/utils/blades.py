"""Blade information."""


from collections import UserDict


class Blades(UserDict):
    """Blade information."""

    def __init__(
        self,
        indata=None,
    ) -> None:
        """Initialize blade object."""
        super(Blades, self).__init__()
        if not indata:
            return

        if hasattr(indata, "blade_work_time"):
            # Total time with blades on in minutes
            self.data["total_on"] = int(indata.blade_work_time)
        else:
            self.data["total_on"] = None

        if hasattr(indata, "blade_work_time_reset"):
            # Blade time reset at minutes
            self.data["reset_at"] = int(indata.blade_work_time_reset)
        else:
            self.data["reset_at"] = None

        if hasattr(indata, "blade_work_time_reset_at"):
            # Blade time reset time and date
            self.data["reset_time"] = indata.blade_work_time_reset_at
        else:
            self.data["reset_time"] = None

        # Calculate blade indata since reset, if possible
        if self.data["reset_at"] and self.data["total_on"]:
            # Blade time since last reset
            self.data["current_on"] = int(self.data["total_on"] - self.data["reset_at"])
        else:
            self.data["current_on"] = self.data["total_on"]
