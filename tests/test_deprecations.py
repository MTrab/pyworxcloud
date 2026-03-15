"""Tests for the deprecation registry."""

from __future__ import annotations

from datetime import date

from pyworxcloud.deprecations import DEPRECATIONS


def test_deprecation_removal_dates_are_still_in_the_future() -> None:
    """Fail once planned removals become due so they are not forgotten."""
    today = date.today()
    due = [entry.old_name for entry in DEPRECATIONS if entry.remove_after <= today]
    assert not due, (
        "Deprecated compatibility aliases are due for removal based on date: "
        + ", ".join(due)
    )


def test_deprecation_registry_uses_date_objects() -> None:
    """Keep the registry machine-readable for CI reminders."""
    for entry in DEPRECATIONS:
        assert isinstance(entry.remove_after, date)
