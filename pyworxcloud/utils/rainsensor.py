"""Rain sensor information."""
from .landroid_class import LDict


class Rainsensor(LDict):
    """Rain sensor definition."""

    def __init__(self):
        """Initialize rain sensor object."""
        super().__init__()

        self["delay"] = 0

    @property
    def delay(self):
        """Return rain delay."""
        return self["delay"]

    @delay.setter
    def delay(self, raindelay: int):
        """Set rain delay information."""
        self["delay"] = raindelay

    @property
    def triggered(self):
        """Return rain sensor trigger state."""
        return self["triggered"]

    @triggered.setter
    def triggered(self, triggered: bool):
        """Set rain sensor trigger state."""
        self["triggered"] = triggered

    @property
    def remaining(self):
        """Return remaining rain delay."""
        return self["remaining"]

    @remaining.setter
    def remaining(self, remaining: int):
        """Set remaining rain delay information."""
        self["remaining"] = remaining
