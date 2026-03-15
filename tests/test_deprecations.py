"""Tests for the deprecation registry."""

from __future__ import annotations

import re
from pathlib import Path

from pyworxcloud.deprecations import DEPRECATIONS


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if match is None:
        raise AssertionError(f"Unsupported version format: {value}")
    return tuple(int(part) for part in match.groups())


def _project_version() -> str:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', content, re.MULTILINE)
    if match is None:
        raise AssertionError("Could not find project version in pyproject.toml")
    return match.group(1)


def test_deprecation_removal_versions_are_still_in_the_future() -> None:
    """Fail once planned removals become due so they are not forgotten."""
    current = _version_tuple(_project_version())
    due = [
        entry.old_name
        for entry in DEPRECATIONS
        if _version_tuple(entry.remove_in) <= current
    ]
    assert not due, (
        "Deprecated compatibility aliases are due for removal in this release: "
        + ", ".join(due)
    )


def test_deprecation_registry_uses_semver_versions() -> None:
    """Keep the registry machine-readable for CI reminders."""
    for entry in DEPRECATIONS:
        assert _version_tuple(entry.remove_in)
