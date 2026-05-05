"""Tests for the manual GUI dashboard worker lifecycle."""

from __future__ import annotations

import asyncio
import queue
from types import SimpleNamespace

import pytest

pytest.importorskip("tkinter")

from test_dashboard_gui import CloudWorker, WorkerMessage
from pyworxcloud.exceptions import TimeoutException


def _device(name: str, serial: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        serial_number=serial,
        model="test-model",
        online=True,
        status=SimpleNamespace(description="idle"),
        error=SimpleNamespace(description="none"),
        battery=SimpleNamespace(percent=80),
        locked=False,
        firmware=SimpleNamespace(version="1.0"),
        schedules={"next_schedule_start": None, "slots": []},
        rainsensor=SimpleNamespace(triggered=False, remaining=0),
        updated=None,
        time_zone="UTC",
    )


def test_cloud_worker_shutdown_future_completes_before_loop_stop() -> None:
    """Shutdown should let run_coroutine_threadsafe futures complete."""
    messages: queue.Queue[WorkerMessage] = queue.Queue()
    worker = CloudWorker(messages)

    future = worker.submit(worker.shutdown())
    try:
        future.result(timeout=1.0)
    finally:
        worker.stop()

    assert future.done() is True


def test_refresh_falls_back_to_api_when_mqtt_command_times_out() -> None:
    """Manual refresh should not surface MQTT command timeouts as dashboard errors."""

    async def _run() -> queue.Queue[WorkerMessage]:
        messages: queue.Queue[WorkerMessage] = queue.Queue()
        initial_device = _device("Mower", "SN-1")
        refreshed_device = _device("Mower", "SN-1")
        refreshed_device.status.description = "api-refreshed"

        class FakeCloud:
            def __init__(self) -> None:
                self.devices = {"Mower": initial_device}
                self.update_calls: list[tuple[str, float | None]] = []
                self.fetch_calls = 0

            def get_mower(self, serial_number: str) -> dict:
                assert serial_number == "SN-1"
                return {
                    "protocol": 0,
                    "mqtt_topics": {"command_in": "topic/in"},
                }

            async def update(
                self, serial_number: str, timeout: float | None = None
            ) -> None:
                self.update_calls.append((serial_number, timeout))
                raise TimeoutException("refresh timed out")

            async def _fetch(self) -> None:
                self.fetch_calls += 1
                self.devices["Mower"] = refreshed_device

        cloud = FakeCloud()
        worker = CloudWorker.__new__(CloudWorker)
        worker._messages = messages
        worker._cloud = cloud
        worker._selected_name = "Mower"
        worker._update_event = asyncio.Event()
        worker._update_event_name = None

        await worker.refresh("Mower")

        assert cloud.update_calls == [("SN-1", 3.0)]
        assert cloud.fetch_calls == 1
        return messages

    messages = asyncio.run(_run())
    emitted = list(messages.queue)

    assert any(
        message.msg_type == "log"
        and "running API fallback fetch" in str(message.payload.get("text"))
        for message in emitted
    )
    assert any(
        message.msg_type == "refresh_done"
        and message.payload.get("source") == "api-fallback"
        and message.payload.get("snapshot", {}).get("status") == "api-refreshed"
        for message in emitted
    )
