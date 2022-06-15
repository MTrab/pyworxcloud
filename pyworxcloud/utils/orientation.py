"""Device orientation."""
import json


class Orientation:
    """Device orientation class."""

    _pitch = 0
    _roll = 0
    _yaw = 0

    def __init__(self, data: list) -> None:
        """Initialize orientation object."""
        if not data:
            return

        self._pitch = data[0]
        self._roll = data[1]
        self._yaw = data[2]

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

    def __repr__(self) -> str:
        return json.dumps(self.to_dict, skipkeys=True)
