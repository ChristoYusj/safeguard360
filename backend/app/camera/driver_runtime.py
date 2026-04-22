from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

from app.inference.driver import DriverDetector


logger = logging.getLogger(__name__)


FACE_OUTLINE = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109,
]
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
MOUTH_OUTER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
NOSE_INDEX = 1


def _driver_default_state(status_message: str = "MediaPipe driver runtime is starting.") -> dict:
    return {
        "face_detected": False,
        "ear_left": 0.0,
        "ear_right": 0.0,
        "mar": 0.0,
        "head_yaw": 0.0,
        "head_pitch": 0.0,
        "eyes_closed_duration": 0.0,
        "is_fatigued": False,
        "is_distracted": False,
        "mediapipe_available": True,
        "detector_ready": False,
        "status_message": status_message,
    }


def _serialize_points(landmarks, indices) -> np.ndarray:
    points = np.empty((len(indices), 2), dtype=np.float32)
    for point_index, landmark_index in enumerate(indices):
        landmark = landmarks[landmark_index]
        points[point_index, 0] = landmark.x
        points[point_index, 1] = landmark.y
    return points


def _serialize_overlay(detector: DriverDetector) -> Optional[dict]:
    landmarks = getattr(detector, "last_landmarks", None)
    if landmarks is None:
        return None

    return {
        "face_outline": _serialize_points(landmarks, FACE_OUTLINE),
        "left_eye": _serialize_points(landmarks, LEFT_EYE),
        "right_eye": _serialize_points(landmarks, RIGHT_EYE),
        "mouth_outer": _serialize_points(landmarks, MOUTH_OUTER),
        "nose": np.array(
            [float(landmarks[NOSE_INDEX].x), float(landmarks[NOSE_INDEX].y)],
            dtype=np.float32,
        ),
        "last_face_seen_at": float(getattr(detector, "last_face_seen_at", 0.0)),
        "hold_seconds": float(getattr(detector, "landmark_hold_seconds", 0.5)),
    }


