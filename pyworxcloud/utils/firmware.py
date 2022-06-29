"""Firmware information handler."""
from __future__ import annotations

from typing import Any

from ..const import CONST_UNKNOWN
from .landroid_class import LDict


class Firmware(LDict):
    """Firmware information handler class."""

    def __init__(self, data: Any) -> None:
        super().__init__()

        self["auto_upgrade"] = (
            data["firmware_auto_upgrade"]
            if "firmware_auto_upgrade" in data
            else CONST_UNKNOWN
        )
        self["version"] = (
            data["firmware_version"] if "firmware_version" in data else CONST_UNKNOWN
        )
