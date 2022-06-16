"""Zone representation."""


from .landroid_base import DictBase


class Zone(DictBase):
    """Class for handling zone data."""

    def __init__(self):
        """Initialize zone object."""
        super(Zone, self).__init__()
        self.__current: int | None = None
        self.__index: int | None = None
        self.__indicies: list = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.__start: list = [0, 0, 0, 0]

    @property
    def __dict__(self):
        """Custom dict creation."""
        out = {
            "current": self.__current,
            "index": self.__index,
            "indicies": self.__indicies,
            "starting_point": self.__start,
        }
        return out

    @property
    def current(self) -> int:
        """Get current zone."""
        return self.__current

    @current.setter
    def current(self, value: int) -> None:
        """Set current zone property."""
        self.__current = value

    @property
    def index(self) -> int:
        """Get current index."""
        return self.__index

    @index.setter
    def index(self, value: int) -> None:
        """Set current index property."""
        self.__index = value

    @property
    def indicies(self) -> int:
        """Get indicies."""
        return self.__indicies

    @indicies.setter
    def indicies(self, value: list) -> None:
        """Set indicies property."""
        self.__indicies = value

    @property
    def starting_point(self) -> int:
        """Get starting points."""
        return self.__start

    @starting_point.setter
    def starting_point(self, value: int) -> None:
        """Set starting points."""
        self.__start = value
