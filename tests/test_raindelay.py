"""Tests for rain_delay validation."""

import pytest
from pyworxcloud import WorxCloud


def test_raindelay_accepts_zero() -> None:
    """Rain delay should accept 0 minutes as valid value."""
    cloud = WorxCloud("fake-api-key")
    # The validation passes if no exception is raised
    try:
        cloud.raindelay("serial123", "0")
    except Exception as e:
        pytest.fail(f"Unexpected error: {type(e).__name__}: {e}")


def test_raindelay_accepts_1440() -> None:
    """Rain delay should accept 1440 minutes (24 hours) as valid value."""
    cloud = WorxCloud("fake-api-key")
    try:
        cloud.raindelay("serial123", "1440")
    except Exception as e:
        pytest.fail(f"Unexpected error: {type(e).__name__}: {e}")


def test_raindelay_rejects_1441() -> None:
    """Rain delay should reject values above 1440 minutes."""
    cloud = WorxCloud("fake-api-key")
    with pytest.raises(ValueError, match="rain_delay must be less than or equal to 1440"):
        cloud.raindelay("serial123", "1441")
