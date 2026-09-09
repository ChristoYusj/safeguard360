from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.inference import driver as driver_module


@dataclass
class FakeLandmark:
    x: float
    y: float


class FakeResults:
    def __init__(self, landmarks):
        self.face_landmarks = [] if landmarks is None else [landmarks]


class SequencedFaceLandmarker:
    def __init__(self, frames):
        self._frames = list(frames)
        self._index = 0

    def detect_for_video(self, mp_image, timestamp_ms):
        frame_index = min(self._index, len(self._frames) - 1)
        self._index += 1
        return FakeResults(self._frames[frame_index])


def _set_eye(landmarks, indices, *, center_x: float, center_y: float, ear: float) -> None:
    horizontal = 0.08
    half_vertical = max(ear, 0.0) * horizontal / 2.0
    points = [
        (center_x - horizontal / 2.0, center_y),
        (center_x - horizontal / 4.0, center_y - half_vertical),
        (center_x + horizontal / 4.0, center_y - half_vertical),
        (center_x + horizontal / 2.0, center_y),
        (center_x + horizontal / 4.0, center_y + half_vertical),
        (center_x - horizontal / 4.0, center_y + half_vertical),
    ]
    for index, (x, y) in zip(indices, points, strict=True):
        landmarks[index] = FakeLandmark(x=x, y=y)


def _build_landmarks(*, ear: float, mar: float):
    landmarks = [FakeLandmark(x=0.5, y=0.5) for _ in range(468)]

    _set_eye(landmarks, driver_module.DriverDetector.LEFT_EYE, center_x=0.62, center_y=0.42, ear=ear)
    _set_eye(landmarks, driver_module.DriverDetector.RIGHT_EYE, center_x=0.38, center_y=0.42, ear=ear)

    mouth_half_width = 0.05
    mouth_half_height = (mar * (mouth_half_width * 2.0)) / 2.0
    landmarks[13] = FakeLandmark(x=0.5, y=0.62 - mouth_half_height)
    landmarks[14] = FakeLandmark(x=0.5, y=0.62 + mouth_half_height)
    landmarks[78] = FakeLandmark(x=0.5 - mouth_half_width, y=0.62)
    landmarks[308] = FakeLandmark(x=0.5 + mouth_half_width, y=0.62)

    landmarks[1] = FakeLandmark(x=0.5, y=0.5)
    landmarks[234] = FakeLandmark(x=0.35, y=0.5)
    landmarks[454] = FakeLandmark(x=0.65, y=0.5)
    landmarks[10] = FakeLandmark(x=0.5, y=0.3)
    landmarks[152] = FakeLandmark(x=0.5, y=0.7)

    return landmarks


def _make_detector(monkeypatch, frame_sequence):
    monkeypatch.setattr(driver_module, "MEDIAPIPE_AVAILABLE", True)

    def fake_initialize(self):
        self.face_landmarker = SequencedFaceLandmarker(frame_sequence)
        self.init_error = ""
        return True

    monkeypatch.setattr(driver_module.DriverDetector, "_initialize_face_landmarker", fake_initialize)
    detector = driver_module.DriverDetector()
    detector.face_landmarker = SequencedFaceLandmarker(frame_sequence)
    return detector


def test_driver_detector_emits_eye_closure_event_after_reopen(monkeypatch):
    current_time = [0.0]
    monkeypatch.setattr(driver_module.time, "time", lambda: current_time[0])
    monkeypatch.setattr(driver_module.time, "monotonic", lambda: current_time[0])

    detector = _make_detector(
        monkeypatch,
        [
            _build_landmarks(ear=0.28, mar=0.2),
            _build_landmarks(ear=0.12, mar=0.2),
            _build_landmarks(ear=0.12, mar=0.2),
            _build_landmarks(ear=0.12, mar=0.2),
            _build_landmarks(ear=0.12, mar=0.2),
            _build_landmarks(ear=0.28, mar=0.2),
        ],
    )

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    timestamps = [100.0, 100.25, 100.5, 100.75, 101.05, 101.3]
    emitted_events = []
    for ts in timestamps:
        current_time[0] = ts
        _, events = detector.process_frame(frame.copy())
        emitted_events.extend(events)

    assert any(
        event.event_type == driver_module.DriverEventType.FATIGUE
        and "Eyes closed" in event.details
        for event in emitted_events
    )


def test_driver_detector_emits_yawn_event_after_mouth_closes(monkeypatch):
    current_time = [0.0]
    monkeypatch.setattr(driver_module.time, "time", lambda: current_time[0])
    monkeypatch.setattr(driver_module.time, "monotonic", lambda: current_time[0])

    detector = _make_detector(
        monkeypatch,
        [
            _build_landmarks(ear=0.28, mar=0.2),
            _build_landmarks(ear=0.28, mar=0.9),
            _build_landmarks(ear=0.28, mar=0.9),
            _build_landmarks(ear=0.28, mar=0.9),
            _build_landmarks(ear=0.28, mar=0.25),
        ],
    )

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    timestamps = [200.0, 200.2, 200.45, 200.75, 200.95]
    emitted_events = []
    for ts in timestamps:
        current_time[0] = ts
        _, events = detector.process_frame(frame.copy())
        emitted_events.extend(events)

    assert any(
        event.event_type == driver_module.DriverEventType.FATIGUE
        and "Yawning" in event.details
        for event in emitted_events
    )
