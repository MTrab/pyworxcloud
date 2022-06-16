"""Device orientation."""

from collections import UserDict


class Orientation(UserDict):
    """Device orientation class."""

    def __init__(self, data: list) -> None:
        """Initialize orientation object."""
        super(Orientation, self).__init__()
        if not data:
            return

        self.data["pitch"] = data[0]
        self.data["roll"] = data[1]
        self.data["yaw"] = data[2]
