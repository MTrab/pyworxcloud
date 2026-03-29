"""Windows-friendly GUI dashboard for live manual pyworxcloud testing."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import queue
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from os import environ
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, Toplevel, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from pyworxcloud import WorxCloud
from pyworxcloud.events import LandroidEvent
from pyworxcloud.utils import DeviceHandler

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows runtime
    winreg = None


REGISTRY_KEY = r"Software\pyworxcloud\Dashboard"


def _load_dotenv(path: str = ".env") -> None:
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


def _resolve_cloud_timezone() -> str | None:
    """Return optional client timezone override for live manual testing."""
    timezone_name = (
        environ.get("PYWORXCLOUD_TZ")
        or environ.get("WORXCLOUD_TZ")
        or environ.get("DASHBOARD_TZ")
    )
    if timezone_name is None:
        return None
    timezone_name = timezone_name.strip()
    return timezone_name or None


def _configure_logging() -> int:
    level_name = environ.get("DASHBOARD_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level)
    for name in ("pyworxcloud", "pyworxcloud.events", "pyworxcloud.utils.mqtt"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
    return level


def _read_registry_credentials() -> tuple[str, str, str] | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            email = winreg.QueryValueEx(key, "email")[0]
            password = winreg.QueryValueEx(key, "password")[0]
            cloud_type = winreg.QueryValueEx(key, "type")[0]
    except OSError:
        return None
    return str(email), str(password), str(cloud_type)


def _write_registry_credentials(email: str, password: str, cloud_type: str) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            winreg.SetValueEx(key, "email", 0, winreg.REG_SZ, email)
            winreg.SetValueEx(key, "password", 0, winreg.REG_SZ, password)
            winreg.SetValueEx(key, "type", 0, winreg.REG_SZ, cloud_type)
    except OSError:
        return False
    return True


def _battery_percent(device: DeviceHandler) -> str:
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


def _auto_schedule(device: DeviceHandler) -> dict[str, Any]:
    schedules = getattr(device, "schedules", None)
    if schedules is None:
        return {}
    value = None
    if isinstance(schedules, dict):
        value = schedules.get("auto_schedule")
    if value is None:
        try:
            value = schedules["auto_schedule"]  # type: ignore[index]
        except Exception:
            value = None
    return value if isinstance(value, dict) else {}


def _auto_schedule_summary(auto_schedule: dict[str, Any]) -> str:
    settings = auto_schedule.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}
    nutrition = settings.get("nutrition")
    nutrition_text = "off"
    if isinstance(nutrition, dict):
        nutrition_text = (
            f"n={nutrition.get('n', '?')},p={nutrition.get('p', '?')},k={nutrition.get('k', '?')}"
        )
    return (
        f"enabled={auto_schedule.get('enabled', False)} | "
        f"grass={settings.get('grass_type', '-') or '-'} | "
        f"soil={settings.get('soil_type', '-') or '-'} | "
        f"irrigation={settings.get('irrigation', False)} | "
        f"nutrition={nutrition_text}"
    )


def _auto_schedule_lines(auto_schedule: dict[str, Any]) -> list[str]:
    settings = auto_schedule.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}
    exclusion = settings.get("exclusion_scheduler", {})
    if not isinstance(exclusion, dict):
        exclusion = {}
    lines = [
        f"Auto schedule enabled: {auto_schedule.get('enabled', False)}",
        f"Boost: {settings.get('boost', '-')}",
        f"Grass type: {settings.get('grass_type', '-') or '-'}",
        f"Soil type: {settings.get('soil_type', '-') or '-'}",
        f"Irrigation: {settings.get('irrigation', False)}",
        f"Nutrition: {settings.get('nutrition', 'off')}",
        f"Exclude nights: {exclusion.get('exclude_nights', False)}",
    ]
    day_names = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ]
    days = exclusion.get("days", [])
    if isinstance(days, list):
        for idx, day in enumerate(days):
            if not isinstance(day, dict):
                continue
            slots = day.get("slots", [])
            if day.get("exclude_day") or slots:
                slot_texts = []
                if isinstance(slots, list):
                    for slot in slots:
                        if not isinstance(slot, dict):
                            continue
                        slot_texts.append(
                            "start="
                            f"{slot.get('start_time', '?')}m "
                            f"duration={slot.get('duration', '?')}m "
                            f"reason={slot.get('reason', '-')}"
                        )
                detail = "; ".join(slot_texts) if slot_texts else "full-day exclude"
                lines.append(
                    f"{day_names[idx] if idx < len(day_names) else idx}: {detail}"
                )
    return lines


def _snapshot_device(device: DeviceHandler) -> dict[str, Any]:
    device_updated = getattr(device, "updated", None)
    if device_updated is None:
        last_status = getattr(device, "last_status", None)
        if isinstance(last_status, dict):
            device_updated = last_status.get("timestamp")

    device_updated_raw = "unknown"
    if isinstance(device_updated, datetime):
        device_updated_raw = device_updated.isoformat()

    auto_schedule = _auto_schedule(device)
    return {
        "name": getattr(device, "name", "unknown"),
        "serial": getattr(device, "serial_number", "unknown"),
        "model": str(getattr(device, "model", "unknown")),
        "online": str(getattr(device, "online", "unknown")),
        "status": str(getattr(device.status, "description", "unknown")),
        "error": str(getattr(device.error, "description", "unknown")),
        "battery": _battery_percent(device),
        "locked": str(getattr(device, "locked", "unknown")),
        "firmware": _firmware_version(device),
        "next_start": _next_schedule_start(device),
        "auto_schedule_summary": _auto_schedule_summary(auto_schedule),
        "auto_schedule_lines": _auto_schedule_lines(auto_schedule),
        "rain_triggered": str(getattr(device.rainsensor, "triggered", "unknown")),
        "rain_remaining": str(getattr(device.rainsensor, "remaining", "unknown")),
        "device_updated": (
            str(device_updated) if device_updated is not None else "unknown"
        ),
        "device_updated_raw": device_updated_raw,
        "device_timezone": str(getattr(device, "time_zone", "unknown")),
        "schedules": _schedule_slots(device),
    }


@dataclass
class WorkerMessage:
    msg_type: str
    payload: dict[str, Any]


class CloudWorker:
    def __init__(self, messages: queue.Queue[WorkerMessage]) -> None:
        self._messages = messages
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._cloud: WorxCloud | None = None
        self._selected_name: str | None = None
        self._log_level = _configure_logging()
        self._update_event = asyncio.Event()
        self._update_event_name: str | None = None

    def _mark_update_received(self, name: str) -> None:
        """Mark update event from any thread in a loop-safe way."""

        def _set() -> None:
            self._update_event_name = name
            self._update_event.set()

        self._loop.call_soon_threadsafe(_set)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _emit(self, msg_type: str, **payload: Any) -> None:
        self._messages.put(WorkerMessage(msg_type=msg_type, payload=payload))

    def submit(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def connect(self, email: str, password: str, cloud_type: str) -> None:
        if self._cloud is not None:
            await self.disconnect()

        self._cloud = WorxCloud(
            email,
            password,
            cloud_type,
            tz=_resolve_cloud_timezone(),
        )
        self._cloud._log.setLevel(self._log_level)
        _configure_logging()

        def _on_data(name: str, device: DeviceHandler) -> None:
            self._mark_update_received(name)
            self._emit(
                "device_update",
                source="mqtt",
                name=name,
                snapshot=_snapshot_device(device),
            )

        def _on_api(name: str, device: DeviceHandler) -> None:
            self._mark_update_received(name)
            self._emit(
                "device_update",
                source="api",
                name=name,
                snapshot=_snapshot_device(device),
            )

        self._cloud.set_callback(LandroidEvent.DATA_RECEIVED, _on_data)
        self._cloud.set_callback(LandroidEvent.API, _on_api)

        await self._cloud.authenticate()
        await self._cloud.connect()

        mowers: list[dict[str, Any]] = []
        for name, device in self._cloud.devices.items():
            mowers.append(
                {
                    "name": name,
                    "serial": getattr(device, "serial_number", "unknown"),
                    "online": getattr(device, "online", "unknown"),
                }
            )
            self._emit(
                "device_update",
                source="connect",
                name=name,
                snapshot=_snapshot_device(device),
            )

        if mowers:
            self._selected_name = mowers[0]["name"]
        self._emit("connected", mowers=mowers, selected=self._selected_name)

    async def disconnect(self) -> None:
        if self._cloud is not None:
            with contextlib.suppress(Exception):
                await self._cloud.disconnect()
            self._cloud = None
            self._selected_name = None
            self._emit("disconnected")

    async def shutdown(self) -> None:
        await self.disconnect()
        self._loop.call_soon_threadsafe(self._loop.stop)

    async def select_mower(self, name: str) -> None:
        if self._cloud is None:
            return
        resolved_name, device = self._resolve_device(name)
        self._selected_name = resolved_name
        if device is None:
            return
        await self._cloud.update(device.serial_number)

    async def refresh(self, selected_name: str | None = None) -> None:
        if self._cloud is None:
            raise RuntimeError("Not connected.")
        if selected_name:
            self._selected_name = selected_name
        if not self._selected_name:
            raise RuntimeError("No mower selected.")
        selected, device = self._resolve_device(self._selected_name)
        self._selected_name = selected
        if device is None:
            known = ", ".join(repr(k) for k in self._cloud.devices.keys()) or "none"
            raise RuntimeError(
                f"Selected mower {selected!r} not found. Known mower keys: {known}"
            )
        mower = self._cloud.get_mower(device.serial_number)
        identifier = device.serial_number
        protocol = mower["protocol"]
        in_topic = mower["mqtt_topics"]["command_in"]
        self._emit(
            "log",
            text=(
                f"Refresh dispatch: mower={selected}, serial={device.serial_number}, "
                f"protocol={protocol}, topic={in_topic}"
            ),
        )

        self._update_event.clear()
        self._update_event_name = None
        self._emit("log", text="Sending forced refresh command...")
        # Keep the exact same refresh entrypoint as CLI dashboard.
        await self._cloud.update(device.serial_number)
        self._emit("log", text="Forced refresh command sent. Waiting for update...")
        got_live_update = False
        try:
            await asyncio.wait_for(self._update_event.wait(), timeout=3.0)
            got_live_update = self._update_event_name == selected
        except TimeoutError:
            got_live_update = False

        if not got_live_update:
            # Fallback to API fetch if mower does not publish a changed MQTT payload.
            self._emit(
                "log",
                text=(
                    "No selected-mower MQTT update observed within timeout; "
                    "running API fallback fetch."
                ),
            )
            await self._cloud._fetch()  # noqa: SLF001
            updated_device = self._cloud.devices.get(selected)
            if updated_device is not None:
                device = updated_device

        self._emit(
            "refresh_done",
            name=selected,
            snapshot=_snapshot_device(device),
            at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source="mqtt" if got_live_update else "api-fallback",
            target=identifier,
        )

    async def _with_selected_serial(self) -> str | None:
        if self._cloud is None or not self._selected_name:
            return None
        selected, device = self._resolve_device(self._selected_name)
        self._selected_name = selected
        if device is None:
            return None
        return device.serial_number

    def _resolve_device(self, name: str) -> tuple[str, DeviceHandler | None]:
        """Resolve mower key robustly from potentially noisy UI input."""
        if self._cloud is None:
            return name, None
        devices = self._cloud.devices
        if name in devices:
            return name, devices[name]

        normalized = str(name).strip()
        if normalized in devices:
            return normalized, devices[normalized]

        folded = self._normalize_key(normalized)
        for key, device in devices.items():
            if self._normalize_key(str(key)) == folded:
                return key, device
            device_name = getattr(device, "name", None)
            if (
                device_name is not None
                and self._normalize_key(str(device_name)) == folded
            ):
                return key, device

        # If exactly one mower exists, prefer deterministic fallback instead of failing.
        if len(devices) == 1:
            only_key = next(iter(devices))
            return only_key, devices[only_key]

        return normalized, None

    @staticmethod
    def _normalize_key(value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        return "".join(
            ch for ch in value if ch.isprintable() and not ch.isspace()
        ).casefold()

    async def action(self, command: str, value: Any = None) -> None:
        if self._cloud is None:
            return
        serial = await self._with_selected_serial()
        if serial is None:
            return
        if command == "start":
            await self._cloud.start(serial)
        elif command == "pause":
            await self._cloud.pause(serial)
        elif command == "home":
            await self._cloud.home(serial)
        elif command == "safehome":
            await self._cloud.safehome(serial)
        elif command == "edgecut":
            await self._cloud.edgecut(serial)
        elif command == "lock":
            await self._cloud.set_lock(serial, bool(value))
        elif command == "raindelay":
            await self._cloud.raindelay(serial, str(value))
        elif command == "cutting_height":
            await self._cloud.set_cutting_height(serial, int(value))
        elif command == "acs":
            await self._cloud.set_acs(serial, bool(value))


class DashboardApp:
    def __init__(self) -> None:
        _load_dotenv()
        registry_credentials = _read_registry_credentials()
        default_email = environ.get("EMAIL", "")
        default_password = environ.get("PASSWORD", "")
        default_type = environ.get("TYPE", "worx")
        if registry_credentials is not None:
            default_email, default_password, default_type = registry_credentials

        self.root = Tk()
        self.root.title("pyworxcloud Windows Dashboard")
        self.root.geometry("980x720")

        self.messages: queue.Queue[WorkerMessage] = queue.Queue()
        self.worker = CloudWorker(self.messages)
        self.device_cache: dict[str, dict[str, Any]] = {}
        self.connected = False
        self._closing = False
        self._shutdown_popup: Toplevel | None = None
        self._status_popup: Toplevel | None = None
        self._requires_connection_widgets: list[Any] = []
        self._pending_connection_action: str | None = None

        self.email_var = StringVar(value=default_email)
        self.password_var = StringVar(value=default_password)
        self.type_var = StringVar(value=default_type)
        self.mower_var = StringVar(value="")
        self.lock_var = BooleanVar(value=False)
        self.acs_var = BooleanVar(value=False)
        self.rain_var = StringVar(value="90")
        self.height_var = StringVar(value="45")
        self.last_event_var = StringVar(value="No events yet")

        self.status_vars = {
            "serial": StringVar(value="-"),
            "model": StringVar(value="-"),
            "online": StringVar(value="-"),
            "status": StringVar(value="-"),
            "error": StringVar(value="-"),
            "battery": StringVar(value="-"),
            "locked": StringVar(value="-"),
            "firmware": StringVar(value="-"),
            "next_start": StringVar(value="-"),
            "auto_schedule": StringVar(value="-"),
            "rain": StringVar(value="-"),
            "last_refresh": StringVar(value="-"),
        }

        self._build_ui()
        self._set_controls(False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._process_messages)

    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        conn = ttk.LabelFrame(root, text="Connection")
        conn.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        for idx in range(8):
            conn.columnconfigure(idx, weight=1)

        ttk.Label(conn, text="Email").grid(row=0, column=0, sticky="w")
        self.email_entry = ttk.Entry(conn, textvariable=self.email_var, width=25)
        self.email_entry.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(conn, text="Password").grid(row=0, column=2, sticky="w")
        self.password_entry = ttk.Entry(
            conn, textvariable=self.password_var, show="*", width=20
        )
        self.password_entry.grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Label(conn, text="Type").grid(row=0, column=4, sticky="w")
        self.type_combo = ttk.Combobox(
            conn,
            textvariable=self.type_var,
            values=("worx", "kress", "landxcape"),
            state="readonly",
            width=12,
        )
        self.type_combo.grid(row=0, column=5, sticky="w", padx=4)
        self.connect_button = ttk.Button(conn, text="Connect", command=self._connect)
        self.connect_button.grid(row=0, column=6, padx=4)
        self.disconnect_button = ttk.Button(
            conn, text="Disconnect", command=self._disconnect, state="disabled"
        )
        self.disconnect_button.grid(row=0, column=7, padx=4)

        mower = ttk.LabelFrame(root, text="Mower")
        mower.grid(row=1, column=0, sticky="ew", padx=10, pady=8)
        mower.columnconfigure(1, weight=1)
        ttk.Label(mower, text="Selected mower").grid(row=0, column=0, sticky="w")
        self.mower_combo = ttk.Combobox(
            mower, textvariable=self.mower_var, state="disabled"
        )
        self.mower_combo.grid(row=0, column=1, sticky="ew", padx=4)
        self.mower_combo.bind("<<ComboboxSelected>>", self._on_mower_selected)
        self.refresh_button = ttk.Button(mower, text="Refresh", command=self._refresh)
        self.refresh_button.grid(row=0, column=2, padx=4)
        self._requires_connection_widgets.append(self.refresh_button)

        status = ttk.LabelFrame(root, text="Live Status")
        status.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        for i in range(4):
            status.columnconfigure(i, weight=1)
        fields = [
            ("Serial", "serial"),
            ("Model", "model"),
            ("Online", "online"),
            ("Status", "status"),
            ("Error", "error"),
            ("Battery", "battery"),
            ("Locked", "locked"),
            ("Firmware", "firmware"),
            ("Next schedule start", "next_start"),
            ("Auto schedule", "auto_schedule"),
            ("Rain", "rain"),
            ("Last data refresh", "last_refresh"),
        ]
        for idx, (label, key) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(status, text=label).grid(row=row, column=col, sticky="w", pady=2)
            ttk.Label(status, textvariable=self.status_vars[key]).grid(
                row=row, column=col + 1, sticky="w", pady=2
            )
        ttk.Label(status, text="Last event").grid(row=5, column=0, sticky="w", pady=2)
        ttk.Label(status, textvariable=self.last_event_var).grid(
            row=5, column=1, columnspan=3, sticky="w", pady=2
        )

        center = ttk.Panedwindow(root, orient="horizontal")
        center.grid(row=3, column=0, sticky="nsew", padx=10, pady=8)

        actions = ttk.LabelFrame(center, text="Actions")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        start_button = ttk.Button(
            actions, text="Start", command=lambda: self._action("start")
        )
        start_button.grid(row=0, column=0, sticky="ew", padx=4, pady=3)
        pause_button = ttk.Button(
            actions, text="Pause", command=lambda: self._action("pause")
        )
        pause_button.grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        home_button = ttk.Button(
            actions, text="Home", command=lambda: self._action("home")
        )
        home_button.grid(row=1, column=0, sticky="ew", padx=4, pady=3)
        safehome_button = ttk.Button(
            actions, text="Safehome", command=lambda: self._action("safehome")
        )
        safehome_button.grid(row=1, column=1, sticky="ew", padx=4, pady=3)
        edgecut_button = ttk.Button(
            actions, text="Edgecut", command=lambda: self._action("edgecut")
        )
        edgecut_button.grid(row=2, column=0, sticky="ew", padx=4, pady=3)
        self._requires_connection_widgets.extend(
            [start_button, pause_button, home_button, safehome_button, edgecut_button]
        )

        lock_check = ttk.Checkbutton(actions, text="Lock", variable=self.lock_var)
        lock_check.grid(row=3, column=0, sticky="w", padx=4, pady=6)
        apply_lock_button = ttk.Button(
            actions, text="Apply Lock", command=self._apply_lock
        )
        apply_lock_button.grid(row=3, column=1, sticky="ew", padx=4, pady=3)
        self._requires_connection_widgets.extend([lock_check, apply_lock_button])

        ttk.Label(actions, text="Rain delay (minutes)").grid(
            row=4, column=0, sticky="w", padx=4
        )
        self.rain_entry = ttk.Entry(actions, textvariable=self.rain_var, width=12)
        self.rain_entry.grid(row=4, column=1, sticky="ew", padx=4)
        apply_rain_button = ttk.Button(
            actions, text="Apply Rain Delay", command=self._apply_raindelay
        )
        apply_rain_button.grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=4, pady=3
        )
        self._requires_connection_widgets.extend([self.rain_entry, apply_rain_button])

        ttk.Label(actions, text="Cutting height (mm)").grid(
            row=6, column=0, sticky="w", padx=4
        )
        self.height_entry = ttk.Entry(actions, textvariable=self.height_var, width=12)
        self.height_entry.grid(row=6, column=1, sticky="ew", padx=4)
        apply_height_button = ttk.Button(
            actions, text="Apply Cutting Height", command=self._apply_cutting_height
        )
        apply_height_button.grid(
            row=7, column=0, columnspan=2, sticky="ew", padx=4, pady=3
        )
        self._requires_connection_widgets.extend(
            [self.height_entry, apply_height_button]
        )

        acs_check = ttk.Checkbutton(actions, text="ACS enabled", variable=self.acs_var)
        acs_check.grid(row=8, column=0, sticky="w", padx=4, pady=6)
        apply_acs_button = ttk.Button(
            actions, text="Apply ACS", command=self._apply_acs
        )
        apply_acs_button.grid(row=8, column=1, sticky="ew", padx=4, pady=3)
        self._requires_connection_widgets.extend([acs_check, apply_acs_button])

        schedules = ttk.LabelFrame(center, text="Schedules")
        schedules.rowconfigure(1, weight=1)
        schedules.columnconfigure(0, weight=1)
        ttk.Label(
            schedules, text="Parsed slots (day, start-end, duration, source)"
        ).grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.schedule_list = ScrolledText(schedules, height=16, wrap="none")
        self.schedule_list.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.schedule_list.configure(state="disabled")

        center.add(actions, weight=1)
        center.add(schedules, weight=1)

        logs = ttk.LabelFrame(root, text="Log")
        logs.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 10))
        logs.columnconfigure(0, weight=1)
        logs.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(logs, height=8, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.log_text.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_controls(self, connected: bool) -> None:
        self._pending_connection_action = None
        self._hide_status_popup()
        self.connected = connected
        mower_state = "readonly" if connected else "disabled"
        self.mower_combo.configure(state=mower_state)
        self.connect_button.configure(state="disabled" if connected else "normal")
        self.disconnect_button.configure(state="normal" if connected else "disabled")
        self.email_entry.configure(state="disabled" if connected else "normal")
        self.password_entry.configure(state="disabled" if connected else "normal")
        self.type_combo.configure(state="disabled" if connected else "readonly")
        for widget in self._requires_connection_widgets:
            widget.configure(state="normal" if connected else "disabled")

    def _set_connecting_pending(self) -> None:
        self._pending_connection_action = "connect"
        self._show_status_popup(
            "Connecting", "Connecting to cloud and MQTT...\nPlease wait..."
        )
        self.connect_button.configure(state="disabled")
        self.disconnect_button.configure(state="disabled")
        self.email_entry.configure(state="disabled")
        self.password_entry.configure(state="disabled")
        self.type_combo.configure(state="disabled")
        self.mower_combo.configure(state="disabled")
        for widget in self._requires_connection_widgets:
            widget.configure(state="disabled")

    def _set_disconnecting_pending(self) -> None:
        self._pending_connection_action = "disconnect"
        self._show_status_popup(
            "Disconnecting", "Disconnecting from cloud and MQTT...\nPlease wait..."
        )
        self.connect_button.configure(state="disabled")
        self.disconnect_button.configure(state="disabled")
        self.email_entry.configure(state="disabled")
        self.password_entry.configure(state="disabled")
        self.type_combo.configure(state="disabled")
        self.mower_combo.configure(state="disabled")
        for widget in self._requires_connection_widgets:
            widget.configure(state="disabled")

    def _show_status_popup(self, title: str, message: str) -> None:
        self._hide_status_popup()
        popup = Toplevel(self.root)
        popup.title(title)
        popup.transient(self.root)
        popup.grab_set()
        popup.resizable(False, False)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(popup, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text=message, justify="center").grid(
            row=0, column=0, sticky="nsew"
        )

        popup.update_idletasks()
        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        pop_w = popup.winfo_width()
        pop_h = popup.winfo_height()
        x = root_x + max((root_w - pop_w) // 2, 0)
        y = root_y + max((root_h - pop_h) // 2, 0)
        popup.geometry(f"+{x}+{y}")
        self._status_popup = popup

    def _hide_status_popup(self) -> None:
        if self._status_popup is None:
            return
        with contextlib.suppress(Exception):
            self._status_popup.grab_release()
        with contextlib.suppress(Exception):
            self._status_popup.destroy()
        self._status_popup = None

    def _connect(self) -> None:
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        cloud_type = self.type_var.get().strip() or "worx"
        if not email or not password:
            self._append_log("Missing email or password.")
            return
        if _write_registry_credentials(email, password, cloud_type):
            self._append_log("Account credentials saved to Windows Registry.")
        self._append_log("Connecting...")
        self._set_connecting_pending()
        fut = self.worker.submit(self.worker.connect(email, password, cloud_type))
        fut.add_done_callback(self._future_error_to_log)

    def _disconnect(self) -> None:
        self._append_log("Disconnecting...")
        self._set_disconnecting_pending()
        fut = self.worker.submit(self.worker.disconnect())
        fut.add_done_callback(self._future_error_to_log)

    def _refresh(self) -> None:
        self._append_log("Refresh requested...")
        selected_name = self.mower_var.get().strip() or None
        fut = self.worker.submit(self.worker.refresh(selected_name))
        fut.add_done_callback(self._future_error_to_log)

    def _on_mower_selected(self, _event: Any) -> None:
        name = self.mower_var.get().strip()
        if not name:
            return
        fut = self.worker.submit(self.worker.select_mower(name))
        fut.add_done_callback(self._future_error_to_log)

    def _action(self, command: str) -> None:
        fut = self.worker.submit(self.worker.action(command))
        fut.add_done_callback(self._future_error_to_log)

    def _apply_lock(self) -> None:
        fut = self.worker.submit(self.worker.action("lock", self.lock_var.get()))
        fut.add_done_callback(self._future_error_to_log)

    def _apply_raindelay(self) -> None:
        value = self.rain_var.get().strip()
        if not value.isdigit():
            self._append_log("Rain delay must be numeric.")
            return
        fut = self.worker.submit(self.worker.action("raindelay", value))
        fut.add_done_callback(self._future_error_to_log)

    def _apply_cutting_height(self) -> None:
        value = self.height_var.get().strip()
        if not value.isdigit():
            self._append_log("Cutting height must be numeric.")
            return
        fut = self.worker.submit(self.worker.action("cutting_height", value))
        fut.add_done_callback(self._future_error_to_log)

    def _apply_acs(self) -> None:
        fut = self.worker.submit(self.worker.action("acs", self.acs_var.get()))
        fut.add_done_callback(self._future_error_to_log)

    def _future_error_to_log(self, fut: Any) -> None:
        err = fut.exception()
        if err is None:
            return
        pending_action = self._pending_connection_action
        if pending_action == "connect":
            self._set_controls(False)
        elif pending_action == "disconnect":
            self._set_controls(True)
        self.messages.put(
            WorkerMessage(
                msg_type="error", payload={"text": f"{type(err).__name__}: {err}"}
            )
        )

    def _future_success_to_log(self, fut: Any, text: str) -> None:
        if fut.exception() is not None:
            return
        self.messages.put(WorkerMessage(msg_type="log", payload={"text": text}))

    def _switch_account(self, reconnect: bool = True) -> None:
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        cloud_type = self.type_var.get().strip() or "worx"
        if not email or not password:
            self._append_log("Missing email or password.")
            return
        if _write_registry_credentials(email, password, cloud_type):
            self._append_log("Account credentials saved to Windows Registry.")
        if reconnect:
            self._append_log("Switching account and reconnecting...")
            fut = self.worker.submit(self.worker.connect(email, password, cloud_type))
            fut.add_done_callback(self._future_error_to_log)

    def _open_account_dialog(self) -> None:
        dialog = Toplevel(self.root)
        dialog.title("Switch Account")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        email_var = StringVar(value=self.email_var.get())
        password_var = StringVar(value=self.password_var.get())
        type_var = StringVar(value=self.type_var.get() or "worx")
        reconnect_var = BooleanVar(value=True)

        frame = ttk.Frame(dialog, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Email").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(frame, textvariable=email_var, width=38).grid(
            row=0, column=1, sticky="ew", pady=2
        )
        ttk.Label(frame, text="Password").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(frame, textvariable=password_var, show="*", width=38).grid(
            row=1, column=1, sticky="ew", pady=2
        )
        ttk.Label(frame, text="Type").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Combobox(
            frame,
            textvariable=type_var,
            values=("worx", "kress", "landxcape"),
            state="readonly",
            width=20,
        ).grid(row=2, column=1, sticky="w", pady=2)

        ttk.Checkbutton(
            frame,
            text="Reconnect immediately after save",
            variable=reconnect_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 2))

        btns = ttk.Frame(frame)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))

        def _apply() -> None:
            self.email_var.set(email_var.get().strip())
            self.password_var.set(password_var.get().strip())
            self.type_var.set(type_var.get().strip() or "worx")
            self._switch_account(reconnect=reconnect_var.get())
            dialog.destroy()

        ttk.Button(btns, text="Cancel", command=dialog.destroy).grid(
            row=0, column=0, padx=4
        )
        ttk.Button(btns, text="Save", command=_apply).grid(row=0, column=1, padx=4)

    def _render_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.status_vars["serial"].set(str(snapshot.get("serial", "-")))
        self.status_vars["model"].set(str(snapshot.get("model", "-")))
        self.status_vars["online"].set(str(snapshot.get("online", "-")))
        self.status_vars["status"].set(str(snapshot.get("status", "-")))
        self.status_vars["error"].set(str(snapshot.get("error", "-")))
        self.status_vars["battery"].set(f"{snapshot.get('battery', '-')}%")
        self.status_vars["locked"].set(str(snapshot.get("locked", "-")))
        self.status_vars["firmware"].set(str(snapshot.get("firmware", "-")))
        self.status_vars["next_start"].set(str(snapshot.get("next_start", "-")))
        self.status_vars["auto_schedule"].set(
            str(snapshot.get("auto_schedule_summary", "-"))
        )
        self.status_vars["rain"].set(
            f"triggered={snapshot.get('rain_triggered', '-')} remaining={snapshot.get('rain_remaining', '-')}"
        )
        self.status_vars["last_refresh"].set(
            " | ".join(
                [
                    f"raw={snapshot.get('device_updated_raw', 'unknown')}",
                    f"ui={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                ]
            )
        )
        self.schedule_list.configure(state="normal")
        self.schedule_list.delete("1.0", "end")
        for line in snapshot.get("auto_schedule_lines", []):
            self.schedule_list.insert("end", f"{line}\n")
        if snapshot.get("auto_schedule_lines"):
            self.schedule_list.insert("end", "-" * 72 + "\n")
        for slot in snapshot.get("schedules", []):
            self.schedule_list.insert(
                "end",
                (
                    f"{slot.get('day', 'unknown'):9}  {slot.get('start', '?')}-{slot.get('end', '?')}  "
                    f"duration={slot.get('duration_extended', slot.get('duration', '?'))}m  "
                    f"boundary={slot.get('boundary', False)}  source={slot.get('source', 'unknown')}\n"
                ),
            )
        self.schedule_list.configure(state="disabled")

    def _process_messages(self) -> None:
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break

            if message.msg_type == "connected":
                mowers = message.payload.get("mowers", [])
                names = [item["name"] for item in mowers]
                self.mower_combo.configure(values=names)
                if names:
                    selected = message.payload.get("selected") or names[0]
                    self.mower_var.set(selected)
                    self._append_log(f"Connected. Selected mower: {selected}")
                    # Initial connect updates can arrive before mower selection is set in UI.
                    # Render cached snapshot immediately and force a refresh for a fresh state.
                    cached = self.device_cache.get(selected)
                    if isinstance(cached, dict):
                        self._render_snapshot(cached)
                    fut = self.worker.submit(self.worker.select_mower(selected))
                    fut.add_done_callback(self._future_error_to_log)
                else:
                    self._append_log("Connected, but no mowers available.")
                self._set_controls(True)
            elif message.msg_type == "disconnected":
                self._append_log("Disconnected.")
                self._set_controls(False)
                self.mower_combo.configure(values=[])
                self.mower_var.set("")
                self.last_event_var.set("No events yet")
            elif message.msg_type == "device_update":
                name = str(message.payload.get("name", "unknown"))
                source = str(message.payload.get("source", "update"))
                snapshot = message.payload.get("snapshot", {})
                if isinstance(snapshot, dict):
                    self.device_cache[name] = snapshot
                if name == self.mower_var.get():
                    self._render_snapshot(snapshot)
                if isinstance(snapshot, dict):
                    status = str(snapshot.get("status", "unknown"))
                    battery = str(snapshot.get("battery", "unknown"))
                    self._append_log(
                        f"{source.upper()} update received for {name}: status={status}, battery={battery}%."
                    )
                else:
                    self._append_log(f"{source.upper()} update received for {name}.")
                self.last_event_var.set(f"{source.upper()} update for {name}")
            elif message.msg_type == "error":
                text = str(message.payload.get("text", "Unknown error"))
                self._append_log(f"Error: {text}")
            elif message.msg_type == "log":
                text = str(message.payload.get("text", ""))
                if text:
                    self._append_log(text)
            elif message.msg_type == "refresh_done":
                name = str(message.payload.get("name", "unknown"))
                snapshot = message.payload.get("snapshot", {})
                at = str(message.payload.get("at", "unknown"))
                source = str(message.payload.get("source", "unknown"))
                target = str(message.payload.get("target", "unknown"))
                if isinstance(snapshot, dict):
                    self.device_cache[name] = snapshot
                if isinstance(snapshot, dict):
                    # Always refresh the visible dashboard on explicit manual refresh.
                    self._render_snapshot(snapshot)
                self._append_log(
                    f"Refresh completed via {source} (target={target}) at {at}."
                )
                self.last_event_var.set(
                    f"Manual refresh completed for {name} at {at} ({source}, target={target})"
                )

        self.root.after(150, self._process_messages)

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._show_shutdown_popup()
        self._append_log("Shutting down...")
        future = self.worker.submit(self.worker.shutdown())
        self._poll_shutdown_future(future)

    def _show_shutdown_popup(self) -> None:
        popup = Toplevel(self.root)
        popup.title("Shutting down")
        popup.transient(self.root)
        popup.grab_set()
        popup.resizable(False, False)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(popup, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            frame,
            text="Closing cloud and MQTT connections.\nPlease wait...",
            justify="center",
        ).grid(row=0, column=0, sticky="nsew")

        popup.update_idletasks()
        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        pop_w = popup.winfo_width()
        pop_h = popup.winfo_height()
        x = root_x + max((root_w - pop_w) // 2, 0)
        y = root_y + max((root_h - pop_h) // 2, 0)
        popup.geometry(f"+{x}+{y}")
        self._shutdown_popup = popup

    def _poll_shutdown_future(self, future: Any) -> None:
        if not future.done():
            self.root.after(100, lambda: self._poll_shutdown_future(future))
            return
        with contextlib.suppress(Exception):
            future.result()
        if self._shutdown_popup is not None:
            with contextlib.suppress(Exception):
                self._shutdown_popup.destroy()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    DashboardApp().run()
