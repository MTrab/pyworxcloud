"""Location information."""
from __future__ import annotations

from .landroid_class import LDict


class Location(LDict):
    """GPS location."""

    def __init__(self, latitude: float = None, longitude: float = None):
        """Initialize location object."""
        super().__init__()

        if not latitude or not longitude:
            return

        self["latitude"] = latitude
        self["longitude"] = longitude
