"""Utility helpers for reading JSON fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Generator, Sequence


def iter_json_documents(text: str) -> Generator[dict[str, Any], None, None]:
    """Yield all JSON objects stored sequentially in a file."""

    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        obj, consumed = decoder.raw_decode(text[index:])
        yield obj
        index += consumed


def load_fixture_entries(file_path: Path) -> Sequence[dict[str, Any]]:
    """Return every JSON document embedded in the fixture file."""

    text = file_path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    return list(iter_json_documents(text))


def load_fixture_payloads(file_path: Path) -> Sequence[dict[str, Any]]:
    """Return the `payload` dictionaries contained in the fixture."""

    return [entry["payload"] for entry in load_fixture_entries(file_path)]
