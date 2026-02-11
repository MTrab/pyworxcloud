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
| `modules` | Submodule health/state (`4G`, `US`, `Rain`, ...). | Captures `module_status`, adds GPS from `4G.gps.coo`, and keeps `module_config`/`module_status` aligned with downstream logic. |
| `rain` | Rain delay state/counter. | Updates `device.rainsensor.triggered`, `remaining`, and `raindelay_active`. |
| `act` | Last activity timestamp (seconds since epoch). | Stored on `device.last_activity` for UI cues. |
| `rsi` | Signal strength. | Stored as `device.rssi`. |
| `conn` | Current connection medium (`wifi`, `4G`). | Mirrors what fixtures expect and is surfaced through `DeviceHandler`. |
| `protocol` | Protocol version hinted by the mower. | Written back to `mower["protocol"]` to ensure schedule parsing stays aligned. |

## `cfg` payload

| Field | Meaning | Usage |
|---|---|---|
| `rd` | Rain delay configured minutes. | Drives `device.rainsensor.delay` and is compared with `rain.cnt` for remaining time. |
| `tq` | Torque helper flag. | Grants `DeviceCapability.TORQUE`. |
| `mz` / `mzv` | Multi-zone start distances and index map. | Sets `zone.starting_point` / `zone.indicies` and derived `zone.current`. |
| `modules` | Module configuration (`DF`, `US`, etc.). | Grants capabilities (Off-Limits / ACS) and flags `offlimit`, `offlimit_shortcut`, `acs_enabled`. |
| `sc` | Schedule definition (legacy `d` arrays or new `slots`). | Drives `schedules["slots"]` plus `["active"]`, `["time_extension"]`, `["party_mode_enabled"]`, `["one_time_schedule"]` and related metadata. |
| `slots` | Derived slot list for every configured run. | Exposed via `schedules["slots"]`, so protocol 1 devices with more than two programs can still enumerate each entry verbatim. |
| `sc.p` | Time extension modifier (minutes to add to each slot). | Stored as `schedules["time_extension"]` and applied to every `slot` end time. |
| `sc.m` / `sc.enabled` | Party mode toggles. | Trigger `DeviceCapability.PARTY_MODE` and populate `schedules["active"]`. |
| `sc.ots` | One-time scheduling info. | Adds `DeviceCapability.ONE_TIME_SCHEDULE` and `DeviceCapability.EDGE_CUT` when present (`ots.bc`, `ots.wtm`). |
| `sc.dd` | Secondary-day schedule matrix. | Mirrors `ScheduleType.SECONDARY` entries so protocol 0 devices keep their legacy extra cuts. |
| `sc.distm` | Distance multiplier tracking. | Tracked under `schedules["slots"]` for reporting and future UI needs. |

### Schedule visualization

For every `sc` payload:

- If `sc.d` is present (protocol 0), each entry `<start, duration, boundary>` is converted into a slot regardless of weekday order; `time_extension` (`sc.p`) affects the computed `end` and `duration_extended`.
- `sc.slots` entries (protocol 1) are mapped one-to-one, decoding `d` (weekday), `s` (start offset), `t` (duration), and nested `cfg.cut.b` (boundary) while recalculating actual start times.
- `sc.dd` produces additional slots tagged with source `secondary`; these are preserved so legacy secondary runs stay visible.
- Fields such as `sc.m`, `sc.enabled`, `sc.ots`/`ots.bc`/`ots.wtm`, and `sc.distm` influence party mode, one-time cuts, and edge cut flags, matching the reference apps.

## Additional notes

- Raw payloads remain available via `device.raw_cfg`/`device.raw_dat`, ensuring every numeric value can be inspected even after transformation.
- `schedules.update_progress_and_next()` keeps `daily_progress`/`next_schedule_start` synced with the current timezone.
- Any new value in `code-ref/data-samples` should be documented here before adding a dedicated property so the visual map stays accurate.
- MQTT fixtures (`mqtt.json`) now ship as sequential JSON payloads from the mower; `dump_mapping.py` and the device decoders iterate every document so the decoded slots/status stay aligned with what flows through the live MQTT stream.
