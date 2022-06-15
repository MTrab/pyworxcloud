"""Location information."""


import json


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
