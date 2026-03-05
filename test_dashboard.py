"""Interactive terminal dashboard for manual pyworxcloud testing."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from os import environ
from typing import Any

from pyworxcloud import WorxCloud
from pyworxcloud.events import LandroidEvent
from pyworxcloud.utils import DeviceHandler


def _clear() -> None:
    print("\033c", end="")


async def _ainput(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def _choose_mower(cloud: WorxCloud) -> str:
    names = list(cloud.devices.keys())
    if len(names) == 1:
        return names[0]

    while True:
        _clear()
        print("Vælg klipper:\n")
        for idx, name in enumerate(names, start=1):
            device = cloud.devices[name]
            print(
                f"{idx}. {name} | serial={device.serial_number} | online={device.online}"
            )
        choice = (await _ainput("\nNummer: ")).strip()
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
    print(f"Klipper: {selected}")
    print(f"Serial: {device.serial_number}")
    print(f"Model: {getattr(device, 'model', 'ukendt')}")
    print(f"Online: {getattr(device, 'online', 'ukendt')}")
    print(f"Status: {getattr(device.status, 'description', 'ukendt')}")
    print(f"Fejl: {getattr(device.error, 'description', 'ukendt')}")
    print(f"Batteri: {getattr(device.battery, 'percent', 'ukendt')}%")
    print(f"Låst: {getattr(device, 'locked', 'ukendt')}")
    print(f"Firmware: {getattr(device.firmware, 'version', 'ukendt')}")
    print(
        "Regn: triggered="
        f"{getattr(device.rainsensor, 'triggered', 'ukendt')} "
        f"remaining={getattr(device.rainsensor, 'remaining', 'ukendt')}"
    )
    print("-" * 72)
    print(f"Sidste event: {event_text}")
    print("-" * 72)
    print("Kommandoer:")
    print("  r  = refresh")
    print("  s  = start")
    print("  p  = pause")
    print("  h  = home")
    print("  sh = safehome")
    print("  e  = edgecut")
    print("  l  = lock/unlock")
    print("  rd = rain delay (minutter)")
    print("  ch = cutting height (mm)")
    print("  acs = acs on/off")
    print("  m  = vælg anden klipper")
    print("  q  = quit")


async def _run_dashboard(cloud: WorxCloud) -> None:
    render_interval = 2.0
    poll_interval = 60.0
    event_text = "ingen events endnu"
    selected = await _choose_mower(cloud)
    last_render = 0.0
    last_poll = 0.0
    running = True
    command_queue: asyncio.Queue[str] = asyncio.Queue()
    dirty = True

    def _on_data(name: str, device: DeviceHandler) -> None:
        nonlocal event_text, dirty
        event_text = (
            f"MQTT refresh for {name} | status={device.status.description}"
            f" | battery={device.battery.percent}%"
        )
        dirty = True

    def _on_api(name: str, device: DeviceHandler) -> None:
        nonlocal event_text, dirty
        event_text = (
            f"API refresh for {name} | status={device.status.description}"
            f" | battery={device.battery.percent}%"
        )
        dirty = True

    cloud.set_callback(LandroidEvent.DATA_RECEIVED, _on_data)
    cloud.set_callback(LandroidEvent.API, _on_api)

    async def _input_worker() -> None:
        while running:
            command = (await _ainput("\ncmd> ")).strip()
            await command_queue.put(command)

    input_task = asyncio.create_task(_input_worker())
    try:
        while running:
            now = asyncio.get_running_loop().time()
            device = cloud.devices[selected]
            serial = device.serial_number

            if dirty or now - last_render >= render_interval:
                _render_device(device, selected, event_text)
                print("Format: command [args] | fx: l on, rd 90, ch 45, acs off")
                last_render = now
                dirty = False

            if now - last_poll >= poll_interval:
                try:
                    await cloud.update(serial)
                except Exception as err:  # pragma: no cover - interactive helper
                    event_text = f"Poll fejl: {type(err).__name__}: {err}"
                last_poll = now

            try:
                raw = command_queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.2)
                continue

            parts = raw.lower().split()
            if not parts:
                continue

            command = parts[0]
            args = parts[1:]

            try:
                if command == "q":
                    running = False
                    continue
                if command == "m":
                    selected = await _choose_mower(cloud)
                    event_text = f"Skiftede til {selected}"
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
                        event_text = "Brug: l on|off"
                        dirty = True
                        continue
                    await cloud.set_lock(serial, args[0] == "on")
                    continue
                if command == "rd":
                    if not args:
                        event_text = "Brug: rd <minutter>"
                        dirty = True
                        continue
                    await cloud.raindelay(serial, args[0])
                    continue
                if command == "ch":
                    if not args:
                        event_text = "Brug: ch <mm>"
                        dirty = True
                        continue
                    await cloud.set_cutting_height(serial, int(args[0]))
                    continue
                if command == "acs":
                    if not args or args[0] not in {"on", "off"}:
                        event_text = "Brug: acs on|off"
                        dirty = True
                        continue
                    await cloud.set_acs(serial, args[0] == "on")
                    continue
                event_text = f"Ukendt kommando: {raw}"
                dirty = True
            except Exception as err:  # pragma: no cover - interactive helper
                event_text = f"Fejl: {type(err).__name__}: {err}"
                dirty = True
    finally:
        input_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await input_task


async def main() -> None:
    email = environ.get("EMAIL") or await _ainput("EMAIL: ")
    password = environ.get("PASSWORD") or await _ainput("PASSWORD: ")
    cloud_type = environ.get("TYPE") or await _ainput("TYPE (worx/kress/landxcape): ")

    cloud = WorxCloud(email, password, cloud_type, tz="Europe/Copenhagen")
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
