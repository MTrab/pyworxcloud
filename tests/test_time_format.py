"""Tests for timestamp normalization helpers."""

from __future__ import annotations

from pyworxcloud.helpers.time_format import convert_to_time


def test_convert_to_time_tolerates_callback_mutating_current_dict() -> None:
    """Mutating callbacks should not raise while iterating nested payloads."""
    payload = {
        "cfg": {
            "updated": "2026-03-18 12:00:00",
        }
    }

    def _callback(_device, _parent, key, value) -> None:
        payload["cfg"][key] = value
        payload["cfg"]["seen"] = True

    convert_to_time("device", payload, callback=_callback)

    assert payload["cfg"]["seen"] is True
