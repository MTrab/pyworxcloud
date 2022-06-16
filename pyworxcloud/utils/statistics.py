"""Landroid Cloud statistics class."""

from collections import UserDict


class Statistic(UserDict):
    """Statistics."""

    def __init__(self, data: list = None):
        """Initialize a statistics class."""
        super(Statistic, self).__init__()

        if not data:
            return

        if "b" in data:
            # Total runtime with blades on in minutes
            self.data["worktime_blades_on"] = data["b"]
        else:
            self.data["worktime_blades_on"] = None

        if "d" in data:
            # Total distance in meters
            self.data["distance"] = data["d"]
        else:
            self.data["distance"] = None

        if "wt" in data:
            # Total worktime in minutes
            self.data["worktime_total"] = data["wt"]
        else:
            self.data["worktime_total"] = None
