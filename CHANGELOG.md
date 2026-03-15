# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

### Changed
- Stabilized connector lifecycle so disconnect stops scheduled API refresh work.
- Hardened HTTP transport retry behavior for connection and timeout failures.
- Reduced API pressure by avoiding repeated product catalog lookups during mower listing.
- Reused HTTP sessions in API calls to improve connection pooling and request performance.
- Logged MQTT timeout metadata (serial, topic, payload) for easier debugging.
- Enforced serialized MQTT command handling: a new command is blocked until the prior command is acknowledged or times out.
- Added configurable MQTT command timeout via `WorxCloud(..., command_timeout=...)`.
- Added normalized schedule CRUD support across protocol 0 primary/secondary schedules and protocol 1 slot-based schedules.
- Made schedule toggling protocol-aware and restricted schedule time extension writes to protocol 0 devices.

### Fixed
- Removed silent token retrieval failure masking in authentication flow.
- Fixed MQTT command flow that previously could continue without bounded response handling.
- Fixed API event callback dispatch so `LandroidEvent.API` supports `api_data` payloads.

### Notes
- This section currently reflects merged refactor hardening PRs: `#294`, `#295`, `#296`.