class DriverDetectorClient:
    """Thread-safe Fleet-only wrapper around the in-process MediaPipe detector."""

    EAR_THRESHOLD = 0.2
    MAR_THRESHOLD = 0.6
    HEAD_YAW_THRESHOLD = 30
    HEAD_PITCH_THRESHOLD = 20

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._detector = DriverDetector()
        self._state = self._detector.get_state_dict()
        self._overlay = _serialize_overlay(self._detector)

    @staticmethod
    def _draw_points(frame: np.ndarray, points, color, *, closed: bool = True, thickness: int = 2) -> None:
        if points is None or len(points) == 0:
            return
        height, width = frame.shape[:2]
        normalized_points = np.asarray(points, dtype=np.float32)
        coords = np.empty((len(normalized_points), 2), dtype=np.int32)
        coords[:, 0] = (normalized_points[:, 0] * width).astype(np.int32)
        coords[:, 1] = (normalized_points[:, 1] * height).astype(np.int32)
        cv2.polylines(frame, [coords], closed, color, thickness)

    def _snapshot(self) -> tuple[dict, Optional[dict]]:
        with self._lock:
            state = dict(self._state)
            overlay = None
            if self._overlay is not None:
                overlay = {
                    key: (value.copy() if isinstance(value, np.ndarray) else value)
                    for key, value in self._overlay.items()
                }
            return state, overlay

    def _draw_status_panel(self, frame: np.ndarray, state: dict, *, overlay: Optional[dict], face_label: Optional[str] = None) -> np.ndarray:
        height, width = frame.shape[:2]
        cv2.rectangle(frame, (5, 5), (162, 112), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, 5), (162, 112), (255, 255, 255), 1)

        avg_ear = (state.get("ear_left", 0.0) + state.get("ear_right", 0.0)) / 2
        y = 22

        resolved_face_label = face_label
        if resolved_face_label is None:
            if state.get("face_detected"):
                resolved_face_label = "FACE OK"
            elif overlay and (time.time() - overlay.get("last_face_seen_at", 0.0)) <= overlay.get("hold_seconds", 0.5):
                resolved_face_label = "FACE HOLD"
            else:
                resolved_face_label = "NO FACE"

        face_color = (0, 255, 0) if resolved_face_label in {"FACE OK", "FACE HOLD"} else (0, 165, 255)
        cv2.putText(frame, resolved_face_label, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, face_color, 1)

        y += 18
        ear_color = (0, 255, 0) if avg_ear > self.EAR_THRESHOLD else (0, 0, 255)
        cv2.putText(frame, f"EAR: {avg_ear:.2f}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ear_color, 1)

        y += 18
        mar_color = (0, 0, 255) if state.get("mar", 0.0) > self.MAR_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"MAR: {state.get('mar', 0.0):.2f}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, mar_color, 1)

        y += 18
        yaw_color = (0, 0, 255) if abs(state.get("head_yaw", 0.0)) > self.HEAD_YAW_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"Yaw: {state.get('head_yaw', 0.0):.1f}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, yaw_color, 1)

        y += 18
        pitch_color = (0, 0, 255) if abs(state.get("head_pitch", 0.0)) > self.HEAD_PITCH_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"Pitch: {state.get('head_pitch', 0.0):.1f}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, pitch_color, 1)

        if state.get("is_fatigued"):
            cv2.rectangle(frame, (width - 220, 10), (width - 10, 45), (0, 0, 200), -1)
            cv2.putText(frame, "FATIGUE!", (width - 210, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        if state.get("is_distracted"):
            cv2.rectangle(frame, (width - 220, 50), (width - 10, 85), (0, 140, 255), -1)
            cv2.putText(frame, "DISTRACTED!", (width - 215, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return frame

    def _draw_annotations(self, frame: np.ndarray, overlay: dict, state: dict) -> np.ndarray:
        self._draw_points(frame, overlay.get("face_outline"), (0, 255, 255), closed=True, thickness=2)
        for eye_key in ("left_eye", "right_eye"):
            eye_points = overlay.get(eye_key)
            self._draw_points(frame, eye_points, (0, 255, 0), closed=True, thickness=2)
            if eye_points is not None and len(eye_points) > 0:
                height, width = frame.shape[:2]
                eye_points_array = np.asarray(eye_points, dtype=np.float32)
                center_x = int(np.mean(eye_points_array[:, 0]) * width)
                center_y = int(np.mean(eye_points_array[:, 1]) * height)
                cv2.circle(frame, (center_x, center_y), 3, (255, 255, 0), -1)

        self._draw_points(frame, overlay.get("mouth_outer"), (255, 0, 255), closed=True, thickness=2)

        nose = overlay.get("nose")
        if nose is not None and len(nose) == 2:
            height, width = frame.shape[:2]
            cv2.circle(frame, (int(nose[0] * width), int(nose[1] * height)), 5, (255, 128, 0), -1)

        return self._draw_status_panel(frame, state, overlay=overlay, face_label="FACE OK")

    def process_frame(self, frame: np.ndarray):
        with self._lock:
            try:
                _, events = self._detector.process_frame(frame)
                self._state = self._detector.get_state_dict()
                self._overlay = _serialize_overlay(self._detector)
                return frame, events
            except Exception:
                logger.exception("Driver detector frame processing failed.")
                failed_state = self._detector.get_state_dict()
                failed_state["status_message"] = "MediaPipe driver runtime crashed while processing a frame."
                self._state = failed_state
                self._overlay = None
                return frame, []

    def draw_live_overlay(self, frame: np.ndarray) -> np.ndarray:
        state, overlay = self._snapshot()
        cv2.putText(frame, f"Frame: {frame.shape[1]}x{frame.shape[0]}", (frame.shape[1] - 120, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        if overlay and (time.time() - overlay.get("last_face_seen_at", 0.0)) <= overlay.get("hold_seconds", 0.5):
            return self._draw_annotations(frame, overlay, state)

        if not state.get("detector_ready"):
            cv2.putText(frame, state.get("status_message", "MediaPipe driver runtime unavailable.")[:48], (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame

        return self._draw_status_panel(frame, state, overlay=overlay)

    def get_state_dict(self) -> dict:
        state, _ = self._snapshot()
        return state

    def reset_live_state(self) -> None:
        with self._lock:
            self._detector.reset_live_state()
            self._state = self._detector.get_state_dict()
            self._overlay = _serialize_overlay(self._detector)

    def shutdown(self) -> None:
        with self._lock:
            self._detector.close()
            self._state = _driver_default_state("MediaPipe driver runtime stopped.")
            self._overlay = None
