"""Tests for the deprecation registry."""

from __future__ import annotations

import warnings
from datetime import date

from pyworxcloud.deprecations import DEPRECATIONS


def test_deprecation_removal_dates_emit_reminders() -> None:
    """Remind maintainers about due removals without breaking patch releases."""
    today = date.today()
    due = [entry.old_name for entry in DEPRECATIONS if entry.remove_after <= today]
    if due:
        warnings.warn(
            "Deprecated compatibility aliases are eligible for removal in a future "
            "major release: " + ", ".join(due),
            UserWarning,
            stacklevel=1,
        )


def test_deprecation_registry_uses_date_objects() -> None:
    """Keep the registry machine-readable for CI reminders."""
    for entry in DEPRECATIONS:
        assert isinstance(entry.remove_after, date)
