#!/usr/bin/env python3
"""Inspect a single dump file and show decoded mapping values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pyworxcloud.utils.devices import DeviceHandler

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "code-ref" / "data-samples"


def iter_json_documents(text: str) -> list[dict[str, Any]]:
    """Return all JSON objects stored sequentially in a file."""
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    items: list[dict[str, Any]] = []
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        obj, consumed = decoder.raw_decode(text[index:])
        if isinstance(obj, dict):
            items.append(obj)
        index += consumed
    return items


def load_payloads(dump_file: Path) -> list[dict[str, Any]]:
    """Load payload dictionaries from dump file."""
    content = dump_file.read_text(encoding="utf-8")
    docs = iter_json_documents(content)
    payloads: list[dict[str, Any]] = []
    for idx, doc in enumerate(docs, start=1):
        if "payload" in doc and isinstance(doc["payload"], dict):
            payloads.append(doc["payload"])
        elif "cfg" in doc and "dat" in doc:
            payloads.append(doc)
        else:
            raise ValueError(f"Entry {idx} has no payload/cfg/dat structure")
    return payloads


def discover_sample_dirs(root: Path) -> list[Path]:
    """Return all sample directories that contain JSON files."""
    if not root.exists():
        return []
    result: list[Path] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if any(entry.glob("*.json")):
            result.append(entry)
    return result


def choose_from_list(title: str, items: list[str]) -> int:
    """Prompt user to select an item index (1-based)."""
    if not items:
        raise ValueError("No items available")
    print(f"\n{title}")
    for idx, item in enumerate(items, start=1):
        print(f"  {idx}. {item}")
    while True:
        value = input("\nSelect number: ").strip()
        try:
            selected = int(value)
        except ValueError:
            print("Please enter a number.")
            continue
        if 1 <= selected <= len(items):
            return selected - 1
        print(f"Please enter a number between 1 and {len(items)}.")


def build_mower(payload: dict[str, Any], protocol: int, name: str) -> dict[str, Any]:
    """Build minimal mower object for DeviceHandler decoding."""
    dat = payload.get("dat", {})
    cfg = payload.get("cfg", {})
    return {
        "name": name,
        "model": {"friendly_name": "Fixture", "code": "FX"},
        "protocol": protocol,
        "serial_number": cfg.get("sn", "SERIAL-FIXTURE"),
        "uuid": dat.get("uuid", "UUID-FIXTURE"),
        "mac_address": dat.get("mac"),
        "time_zone": cfg.get("tz", "UTC"),
        "warranty_expires_at": None,
        "warranty_registered": False,
        "mqtt_topics": {"command_in": "in/topic", "command_out": "out/topic"},
        "last_status": {"payload": payload},
    }


def summarize(
    device: DeviceHandler, payload: dict[str, Any], include_raw: bool
) -> None:
    """Print concise mapping summary for one payload."""
    sc = (
        payload.get("cfg", {}).get("sc", {})
        if isinstance(payload.get("cfg"), dict)
        else {}
    )
    rain = (
        payload.get("dat", {}).get("rain", {})
        if isinstance(payload.get("dat"), dict)
        else {}
    )

    print("\nMapped Core")
    print(f"  status: {device.status.id} ({device.status.description})")
    print(f"  error:  {device.error.id} ({device.error.description})")

    print("\nRain Delay")
    print(
        f"  cfg.rd -> rainsensor.delay: {payload.get('cfg', {}).get('rd')} -> {device.rainsensor.delay}"
    )
    print(
        f"  dat.rain.s -> raindelay_active: {rain.get('s')} -> {device.raindelay_active}"
    )
    print(
        f"  dat.rain.cnt -> rainsensor.remaining: {rain.get('cnt')} -> {device.rainsensor.get('remaining', 0)}"
    )

    print("\nSchedule")
    print(f"  active: {device.schedules.get('active')}")
    print(f"  party_mode_enabled: {device.schedules.get('party_mode_enabled')}")
    print(f"  one_time_schedule: {device.schedules.get('one_time_schedule')}")
    print(
        f"  time_extension (sc.p): {sc.get('p', 0)} -> {device.schedules.get('time_extension')}"
    )
    slots = device.schedules.get("slots", []) or []
    print(f"  slots: {len(slots)}")
    for idx, slot in enumerate(slots, start=1):
        print(
            "    "
            f"{idx:02d}. {slot.get('day'):<9} {slot.get('start')}->{slot.get('end')} "
            f"dur={slot.get('duration')} ext={slot.get('duration_extended')} "
            f"boundary={slot.get('boundary')} source={slot.get('source')}"
        )

    if include_raw:
        print("\nRaw cfg/dat")
        print(
            json.dumps(
                {"cfg": device.raw_cfg, "dat": device.raw_dat}, indent=2, default=str
            )
        )


def resolve_dump_file(args: argparse.Namespace) -> Path:
    """Resolve dump file from args or interactive selection."""
    if args.file:
        dump_file = Path(args.file)
        if not dump_file.exists():
            raise SystemExit(f"File not found: {dump_file}")
        return dump_file

    root = Path(args.root)
    samples = discover_sample_dirs(root)
    if not samples:
        raise SystemExit(f"No sample directories found under: {root}")

    sample_dir: Path
    if args.sample:
        sample_dir = root / args.sample
        if not sample_dir.exists():
            raise SystemExit(f"Sample directory not found: {sample_dir}")
    else:
        choice = choose_from_list("Available sample dumps", [p.name for p in samples])
        sample_dir = samples[choice]

    candidates = sorted(p.name for p in sample_dir.glob("*.json"))
    if not candidates:
        raise SystemExit(f"No JSON dump files found in: {sample_dir}")

    selected_name: str
    if args.dump_name:
        if args.dump_name not in candidates:
            raise SystemExit(
                f"Dump file '{args.dump_name}' not found in {sample_dir}. Available: {candidates}"
            )
        selected_name = args.dump_name
    else:
        choice = choose_from_list(
            f"Available dump files in {sample_dir.name}",
            candidates,
        )
        selected_name = candidates[choice]

    return sample_dir / selected_name


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect dump mapping for one sample file. "
            "If no file is provided, interactive selection is used."
        )
    )
    parser.add_argument(
        "--root", default=str(DEFAULT_ROOT), help="Root folder with sample directories"
    )
    parser.add_argument("--sample", help="Sample directory name (UUID)")
    parser.add_argument(
        "--dump-name",
        help="Dump filename inside sample dir, e.g. http.json or mqtt.json",
    )
    parser.add_argument("--file", help="Direct path to dump file")
    parser.add_argument(
        "--entry", type=int, default=1, help="1-based entry index to inspect"
    )
    parser.add_argument(
        "--all", action="store_true", help="Inspect all entries in selected dump file"
    )
    parser.add_argument(
        "--raw", action="store_true", help="Print raw cfg/dat structures"
    )
    parser.add_argument(
        "--as-json", action="store_true", help="Print decoded summary as JSON"
    )
    return parser.parse_args()


def main() -> None:
    """Run CLI."""
    args = parse_args()
    dump_file = resolve_dump_file(args)
    payloads = load_payloads(dump_file)
    if not payloads:
        raise SystemExit(f"No payloads found in: {dump_file}")

    if args.all:
        indexes = list(range(len(payloads)))
    else:
        entry_index = args.entry - 1
        if entry_index < 0 or entry_index >= len(payloads):
            raise SystemExit(
                f"Entry out of range: {args.entry}. Dump has {len(payloads)} entries."
            )
        indexes = [entry_index]

    print(f"\nDump file: {dump_file}")
    print(f"Entries: {len(payloads)} | Selected: {[i + 1 for i in indexes]}")

    for i in indexes:
        payload = payloads[i]
        sc = (
            payload.get("cfg", {}).get("sc", {})
            if isinstance(payload.get("cfg"), dict)
            else {}
        )
        protocol = 1 if isinstance(sc, dict) and "slots" in sc else 0
        mower = build_mower(payload, protocol, f"{dump_file.parent.name}#{i + 1}")
        device = DeviceHandler(api=object(), mower=mower, tz="UTC")

        print(f"\n=== Entry {i + 1} ===")
        if args.as_json:
            summary = {
                "status": dict(device.status),
                "error": dict(device.error),
                "rain": {
                    "cfg_rd": payload.get("cfg", {}).get("rd"),
                    "dat_rain_s": payload.get("dat", {}).get("rain", {}).get("s"),
                    "dat_rain_cnt": payload.get("dat", {}).get("rain", {}).get("cnt"),
                    "mapped_delay": device.rainsensor.delay,
                    "mapped_triggered": device.rainsensor.get("triggered"),
                    "mapped_remaining": device.rainsensor.get("remaining"),
                    "mapped_active": device.raindelay_active,
                },
                "schedule": {
                    "raw_sc": sc,
                    "mapped": dict(device.schedules),
                },
            }
            if args.raw:
                summary["raw"] = {"cfg": device.raw_cfg, "dat": device.raw_dat}
            print(json.dumps(summary, indent=2, default=str))
        else:
            summarize(device, payload, include_raw=args.raw)


if __name__ == "__main__":
    main()
