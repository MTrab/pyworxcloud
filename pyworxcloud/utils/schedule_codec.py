"""Normalized schedule models and protocol-specific codecs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..day_map import DAY_MAP

DAY_TO_INDEX = {name: index for index, name in DAY_MAP.items()}
EMPTY_P0_ENTRY = ["00:00", 0, 0]


@dataclass(slots=True)
class ScheduleEntry:
    """Normalized schedule entry."""

    entry_id: str
    day: str
    start: str
    duration: int
    boundary: bool | None
    source: str
    secondary: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScheduleModel:
    """Normalized schedule model."""

    enabled: bool
    time_extension: int | None
    entries: list[ScheduleEntry]
    protocol: int


def _require_day(day: str) -> str:
    if day not in DAY_TO_INDEX:
        raise ValueError(f"day must be one of: {', '.join(DAY_TO_INDEX)}")
    return day


def _require_start(start: str) -> str:
    parts = start.split(":")
    if len(parts) != 2:
        raise ValueError("start must be in HH:MM format")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as err:
        raise ValueError("start must be in HH:MM format") from err
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("start must be in HH:MM format")
    return f"{hour:02d}:{minute:02d}"


def _require_duration(duration: Any) -> int:
    if isinstance(duration, bool):
        raise ValueError("duration must be an integer value")
    try:
        value = int(duration)
    except (TypeError, ValueError) as err:
        raise ValueError("duration must be an integer value") from err
    if value < 0:
        raise ValueError("duration must be greater than or equal to 0")
    return value


def _minutes_from_hhmm(value: str) -> int:
    normalized = _require_start(value)
    hour, minute = normalized.split(":")
    return (int(hour) * 60) + int(minute)


def _hhmm_from_minutes(value: int) -> str:
    if value < 0:
        raise ValueError("minutes must be greater than or equal to 0")
    hour, minute = divmod(value, 60)
    hour = hour % 24
    return f"{hour:02d}:{minute:02d}"


def _ensure_bool_or_none(value: Any, name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean value")
    return value


def _entry_key(entry: ScheduleEntry) -> tuple[int, str, str]:
    return (DAY_TO_INDEX[entry.day], entry.start, entry.entry_id)


def _entry_id_for_protocol_zero(day: str, secondary: bool) -> str:
    return f"p0:{day}:{'secondary' if secondary else 'primary'}"


def _entry_id_for_protocol_one(index: int) -> str:
    return f"p1:{index}"


def _clone_entry(entry: ScheduleEntry) -> ScheduleEntry:
    return ScheduleEntry(
        entry_id=entry.entry_id,
        day=entry.day,
        start=entry.start,
        duration=entry.duration,
        boundary=entry.boundary,
        source=entry.source,
        secondary=entry.secondary,
        metadata=deepcopy(entry.metadata),
    )


def _clone_model(model: ScheduleModel) -> ScheduleModel:
    return ScheduleModel(
        enabled=bool(model.enabled),
        time_extension=model.time_extension,
        entries=[_clone_entry(entry) for entry in model.entries],
        protocol=model.protocol,
    )


def _normalize_protocol_zero_entries(entries: list[ScheduleEntry]) -> list[ScheduleEntry]:
    grouped: dict[str, dict[str, ScheduleEntry]] = {
        day: {} for day in DAY_TO_INDEX
    }
    for entry in entries:
        if entry.duration <= 0:
            continue
        slot_type = "secondary" if entry.secondary else "primary"
        grouped[entry.day][slot_type] = _clone_entry(entry)

    normalized: list[ScheduleEntry] = []
    for day in DAY_TO_INDEX:
        primary = grouped[day].get("primary")
        secondary = grouped[day].get("secondary")
        if primary is None and secondary is not None:
            secondary.secondary = False
            secondary.source = "primary"
            secondary.entry_id = _entry_id_for_protocol_zero(day, False)
            primary = secondary
            secondary = None
        if primary is not None:
            normalized.append(primary)
        if secondary is not None:
            normalized.append(secondary)
    return normalized


def validate_schedule_entry(entry: ScheduleEntry, protocol: int) -> ScheduleEntry:
    """Validate and normalize one schedule entry."""
    if not isinstance(entry, ScheduleEntry):
        raise ValueError("entry must be a ScheduleEntry")

    day = _require_day(entry.day)
    start = _require_start(entry.start)
    duration = _require_duration(entry.duration)
    boundary = _ensure_bool_or_none(entry.boundary, "boundary")
    metadata = deepcopy(entry.metadata)

    if protocol == 0 and boundary is None:
        raise ValueError("boundary must be provided for protocol 0 schedules")

    source = entry.source
    secondary = bool(entry.secondary)
    if protocol == 0:
        if source not in {"primary", "secondary"}:
            raise ValueError("protocol 0 source must be 'primary' or 'secondary'")
        secondary = source == "secondary" or secondary
        source = "secondary" if secondary else "primary"
    else:
        source = "slot"
        secondary = False

    return ScheduleEntry(
        entry_id=entry.entry_id,
        day=day,
        start=start,
        duration=duration,
        boundary=boundary,
        source=source,
        secondary=secondary,
        metadata=metadata,
    )


def validate_schedule_model(model: ScheduleModel) -> ScheduleModel:
    """Validate and normalize a schedule model."""
    if not isinstance(model, ScheduleModel):
        raise ValueError("schedule must be a ScheduleModel")

    normalized_entries = [
        validate_schedule_entry(entry, model.protocol) for entry in model.entries
    ]

    time_extension = model.time_extension
    if model.protocol == 0:
        if time_extension is None:
            time_extension = 0
        if isinstance(time_extension, bool):
            raise ValueError("time_extension must be an integer value")
        time_extension = int(time_extension)
    elif time_extension is not None:
        raise ValueError("time_extension is not supported for protocol 1 schedules")

    if model.protocol == 0:
        by_day_source: set[tuple[str, str]] = set()
        for entry in normalized_entries:
            key = (entry.day, entry.source)
            if key in by_day_source:
                raise ValueError(
                    "protocol 0 schedules support at most one entry per day/source"
                )
            by_day_source.add(key)
        normalized_entries = _normalize_protocol_zero_entries(normalized_entries)

    normalized_entries.sort(key=_entry_key)
    return ScheduleModel(
        enabled=bool(model.enabled),
        time_extension=time_extension,
        entries=normalized_entries,
        protocol=model.protocol,
    )


def schedule_model_from_payload(protocol: int, sc_payload: dict[str, Any] | None) -> ScheduleModel:
    """Create a normalized model from a raw schedule payload."""
    sc_payload = deepcopy(sc_payload) if isinstance(sc_payload, dict) else {}

    if protocol == 0:
        entries: list[ScheduleEntry] = []
        for index, slot in enumerate(sc_payload.get("d", [])):
            if not isinstance(slot, list) or len(slot) < 2:
                continue
            duration = int(slot[1])
            if duration <= 0:
                continue
            day = DAY_MAP[index]
            entries.append(
                ScheduleEntry(
                    entry_id=_entry_id_for_protocol_zero(day, False),
                    day=day,
                    start=_require_start(str(slot[0])),
                    duration=duration,
                    boundary=bool(slot[2]) if len(slot) > 2 else False,
                    source="primary",
                    secondary=False,
                )
            )
        for index, slot in enumerate(sc_payload.get("dd", [])):
            if not isinstance(slot, list) or len(slot) < 2:
                continue
            duration = int(slot[1])
            if duration <= 0:
                continue
            day = DAY_MAP[index]
            entries.append(
                ScheduleEntry(
                    entry_id=_entry_id_for_protocol_zero(day, True),
                    day=day,
                    start=_require_start(str(slot[0])),
                    duration=duration,
                    boundary=bool(slot[2]) if len(slot) > 2 else False,
                    source="secondary",
                    secondary=True,
                )
            )

        return validate_schedule_model(
            ScheduleModel(
                enabled=str(sc_payload.get("m", 0)) in {"1", "2"},
                time_extension=int(sc_payload.get("p", 0)),
                entries=entries,
                protocol=0,
            )
        )

    entries = []
    for index, slot in enumerate(sc_payload.get("slots", [])):
        if not isinstance(slot, dict):
            continue
        day = DAY_MAP.get(int(slot.get("d", 0)), "monday")
        cut_cfg = slot.get("cfg", {}).get("cut", {})
        entries.append(
            ScheduleEntry(
                entry_id=_entry_id_for_protocol_one(index),
                day=day,
                start=_hhmm_from_minutes(int(slot.get("s", 0))),
                duration=int(slot.get("t", 0)),
                boundary=(
                    bool(cut_cfg["b"])
                    if isinstance(cut_cfg, dict) and "b" in cut_cfg
                    else None
                ),
                source="slot",
                secondary=False,
                metadata={"raw_slot": deepcopy(slot)},
            )
        )

    return validate_schedule_model(
        ScheduleModel(
            enabled=str(sc_payload.get("enabled", 0)) == "1",
            time_extension=None,
            entries=entries,
            protocol=1,
        )
    )


def schedule_payload_from_model(
    model: ScheduleModel, current_payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Serialize a normalized model into a protocol-specific payload."""
    model = validate_schedule_model(model)
    current_payload = deepcopy(current_payload) if isinstance(current_payload, dict) else {}

    if model.protocol == 0:
        payload = {}
        for key in ("distm", "ots"):
            if key in current_payload:
                payload[key] = deepcopy(current_payload[key])

        current_mode = str(current_payload.get("m", 0))
        payload["m"] = 2 if model.enabled and current_mode == "2" else (1 if model.enabled else 0)
        payload["p"] = int(model.time_extension or 0)
        primary = [deepcopy(EMPTY_P0_ENTRY) for _ in range(7)]
        secondary = [deepcopy(EMPTY_P0_ENTRY) for _ in range(7)]

        for entry in model.entries:
            target = secondary if entry.secondary else primary
            target[DAY_TO_INDEX[entry.day]] = [
                entry.start,
                entry.duration,
                1 if bool(entry.boundary) else 0,
            ]

        payload["d"] = primary
        has_secondary = any(entry.secondary for entry in model.entries)
        if has_secondary or "dd" in current_payload:
            payload["dd"] = secondary
        return payload

    payload = {}
    for key, value in current_payload.items():
        if key not in {"enabled", "slots"}:
            payload[key] = deepcopy(value)
    payload["enabled"] = 1 if model.enabled else 0
    slots: list[dict[str, Any]] = []
    for entry in model.entries:
        raw_slot = deepcopy(entry.metadata.get("raw_slot", {}))
        slot = raw_slot if isinstance(raw_slot, dict) else {}
        slot["e"] = int(slot.get("e", 1))
        slot["d"] = DAY_TO_INDEX[entry.day]
        slot["s"] = _minutes_from_hhmm(entry.start)
        slot["t"] = entry.duration

        cfg = slot.get("cfg")
        if not isinstance(cfg, dict):
            cfg = {}
        cut = cfg.get("cut")
        if not isinstance(cut, dict):
            cut = {}
        if entry.boundary is not None:
            cut["b"] = int(entry.boundary)
        elif "b" in cut:
            del cut["b"]
        cut.setdefault("z", [])
        cfg["cut"] = cut
        slot["cfg"] = cfg
        slots.append(slot)
    payload["slots"] = slots
    return payload


