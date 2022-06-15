"""Landroid data classes."""


class Location:
    """GPS location."""

    _lat: float | None = None
    _lon: float | None = None

    def __init__(self, latitude: float | None = None, longitude: float | None = None):
        """Initialize location object."""
        self._lat = latitude
        self._lon = longitude

    @property
    def to_list(self) -> list:
        """Return object as a list.

        0: Latitude
        1: Longitude
        """
        return [self._lat, self._lon]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {"latitude": self._lat, "longitude": self._lon}

    @property
    def latitude(self):
        """Return latitude."""
        return self._lat

    @property
    def longitude(self):
        """Return longitude."""
        return self._longitude


class Orientation:
    """Device orientation class."""

    _pitch = 0
    _roll = 0
    _yaw = 0

    def __init__(self, orientation: list) -> None:
        """Initialize orientation object."""
        self._pitch = orientation[0]
        self._roll = orientation[1]
        self._yaw = orientation[2]

    @property
    def to_list(self) -> list:
        """Return object as a list.

        0: Pitch
        1: Roll
        2: Yaw
        """
        return [self._pitch, self._roll, self._yaw]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {"pitch": self._pitch, "roll": self._roll, "yaw": self._yaw}

    @property
    def pitch(self):
        """Return pitch."""
        return self._pitch

    @property
    def roll(self):
        """Return roll."""
        return self._roll

    @property
    def yaw(self):
        """Return yaw."""
        return self._yaw
