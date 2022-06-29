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

        # Total runtime with blades on in minutes
        self["worktime_blades_on"] = data["b"] if "b" in data else None

        # Total distance in meters
        self["distance"] = data["d"] if "d" in data else None

        # Total worktime in minutes
        self["worktime_total"] = data["wt"] if "wt" in data else None
