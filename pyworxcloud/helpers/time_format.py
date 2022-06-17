"""Time formatting helpers."""

from datetime import datetime
import re
from typing import Any
import pytz

from ..utils import (
    __all__ as all_utils,
    Blades,
    Battery,
    Capability,
    Command,
    DeviceCapability,
    Location,
    MQTT,
    MQTTHandler,
    Orientation,
    Schedule,
    ScheduleType,
    States,
    StateType,
    Statistic,
    Zone,
)


@staticmethod
def string_to_time(
    dt_string: str, tz: str = "UTC", format: str = "%Y-%m-%d %H:%M:%S"
) -> datetime:
    """Convert string to datetime object.

    Args:
        dt_string (str): String containing the date/time
        tz (str): Timezone for the string. default = "UTC"
        format (str): String format. default = "%Y-%m-%d %H:%M:%S"

    Returns:
        datetime: datatime object
    """
    timezone = pytz.timezone(tz)
    dt_object = datetime.strptime(dt_string, format).astimezone(timezone)

    return dt_object


@staticmethod
def convert_to_time(
    data: dict,
    tz: str = "UTC",
    expression: str = "\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2}",
) -> Any:
    """Find and convert all strings resembling timestamps."""
    if not hasattr(data, "items"):
        return data

    for attribute, value in data.items():
        if attribute.startswith("_"):
            continue

        print(f"{attribute} - {type(value)}")
        if isinstance(value, tuple(all_utils)) or isinstance(value, dict):
            results = convert_to_time(value, tz, expression)
            print(results)
        elif isinstance(value, str):
            results = re.findall(expression, value)
        else:
            continue

        if not results:
            continue

        yield string_to_time(results[0], tz)
