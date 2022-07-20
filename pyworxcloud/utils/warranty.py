"""Warranty information handler."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .landroid_class import LDict


class Warranty(LDict):
    """Class for handling warranty information."""

    def __init__(self, data: Any) -> None:
        from ..helpers.time_format import string_to_time

        super().__init__()

        self["expires_at"] = string_to_time(
            data["warranty_expires_at"], data["time_zone"]
        )
        self["registered"] = data["warranty_registered"]
        self["expired"] = (
            bool(self["expires_at"] < datetime.now().astimezone())
            if not isinstance(self["expires_at"], type(None))
            else None
        )
