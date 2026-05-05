"""Tests for the manual GUI dashboard worker lifecycle."""

from __future__ import annotations

import queue

import pytest

pytest.importorskip("tkinter")

from test_dashboard_gui import CloudWorker, WorkerMessage


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
