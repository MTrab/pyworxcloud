"""A class set that helps representing data as wanted."""
from __future__ import annotations

from typing import Any


class LDict(dict):
    """A Landroid custom dict."""

    def __init__(self, default: Any | None = None):
        """Init dict."""
        super().__init__(self)
