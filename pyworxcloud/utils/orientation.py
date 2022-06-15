"""Device orientation."""


class Orientation(dict):
    """Device orientation class."""

    pitch = 0
    roll = 0
    yaw = 0

    def __init__(self, data: list) -> None:
        """Initialize orientation object."""
        super(Orientation, self).__init__()
        if not data:
            return

        self.pitch = data[0]
        self.roll = data[1]
        self.yaw = data[2]

    def __repr__(self) -> str:
        return repr(self.__dict__)
