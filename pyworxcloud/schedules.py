"""Defines schedule classes."""
from __future__ import annotations

import calendar
from collections import UserDict
from enum import IntEnum


class ScheduleType(IntEnum):
    """Schedule types."""

    PRIMARY = 0
    SECONDARY = 1


TYPE_TO_STRING = {ScheduleType.PRIMARY: "primary", ScheduleType.SECONDARY: "secondary"}


class WeekdaySettings(UserDict):
    """Class representing a weekday setting."""

    def __init__(
        self,
        start: str = "00:00",
        end: str = "00:00",
        duration: int = 0,
        boundary: bool = False,
    ):
        """Initialize the settings."""
        super(WeekdaySettings, self).__init__()
        self.data["start"] = start
        self.data["end"] = end
        self.data["duration"] = duration
        self.data["boundary"] = boundary


class Schedule(UserDict):
    """Represents a schedule."""

    def __init__(self, schedule_type: ScheduleType):
        """Initialize an empty schedule.

        Args:
            schedule_type (ScheduleType): Which ScheduleType to initialize.
        """
        super(Schedule, self).__init__()

        self.data["type"] = schedule_type
        self.data["days"] = {}

        for day in list(calendar.day_name):
            self.data["days"].update({day.lower(): WeekdaySettings()})
