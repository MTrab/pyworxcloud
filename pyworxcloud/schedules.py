"""Defines schedule classes."""
from __future__ import annotations

import calendar
from enum import IntEnum


class ScheduleType(IntEnum):
    """Schedule types."""

    PRIMARY = 0
    SECONDARY = 1


TYPE_TO_STRING = {ScheduleType.PRIMARY: "primary", ScheduleType.SECONDARY: "secondary"}


class Weekday:
    """Class representing a weekday."""

    def __init__(self, weekday: str) -> None:
        """Initialize a weekday.

        Args:
            weekday (str): Name of the weekday.
        """
        self._name = weekday.lower()
        self._start = None
        self._end = None
        self._duration = None
        self._boundary = False

    @property
    def todict(self) -> dict:
        """Return the weekday as a dictionary.

        Returns:
            dict: Dictionary containing the weekday.
        """
        day = {
            "name": self._name,
            "settings": {
                "start": self._start,
                "end": self._end,
                "duration": self._duration,
                "boundary": self._boundary,
            },
        }
        return day

    @property
    def name(self) -> str:
        """Returns the weekday name."""
        return self._name

    @property
    def start(self) -> str:
        """Returns the start time."""
        return self._start

    @property
    def end(self) -> str:
        """Returns the end time."""
        return self._end

    @property
    def duration(self) -> int:
        """Returns the duration."""
        return self._duration

    @property
    def boundary(self) -> bool:
        """Returns a bool representating if the device should start the day with doing boundary / edge cut."""
        return self._boundary


class Schedule:
    """Represents a schedule."""

    def __init__(self, schedule_type: ScheduleType):
        """Initialize an empty schedule.

        Args:
            schedule_type (ScheduleType): Which ScheduleType to initialize.
        """
        self.type = schedule_type
        self.weekdays = {}

        for day in list(calendar.day_name):
            newday = Weekday(day).todict
            self.weekdays[newday["name"]] = newday["settings"]

    @property
    def todict(self) -> dict:
        """Return the schedule as a dictionary.

        Returns:
            dict: Dictionary containing the weekday.
        """
        val = {"type": self.type, "days": self.weekdays}
        return val
