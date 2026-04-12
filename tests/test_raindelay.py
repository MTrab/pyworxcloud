"""Tests for rain_delay validation."""

import pytest

from pyworxcloud import WorxCloud


def test_coerce_int_accepts_zero() -> None:
    """_coerce_int should accept 0 as valid value."""
    cloud = WorxCloud("test@example.com", "password")
    result = cloud._coerce_int("0", "rain_delay", minimum=0, maximum=1440)
    assert result == 0


def test_coerce_int_accepts_1440() -> None:
    """_coerce_int should accept 1440 as valid value."""
    cloud = WorxCloud("test@example.com", "password")
    result = cloud._coerce_int("1440", "rain_delay", minimum=0, maximum=1440)
    assert result == 1440


def test_coerce_int_rejects_1441() -> None:
    """_coerce_int should reject values above 1440."""
    cloud = WorxCloud("test@example.com", "password")
    with pytest.raises(
        ValueError, match="rain_delay must be less than or equal to 1440"
    ):
        cloud._coerce_int("1441", "rain_delay", minimum=0, maximum=1440)
