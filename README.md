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

## Data mapping

`DeviceHandler` now keeps the raw `cfg`/`dat` dictionaries alongside the richer surface model that mirrors what is described in `code-ref`. Highlights include:

- full `primary`/`secondary` schedule generation for both legacy `d` arrays and the newer `slots` model, with calculated `end` times, party-mode awareness, and time-extension handling.
- complete rain-delay state tracking (raw counter, active flag, remaining minutes) plus module status/configuration (ACS, Off Limits shortcuts, etc.).
- real-time updates of lock state, battery/blade statistics, orientation, GPS hooks, and module-specific metadata so MQTT and API consumers stay synchronized.

The fixture-driven `tests/test_device_decode.py` now asserts that the raw payloads, module data, and rain delay flags survive the round-trip, making regressions obvious as the refactor continues.

## Networking helpers

`pyworxcloud.utils.requests` now builds a shared `requests.Session` configured with an `HTTPAdapter`/`Retry` pair targeting `429`, `500`, `502`, `503` and `504` so every API call benefits from exponential retries without duplicating session setup. Use the exported `create_session()` when you need to decorate or instrument this session (see `scripts/session_trace.py`), while the default `GET/POST` helpers continue working without additional configuration.

## Command timeout configuration

`WorxCloud` accepts a `command_timeout` argument (seconds) that controls how long MQTT command calls wait for a matching mower response before raising `TimeoutException`.

```python
from pyworxcloud import WorxCloud

cloud = WorxCloud("user@example.com", "secret", "worx", command_timeout=15.0)
```
