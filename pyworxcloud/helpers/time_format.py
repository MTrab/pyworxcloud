"""Time formatting helpers."""

from datetime import datetime
import re
from typing import Any
import pytz

from ..utils import (
    __all__ as all_utils,
)

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
]


@staticmethod
def string_to_time(dt_string: str, tz: str = "UTC") -> datetime:
    """Convert string to datetime object.
    Trying all known date/time formats as defined in DATE_FORMATS constant.

    Args:
        dt_string (str): String containing the date/time
        tz (str): Timezone for the string. default = "UTC"

    Returns:
        datetime: datatime object
    """
    timezone = pytz.timezone(tz)
    for format in DATE_FORMATS:
        try:
            dt_object = datetime.strptime(dt_string, format).astimezone(timezone)
            break
        except ValueError:
            pass

    return dt_object


@staticmethod
def convert_to_time(
    data: Any,
    tz: str = "UTC",
    expression: str | None = None,
    parent: str | None = None,
    subkey: str | None = None,
    callback: Any | None = None,
) -> None:
    """Find and convert all strings resembling timestamps."""
    expression = (
        expression or r"\d{2,4}[-\/]\d{1,2}[-\/]\d{1,4} \d{1,2}:\d{1,2}:\d{1,2}"
    )
    if hasattr(data, "__dict__"):
        data = data.__dict__

    if isinstance(subkey, type(None)):
        parent = subkey
    else:
        if isinstance(parent, type(None)):
            parent = subkey
        else:
            parent += f";;{subkey}"

    for key in data:
        if key.startswith("_"):
            continue

        if not key in data:
            continue

        hits = []
        value = data[key]

        if isinstance(value, tuple(all_utils)) or isinstance(value, dict):
            convert_to_time(
                data=value,
                tz=tz,
                expression=expression,
                parent=parent,
                subkey=key,
                callback=callback,
            )
        elif isinstance(value, str):
            hits = re.findall(expression, value)
        else:
            continue

        if len(hits) == 1:
            newtime = string_to_time(hits[0])
            callback(parent, key, newtime)