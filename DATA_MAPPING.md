# Device payload mapping

This document visualizes how the JSON `cfg`/`dat` payloads from the Worx/Kress/LX APIs are interpreted by `DeviceHandler`. The goal is to keep the mapping tight to the reference implementations in `code-ref` while revealing the meaning of each field that surfaces in the public `mower` object and its substructures.

## `dat` payload

| Field | Meaning | Usage |
|---|---|---|
| `uuid` / `mac` | Unique mower identifier (UUID preferred on newer models, MAC on legacy.) | Populates `mower["uuid"]` and `device.uuid`, stored in `raw_dat`. |
| `ls` | Current status/state code. | Updates `device.status` via `States.update`. |
| `le` | Error code. | Updates `device.error`. |
| `lz` | Active zone index. | Sets `device.zone.index`; used with `mzv` to determine `zone.current`. |
| `lk` | Lock status (0/1). | Sets `device.locked` and the cached `mower["locked"]`. |
| `bt` | Battery telemetry (`t`, `v`, `p`, ...). | Mapped through `Battery` and kept in sync with blade runtime. |
| `st` | Runtime statistics (`b`, `d`, `wt`, `bl`). | Feeds `Statistic` and `Blades` objects. |
| `dmp` | Orientation vector (pitch/roll/yaw). | Replaces `device.orientation`. |
| `modules` | Submodule health (`4G`, `US`, etc.). | Captures `module_status`; `4G` GPS co-ordinates populate `device.gps`. |
| `rain` | Rain delay state/counter. | Updates `device.rainsensor.triggered`, `remaining`, and `raindelay_active`. |
| `rsi` | Signal strength. | Stored as `device.rssi`. |
| `conn` | Current connection medium (`wifi`, `4G`). | Used in fixtures/tests for verification.| 

## `cfg` payload

| Field | Meaning | Usage |
|---|---|---|
| `rd` | Rain delay configured minutes. | Drives `device.rainsensor.delay`. |
| `tq` | Torque helper flag. | Grants `DeviceCapability.TORQUE`. |
| `mz` / `mzv` | Multi-zone start distances and index map. | Sets `zone.starting_point` / `zone.indicies` and derived `zone.current`. |
| `modules` | Module configuration (`DF`, `US`, etc.). | Grants capabilities (Off-Limits / ACS) and flags `offlimit`, `offlimit_shortcut`, `acs_enabled`. |
| `sc` | Schedule definition (legacy `d` arrays or new `slots`). | Drives the `schedules` object with `primary`, `secondary`, `active`, `time_extension`, and party-mode metadata. |
| `slots` | Derived slot list for every configured run. | Exposed via `schedules["slots"]`, so protocol 1 devices with more than two programs can still enumerate each entry verbatim. |

### Schedule visualization

For every `sc` payload:

- If `sc.d` is present (protocol 0), each entry `<start, duration, boundary>` is stored under `schedules.primary` for `DAY_MAP[idx]`. The duration is adjusted by `time_extension` (`sc.p`).
- If `sc.slots` exists (protocol 1), each slot includes `d` (weekday), `s` (start offset), `t` (duration), and nested `cfg.cut.b` (boundary). Start times are recalculated from `00:00` plus `s` minutes.
- Secondary schedules (`sc.dd`) are mapped similarly under `schedules.secondary` by weekday index.
- Fields such as `sc.m`, `sc.enabled`, `sc.ots`/`ots.bc`/`ots.wtm`, and `sc.distm` influence party mode, one-time cuts, and edge cut flags, matching the reference apps.

## Additional notes

- Raw payloads remain available via `device.raw_cfg`/`device.raw_dat`, ensuring every numeric value can be inspected even after transformation.
- `schedules.update_progress_and_next()` keeps `daily_progress`/`next_schedule_start` synced with the current timezone.
- Any new value in `code-ref/data-samples` should be documented here before adding a dedicated property so the visual map stays accurate.
