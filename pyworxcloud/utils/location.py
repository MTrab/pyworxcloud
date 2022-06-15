"""Location information."""


class Location(dict):
    """GPS location."""

    # latitude: float | None = None
    # longitude: float | None = None

    def __init__(self, latitude: float | None = None, longitude: float | None = None):
        """Initialize location object."""
        super(Location, self).__init__()

        if not latitude or not longitude:
            return
        self.latitude = latitude
        self.longitude = longitude

    def __repr__(self) -> str:
        return repr(self.__dict__)
