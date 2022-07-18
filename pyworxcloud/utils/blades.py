"""Blade information."""
from __future__ import annotations

from typing import Any

from .landroid_class import LDict


class Blades(LDict):
    """Blade information."""

    def __init__(
        self,
        data: Any | None = None,
    ) -> None:
        """Initialize blade object."""
        super().__init__()
        from ..helpers import string_to_time

        if isinstance(data, type(None)):
            return

        if "blade_work_time" in data:
            # Total time with blades on in minutes
            self["total_on"] = (
                int(data["blade_work_time"])
                if not isinstance(data["blade_work_time_reset"], type(None))
                else None
            )
        else:
            self["total_on"] = None

        if "blade_work_time_reset" in data:
            # Blade time reset at minutes
            self["reset_at"] = (
                int(data["blade_work_time_reset"])
                if not isinstance(data["blade_work_time_reset"], type(None))
                else None
            )
        else:
            self["reset_at"] = None

        if "blade_work_time_reset_at" in data:
            # Blade time reset time and date
            self["reset_time"] = (
                string_to_time(data["blade_work_time_reset_at"], data["time_zone"])
                if not isinstance(data["blade_work_time_reset_at"], type(None))
                else None
            )
        else:
            self["reset_time"] = None

        self._calculate_current_on()

    def set_data(self, indata: list):
        """Update data on existing dataset."""
        if "b" in indata:
            self["total_on"] = indata["b"]

        self._calculate_current_on()

    def _calculate_current_on(self) -> None:
        """Calculate current_on attribute."""

        # Calculate blade data since reset, if possible
        if self["reset_at"] and self["total_on"]:
            # Blade time since last reset
            self["current_on"] = int(self["total_on"] - self["reset_at"])
        else:
            self["current_on"] = self["total_on"]
