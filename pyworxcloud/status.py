"""Status and error codes."""
from __future__ import annotations

from enum import IntEnum


class WorxStatus(IntEnum):
    STOPPED = 0
    HOME = 1
    START_SEQUENCE = 2
    LEAVING_HOME = 3
    GOING_HOME = 5
    SEARCHING_FOR_BORDER = 6
    CUTTING_GRASS = 7
    LIFTED_RECOVERY = 8
    TRAPPED_RECOVERY = 9
    BLADE_BLOCKED = 10
    OUTSIDE_FENCE = 13
    FOLLOW_BORDER_HOME = 30
    FOLLOW_BORDER_TRAINING = 31
    FOLLOW_BORDER_CUTTING = 32
    FOLLOW_BORDER_GOING_TO_ZONE = 33
    PAUSE = 34


StatusMap = {
    0: "Manual stop",
    1: "Home",
    2: "Starting",
    3: "Leaving home",
    5: "Searching border, going home",
    6: "Searching border",
    7: "Mowing",
    8: "Recovering from being lifted",
    9: "Recovering from being trapped",
    10: "Recovering after blocked blades",
    13: "Outside digital fence",
    30: "Going home",
    31: "Zonetraining",
    32: "Mowing along border",
    33: "Following border to zone start",
    34: "Paused",
}


class WorxError(IntEnum):
    NO_ERROR = 0
    TRAPPED = 1
    LIFTED = 2
    WIRE_MISSING = 3
    OUTSIDE_BOUNDARY = 4
    RAINING = 5
    CLOSE_DOOR_TO_CUT = 6
    CLOSE_DOOR_TO_GO_HOME = 7
    BLADE_MOTOR_ERROR = 8
    WHEEL_MOTOR_ERROR = 9
    TRAPPED_TIMEOUT = 10
    UPSIDE_DOWN = 11
    BATTERY_LOW = 12
    BOUNDARY_WIRE_REVERSED = 13
    BATTERY_CHARGE_ERRPR = 14
    HOME_SEARCH_TIMEOUT = 15
    WIFI_LOCKED = 16
    BATTERY_TEMPERETURE = 17
    DOOR_OPEN_TIMEOUT = 19
    BOUNDARY_WIRE_OUT_OF_SYNC = 20


ErrorMap = {
    0: "No error",
    1: "Trapped",
    2: "Lifted",
    3: "Wire missing",
    4: "Outside boundary",
    5: "Rain delay",
    6: "Close door to start mowing",
    7: "Close door to go home",
    8: "Blade motor error",
    9: "Wheel motor error",
    10: "Trapped timeout",
    11: "Upside down",
    12: "Battery low",
    13: "Boundary wire reversed",
    14: "Battery charge error",
    15: "Timeout going home",
    16: "Wifi locked",
    17: "Battery temperature out of range",
    19: "Door open timeout",
    20: "Boundary wire signal out of sync",
}
