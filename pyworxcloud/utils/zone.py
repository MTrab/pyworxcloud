"""Zone representation."""
from __future__ import annotations

from .landroid_class import LDict


class Zone(LDict):
    """Class for handling zone data."""

    def __init__(self) -> dict:
        """Initialize zone object."""
        super().__init__()

        self["current"] = None
        self["next"] = None
        self["index"] = None
        self["indicies"] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self["starting_point"] = [0, 0, 0, 0]

    @property
    def current(self) -> int:
        """Get current zone."""
        return self["current"]

    @current.setter
    def current(self, value: int) -> None:
        """Set current zone property."""
        self["current"] = value

    @property
    def next(self) -> int:
        """Get next zone."""
        return self["next"]

    @next.setter
    def next(self, value: int) -> None:
        """Set next zone property."""
        self["next"] = value

    @property
    def index(self) -> int:
        """Get current index."""
        return self["index"]

    @index.setter
    def index(self, value: int) -> None:
        """Set current index property."""
        self["index"] = value

    @property
    def indicies(self) -> int:
        """Get indicies."""
        return self["indicies"]

    @indicies.setter
    def indicies(self, value: list) -> None:
        """Set indicies property."""
        self["indicies"] = value

    @property
    def starting_point(self) -> int:
        """Get starting points."""
        return self["starting_point"]

    @starting_point.setter
    def starting_point(self, value: int) -> None:
        """Set starting points."""
        self["starting_point"] = value
