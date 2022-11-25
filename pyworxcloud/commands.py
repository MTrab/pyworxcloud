"""Commands handler."""
from __future__ import annotations

from enum import IntEnum


class WorxCommand(IntEnum):
    NO_COMMAND = 0
    START = 1
    PAUSE = 2
    GO_HOME = 3
    FOLLOW_BORDER = 4
    ENABLE_WIFI_LOCK = 5
    DISABLE_WIFI_LOCK = 6
    RESET_LOG = 7
    PAUSE_ON_BORDER = 8
    SAFE_GO_HOME = 9
