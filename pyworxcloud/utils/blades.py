"""Blade information."""


class Blades(dict):
    """Blade information."""

    total_on: int | None = None  # Total runtime with blades on in minutes
    distance: int | None = None  # Total distance in meters
    worktime: int | None = None  # Total worktime in minutes
    current_on: int | None = None  # Blade time since last reset

    def __init__(self, data: list = None) -> None:
        """Initialize blade object."""
        super(Blades, self).__init__()
        if not data:
            return

        self.total_on = data["b"] if "b" in data else None
        self.distance = data["d"] if "d" in data else None
        self.worktime = data["wt"] if "wt" in data else None
        self.current_on = data["bl"] if "bl" in data else None

    def __repr__(self) -> str:
        return repr(self.__dict__)
