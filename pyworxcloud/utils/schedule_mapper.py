"""Helpers for parsing schedule payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..day_map import DAY_MAP


def _minutes_to_time(minutes: int) -> str:
    base = datetime.strptime("00:00", "%H:%M")
    return (base + timedelta(minutes=minutes)).strftime("%H:%M")


def _apply_time_extension(duration: int, time_extension: int) -> int:
    return int(duration * (1 + (time_extension / 100)))


@dataclass
class ScheduleSlot:
    """Single schedule slot used for protocol analysis."""

    day: str
    start: str
    duration: int
    boundary: bool | None
    source: str
    duration_extended: int
    end: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "duration_extended": self.duration_extended,
            "boundary": self.boundary,
            "source": self.source,
        }


@dataclass
class ScheduleParseResult:
    """Normalized schedule output used by DeviceHandler."""

    slots: list[ScheduleSlot]
    pause_mode_enabled: bool
    active: bool
    time_extension: int
    one_time_schedule: bool


class ScheduleParser:
    """Parse Worx schedule payloads for multiple protocols."""

    def __init__(self, payload: dict[str, Any], protocol: int):
        self._payload = payload
        self._protocol = protocol
        self._slots: list[ScheduleSlot] = []

    def parse(self) -> ScheduleParseResult:
        sc = self._payload
        time_extension = int(sc.get("p", 0))
        one_time = "ots" in sc or "once" in sc
        pause_mode_enabled = bool(
            str(sc.get("m")) == "2" or str(sc.get("enabled")) == "0"
        )
        active = bool(
            (self._protocol == 0 and str(sc.get("m")) in {"1", "2"})
            or (self._protocol != 0 and str(sc.get("enabled")) == "0")
        )

        if self._protocol == 0:
            self._parse_protocol_zero(sc, time_extension)
        else:
            self._parse_protocol_one(sc, time_extension)

        if "dd" in sc:
            self._parse_secondary(sc["dd"], time_extension)

        return ScheduleParseResult(
            slots=self._slots,
            pause_mode_enabled=pause_mode_enabled,
            active=active,
            time_extension=time_extension,
            one_time_schedule=one_time,
        )

    def _parse_protocol_zero(self, sc: dict[str, Any], time_extension: int) -> None:
        for index, slot in enumerate(sc.get("d", [])):
            day_name = DAY_MAP[index]
            start = slot[0]
            duration = int(slot[1])
            boundary = bool(slot[2]) if len(slot) > 2 else False
            self._slots.append(
                self._build_slot(
                    day_name,
                    start,
                    duration,
                    boundary,
                    "protocol0",
                    time_extension,
                )
            )

    def _parse_protocol_one(self, sc: dict[str, Any], time_extension: int) -> None:
        for slot in sc.get("slots", []):
            day_index = slot.get("d", 0)
            day_name = DAY_MAP.get(day_index, "monday")
            start = _minutes_to_time(slot.get("s", 0))
            duration = int(slot.get("t", 0))
            cfg_cut = slot.get("cfg", {}).get("cut", {})
            boundary = bool(cfg_cut["b"]) if "b" in cfg_cut else None
            self._slots.append(
                self._build_slot(
                    day_name,
                    start,
                    duration,
                    boundary,
                    "protocol1",
                    time_extension,
                )
            )

    def _parse_secondary(self, dd_payload: Any, time_extension: int) -> None:
        for index, entry in enumerate(
            dd_payload if isinstance(dd_payload, list) else []
        ):
            day_name = DAY_MAP.get(index)
            if day_name is None:
                continue
            start = entry[0]
            duration = int(entry[1])
            boundary = bool(entry[2]) if len(entry) > 2 else False
            self._slots.append(
                self._build_slot(
                    day_name,
                    start,
                    duration,
                    boundary,
                    "secondary",
                    time_extension,
                )
            )

    @staticmethod
    def _build_slot(
        day_name: str,
        start: str,
        duration: int,
        boundary: bool | None,
        source: str,
        time_extension: int,
    ) -> ScheduleSlot:
        duration_extended = int(_apply_time_extension(duration, time_extension))
        start_dt = datetime.strptime(start, "%H:%M")
        end_dt = start_dt + timedelta(minutes=duration_extended)
        return ScheduleSlot(
            day=day_name,
            start=start,
            duration=duration,
            boundary=boundary,
            source=source,
            duration_extended=duration_extended,
            end=end_dt.strftime("%H:%M"),
        )
