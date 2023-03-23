"""Device orientation."""
from __future__ import annotations

from .landroid_class import LDict


class Orientation(LDict):
    """Device orientation class."""

    def __init__(self, data: list) -> None:
        """Initialize orientation object."""
        super().__init__()
        if not data:
            return

        self["pitch"] = data[0]
        self["roll"] = data[1]
        self["yaw"] = data[2]
