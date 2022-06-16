"""Device orientation."""

from .landroid_base import DictBase


class Orientation(DictBase):
    """Device orientation class."""

    def __init__(self, data: list) -> None:
        """Initialize orientation object."""
        super(Orientation, self).__init__()
        if not data:
            return

        self.pitch = data[0]
        self.roll = data[1]
        self.yaw = data[2]
