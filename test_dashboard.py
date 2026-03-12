"""Interactive terminal dashboard for manual pyworxcloud testing."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from os import environ
from pathlib import Path
from typing import Any

from pyworxcloud import WorxCloud
from pyworxcloud.events import LandroidEvent
from pyworxcloud.utils import DeviceHandler

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout

    _PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PromptSession = None
    patch_stdout = None
    _PROMPT_TOOLKIT_AVAILABLE = False


def _clear() -> None:
    print("\033c", end="")


def _load_dotenv(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs into environment if missing."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in environ:
            environ[key] = value


def _configure_logging() -> int:
    """Configure runtime log verbosity for interactive dashboard use."""
    level_name = environ.get("DASHBOARD_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level)
    for name in (
        "pyworxcloud",
        "pyworxcloud.events",
        "pyworxcloud.utils.mqtt",
    ):
        logger = logging.getLogger(name)
        logger.setLevel(level)
    return level


async def _ainput(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


def _battery_percent(device: DeviceHandler) -> str:
    """Return battery percentage from both object-like and dict-like payloads."""
    battery = getattr(device, "battery", None)
    if battery is None:
        return "unknown"

    value = getattr(battery, "percent", None)
    if value is None and isinstance(battery, dict):
        value = battery.get("percent")
    if value is None:
        try:
            value = battery["percent"]  # type: ignore[index]
        except Exception:
            value = None
    return str(value) if value is not None else "unknown"


def _firmware_version(device: DeviceHandler) -> str:
    """Return firmware version from both object-like and dict-like payloads."""
    firmware = getattr(device, "firmware", None)
    if firmware is None:
        return "unknown"

    value = getattr(firmware, "version", None)
    if value is None and isinstance(firmware, dict):
        value = firmware.get("version")
    if value is None:
        try:
            value = firmware["version"]  # type: ignore[index]
        except Exception:
            value = None
    return str(value) if value is not None else "unknown"


def _next_schedule_start(device: DeviceHandler) -> str:
    """Return human-readable next schedule start from parsed schedules."""
    schedules = getattr(device, "schedules", None)
    if schedules is None:
        return "unknown"
    value = None
    if isinstance(schedules, dict):
        value = schedules.get("next_schedule_start")
    if value is None:
        try:
            value = schedules["next_schedule_start"]  # type: ignore[index]
        except Exception:
            value = None
    return str(value) if value is not None else "none"


def _schedule_slots(device: DeviceHandler) -> list[dict[str, Any]]:
    """Extract parsed schedule slots as list."""
    schedules = getattr(device, "schedules", None)
    if schedules is None:
        return []
    slots = None
    if isinstance(schedules, dict):
        slots = schedules.get("slots")
    if slots is None:
        try:
            slots = schedules["slots"]  # type: ignore[index]
        except Exception:
            slots = None
    return slots if isinstance(slots, list) else []


async def _show_schedule_view(device: DeviceHandler, selected: str) -> None:
    """Render a schedule details page and wait for return."""
    _clear()
    print(f"Schedule details | {selected}")
    print("=" * 72)
    print(f"Next schedule start: {_next_schedule_start(device)}")
    print(f"Daily progress: {device.schedules.get('daily_progress', 'unknown')}%")
    print(f"Schedule active: {device.schedules.get('active', 'unknown')}")
    print("-" * 72)
    slots = _schedule_slots(device)
    if not slots:
        print("No parsed schedule slots.")
    else:
        print("Slots:")
        for slot in slots:
            day = slot.get("day", "unknown")
            start = slot.get("start", "?")
            end = slot.get("end", "?")
            duration = slot.get("duration_extended", slot.get("duration", "?"))
            boundary = slot.get("boundary", False)
            source = slot.get("source", "unknown")
            print(
                f"- {day:9} {start}-{end} | duration={duration}m | boundary={boundary} | source={source}"
            )
    print("-" * 72)
    await _ainput("Press Enter to return...")


async def _choose_mower(cloud: WorxCloud) -> str:
    names = list(cloud.devices.keys())
    if len(names) == 1:
        return names[0]

    while True:
        _clear()
        print("Select mower:\n")
        for idx, name in enumerate(names, start=1):
            device = cloud.devices[name]
            print(
                f"{idx}. {name} | serial={device.serial_number} | online={device.online}"
            )
        choice = (await _ainput("\nNumber: ")).strip()
        try:
            index = int(choice)
        except ValueError:
            continue
        if 1 <= index <= len(names):
            return names[index - 1]


def _render_device(device: DeviceHandler, selected: str, event_text: str) -> None:
    _clear()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"pyworxcloud dashboard | {now}")
    print("=" * 72)
    print(f"Mower: {selected}")
    print(f"Serial: {device.serial_number}")
    print(f"Model: {getattr(device, 'model', 'unknown')}")
    print(f"Online: {getattr(device, 'online', 'unknown')}")
    print(f"Status: {getattr(device.status, 'description', 'unknown')}")
    print(f"Error: {getattr(device.error, 'description', 'unknown')}")
    print(f"Battery: {_battery_percent(device)}%")
    print(f"Locked: {getattr(device, 'locked', 'unknown')}")
    print(f"Firmware: {_firmware_version(device)}")
    print(f"Next schedule start: {_next_schedule_start(device)}")
    print(
        "Rain: triggered="
        f"{getattr(device.rainsensor, 'triggered', 'unknown')} "
        f"remaining={getattr(device.rainsensor, 'remaining', 'unknown')}"
    )
    print("-" * 72)
    print(f"Last event: {event_text}")
    print("-" * 72)
    print("Commands:")
    print("  r  = force refresh")
    print("  s  = start")
    print("  p  = pause")
    print("  h  = home")
    print("  sh = safehome")
    print("  e  = edgecut")
    print("  l  = lock/unlock (l on|off)")
    print("  rd = rain delay (minutes)")
    print("  ch = cutting height (mm)")
    print("  acs = acs on/off")
    print("  sc = show schedules page")
    print("  m  = choose another mower")
    print("  q  = quit")


async def _run_dashboard(cloud: WorxCloud) -> None:
    poll_interval = 60.0
    event_text = "no events yet"
    selected = await _choose_mower(cloud)
    last_poll = 0.0
    running = True
    input_task: asyncio.Task[str] | None = None
    input_in_progress = False
    dirty = True
    prompt_session = PromptSession() if _PROMPT_TOOLKIT_AVAILABLE else None

    async def _prompt_input(prompt: str) -> str:
        if prompt_session is None:
            return await _ainput(prompt)
        with patch_stdout(raw=True):
            return await prompt_session.prompt_async(prompt)

    def _on_data(name: str, device: DeviceHandler) -> None:
        nonlocal event_text, dirty
        event_text = (
            f"MQTT refresh for {name} | status={device.status.description}"
            f" | battery={_battery_percent(device)}%"
        )
        dirty = True

    def _on_api(name: str, device: DeviceHandler) -> None:
        nonlocal event_text, dirty
        event_text = (
            f"API refresh for {name} | status={device.status.description}"
            f" | battery={_battery_percent(device)}%"
        )
        dirty = True

    cloud.set_callback(LandroidEvent.DATA_RECEIVED, _on_data)
    cloud.set_callback(LandroidEvent.API, _on_api)

    try:
        while running:
            now = asyncio.get_running_loop().time()
            device = cloud.devices[selected]
            serial = device.serial_number

            # prompt_toolkit can redraw prompt safely while user is typing.
            if dirty and (not input_in_progress or prompt_session is not None):
                _render_device(device, selected, event_text)
                print("Format: command [args] | e.g.: l on, rd 90, ch 45, acs off")
                dirty = False

            if input_task is None:
                input_task = asyncio.create_task(_prompt_input("\ncmd> "))
                input_in_progress = True

            if now - last_poll >= poll_interval:
                try:
                    await cloud.update(serial)
                except Exception as err:  # pragma: no cover - interactive helper
                    event_text = f"Poll error: {type(err).__name__}: {err}"
                last_poll = now

            if input_task is None or not input_task.done():
                await asyncio.sleep(0.2)
                continue

            raw = input_task.result().strip()
            input_task = None
            input_in_progress = False

            parts = raw.lower().split()
            if not parts:
                continue

            # Keep a visible trace of the typed command in the dashboard event line.
            event_text = f"Command entered: {raw}"
            # Redraw quickly after each command input so typed text is not left on screen.
            dirty = True
            command = parts[0]
            args = parts[1:]

            try:
                if command == "q":
                    print("\nShutting down: closing cloud and MQTT connections...")
                    running = False
                    continue
                if command == "m":
                    selected = await _choose_mower(cloud)
                    event_text = f"Switched to {selected}"
                    dirty = True
                    continue
                if command == "r":
                    await cloud.update(serial)
                    continue
                if command == "s":
                    await cloud.start(serial)
                    continue
                if command == "p":
                    await cloud.pause(serial)
                    continue
                if command == "h":
                    await cloud.home(serial)
                    continue
                if command == "sh":
                    await cloud.safehome(serial)
                    continue
                if command == "e":
                    await cloud.edgecut(serial)
                    continue
                if command == "l":
                    if not args or args[0] not in {"on", "off"}:
                        event_text = "Usage: l on|off"
                        dirty = True
                        continue
                    await cloud.set_lock(serial, args[0] == "on")
                    continue
                if command == "rd":
                    if not args:
                        event_text = "Usage: rd <minutes>"
                        dirty = True
                        continue
                    await cloud.raindelay(serial, args[0])
                    continue
                if command == "ch":
                    if not args:
                        event_text = "Usage: ch <mm>"
                        dirty = True
                        continue
                    await cloud.set_cutting_height(serial, int(args[0]))
                    continue
                if command == "acs":
                    if not args or args[0] not in {"on", "off"}:
                        event_text = "Usage: acs on|off"
                        dirty = True
                        continue
                    await cloud.set_acs(serial, args[0] == "on")
                    continue
                if command == "sc":
                    await _show_schedule_view(device, selected)
                    dirty = True
                    continue
                event_text = f"Unknown command: {raw}"
                dirty = True
            except Exception as err:  # pragma: no cover - interactive helper
                event_text = f"Error: {type(err).__name__}: {err}"
                dirty = True
    finally:
        if input_task is not None:
            input_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await input_task


async def main() -> None:
    _load_dotenv()
    log_level = _configure_logging()
    if not _PROMPT_TOOLKIT_AVAILABLE:
        print(
            "Info: install 'prompt_toolkit' for fully non-blocking CLI prompt behavior."
        )
    email = environ.get("EMAIL") or await _ainput("EMAIL: ")
    password = environ.get("PASSWORD") or await _ainput("PASSWORD: ")
    cloud_type = environ.get("TYPE") or await _ainput("TYPE (worx/kress/landxcape): ")

    cloud = WorxCloud(email, password, cloud_type, tz="Europe/Copenhagen")
    cloud._log.setLevel(log_level)
    _configure_logging()
    await cloud.authenticate()
    await cloud.connect()
    try:
        await _run_dashboard(cloud)
    finally:
        await cloud.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