def add_schedule_entry(model: ScheduleModel, entry: ScheduleEntry) -> ScheduleModel:
    """Return a model with one additional entry."""
    model = validate_schedule_model(model)
    entry = validate_schedule_entry(entry, model.protocol)

    if model.protocol == 0:
        if entry.secondary and not any(
            existing.day == entry.day and not existing.secondary for existing in model.entries
        ):
            entry.secondary = False
            entry.source = "primary"
            entry.entry_id = _entry_id_for_protocol_zero(entry.day, False)
        for existing in model.entries:
            if existing.day == entry.day and existing.source == entry.source:
                raise ValueError("schedule entry already exists for the requested day/source")
        if not entry.entry_id:
            entry.entry_id = _entry_id_for_protocol_zero(entry.day, entry.secondary)
    else:
        if not entry.entry_id:
            entry.entry_id = _entry_id_for_protocol_one(len(model.entries))

    updated = _clone_model(model)
    updated.entries.append(entry)
    return validate_schedule_model(updated)


def update_schedule_entry(
    model: ScheduleModel, entry_id: str, entry: ScheduleEntry
) -> ScheduleModel:
    """Return a model with one updated entry."""
    model = validate_schedule_model(model)
    updated_entry = validate_schedule_entry(entry, model.protocol)

    target_index = next(
        (index for index, existing in enumerate(model.entries) if existing.entry_id == entry_id),
        None,
    )
    if target_index is None:
        raise ValueError(f"schedule entry '{entry_id}' was not found")

    current_entry = model.entries[target_index]
    if model.protocol == 0:
        updated_entry.entry_id = _entry_id_for_protocol_zero(
            updated_entry.day,
            updated_entry.secondary,
        )
        for index, existing in enumerate(model.entries):
            if index == target_index:
                continue
            if existing.day == updated_entry.day and existing.source == updated_entry.source:
                raise ValueError("schedule entry already exists for the requested day/source")
    else:
        merged_metadata = deepcopy(current_entry.metadata)
        merged_metadata.update(deepcopy(updated_entry.metadata))
        updated_entry.metadata = merged_metadata
        updated_entry.entry_id = current_entry.entry_id

    updated = _clone_model(model)
    updated.entries[target_index] = updated_entry
    return validate_schedule_model(updated)


