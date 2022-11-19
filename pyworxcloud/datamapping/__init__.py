"""Datamapping module."""
from __future__ import annotations

_MAP = {
    "cfg": {
        "name": "configuration",
        "sub": {
            "id": {"name": "id"},
            "lg": {"name": "language"},
            "tm": {"name": "time"},
            "dt": {"name": "date"},
            "sc": {
                "text": "schedule",
                "sub": {
                    "m": "schedule_active",
                    "p": "schedule_extension",
                    "d": "schedule_primary",
                    "dd": "schedule_secondary",
                },
            },
        },
    },
    "cmd": {
        "name": "command",
        "sub": {
            "mz": {"zone"},
            "mzv": {"zone_indicator"},
            "rd": {"raindelay"},
            "sn": {"serial_number"},
            "dat": {"data"},
            "mac": {"mac"},
            "fw": {"firmware_version"},
            "bt": {
                "name": "battery",
                "sub": {
                    "t": "temperature",
                    "v": "voltage",
                    "p": "charge_percent",
                    "nr": "charge_cycles",
                    "c": "is_charging",
                    "m": "m",  # Naming?!
                },
            },
            "dmp": {"name": "accelerometer"},
            "st": {
                "name": "statistics",
                "sub": {"b": "blade_on", "d": "distance", "wt": "time_mowing"},
            },
            "ls": {"name": "status_code"},
            "le": {"name": "error_code"},
            "lz": {"name": "next_zone"},
            "rsi": {"name": "wifi_signal_strength"},
            "lk": {"name": "lk"},  # Naming?!
        },
    },
}


def DataMap(data: dict) -> dict:
    """Map data to properties."""
    # for key,value in data.items():
