"""Rain sensor information."""
from __future__ import annotations

from .landroid_class import LDict


class Rainsensor(LDict):
    """Rain sensor definition."""

    def __init__(self) -> dict:
        """Initialize rain sensor object."""
        super().__init__()

        self["delay"] = 0

    @property
    def delay(self) -> int:
        """Return rain delay."""
        return self["delay"]

    @delay.setter
    def delay(self, raindelay: int) -> None:
        """Set rain delay information."""
        self["delay"] = raindelay

    @property
    def triggered(self) -> bool:
        """Return rain sensor trigger state."""
        return self["triggered"]

    @triggered.setter
    def triggered(self, triggered: bool) -> None:
        """Set rain sensor trigger state."""
        self["triggered"] = triggered

    @property
    def remaining(self) -> int:
        """Return remaining rain delay."""
        return self["remaining"]

    @remaining.setter
    def remaining(self, remaining: int) -> None:
        """Set remaining rain delay information."""
        self["remaining"] = remaining
