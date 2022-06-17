"""Defines schedule classes."""
from __future__ import annotations

import calendar
from enum import IntEnum

from .landroid_class import LDict


class ScheduleType(IntEnum):
    """Schedule types."""

    PRIMARY = 0
    SECONDARY = 1


TYPE_TO_STRING = {ScheduleType.PRIMARY: "primary", ScheduleType.SECONDARY: "secondary"}


class WeekdaySettings(LDict):
    """Class representing a weekday setting."""

    def __init__(
        self,
        start: str = "00:00",
        end: str = "00:00",
        duration: int = 0,
        boundary: bool = False,
    ) -> None:
        """Initialize the settings."""
        super().__init__()
        self["start"] = start
        self["end"] = end
        self["duration"] = duration
        self["boundary"] = boundary


class Schedule(LDict):
    """Represents a schedule."""

    def __init__(
        self, schedule_type: ScheduleType, variation: int = 0, active: bool = True
    ) -> None:
        """Initialize an empty primary or secondary schedule.

        Args:
            schedule_type (ScheduleType): Which ScheduleType to initialize.
        """
        super().__init__()

        self["time_extension"] = variation
        self["active"] = active
        self["type"] = schedule_type
        self["days"] = {}

        for day in list(calendar.day_name):
            self["days"].update({day.lower(): WeekdaySettings()})
