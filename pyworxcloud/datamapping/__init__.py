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
                "name": "schedule",
                "sub": {
                    "m": {"name": "schedule_active"},
                    "p": {"name": "schedule_extension"},
                    "d": {"name": "schedule_primary"},
                    "dd": {"name": "schedule_secondary"},
                },
            },
            "cmd": {"name": "command"},
            "mz": {"name": "zone"},
            "mzv": {"name": "zone_indicator"},
            "rd": {"name": "raindelay"},
            # "sn": {"name": "serial_number"},
        },
    },
    "dat": {
        "name": "data",
        "sub": {
            "mac": {"name": "mac"},
            "fw": {"name": "firmware_version"},
            "bt": {
                "name": "battery",
                "sub": {
                    "t": {"name": "temperature"},
                    "v": {"name": "voltage"},
                    "p": {"name": "charge_percent"},
                    "nr": {"name": "charge_cycles"},
                    "c": {"name": "is_charging"},
                    "m": {"name": "m"},  # Naming?!
                },
            },
            "dmp": {"name": "accelerometer"},
            "st": {
                "name": "statistics",
                "sub": {
                    "b": {"name": "blade_on"},
                    "d": {"name": "distance"},
                    "wt": {"name": "time_mowing"},
                },
            },
            "ls": {"name": "status_code"},
            "le": {"name": "error_code"},
            "lz": {"name": "next_zone"},
            "rsi": {"name": "wifi_signal_strength"},
            "lk": {"name": "lk"},  # Naming?!
        },
    },
}


def _recursive(key: str, value: str, parent: dict) -> dict:
    """Recursive mapping."""
    okey = key
    ovalue = value

    dataset: dict = {}
    for key, value in ovalue.items():
        if isinstance(value, dict):
            if key in parent["sub"]:
                dataset.update(
                    {
                        parent["sub"][key]["name"]: _recursive(
                            key, value, parent["sub"][key]
                        )
                    }
                )
            else:
                dataset.update({key: value})
        else:
            if key in parent["sub"]:
                dataset.update({parent["sub"][key]["name"]: value})
            else:
                dataset.update({key: value})

    return dataset


def DataMap(data: dict) -> dict | None:
    """Map data to properties."""
    dataset = {}
    for key, value in data.items():
        if isinstance(value, dict):
            if key in _MAP:
                dataset.update({_MAP[key]["name"]: _recursive(key, value, _MAP[key])})
            else:
                dataset.update({key: value})
        else:
            if key in _MAP:
                dataset.update({_MAP[key]["name"]: value})
            else:
                dataset.update({key: value})

    if "last_status" in dataset:
        data = dataset.pop("last_status")["payload"]
        for key, value in data.items():
            if isinstance(value, dict):
                if key in _MAP:
                    dataset.update({_MAP[key]["name"]: _recursive(key, value, _MAP[key])})
                else:
                    dataset.update({key: value})
            else:
                if key in _MAP:
                    dataset.update({_MAP[key]["name"]: value})
                else:
                    dataset.update({key: value})

    return dataset
