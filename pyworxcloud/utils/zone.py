"""Zone representation."""

from __future__ import annotations

from typing import Any

from .landroid_class import LDict


class Zone(LDict):
    """Class for handling zone data."""

    def __init__(self, data: Any | None = None) -> dict:
        """Initialize zone object."""
        super().__init__()

        self["current"] = 0
        self["index"] = 0
        self["ids"] = []
        self["indicies"] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self["starting_point"] = [0, 0, 0, 0]

        if data is None:
            return

        try:
            if not "last_status" in data:
                return

            if not "payload" in data["last_status"]:
                return

            if (
                not "dat" in data["last_status"]["payload"]
                or not "cfg" in data["last_status"]["payload"]
            ):
                return

            self["index"] = (
                data["last_status"]["payload"]["dat"]["lz"]
                if "lz" in data["last_status"]["payload"]["dat"]
                else 0
            )
            self["indicies"] = (
                data["last_status"]["payload"]["cfg"]["mzv"]
                if "mzv" in data["last_status"]["payload"]["cfg"]
                else [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            )
            self["starting_point"] = (
                data["last_status"]["payload"]["cfg"]["mz"]
                if "mz" in data["last_status"]["payload"]["cfg"]
                else [0, 0, 0, 0]
            )
            rtk = data["last_status"]["payload"]["cfg"].get("rtk")
            if isinstance(rtk, dict) and isinstance(rtk.get("zs"), list):
                self["ids"] = [
                    int(zone["id"])
                    for zone in rtk["zs"]
                    if isinstance(zone, dict) and "id" in zone
                ]

            cut = data["last_status"]["payload"]["dat"].get("cut")
            if isinstance(cut, dict) and "z" in cut:
                self["current"] = int(cut["z"])
        except TypeError:  # pylint: disable=bare-except
            pass

        if self["current"] == 0:
            self["current"] = self["indicies"][self["index"]]
        if self["ids"] and self["current"] in self["ids"]:
            self["index"] = self["ids"].index(self["current"])

    @property
    def current(self) -> int:
        """Get current zone."""
        return self["current"]

    @current.setter
    def current(self, value: int) -> None:
        """Set current zone property."""
        self["current"] = value

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

    @property
    def ids(self) -> list[int]:
        """Get RTK zone IDs."""
        return self["ids"]

    @ids.setter
    def ids(self, value: list[int]) -> None:
        """Set RTK zone IDs."""
        self["ids"] = value
