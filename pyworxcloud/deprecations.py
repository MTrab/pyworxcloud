"""Central registry for public deprecations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeprecationEntry:
    """Describe one public deprecation and its planned removal release."""

    old_name: str
    replacement: str
    remove_in: str
    note: str = ""


DEPRECATIONS: tuple[DeprecationEntry, ...] = (
    DeprecationEntry(
        old_name="WorxCloud.set_partymode()",
        replacement="WorxCloud.set_pause_mode()",
        remove_in="6.0.0",
        note="Deprecated Party mode method alias.",
    ),
    DeprecationEntry(
        old_name="NoPartymodeError",
        replacement="NoPauseModeError",
        remove_in="6.0.0",
        note="Deprecated exception alias.",
    ),
    DeprecationEntry(
        old_name="DeviceCapability.PARTY_MODE",
        replacement="DeviceCapability.PAUSE_MODE",
        remove_in="6.0.0",
        note="Deprecated capability alias.",
    ),
    DeprecationEntry(
        old_name="DeviceHandler.partymode_enabled",
        replacement="DeviceHandler.pause_mode_enabled",
        remove_in="6.0.0",
        note="Deprecated device attribute alias.",
    ),
    DeprecationEntry(
        old_name='schedules["party_mode_enabled"]',
        replacement='schedules["pause_mode_enabled"]',
        remove_in="6.0.0",
        note="Deprecated schedule field alias.",
    ),
)