def delete_schedule_entry(model: ScheduleModel, entry_id: str) -> ScheduleModel:
    """Return a model with one entry deleted."""
    model = validate_schedule_model(model)
    target = next((entry for entry in model.entries if entry.entry_id == entry_id), None)
    if target is None:
        raise ValueError(f"schedule entry '{entry_id}' was not found")

    if model.protocol == 0:
        updated_entries = [
            _clone_entry(entry)
            for entry in model.entries
            if entry.entry_id != entry_id
        ]
        if not target.secondary:
            secondary = next(
                (
                    entry
                    for entry in updated_entries
                    if entry.day == target.day and entry.secondary
                ),
                None,
            )
            if secondary is not None:
                secondary.secondary = False
                secondary.source = "primary"
                secondary.entry_id = _entry_id_for_protocol_zero(secondary.day, False)
        updated = ScheduleModel(
            enabled=model.enabled,
            time_extension=model.time_extension,
            entries=updated_entries,
            protocol=model.protocol,
        )
        return validate_schedule_model(updated)

    updated = ScheduleModel(
        enabled=model.enabled,
        time_extension=model.time_extension,
        entries=[
            _clone_entry(entry) for entry in model.entries if entry.entry_id != entry_id
        ],
        protocol=model.protocol,
    )
    return validate_schedule_model(updated)
