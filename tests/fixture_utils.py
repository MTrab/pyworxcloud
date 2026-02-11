"""Utility helpers for reading JSON fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Generator, Iterable, Sequence, Set

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "data-samples"
CODE_REF_DIR = Path(__file__).resolve().parents[1] / "code-ref" / "data-samples"
BACKUP_DIR = Path(__file__).resolve().parent / "reference-data" / "data-samples"


def _resolve_fixture_path(file_path: Path) -> Path:
    if file_path.exists():
        return file_path

    try:
        relative = file_path.relative_to(FIXTURES_DIR)
    except ValueError:
        return file_path

    candidate = CODE_REF_DIR / relative
    if candidate.exists():
        return candidate

    backup_candidate = BACKUP_DIR / relative
    return backup_candidate if backup_candidate.exists() else file_path


def _collect_fixture_directories() -> Iterable[Path]:
    """Return every discovered fixture directory."""

    seen: Set[str] = set()
    for base in (FIXTURES_DIR, CODE_REF_DIR, BACKUP_DIR):
        if not base.exists():
            continue
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in seen:
                continue
            seen.add(entry.name)
            yield entry


def fixture_paths(filename: str) -> Sequence[Path]:
    """Return the paths to every fixture file with the requested name."""

    paths: list[Path] = []
    for directory in _collect_fixture_directories():
        candidate = directory / filename
        if candidate.exists():
            paths.append(candidate)
    return paths


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

    source = _resolve_fixture_path(file_path)
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        return []
    return list(iter_json_documents(text))


def load_fixture_payloads(file_path: Path) -> Sequence[dict[str, Any]]:
    """Return the `payload` dictionaries contained in the fixture."""

    return [entry["payload"] for entry in load_fixture_entries(file_path)]
