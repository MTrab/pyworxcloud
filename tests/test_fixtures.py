"""Fixture integrity tests."""

from __future__ import annotations

from tests.fixture_utils import load_fixture_entries


def test_generated_data_samples_are_valid_json(fixtures_dir) -> None:
    """Ensure copied data sample fixtures are valid JSON documents."""
    data_samples_dir = fixtures_dir / "data-samples"
    if not data_samples_dir.exists():
        return

    for file_path in data_samples_dir.rglob("*.json"):
        entries = load_fixture_entries(file_path)
        assert entries
