"""Defines schedule handling and progress helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..day_map import DAY_MAP
from .landroid_class import LDict


class ScheduleInfo:
    """Provide slot-based progress calculations."""

    def __init__(self, schedule: Schedule, tz: str | None = None) -> None:
        self.__schedule = schedule
        now = datetime.now()
        timezone_info = self._resolve_timezone(tz)
        self._tz = tz
        self.__now = now.astimezone(timezone_info)
        self.__slots = schedule.get("slots", []) or []

    @staticmethod
    def _resolve_timezone(tz: str | None) -> datetime.tzinfo:
        if tz is None:
            return timezone.utc
        try:
            return ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            return timezone.utc

    def _slots_for_date(self, date: datetime) -> list[dict[str, Any]]:
        day = DAY_MAP[int(date.strftime("%w"))]
        slots = [slot for slot in self.__slots if slot.get("day") == day]
        return sorted(slots, key=lambda slot: slot.get("start", "00:00"))

    def _slot_datetimes(
        self, slot: dict[str, Any], date: datetime
    ) -> tuple[datetime, datetime]:
        from ..helpers.time_format import string_to_time

        day_string = date.strftime("%d/%m/%Y")
        start = string_to_time(f"{day_string} {slot['start']}:00", self._tz)
        end = string_to_time(f"{day_string} {slot['end']}:00", self._tz)
        return start, end

    def calculate_progress(self) -> int:
        """Return the percentage of the day already covered by slots."""
        slots = self._slots_for_date(self.__now)
        total_run = sum(slot.get("duration_extended", 0) for slot in slots)
        if total_run == 0:
            return 100

        has_run = 0.0
        for slot in slots:
            start, end = self._slot_datetimes(slot, self.__now)
            if self.__now >= end:
                has_run += slot.get("duration_extended", 0)
            elif self.__now > start:
                elapsed = (self.__now - start).total_seconds() / 60
                has_run += min(elapsed, slot.get("duration_extended", 0))

        pct = (has_run / total_run) * 100
        return int(round(min(pct, 100)))

    def next_schedule(self) -> str | None:
        """Return the wall-clock of the next slot start."""
        candidates: list[datetime] = []
        for offset in range(0, 14):
            target_date = self.__now + timedelta(days=offset)
            slots = self._slots_for_date(target_date)
            for slot in slots:
                start, _ = self._slot_datetimes(slot, target_date)
                if offset == 0 and start <= self.__now:
                    continue
                candidates.append(start)

        if not candidates:
            return None

        next_slot = min(candidates)
        return next_slot.strftime("%Y-%m-%d %H:%M:%S")


class Schedule(LDict):
    """Represents an aggregate schedule snapshot."""

    def __init__(self, data: Any | None = None) -> None:
        super().__init__()
        self["daily_progress"] = None
        self["next_schedule_start"] = None
        self["time_extension"] = 0
        self["active"] = True
        self["slots"] = []
        self["party_mode_enabled"] = False
        self["pause_mode_enabled"] = False
        self["one_time_schedule"] = False
        self["auto_schedule"] = self._normalize_auto_schedule(data)

    def update_progress_and_next(self, tz: str | None = None) -> None:
        info = ScheduleInfo(self, tz)
        self["daily_progress"] = info.calculate_progress()
        self["next_schedule_start"] = info.next_schedule()

    @staticmethod
    def _normalize_auto_schedule(data: Any | None) -> dict[str, Any]:
        """Normalize auto-schedule settings to a stable read-side structure."""
        raw_settings = (
            data.get("auto_schedule_settings", {})
            if isinstance(data, dict)
            else {}
        )
        settings = raw_settings if isinstance(raw_settings, dict) else {}
        exclusion = settings.get("exclusion_scheduler", {})
        exclusion_scheduler = (
            exclusion if isinstance(exclusion, dict) else {}
        )
        raw_days = exclusion_scheduler.get("days", [])
        days = raw_days if isinstance(raw_days, list) else []

        normalized_days = [
            Schedule._normalize_auto_schedule_day(day)
            for day in days[:7]
        ]
        while len(normalized_days) < 7:
            normalized_days.append(Schedule._normalize_auto_schedule_day({}))

        nutrition = settings.get("nutrition")
        normalized_nutrition = (
            Schedule._normalize_auto_schedule_nutrition(nutrition)
            if isinstance(nutrition, dict)
            else nutrition
        )

        return {
            "enabled": (
                bool(data.get("auto_schedule", False))
                if isinstance(data, dict)
                else False
            ),
            "settings": {
                "boost": settings.get("boost"),
                "grass_type": settings.get("grass_type"),
                "soil_type": settings.get("soil_type"),
                "irrigation": settings.get("irrigation"),
                "nutrition": normalized_nutrition,
                "exclusion_scheduler": {
                    "exclude_nights": bool(
                        exclusion_scheduler.get("exclude_nights", False)
                    ),
                    "days": normalized_days,
                },
            },
        }

    @staticmethod
    def _normalize_auto_schedule_day(day: Any) -> dict[str, Any]:
        """Normalize one auto-schedule exclusion day entry."""
        day_entry = day if isinstance(day, dict) else {}
        raw_slots = day_entry.get("slots", [])
        slots = raw_slots if isinstance(raw_slots, list) else []
        return {
            "exclude_day": bool(day_entry.get("exclude_day", False)),
            "slots": [
                Schedule._normalize_auto_schedule_slot(slot)
                for slot in slots
                if isinstance(slot, dict)
            ],
        }

    @staticmethod
    def _normalize_auto_schedule_slot(slot: dict[str, Any]) -> dict[str, Any]:
        """Normalize one auto-schedule exclusion slot entry."""
        return {
            "start_time": slot.get("start_time"),
            "duration": slot.get("duration"),
            "reason": slot.get("reason"),
        }

    @staticmethod
    def _normalize_auto_schedule_nutrition(
        nutrition: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize NPK nutrition settings when present."""
        return {
            "n": nutrition.get("n"),
            "p": nutrition.get("p"),
            "k": nutrition.get("k"),
        }
