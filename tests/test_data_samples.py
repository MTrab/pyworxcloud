"""Validate code-ref data samples expose required keys."""

from __future__ import annotations

from scripts.verify_data_samples import validate_data_samples


def test_data_samples_contain_expected_fields() -> None:
    """Ensure every fixture exposes core cfg/dat keys we rely on."""
    issues = validate_data_samples()
    assert not issues, f"data sample validation failed: {issues}"
