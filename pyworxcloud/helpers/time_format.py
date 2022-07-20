"""Time formatting helpers."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pyworxcloud.utils.schedules import Schedule

try:
    from ..utils import __all__ as all_utils
except:
    pass

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
]


def string_to_time(dt_string: str, tz: str = "UTC") -> datetime | str:
    """Convert string to datetime object.
    Trying all known date/time formats as defined in DATE_FORMATS constant.

    Args:
        dt_string (str): String containing the date/time
        tz (str): Timezone for the string. default = "UTC"

    Returns:
        datetime: datatime object
    """
    timezone = ZoneInfo(tz) if not isinstance(tz, type(None)) else ZoneInfo("UTC")
    for format in DATE_FORMATS:
        try:
            dt_object = datetime.strptime(dt_string, format).replace(
                tzinfo=timezone
            )  # .astimezone(timezone)
            break
        except ValueError:
            pass
        except TypeError:
            # Something wasn't right with the provided string, just return it as it was
            dt_object = dt_string

    return dt_object


def convert_to_time(
    device: str,
    data: Any,
    tz: str = "UTC",
    expression: str = None,
    parent: str = None,
    subkey: str = None,
    callback: Any = None,
) -> None:
    """Find and convert all strings resembling timestamps."""
    expression = (
        expression or r"\d{2,4}[-\/]\d{1,2}[-\/]\d{1,4} \d{1,2}:\d{1,2}:\d{1,2}"
    )
    if hasattr(data, "__dict__"):
        if isinstance(data, Schedule):
            pass
        data = data.__dict__ if len(data.__dict__) > 0 else data

    if isinstance(subkey, type(None)):
        parent = subkey
    else:
        if isinstance(parent, type(None)):
            parent = subkey
        else:
            parent += f";;{subkey}"

    for key in data:
        if key.startswith("_") or key == "devices":
            continue

        if not key in data:
            continue

        hits = []
        value = data[key]

        if isinstance(value, tuple(all_utils)) or isinstance(value, dict):
            convert_to_time(
                device=device,
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
            newtime = string_to_time(hits[0], tz)
            callback(device, parent, key, newtime)
