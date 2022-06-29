"""Firmware information handler."""
from __future__ import annotations

from typing import Any

from .landroid_class import LDict


class Firmware(LDict):
    """Firmware information handler class."""

    def __init__(self, data: Any) -> None:
        super().__init__()

        self["auto_upgrade"] = data["firmware_auto_upgrade"]
        self["version"] = data["firmware_version"]
