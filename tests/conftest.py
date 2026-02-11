"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return fixture root directory."""
    return Path(__file__).resolve().parent / "fixtures"
