"""Windows-friendly GUI dashboard for live manual pyworxcloud testing."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import queue
import threading
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


def _configure_logging() -> int:
    level_name = environ.get("DASHBOARD_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    for name in ("pyworxcloud", "pyworxcloud.events", "pyworxcloud.utils.mqtt"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
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


def _snapshot_device(device: DeviceHandler) -> dict[str, Any]:
    device_updated = getattr(device, "updated", None)
    if device_updated is None:
        last_status = getattr(device, "last_status", None)
        if isinstance(last_status, dict):
            device_updated = last_status.get("timestamp")

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
        "rain_triggered": str(getattr(device.rainsensor, "triggered", "unknown")),
        "rain_remaining": str(getattr(device.rainsensor, "remaining", "unknown")),
        "device_updated": str(device_updated) if device_updated is not None else "unknown",
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
        self._poll_task: asyncio.Task | None = None
        self._selected_name: str | None = None
        self._log_level = _configure_logging()

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

        self._cloud = WorxCloud(email, password, cloud_type, tz="Europe/Copenhagen")
        self._cloud._log.setLevel(self._log_level)
        for handler in self._cloud._log.handlers:
            handler.setLevel(self._log_level)
        _configure_logging()

        def _on_data(name: str, device: DeviceHandler) -> None:
            self._emit("device_update", source="mqtt", name=name, snapshot=_snapshot_device(device))

        def _on_api(name: str, device: DeviceHandler) -> None:
            self._emit("device_update", source="api", name=name, snapshot=_snapshot_device(device))

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
            self._emit("device_update", source="connect", name=name, snapshot=_snapshot_device(device))

        if mowers:
            self._selected_name = mowers[0]["name"]
        self._emit("connected", mowers=mowers, selected=self._selected_name)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        while self._cloud is not None:
            await asyncio.sleep(60)
            if self._cloud is None or not self._selected_name:
                continue
            device = self._cloud.devices.get(self._selected_name)
            if not device:
                continue
            with contextlib.suppress(Exception):
                await self._cloud.update(device.serial_number)

    async def disconnect(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None

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
        self._selected_name = name
        if self._cloud is None:
            return
        device = self._cloud.devices.get(name)
        if not device:
            return
        await self._cloud.update(device.serial_number)

    async def refresh(self) -> None:
        if self._cloud is None or not self._selected_name:
            return
        selected = self._selected_name
        device = self._cloud.devices.get(selected)
        if not device:
            return
        await self._cloud.update(device.serial_number)
        # Even if payload is unchanged, emit a refresh completion snapshot for UI feedback.
        self._emit(
            "refresh_done",
            name=selected,
            snapshot=_snapshot_device(device),
            at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    async def _with_selected_serial(self) -> str | None:
        if self._cloud is None or not self._selected_name:
            return None
        device = self._cloud.devices.get(self._selected_name)
        if not device:
            return None
        return device.serial_number

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
            "rain": StringVar(value="-"),
            "last_refresh": StringVar(value="-"),
        }

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._process_messages)

    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        conn = ttk.LabelFrame(root, text="Connection")
        conn.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        for idx in range(9):
            conn.columnconfigure(idx, weight=1)

        ttk.Label(conn, text="Email").grid(row=0, column=0, sticky="w")
        ttk.Entry(conn, textvariable=self.email_var, width=25).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(conn, text="Password").grid(row=0, column=2, sticky="w")
        ttk.Entry(conn, textvariable=self.password_var, show="*", width=20).grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Label(conn, text="Type").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            conn,
            textvariable=self.type_var,
            values=("worx", "kress", "landxcape"),
            state="readonly",
            width=12,
        ).grid(row=0, column=5, sticky="w", padx=4)
        ttk.Button(conn, text="Connect", command=self._connect).grid(row=0, column=6, padx=4)
        ttk.Button(conn, text="Disconnect", command=self._disconnect).grid(row=0, column=7, padx=4)
        ttk.Button(conn, text="Switch Account", command=self._open_account_dialog).grid(row=0, column=8, padx=4)

        mower = ttk.LabelFrame(root, text="Mower")
        mower.grid(row=1, column=0, sticky="ew", padx=10, pady=8)
        mower.columnconfigure(1, weight=1)
        ttk.Label(mower, text="Selected mower").grid(row=0, column=0, sticky="w")
        self.mower_combo = ttk.Combobox(mower, textvariable=self.mower_var, state="disabled")
        self.mower_combo.grid(row=0, column=1, sticky="ew", padx=4)
        self.mower_combo.bind("<<ComboboxSelected>>", self._on_mower_selected)
        ttk.Button(mower, text="Refresh", command=self._refresh).grid(row=0, column=2, padx=4)

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
            ("Rain", "rain"),
            ("Last data refresh", "last_refresh"),
        ]
        for idx, (label, key) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(status, text=label).grid(row=row, column=col, sticky="w", pady=2)
            ttk.Label(status, textvariable=self.status_vars[key]).grid(row=row, column=col + 1, sticky="w", pady=2)
        ttk.Label(status, text="Last event").grid(row=5, column=0, sticky="w", pady=2)
        ttk.Label(status, textvariable=self.last_event_var).grid(row=5, column=1, columnspan=3, sticky="w", pady=2)

        center = ttk.Panedwindow(root, orient="horizontal")
        center.grid(row=3, column=0, sticky="nsew", padx=10, pady=8)

        actions = ttk.LabelFrame(center, text="Actions")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Start", command=lambda: self._action("start")).grid(row=0, column=0, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Pause", command=lambda: self._action("pause")).grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Home", command=lambda: self._action("home")).grid(row=1, column=0, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Safehome", command=lambda: self._action("safehome")).grid(row=1, column=1, sticky="ew", padx=4, pady=3)
        ttk.Button(actions, text="Edgecut", command=lambda: self._action("edgecut")).grid(row=2, column=0, sticky="ew", padx=4, pady=3)

        ttk.Checkbutton(actions, text="Lock", variable=self.lock_var).grid(row=3, column=0, sticky="w", padx=4, pady=6)
        ttk.Button(actions, text="Apply Lock", command=self._apply_lock).grid(row=3, column=1, sticky="ew", padx=4, pady=3)

        ttk.Label(actions, text="Rain delay (minutes)").grid(row=4, column=0, sticky="w", padx=4)
        ttk.Entry(actions, textvariable=self.rain_var, width=12).grid(row=4, column=1, sticky="ew", padx=4)
        ttk.Button(actions, text="Apply Rain Delay", command=self._apply_raindelay).grid(row=5, column=0, columnspan=2, sticky="ew", padx=4, pady=3)

        ttk.Label(actions, text="Cutting height (mm)").grid(row=6, column=0, sticky="w", padx=4)
        ttk.Entry(actions, textvariable=self.height_var, width=12).grid(row=6, column=1, sticky="ew", padx=4)
        ttk.Button(actions, text="Apply Cutting Height", command=self._apply_cutting_height).grid(row=7, column=0, columnspan=2, sticky="ew", padx=4, pady=3)

        ttk.Checkbutton(actions, text="ACS enabled", variable=self.acs_var).grid(row=8, column=0, sticky="w", padx=4, pady=6)
        ttk.Button(actions, text="Apply ACS", command=self._apply_acs).grid(row=8, column=1, sticky="ew", padx=4, pady=3)

        schedules = ttk.LabelFrame(center, text="Schedules")
        schedules.rowconfigure(1, weight=1)
        schedules.columnconfigure(0, weight=1)
        ttk.Label(schedules, text="Parsed slots (day, start-end, duration, source)").grid(row=0, column=0, sticky="w", padx=4, pady=2)
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
        self.connected = connected
        state = "readonly" if connected else "disabled"
        self.mower_combo.configure(state=state)

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
        fut = self.worker.submit(self.worker.connect(email, password, cloud_type))
        fut.add_done_callback(self._future_error_to_log)

    def _disconnect(self) -> None:
        self._append_log("Disconnecting...")
        fut = self.worker.submit(self.worker.disconnect())
        fut.add_done_callback(self._future_error_to_log)

    def _refresh(self) -> None:
        self._append_log("Refresh requested...")
        fut = self.worker.submit(self.worker.refresh())
        fut.add_done_callback(self._future_error_to_log)
        fut.add_done_callback(lambda f: self._future_success_to_log(f, "Refresh completed."))

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
        self.messages.put(
            WorkerMessage(msg_type="error", payload={"text": f"{type(err).__name__}: {err}"})
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
        ttk.Entry(frame, textvariable=email_var, width=38).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(frame, text="Password").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(frame, textvariable=password_var, show="*", width=38).grid(row=1, column=1, sticky="ew", pady=2)
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

        ttk.Button(btns, text="Cancel", command=dialog.destroy).grid(row=0, column=0, padx=4)
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
        self.status_vars["rain"].set(
            f"triggered={snapshot.get('rain_triggered', '-')} remaining={snapshot.get('rain_remaining', '-')}"
        )
        self.status_vars["last_refresh"].set(
            f"device={snapshot.get('device_updated', 'unknown')} | ui={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.schedule_list.configure(state="normal")
        self.schedule_list.delete("1.0", "end")
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
                if isinstance(snapshot, dict):
                    self.device_cache[name] = snapshot
                if name == self.mower_var.get() and isinstance(snapshot, dict):
                    self._render_snapshot(snapshot)
                self.last_event_var.set(f"Manual refresh completed for {name} at {at}")

        self.root.after(150, self._process_messages)

    def _on_close(self) -> None:
        self._append_log("Shutting down...")
        with contextlib.suppress(Exception):
            self.worker.submit(self.worker.shutdown()).result(timeout=10)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    DashboardApp().run()
