"""Handling lawn parameters."""
from __future__ import annotations

from .landroid_class import LDict


class Lawn(LDict):
    """Handler for lawn parameters."""

    def __init__(self, perimeter, size) -> None:
        super().__init__()

        self["perimeter"] = perimeter
        self["size"] = size
