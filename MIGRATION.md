# Migration Guide

This guide covers behavior and integration changes introduced by the refactor hardening series.

## Scope

The changes in this guide are based on merged hardening pull requests:

- `#294` lifecycle/disconnect stabilization
- `#295` HTTP transport hardening
- `#296` MQTT command serialization + timeout enforcement

## Breaking Behavior Changes

### 0. `WorxCloud` API is now async-first

`WorxCloud` methods that perform I/O are now coroutine methods and must be awaited.

Affected methods include (non-exhaustive):

- `authenticate()`
- `connect()`
- `disconnect()`
- `update()`
- command/control methods such as `start()`, `pause()`, `home()`, `safehome()`, `send()`, `set_*()`

`async with WorxCloud(...)` is supported.

What this means for integrations:

- Call methods with `await`.
- Ensure lifecycle setup/teardown runs inside an event loop.
- For Home Assistant, call methods from async setup/update/service handlers directly.

Quick before/after:

```python
# Before
cloud.authenticate()
cloud.connect()
cloud.update("SERIAL")
cloud.disconnect()
```

```python
# After
await cloud.authenticate()
await cloud.connect()
await cloud.update("SERIAL")
await cloud.disconnect()
```

### 1. MQTT commands are now serialized

Only one command can be in flight per MQTT client at a time.

What this means for integrations:

- Do not assume fire-and-forget behavior.
- Queue commands on your side if you trigger multiple actions quickly.
- Expect the next command to wait until prior command response or timeout.

### 2. Command response timeout is now enforced

MQTT command send now has bounded wait behavior and raises timeout errors when no matching response is received in time.

What this means for integrations:

- Handle `TimeoutException` explicitly.
- Surface timeout errors in UI/automation logic as retryable failures.
- Avoid infinite waiting states in calling code.

`WorxCloud` now supports explicit timeout configuration:

- `WorxCloud(..., command_timeout=<seconds>)`

### 3. Transport-level failures are no longer misclassified

Connection and timeout failures in HTTP transport now map to connection-style failures after retries, not rate-limit errors.

What this means for integrations:

- Treat `NoConnectionError` as network/transient endpoint availability failure.
- Keep `TooManyRequestsError` handling for actual quota/rate-limit cases.
- Introduced a shared `requests.Session` with `HTTPAdapter`/`Retry` for consistent HTTP request retries on `429`/`5xx` responses and connection failures.

### 4. Disconnect semantics are stricter

Calling `disconnect()` now reliably blocks new refresh scheduling and cancels timers.

What this means for integrations:

- You can rely on disconnect to stop background API refresh loops.
- Reconnect paths should call `connect()` explicitly to re-enable background refresh.

### 5. Schedule CRUD is now supported through a normalized model

Schedule reads and writes no longer need separate frontend handling for protocol 0 and protocol 1 mowers.

What this means for integrations:

- Use `get_schedule()` to retrieve a normalized `ScheduleModel`.
- Use `set_schedule()`, `add_schedule_entry()`, `update_schedule_entry()`, and `delete_schedule_entry()` for schedule mutations.
- Protocol 0 primary/secondary schedules are normalized into entries and serialized back into `d`/`dd`.
- Protocol 1 slot-based schedules are normalized into entries and serialized back into `slots` while preserving existing slot metadata.
- `toggle_schedule()` now sends the correct protocol-specific payload for both schedule formats.
- `set_time_extension()` is limited to protocol 0 schedules.

## Recommended Integration Updates

1. Add explicit timeout handling around command dispatch.
2. Centralize retry policy in your integration layer for `NoConnectionError`.
3. Ensure your command API is queue-based or lock-protected.
4. Update user-facing error texts to distinguish:
   - rate-limited
   - offline/no connection
   - command timed out
