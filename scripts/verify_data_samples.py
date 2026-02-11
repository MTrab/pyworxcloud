"""Utility to validate code-ref data samples match required payload structure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, NamedTuple


class ValidationIssue(NamedTuple):
    path: Path
    message: str


REQUIRED_CFG_KEYS = {"id"}
REQUIRED_DAT_KEYS = {"conn"}


def _validate_payload(payload: dict[str, dict]) -> Iterable[str]:
    errors: list[str] = []
    cfg = payload.get("cfg", {})
    dat = payload.get("dat", {})

    if not REQUIRED_CFG_KEYS.issubset(cfg.keys()):
        errors.append(f"cfg missing keys: {sorted(REQUIRED_CFG_KEYS - set(cfg.keys()))}")

    if not REQUIRED_DAT_KEYS.issubset(dat.keys()):
        errors.append(f"dat missing keys: {sorted(REQUIRED_DAT_KEYS - set(dat.keys()))}")

    if not dat.get("uuid") and not dat.get("mac"):
        errors.append("dat must contain uuid or mac")

    return errors


def validate_data_samples(root: Path | None = None) -> list[ValidationIssue]:
    """Return list of validation issues for each JSON sample."""
    root_path = root or Path(__file__).resolve().parent.parent / "code-ref" / "data-samples"
    issues: list[ValidationIssue] = []

    for file in sorted(root_path.rglob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            issues.append(ValidationIssue(file, f"invalid JSON: {err}"))
            continue

        payload = data.get("payload")
        if not isinstance(payload, dict):
            issues.append(ValidationIssue(file, "missing payload dict"))
            continue

        for error in _validate_payload(payload):
            issues.append(ValidationIssue(file, error))

    return issues


def main() -> None:
    issues = validate_data_samples()
    if issues:
        for issue in issues:
            print(f"{issue.path}: {issue.message}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
