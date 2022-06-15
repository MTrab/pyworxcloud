"""Blade information."""
import json


class Blades:
    """Blade information."""

    _total_on: int | None = None  # Total runtime with blades on in minutes
    _distance: int | None = None  # Total distance in meters
    _worktime: int | None = None  # Total worktime in minutes
    _current: int | None = None  # Blade time since last reset

    def __init__(self, data: list = None) -> None:
        """Initialize blade object."""
        if not data:
            return

        self._total_on = data["b"] if "b" in data else None
        self._distance = data["d"] if "d" in data else None
        self._worktime = data["wt"] if "wt" in data else None
        self._current = data["bl"] if "bl" in data else None

    @property
    def to_list(self) -> list:
        """Return object as a list.

        0: Total on
        1: Distance
        2: Worktime
        3: Current on
        """
        return [
            self._total_on,
            self._distance,
            self._worktime,
            self._current,
        ]

    @property
    def to_dict(self) -> dict:
        """Return object as a dict."""
        return {
            "total_on": self._total_on,
            "distance": self._distance,
            "worktime": self._worktime,
            "current_on": self._current,
        }

    def __repr__(self) -> str:
        return json.dumps(self.to_dict, skipkeys=True)
