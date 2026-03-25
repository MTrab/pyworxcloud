"""Tests for normalized schedule codec helpers."""

from __future__ import annotations

import warnings

from pyworxcloud.exceptions import NoPauseModeError
from pyworxcloud.utils.capability import DeviceCapability
from pyworxcloud.utils.schedule_codec import (
    ScheduleEntry,
    add_schedule_entry,
    delete_schedule_entry,
    schedule_model_from_payload,
    schedule_payload_from_model,
    update_schedule_entry,
)


def test_protocol0_roundtrip_preserves_primary_and_secondary() -> None:
    """Protocol 0 should roundtrip legacy d/dd arrays through the normalized model."""
    payload = {
        "m": 1,
        "p": 20,
        "distm": 0,
        "ots": {"bc": 0, "wtm": 0},
        "d": [
            ["09:00", 30, 1],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
        ],
        "dd": [
            ["12:00", 20, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
        ],
    }

    model = schedule_model_from_payload(0, payload)
    encoded = schedule_payload_from_model(model, payload)

    assert encoded == payload


def test_protocol0_delete_primary_promotes_secondary() -> None:
    """Deleting a primary entry should promote same-day secondary to primary."""
    model = schedule_model_from_payload(
        0,
        {
            "m": 1,
            "p": 0,
            "d": [
                ["09:00", 30, 1],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
            ],
            "dd": [
                ["12:00", 20, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
            ],
        },
    )

    updated = delete_schedule_entry(model, "p0:sunday:primary")
    encoded = schedule_payload_from_model(updated, {"dd": [None] * 7})

    assert encoded["d"][0] == ["12:00", 20, 0]
    assert encoded["dd"][0] == ["00:00", 0, 0]


def test_protocol0_add_existing_day_source_fails() -> None:
    """Protocol 0 cannot add two entries for the same day/source."""
    model = schedule_model_from_payload(
        0,
        {
            "m": 1,
            "p": 0,
            "d": [
                ["09:00", 30, 1],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
                ["00:00", 0, 0],
            ],
        },
    )

    try:
        add_schedule_entry(
            model,
            ScheduleEntry(
                entry_id="",
                day="sunday",
                start="10:00",
                duration=15,
                boundary=False,
                source="primary",
                secondary=False,
            ),
        )
    except ValueError as err:
        assert "already exists" in str(err)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for duplicate protocol 0 source")


def test_protocol1_roundtrip_preserves_freq() -> None:
    """Protocol 1 should keep unknown top-level schedule fields such as freq."""
    payload = {
        "enabled": 1,
        "paused": 0,
        "freq": 0,
        "slots": [
            {"e": 1, "d": 1, "s": 600, "t": 120, "cfg": {"cut": {"b": 0, "z": [1]}}}
        ],
    }

    model = schedule_model_from_payload(1, payload)
    encoded = schedule_payload_from_model(model, payload)

    assert encoded == payload


def test_protocol1_update_preserves_slot_metadata() -> None:
    """Protocol 1 updates should preserve raw slot metadata such as zones and ob."""
    payload = {
        "enabled": 1,
        "paused": 0,
        "slots": [
            {
                "e": 1,
                "d": 1,
                "s": 600,
                "t": 120,
                "cfg": {"cut": {"b": 0, "ob": 1, "z": [1, 2]}},
            }
        ],
    }

    model = schedule_model_from_payload(1, payload)
    updated = update_schedule_entry(
        model,
        "p1:0",
        ScheduleEntry(
            entry_id="ignored",
            day="monday",
            start="11:30",
            duration=45,
            boundary=True,
            source="slot",
            secondary=False,
        ),
    )
    encoded = schedule_payload_from_model(updated, payload)

    assert encoded["slots"][0]["s"] == 690
    assert encoded["slots"][0]["t"] == 45
    assert encoded["slots"][0]["cfg"]["cut"]["b"] == 1
    assert encoded["slots"][0]["cfg"]["cut"]["ob"] == 1
    assert encoded["slots"][0]["cfg"]["cut"]["z"] == [1, 2]


def test_protocol1_delete_removes_slot() -> None:
    """Deleting a protocol 1 entry should physically remove the slot."""
    model = schedule_model_from_payload(
        1,
        {
            "enabled": 1,
            "slots": [
                {"e": 1, "d": 1, "s": 600, "t": 120, "cfg": {"cut": {"z": [1]}}},
                {"e": 1, "d": 2, "s": 700, "t": 60, "cfg": {"cut": {"z": [1]}}},
            ],
        },
    )

    updated = delete_schedule_entry(model, "p1:0")
    encoded = schedule_payload_from_model(updated, {"enabled": 1, "slots": []})

    assert len(updated.entries) == 1
    assert len(encoded["slots"]) == 1
    assert encoded["slots"][0]["d"] == 2


def test_protocol0_delete_preserves_party_mode() -> None:
    """Deleting a protocol 0 entry should not disable party mode."""
    payload = {
        "m": 2,
        "p": 0,
        "d": [
            ["09:00", 60, 0],
            ["10:00", 45, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
            ["00:00", 0, 0],
        ],
    }

    model = schedule_model_from_payload(0, payload)
    updated = delete_schedule_entry(model, "p0:sunday:primary")
    encoded = schedule_payload_from_model(updated, payload)

    assert len(updated.entries) == 1
    assert encoded["m"] == 2


def test_protocol1_set_schedule_preserves_enabled_state() -> None:
    """Schedule serialization should not change protocol 1 enabled state."""
    payload = {
        "enabled": 1,
        "paused": 0,
        "slots": [
            {"e": 1, "d": 1, "s": 600, "t": 120, "cfg": {"cut": {"z": [1]}}},
        ],
    }

    model = schedule_model_from_payload(1, payload)
    model.enabled = False
    encoded = schedule_payload_from_model(model, payload)

    assert encoded["enabled"] == 1


def test_deprecated_pause_mode_error_warns() -> None:
    """The deprecated exception alias should emit a warning."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        err = NoPauseModeError("deprecated")

    assert str(err) == "deprecated"
    assert any(
        "NoPauseModeError is deprecated" in str(item.message) for item in captured
    )


def test_deprecated_pause_mode_capability_warns() -> None:
    """The deprecated enum alias should emit a warning."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        capability = DeviceCapability.PAUSE_MODE

    assert capability is DeviceCapability.PARTY_MODE
    assert any(
        "DeviceCapability.PAUSE_MODE is deprecated" in str(item.message)
        for item in captured
    )
