"""Time formatting helpers."""

from datetime import datetime
import re
from typing import Any
import pytz

from ..utils import (
    __all__ as all_utils,
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


def convert_to_time(
    data: Any,
    tz: str = "UTC",
    expression: str | None = None,
) -> dict | None:
    """Find and convert all strings resembling timestamps."""
    expression = expression or r"\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2}"
    if hasattr(data, "__dict__"):
        recur = data.__dict__
    else:
        recur = data

    retval = {}

    for key in recur:
        if key.startswith("_"):
            continue

        result = None
        results = None

        if not key in recur:
            continue

        value = recur[key]

        if isinstance(value, tuple(all_utils)) or isinstance(value, dict):
            result = convert_to_time(value, tz, expression)
            if result:
                print(f"{key} returned {result}")
                retval.update({key: result})
        elif isinstance(value, str):
            results = re.findall(expression, value)
        else:
            continue

        if not results or not result:
            retval.update({key: value})
            continue

        retval.update({key: string_to_time(results[0])})

    if len(retval) > 0:
        # print(retval)
        return retval
    else:
        return None


def convert_to_time_recursive(
    data: Any,
    tz: str = "UTC",
    expression: str | None = None,
    computed: dict = {},
) -> dict | None:
    """Find and convert all strings resembling timestamps."""
    expression = expression or r"\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2}"
    recur = data
    if hasattr(data, "__dict__"):
        if len(recur.__dict__) > 0:
            recur = data.__dict__

    child = {}
    for attr in recur:
        if attr.startswith("_"):
            continue

        if not attr in recur:
            if not hasattr(recur, attr):
                continue

            value = getattr(recur, attr)
        else:
            value = recur[attr]

        # if isinstance(value, type(None)):
        #     continue

        if isinstance(value, tuple(all_utils)) or isinstance(value, dict):
            child.update(
                {attr: convert_to_time_recursive(value, tz, expression, computed)}
            )
        else:
            child.update({attr: value})

    computed.update(child)
    print(computed)
    return computed
