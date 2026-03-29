<a href="https://www.buymeacoffee.com/mtrab" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

# pyWorxCloud

This is a PyPI module for communicating with Worx Cloud mowers, primarily developed for use with [Home Assistant](https://home-assistant.io), but I try to keep it as widely usable as possible.<br/>
<br/>
The module are compatible with cloud enabled devices from [these vendors](https://github.com/MTrab/pyworxcloud/wiki#current-supported-brands--vendors)

## Documentation

The documentation have been moved to the [Wiki](https://github.com/MTrab/pyworxcloud/wiki)<br/>
Additional project docs:

- [Migration Guide](./MIGRATION.md)
- [Changelog](./CHANGELOG.md)

## Async usage

`WorxCloud` is now async-first.

```python
import asyncio
from pyworxcloud import WorxCloud


async def main() -> None:
    cloud = WorxCloud("user@example.com", "secret", "worx")
    await cloud.authenticate()
    await cloud.connect()
    try:
        for _, device in cloud.devices.items():
            print(device.name, device.online)
    finally:
        await cloud.disconnect()


asyncio.run(main())
```

You can also use `async with`:

```python
async with WorxCloud("user@example.com", "secret", "worx") as cloud:
    ...
```

### Async migration cheat sheet

Before (sync):

```python
cloud = WorxCloud("user@example.com", "secret", "worx")
cloud.authenticate()
cloud.connect()
cloud.start("SERIAL")
cloud.disconnect()
```

After (async):

```python
cloud = WorxCloud("user@example.com", "secret", "worx")
await cloud.authenticate()
await cloud.connect()
await cloud.start("SERIAL")
await cloud.disconnect()
```

## Testing

Run tests locally with:

```bash
python -m pip install -e . pytest
bash scripts/prepare_test_fixtures.sh
pytest -q
```

The fixture prepare script copies JSON sample files from `code-ref/data-samples` to `tests/fixtures/data-samples` when available.

## Sample validation

Run `python scripts/verify_data_samples.py` (or rely on `tests/test_data_samples.py`) to ensure every `code-ref/data-samples` fixture contains the minimal `payload/cfg/dat` structure (`id`, `conn`, and `uuid`/`mac`). This keeps the fixtures aligned with `DeviceHandler`/`EventHandler` expectations even as you add new samples.

You can also run `python scripts/dump_mapping.py` to print the decoded snapshot for each fixture (status, schedules, rain delay, module data, etc.) so you can visually compare the raw JSON against the values `DeviceHandler` exposes. The script now scans both `http.json` and `mqtt.json` fixtures (including multi-document MQTT exports) so you can inspect how either transport influences the decoded output.

## Data mapping

`DeviceHandler` now keeps the raw `cfg`/`dat` dictionaries alongside the richer surface model that mirrors what is described in `code-ref`. Highlights include:

- `schedules["slots"]` retains every slot that was present in `sc.slots` or `sc.d`, so protocol 1 devices with more end-of-day runs can be inspected.
- `schedules["auto_schedule"]` now exposes a normalized automatic-scheduling view with typed `boost`, `grass_type`, `soil_type`, `irrigation`, `nutrition`, and exclusion-scheduler fields when the mower API payload provides them. Live-observed `boost` levels are `0`, `1`, and `2`.

- slot-first schedule generation that captures each configured run (legacy `d` arrays and protocol 1 `slots`) along with calculated `end` times, pause-mode awareness, and time-extension handling.
- complete rain-delay state tracking (raw counter, active flag, remaining minutes) plus module status/configuration (ACS, Off Limits shortcuts, etc.).
- real-time updates of lock state, battery/blade statistics, orientation, GPS hooks, and module-specific metadata so MQTT and API consumers stay synchronized.

The fixture-driven `tests/test_device_decode.py` now asserts that the raw payloads, module data, and rain delay flags survive the round-trip, making regressions obvious as the refactor continues.

## Networking helpers

`pyworxcloud.utils.requests` now exposes async `AGET/APOST` helpers backed by `aiohttp.ClientSession` for non-blocking API access. Legacy sync `GET/POST` helpers are still available for compatibility and utility scripts.

## Command timeout configuration

`WorxCloud` accepts a `command_timeout` argument (seconds) that controls how long MQTT command calls wait for a matching mower response before raising `TimeoutException`.

```python
from pyworxcloud import WorxCloud

cloud = WorxCloud("user@example.com", "secret", "worx", command_timeout=15.0)
```

## Schedule CRUD

`WorxCloud` now exposes a normalized schedule API for both protocol 0 (`d`/`dd`) and protocol 1 (`slots`) mowers.

```python
from pyworxcloud import WorxCloud
from pyworxcloud.utils.schedule_codec import ScheduleEntry


schedule = cloud.get_schedule("SERIAL")

await cloud.add_schedule_entry(
    "SERIAL",
    ScheduleEntry(
        entry_id="",
        day="monday",
        start="09:00",
        duration=60,
        boundary=False,
        source="slot",
        secondary=False,
    ),
)
```

Notes:

- `get_schedule()` returns a normalized `ScheduleModel`.
- `set_schedule()`, `add_schedule_entry()`, `update_schedule_entry()`, and `delete_schedule_entry()` automatically serialize back to the correct protocol payload.
- Protocol 0 deletion promotes same-day secondary schedules into primary when needed.
- Protocol 1 updates preserve extra slot metadata such as zone lists when the current payload contains them.
- `set_time_extension()` is only supported for protocol 0 mowers.

## Lawn fields

`WorxCloud` can now read and write top-level REST lawn fields on `product-items`:
`lawn_size` (m²) and `lawn_perimeter` (m).

```python
from pyworxcloud import WorxCloud


async with WorxCloud("user@example.com", "secret", "worx") as cloud:
    serial = "SERIAL"

    # Update fields individually.
    await cloud.set_lawn_size(serial, 250)
    await cloud.set_lawn_perimeter(serial, 115)

    # Or update both in one request.
    await cloud.set_lawn(serial, size=250, perimeter=115)
```

## Deprecations

> [!WARNING]
> The old Party mode names are deprecated and are planned for removal after `2026-09-15`.
> Compatibility aliases still work for now, but new integrations should use the Pause mode names below.

| Deprecated | Use instead |
| --- | --- |
| `set_partymode()` | `set_pause_mode()` |
| `NoPartymodeError` | `NoPauseModeError` |
| `DeviceCapability.PARTY_MODE` | `DeviceCapability.PAUSE_MODE` |
| `partymode_enabled` | `pause_mode_enabled` |
| `party_mode_enabled` | `pause_mode_enabled` |
