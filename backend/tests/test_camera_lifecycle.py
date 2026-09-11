"""Camera start/stop lifecycle (Phase 2b).

Three failure modes this pins down, none of which needed a real camera to
reproduce:
  * stop() released the capture device before joining the thread that was
    reading from it;
  * a thread that missed its join was forgotten, and the next start() cleared
    stop_event and woke it back up alongside its replacement;
  * a capture loop that died on its own left running=True, so the interface
    kept showing a live feed frozen on its last frame.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.camera import manager as manager_module
from app.camera.manager import CameraManager


@pytest.fixture()
def manager(monkeypatch):
    """The manager is a process-wide singleton; hand each test a clean one."""
    instance = CameraManager()
    saved = {
        "cap": instance.cap,
        "running": instance.running,
        "thread": instance.thread,
        "gate_processing_thread": instance.gate_processing_thread,
        "driver_processing_thread": instance.driver_processing_thread,
        "preview_processing_thread": instance.preview_processing_thread,
        "gate_detector": instance.gate_detector,
        "driver_detector": instance.driver_detector,
        "error": instance.error,
        "mode": instance.mode,
    }
    # getattr, not attribute access: this bookkeeping does not exist before
    # this change, and the point of the tests is to fail on the behaviour
    # rather than on a missing field.
    def _reset() -> None:
        for field in ("_orphaned_threads", "_detector_load_failures", "_detector_retry_at"):
            container = getattr(instance, field, None)
            if container is not None:
                container.clear()

    _reset()
    instance.stop_event.set()
    # Keep the joins short: these tests are about ordering, not patience.
    # raising=False for the same reason as _reset: these constants arrive with
    # this change, and a missing one must not hide the behavioural failure.
    monkeypatch.setattr(manager_module, "CAPTURE_JOIN_TIMEOUT", 0.15, raising=False)
    monkeypatch.setattr(manager_module, "ORPHAN_GRACE_SECONDS", 0.15, raising=False)
    try:
        yield instance
    finally:
        instance.stop_event.set()
        _reset()
        for key, value in saved.items():
            setattr(instance, key, value)


class OrderRecordingCapture:
    """Records whether the reader thread was still alive at release time."""

    def __init__(self, reader: threading.Event):
        self.reader_finished_at_release = None
        self.released = False
        self._reader = reader

    def release(self) -> None:
        self.released = True
        self.reader_finished_at_release = self._reader.is_set()


def test_the_capture_thread_is_joined_before_the_device_is_released(manager):
    finished = threading.Event()

    def slow_reader() -> None:
        # Stands in for a thread parked inside cap.read().
        time.sleep(0.05)
        finished.set()

    capture = OrderRecordingCapture(finished)
    reader = threading.Thread(target=slow_reader, daemon=True)
    reader.start()

    manager.cap = capture
    manager.running = True
    manager.thread = reader
    manager.stop_event.clear()

    manager.stop()

    assert capture.released is True
    assert capture.reader_finished_at_release is True, (
        "release() ran while the capture thread was still reading"
    )
    assert manager._orphaned_threads == []


def test_a_thread_that_misses_its_join_is_remembered(manager):
    keep_running = threading.Event()
    keep_running.set()

    def stubborn() -> None:
        while keep_running.is_set():
            time.sleep(0.01)

    stuck = threading.Thread(target=stubborn, daemon=True)
    stuck.start()
    manager.thread = stuck
    manager.running = True
    manager.stop_event.clear()

    try:
        manager.stop()
        assert manager._orphaned_threads == [stuck]
    finally:
        keep_running.clear()
        stuck.join(timeout=2)

    assert manager._live_orphaned_threads() == []  # it drains once the thread exits


def test_start_refuses_while_a_previous_worker_is_still_alive(manager, monkeypatch):
    opened = []
    monkeypatch.setattr(manager, "_open_webcam_capture", lambda device_id: opened.append(device_id))

    keep_running = threading.Event()
    keep_running.set()

    def stubborn() -> None:
        while keep_running.is_set():
            time.sleep(0.01)

    stuck = threading.Thread(target=stubborn, daemon=True)
    stuck.start()
    manager._orphaned_threads.append(stuck)
    manager.running = False
    manager.stop_event.set()

    try:
        started = manager.start(source_type="webcam", source_id="0", owner_module="attendance")

        assert started is False
        assert "still shutting down" in manager.error
        assert opened == [], "the camera was opened despite a live straggler"
        assert manager.stop_event.is_set(), (
            "stop_event was cleared, which would have reanimated the old thread"
        )
    finally:
        keep_running.clear()
        stuck.join(timeout=2)


def test_a_capture_loop_that_dies_marks_the_camera_stopped(manager):
    manager.cap = None  # the loop exits immediately, as it does on a dead device
    manager.running = True
    manager.error = ""
    manager.stop_event.clear()

    manager._capture_loop()

    assert manager.running is False
    assert manager.error == "Camera stopped delivering frames."


def test_a_session_that_ended_on_its_own_is_cleaned_up_by_the_next_start(manager, monkeypatch):
    """The capture loop cannot tear itself down: a thread cannot join itself.

    So it only flips running to False, and start() has to notice. It used to
    gate teardown on `if self.running:` alone, which skipped it and leaked the
    dead VideoCapture -- and on Windows a leaked handle keeps the device busy,
    so the feed never came back without restarting the process.
    """
    dead_capture = OrderRecordingCapture(threading.Event())
    manager.cap = dead_capture
    manager.running = True
    manager.stop_event.clear()

    manager._capture_loop()  # the device died; the loop retires the session

    assert manager.running is False
    assert manager.cap is dead_capture, "the loop cannot release it from inside itself"

    opened = []

    def fake_open(device_id):
        opened.append(device_id)
        return None, "TEST"  # open fails, which is fine: teardown already ran

    monkeypatch.setattr(manager, "_open_webcam_capture", fake_open)

    manager.start(source_type="webcam", source_id="0", owner_module="attendance")

    assert dead_capture.released is True, "the next start() leaked the dead capture"
    assert opened == [0], "start() never got as far as opening the device"


def test_a_real_stop_is_not_reported_as_a_failure(manager):
    manager.cap = None
    manager.running = True
    manager.error = ""
    manager.stop_event.set()  # an actual stop() request

    manager._capture_loop()

    assert manager.error == ""


# --- a detector that cannot load backs off ------------------------------------


def test_detector_backoff_doubles_and_is_capped(manager):
    assert manager._detector_backoff_seconds("gate") == 0.0

    delays = []
    for _ in range(8):
        manager._record_detector_failure("gate", "Failed to load the gate attendance recognizer.")
        delays.append(manager._detector_backoff_seconds("gate"))

    assert delays[:4] == [0.5, 1.0, 2.0, 4.0]
    assert delays[-1] == 30.0  # capped, not unbounded
    assert manager.error == "Failed to load the gate attendance recognizer."


def test_a_backed_off_detector_is_not_retried_yet(manager):
    manager.gate_detector = None
    manager._detector_retry_at["gate"] = time.time() + 60

    manager._ensure_gate_detector()

    assert manager.gate_detector is None, "retried during the backoff window"

    manager._detector_retry_at["gate"] = 0.0
    manager._ensure_gate_detector()

    assert manager.gate_detector is not None  # loads normally once the window passes
    assert "gate" not in manager._detector_load_failures


def test_a_successful_load_clears_the_failure_count(manager):
    manager._record_detector_failure("gate", "Failed to load the gate attendance recognizer.")
    manager.gate_detector = None
    manager._detector_retry_at["gate"] = 0.0

    manager._ensure_gate_detector()

    assert manager._detector_load_failures.get("gate") is None
    assert manager._detector_backoff_seconds("gate") == 0.0
