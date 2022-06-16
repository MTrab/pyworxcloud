"""Location information."""
from collections import UserDict


class Location(UserDict):
    """GPS location."""

    def __init__(self, latitude: float | None = None, longitude: float | None = None):
        """Initialize location object."""
        super(Location, self).__init__()

        if not latitude or not longitude:
            return

        self.data["latitude"] = latitude
        self.data["longitude"] = longitude
