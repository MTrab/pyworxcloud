"""Utility to validate code-ref data samples match required payload structure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Generator, Iterable, NamedTuple


class ValidationIssue(NamedTuple):
    path: Path
    message: str


REQUIRED_CFG_KEYS = {"id"}
REQUIRED_DAT_KEYS = {"conn"}


def _iter_json_documents(text: str) -> Generator[dict[str, Any], None, None]:
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
        if isinstance(obj, dict):
            yield obj
        index += consumed


def _validate_payload(payload: dict[str, dict]) -> Iterable[str]:
    errors: list[str] = []
    cfg = payload.get("cfg", {})
    dat = payload.get("dat", {})

    if not REQUIRED_CFG_KEYS.issubset(cfg.keys()):
        errors.append(
            f"cfg missing keys: {sorted(REQUIRED_CFG_KEYS - set(cfg.keys()))}"
        )

    if not REQUIRED_DAT_KEYS.issubset(dat.keys()):
        errors.append(
            f"dat missing keys: {sorted(REQUIRED_DAT_KEYS - set(dat.keys()))}"
        )

    if not dat.get("uuid") and not dat.get("mac"):
        errors.append("dat must contain uuid or mac")

    return errors


def validate_data_samples(root: Path | None = None) -> list[ValidationIssue]:
    """Return list of validation issues for each JSON sample."""
    root_path = (
        root or Path(__file__).resolve().parent.parent / "code-ref" / "data-samples"
    )
    issues: list[ValidationIssue] = []

    for file in sorted(root_path.rglob("*.json")):
        try:
            text = file.read_text(encoding="utf-8")
            data = list(_iter_json_documents(text))
        except json.JSONDecodeError as err:
            issues.append(ValidationIssue(file, f"invalid JSON: {err}"))
            continue

        if not data:
            issues.append(ValidationIssue(file, "no JSON objects found"))
            continue

        for index, entry in enumerate(data, start=1):
            payload = entry.get("payload")
            if not isinstance(payload, dict):
                issues.append(
                    ValidationIssue(file, f"entry {index}: missing payload dict")
                )
                continue

            for error in _validate_payload(payload):
                issues.append(ValidationIssue(file, f"entry {index}: {error}"))

    return issues


def main() -> None:
    issues = validate_data_samples()
    if issues:
        for issue in issues:
            print(f"{issue.path}: {issue.message}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
