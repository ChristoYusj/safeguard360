from __future__ import annotations

import numpy as np

from app.camera.driver_runtime import DriverDetectorClient


class FakeDetector:
    def __init__(self) -> None:
        self.process_calls = 0
        self.reset_calls = 0
        self.close_calls = 0
        self.last_landmarks = None
        self.last_face_seen_at = 0.0
        self.landmark_hold_seconds = 0.5

    def process_frame(self, frame):
        self.process_calls += 1
        return frame, [{"event_type": "INFO", "details": "processed"}]

    def get_state_dict(self):
        return {
            "face_detected": True,
            "ear_left": 0.25,
            "ear_right": 0.24,
            "mar": 0.1,
            "head_yaw": 0.0,
            "head_pitch": 0.0,
            "eyes_closed_duration": 0.0,
            "is_fatigued": False,
            "is_distracted": False,
            "mediapipe_available": True,
            "detector_ready": True,
            "status_message": "ready",
        }

    def reset_live_state(self):
        self.reset_calls += 1

    def close(self):
        self.close_calls += 1


def test_driver_detector_client_processes_frames_and_draws_overlay():
    client = DriverDetectorClient()
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    try:
        returned_frame, events = client.process_frame(frame.copy())
        state = client.get_state_dict()
        overlay = client.draw_live_overlay(frame.copy())

        assert returned_frame.shape == frame.shape
        assert isinstance(events, list)
        assert isinstance(state, dict)
        assert overlay.shape == frame.shape
    finally:
        client.shutdown()


def test_driver_detector_client_reset_and_shutdown(monkeypatch):
    fake_detector = FakeDetector()
    client = object.__new__(DriverDetectorClient)
    client._lock = None  # placeholder before replacement
    import threading

    client._lock = threading.RLock()
    client._detector = fake_detector
    client._state = fake_detector.get_state_dict()
    client._overlay = None

    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    returned_frame, events = DriverDetectorClient.process_frame(client, frame)

    assert returned_frame is frame
    assert events == [{"event_type": "INFO", "details": "processed"}]
    assert fake_detector.process_calls == 1

    DriverDetectorClient.reset_live_state(client)
    assert fake_detector.reset_calls == 1

    DriverDetectorClient.shutdown(client)
    assert fake_detector.close_calls == 1
    assert client.get_state_dict()["detector_ready"] is False
