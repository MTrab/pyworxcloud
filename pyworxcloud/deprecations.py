"""Central registry for public deprecations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DeprecationEntry:
    """Describe one public deprecation and its planned removal date."""

    old_name: str
    replacement: str
    remove_after: date
    note: str = ""


DEPRECATIONS: tuple[DeprecationEntry, ...] = (
    DeprecationEntry(
        old_name="WorxCloud.set_partymode()",
        replacement="WorxCloud.set_pause_mode()",
        remove_after=date(2026, 9, 15),
        note="Deprecated Party mode method alias.",
    ),
    DeprecationEntry(
        old_name="NoPartymodeError",
        replacement="NoPauseModeError",
        remove_after=date(2026, 9, 15),
        note="Deprecated exception alias.",
    ),
    DeprecationEntry(
        old_name="DeviceCapability.PARTY_MODE",
        replacement="DeviceCapability.PAUSE_MODE",
        remove_after=date(2026, 9, 15),
        note="Deprecated capability alias.",
    ),
    DeprecationEntry(
        old_name="DeviceHandler.partymode_enabled",
        replacement="DeviceHandler.pause_mode_enabled",
        remove_after=date(2026, 9, 15),
        note="Deprecated device attribute alias.",
    ),
    DeprecationEntry(
        old_name='schedules["party_mode_enabled"]',
        replacement='schedules["pause_mode_enabled"]',
        remove_after=date(2026, 9, 15),
        note="Deprecated schedule field alias.",
    ),
)
