"""Landroid Cloud statistics class."""
from __future__ import annotations

from .landroid_class import LDict


class Statistic(LDict):
    """Statistics."""

    def __init__(self, data: list | None = None) -> dict:
        """Initialize a statistics class."""
        super().__init__()

        if not data:
            return

        if "b" in data:
            # Total runtime with blades on in minutes
            self["worktime_blades_on"] = data["b"]
        else:
            self["worktime_blades_on"] = None

        if "d" in data:
            # Total distance in meters
            self["distance"] = data["d"]
        else:
            self["distance"] = None

        if "wt" in data:
            # Total worktime in minutes
            self["worktime_total"] = data["wt"]
        else:
            self["worktime_total"] = None
