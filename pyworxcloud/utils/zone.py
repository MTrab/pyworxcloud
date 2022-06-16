"""Zone representation."""

from collections import UserDict
import json


class Zone(UserDict):
    """Class for handling zone data."""

    def __init__(self):
        """Initialize zone object."""
        super(Zone, self).__init__()

        self.data["current"] = None
        self.data["index"] = None
        self.data["indicies"] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.data["starting_point"] = [0, 0, 0, 0]

    def __repr__(self) -> str:
        return json.dumps(self.data)

    @property
    def current(self) -> int:
        """Get current zone."""
        return self.data["current"]

    @current.setter
    def current(self, value: int) -> None:
        """Set current zone property."""
        self.data["current"] = value

    @property
    def index(self) -> int:
        """Get current index."""
        return self.data["index"]

    @index.setter
    def index(self, value: int) -> None:
        """Set current index property."""
        self.data["index"] = value

    @property
    def indicies(self) -> int:
        """Get indicies."""
        return self.data["indicies"]

    @indicies.setter
    def indicies(self, value: list) -> None:
        """Set indicies property."""
        self.data["indicies"] = value

    @property
    def starting_point(self) -> int:
        """Get starting points."""
        return self.data["starting_point"]

    @starting_point.setter
    def starting_point(self, value: int) -> None:
        """Set starting points."""
        self.data["starting_point"] = value
