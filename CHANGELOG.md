# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

### Changed
- Stabilized connector lifecycle so disconnect stops scheduled API refresh work.
- Hardened HTTP transport retry behavior for connection and timeout failures.
- Reduced API pressure by avoiding repeated product catalog lookups during mower listing.
- Enforced serialized MQTT command handling: a new command is blocked until the prior command is acknowledged or times out.
- Added configurable MQTT command timeout via `WorxCloud(..., command_timeout=...)`.

### Fixed
- Removed silent token retrieval failure masking in authentication flow.
- Fixed MQTT command flow that previously could continue without bounded response handling.

### Notes
- This section currently reflects merged refactor hardening PRs: `#294`, `#295`, `#296`.
