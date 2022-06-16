"""Landroid Cloud statistics class."""

from .landroid_base import DictBase


class Statistic(DictBase):
    """Statistics."""

    def __init__(self, data: list = None):
        """Initialize a statistics class."""
        super(Statistic, self).__init__()

        if not data:
            return

        if "b" in data:
            # Total runtime with blades on in minutes
            self.worktime_blades_on = data["b"]
        else:
            self.worktime_blades_on = None

        if "d" in data:
            # Total distance in meters
            self.distance = data["d"]
        else:
            self.distance = None

        if "wt" in data:
            # Total worktime in minutes
            self.worktime_total = data["wt"]
        else:
            self.worktime_total = None
