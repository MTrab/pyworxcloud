"""Location information."""
from .landroid_base import DictBase


class Location(DictBase):
    """GPS location."""

    def __init__(self, latitude: float | None = None, longitude: float | None = None):
        """Initialize location object."""
        super(Location, self).__init__()

        if not latitude or not longitude:
            return

        self.latitude = latitude
        self.longitude = longitude
