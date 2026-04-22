from __future__ import annotations

import threading

import numpy as np

from app.camera.manager import CameraManager, DriverEventData, GateEventData, WebcamProbeResult


class DummyCapture:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeGateDetector:
    def __init__(self) -> None:
        self.reset_calls = []

    def reset_live_session(self, **kwargs) -> None:
        self.reset_calls.append(kwargs)

    def get_state_dict(self) -> dict:
        return {"status": "idle"}


class FakeDriverDetector:
    def __init__(self) -> None:
        self.reset_calls = 0

    def reset_live_state(self) -> None:
        self.reset_calls += 1

    def get_state_dict(self) -> dict:
        return {
            "detector_ready": True,
            "status_message": "ready",
        }


def _worker(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        stop_event.wait(0.01)


def test_camera_manager_stop_releases_camera_and_clears_runtime_state():
    manager = CameraManager()
    original_driver_detector = manager.driver_detector
    original_gate_detector = manager.gate_detector

    try:
        manager.stop()
        manager.stop_event.clear()

        capture = DummyCapture()
        gate_detector = FakeGateDetector()
        driver_detector = FakeDriverDetector()

        manager.cap = capture
        manager.running = True
        manager.mode = "driver"
        manager.owner_module = "drivers"
        manager.owner_token = "owner-token"
        manager.driver_detector = driver_detector
        manager.gate_detector = gate_detector
        manager.latest_frame = b"frame"
        manager.latest_frame_sequence = 3
        manager.latest_raw_frame = object()
        manager.latest_raw_frame_sequence = 4
        manager.pending_driver_events = [
            DriverEventData(
                event_type="fatigue",
                timestamp=1.0,
                confidence=0.9,
                details="Eyes closed",
            )
        ]
        manager.pending_gate_events = [
            GateEventData(
                event_type="ENTRY_OK",
                timestamp=2.0,
                confidence=0.95,
                details="Access granted",
            )
        ]

        for attr in (
            "thread",
            "gate_processing_thread",
            "driver_processing_thread",
            "preview_processing_thread",
        ):
            worker = threading.Thread(target=_worker, args=(manager.stop_event,), daemon=True)
            worker.start()
            setattr(manager, attr, worker)

        manager.stop()

        assert capture.released is True
        assert manager.running is False
        assert manager.cap is None
        assert manager.thread is None
        assert manager.gate_processing_thread is None
        assert manager.driver_processing_thread is None
        assert manager.preview_processing_thread is None
        assert manager.latest_frame is None
        assert manager.latest_frame_sequence == 0
        assert manager.latest_raw_frame is None
        assert manager.latest_raw_frame_sequence == 0
        assert manager.pending_driver_events == []
        assert manager.pending_gate_events == []
        assert manager.mode == "idle"
        assert manager.owner_module is None
        assert manager.owner_token is None
        assert gate_detector.reset_calls
        assert driver_detector.reset_calls == 1
    finally:
        manager.driver_detector = original_driver_detector
        manager.gate_detector = original_gate_detector


def test_camera_manager_uses_lighter_preview_profile_for_driver_mode():
    manager = CameraManager()

    manager.mode = "driver"
    interval, max_width, jpeg_quality = manager._get_preview_profile()

    assert interval == manager.driver_preview_frame_interval
    assert max_width == manager.driver_preview_max_width
    assert jpeg_quality == manager.driver_preview_jpeg_quality

    manager.mode = "gate"
    interval, max_width, jpeg_quality = manager._get_preview_profile()

    assert interval == manager.preview_frame_interval
    assert max_width == 0
    assert jpeg_quality == manager.preview_jpeg_quality


def test_camera_manager_driver_state_is_json_safe():
    manager = CameraManager()
    manager.driver_state = {
        "face_detected": np.bool_(True),
        "debug": {
            "frames_with_face": np.int64(3),
            "detect_ms_last": np.float32(12.5),
        },
    }

    state = manager.get_driver_state()

    assert state["face_detected"] is True
    assert state["debug"]["frames_with_face"] == 3
    assert isinstance(state["debug"]["detect_ms_last"], float)


def test_camera_manager_prefers_brighter_webcam_for_driver_mode(monkeypatch):
    manager = CameraManager()

    probes = {
        0: WebcamProbeResult(device_id=0, brightness=24.0, contrast=8.0, backend="DSHOW"),
        1: WebcamProbeResult(device_id=1, brightness=160.0, contrast=22.0, backend="DSHOW"),
    }

    monkeypatch.setattr(manager, "_probe_webcam_source", lambda device_id: probes.get(device_id))

    selected = manager._select_driver_webcam_source(0)

    assert selected == 1
