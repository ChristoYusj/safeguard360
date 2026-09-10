"""Driver Monitoring - Fatigue and Distraction Detection using MediaPipe."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np


logger = logging.getLogger(__name__)

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    MEDIAPIPE_AVAILABLE = True
except ImportError as exc:
    MEDIAPIPE_AVAILABLE = False
    logger.warning("MediaPipe not installed: %s", exc)


MODEL_DOWNLOAD_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
# SHA-256 of the float16/1 release above. The file is not committed (it is a
# 3.7 MB runtime asset); it is fetched once and verified before use.
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
MODEL_DOWNLOAD_TIMEOUT_SECONDS = 30
_MODEL_BUFFER_LOCK = threading.Lock()
_MODEL_ASSET_BUFFER: Optional[bytes] = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download_model_asset(model_path: Path) -> bytes:
    """Fetch the face landmarker model, verify its checksum, write it atomically."""
    logger.info("Downloading MediaPipe face landmarker model to %s", model_path)
    with urllib.request.urlopen(
        MODEL_DOWNLOAD_URL, timeout=MODEL_DOWNLOAD_TIMEOUT_SECONDS
    ) as response:
        data = response.read()
    digest = _sha256(data)
    if digest != MODEL_SHA256:
        raise RuntimeError(
            "face_landmarker.task checksum mismatch: "
            f"expected {MODEL_SHA256}, got {digest}"
        )
    partial_path = model_path.with_suffix(model_path.suffix + ".part")
    partial_path.write_bytes(data)
    partial_path.replace(model_path)
    return data


class DriverEventType(str, Enum):
    FATIGUE = "FATIGUE"
    DISTRACTION = "DISTRACTION"


@dataclass
class DriverEvent:
    event_type: DriverEventType
    timestamp: float
    confidence: float
    details: str


@dataclass
class DriverState:
    face_detected: bool = False
    ear_left: float = 0.0
    ear_right: float = 0.0
    mar: float = 0.0
    head_pitch: float = 0.0
    head_yaw: float = 0.0
    eyes_closed_duration: float = 0.0
    is_fatigued: bool = False
    is_distracted: bool = False


class DriverDetector:
    """MediaPipe-backed driver detector used by Fleet Monitoring only."""

    LEFT_EYE = [362, 385, 387, 263, 373, 380]
    RIGHT_EYE = [33, 160, 158, 133, 153, 144]
    MOUTH_VERTICAL = [13, 14]
    MOUTH_HORIZONTAL = [78, 308]

    EAR_THRESHOLD = 0.2
    EAR_CLOSED_THRESHOLD = 0.18
    EAR_OPEN_THRESHOLD = 0.2
    EYES_CLOSED_TIME_THRESHOLD = 0.8
    MAR_THRESHOLD = 0.6
    MAR_END_THRESHOLD = 0.52
    HEAD_YAW_THRESHOLD = 30
    HEAD_PITCH_THRESHOLD = 20
    METRIC_SMOOTHING_ALPHA = 0.35
    MODEL_FILENAME = "face_landmarker.task"

    def __init__(self) -> None:
        self.state = DriverState()
        self.eyes_closed_start: Optional[float] = None
        self.yawn_start: Optional[float] = None
        self.last_fatigue_event = 0.0
        self.last_distraction_event = 0.0
        self.event_cooldown = 5.0

        self.prev_eyes_closed = False
        self.prev_yawning = False
        self.prev_distracted = False

        self.frame_count = 0
        self.face_landmarker = None
        self.init_error = ""
        self.last_landmarks = None
        self.last_face_seen_at = 0.0
        self.landmark_hold_seconds = 0.5
        self.detection_max_width = 640
        self.last_video_timestamp_ms = 0
        self.init_retry_cooldown_seconds = 5.0
        self.last_init_attempt_at = 0.0
        self.init_lock = threading.Lock()
        self.smoothed_ear_left: Optional[float] = None
        self.smoothed_ear_right: Optional[float] = None
        self.smoothed_mar: Optional[float] = None
        self.smoothed_head_yaw: Optional[float] = None
        self.smoothed_head_pitch: Optional[float] = None
        self.last_detect_ms = 0.0
        self.avg_detect_ms = 0.0
        self.last_process_ms = 0.0
        self.avg_process_ms = 0.0
        self.frames_with_face = 0
        self.frames_without_face = 0

        self._initialize_face_landmarker()

    @classmethod
    def _resolve_model_path(cls) -> Path:
        return Path(__file__).resolve().parent / "models" / cls.MODEL_FILENAME

    @classmethod
    def _load_model_asset_buffer(cls) -> bytes:
        global _MODEL_ASSET_BUFFER

        if _MODEL_ASSET_BUFFER is not None:
            return _MODEL_ASSET_BUFFER

        with _MODEL_BUFFER_LOCK:
            if _MODEL_ASSET_BUFFER is not None:
                return _MODEL_ASSET_BUFFER

            model_path = cls._resolve_model_path()
            model_path.parent.mkdir(parents=True, exist_ok=True)
            data = model_path.read_bytes() if model_path.exists() else None
            if data is not None and _sha256(data) != MODEL_SHA256:
                logger.warning(
                    "Cached %s failed its checksum; re-downloading.", model_path.name
                )
                data = None
            if data is None:
                data = _download_model_asset(model_path)

            _MODEL_ASSET_BUFFER = data
            return _MODEL_ASSET_BUFFER

    def _get_detector_status_message(self) -> str:
        if not MEDIAPIPE_AVAILABLE:
            return "MediaPipe is not installed in the backend runtime."
        if self.face_landmarker is not None:
            return "MediaPipe face landmarker ready."
        if self.init_error:
            return f"MediaPipe face landmarker unavailable: {self.init_error}"
        return "MediaPipe face landmarker is still initializing."

    def _initialize_face_landmarker(self) -> bool:
        if not MEDIAPIPE_AVAILABLE:
            self.init_error = "mediapipe import failed"
            self.face_landmarker = None
            return False

        try:
            self.last_init_attempt_at = time.monotonic()
            model_asset_buffer = self._load_model_asset_buffer()
            base_options = mp_python.BaseOptions(model_asset_buffer=model_asset_buffer)
            options = mp_vision.FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.3,
                min_face_presence_confidence=0.3,
                min_tracking_confidence=0.3,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            new_landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            previous_landmarker = self.face_landmarker
            self.face_landmarker = new_landmarker
            self.init_error = ""
            if previous_landmarker is not None and previous_landmarker is not new_landmarker:
                try:
                    previous_landmarker.close()
                except Exception:
                    logger.exception("Failed to close previous face landmarker instance.")
            return True
        except Exception as exc:
            logger.exception("Failed to initialize FaceLandmarker.")
            self.init_error = str(exc)
            self.face_landmarker = None
            return False

    def _ensure_face_landmarker_ready(self) -> bool:
        if self.face_landmarker is not None:
            return True

        now = time.monotonic()
        if self.init_error and (now - self.last_init_attempt_at) < self.init_retry_cooldown_seconds:
            return False

        with self.init_lock:
            if self.face_landmarker is not None:
                return True
            now = time.monotonic()
            if self.init_error and (now - self.last_init_attempt_at) < self.init_retry_cooldown_seconds:
                return False
            self.last_init_attempt_at = now
            return self._initialize_face_landmarker()

    def close(self) -> None:
        landmarker = self.face_landmarker
        self.face_landmarker = None
        if landmarker is None:
            return
        try:
            landmarker.close()
        except Exception:
            logger.exception("Failed to close MediaPipe face landmarker.")

    def reset_live_state(self) -> None:
        self.state = DriverState()
        self.eyes_closed_start = None
        self.yawn_start = None
        self.last_fatigue_event = 0.0
        self.last_distraction_event = 0.0
        self.prev_eyes_closed = False
        self.prev_yawning = False
        self.prev_distracted = False
        self.last_landmarks = None
        self.last_face_seen_at = 0.0
        self.last_video_timestamp_ms = 0
        self.smoothed_ear_left = None
        self.smoothed_ear_right = None
        self.smoothed_mar = None
        self.smoothed_head_yaw = None
        self.smoothed_head_pitch = None

    @staticmethod
    def _smooth_metric(previous: Optional[float], current: float, alpha: float) -> float:
        if previous is None:
            return current
        return (previous * (1.0 - alpha)) + (current * alpha)

    def _record_timing(self, name: str, value_ms: float, *, alpha: float = 0.18) -> None:
        if name == "detect":
            self.last_detect_ms = round(value_ms, 3)
            self.avg_detect_ms = round(
                value_ms if self.avg_detect_ms == 0.0 else (self.avg_detect_ms * (1.0 - alpha)) + (value_ms * alpha),
                3,
            )
            return

        if name == "process":
            self.last_process_ms = round(value_ms, 3)
            self.avg_process_ms = round(
                value_ms if self.avg_process_ms == 0.0 else (self.avg_process_ms * (1.0 - alpha)) + (value_ms * alpha),
                3,
            )

    def _next_video_timestamp_ms(self) -> int:
        timestamp_ms = int(time.monotonic() * 1000)
        if timestamp_ms <= self.last_video_timestamp_ms:
            timestamp_ms = self.last_video_timestamp_ms + 1
        self.last_video_timestamp_ms = timestamp_ms
        return timestamp_ms

    @staticmethod
    def _equalize_detection_frame(frame: np.ndarray) -> np.ndarray:
        ycrcb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        y_channel, cr_channel, cb_channel = cv2.split(ycrcb_frame)
        y_channel = cv2.equalizeHist(y_channel)
        return cv2.cvtColor(
            cv2.merge((y_channel, cr_channel, cb_channel)),
            cv2.COLOR_YCrCb2BGR,
        )

    def _detect_landmarks(self, frame: np.ndarray):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        return self.face_landmarker.detect_for_video(mp_image, self._next_video_timestamp_ms())

    @staticmethod
    def _point(landmark, width: int, height: int) -> np.ndarray:
        return np.array([landmark.x * width, landmark.y * height], dtype=np.float32)

    def _calculate_ear(self, landmarks, eye_indices, width: int, height: int) -> float:
        points = [self._point(landmarks[index], width, height) for index in eye_indices]
        v1 = np.linalg.norm(points[1] - points[5])
        v2 = np.linalg.norm(points[2] - points[4])
        h1 = np.linalg.norm(points[0] - points[3])
        if h1 == 0.0:
            return 0.3
        return float((v1 + v2) / (2.0 * h1))

    def _calculate_mar(self, landmarks, width: int, height: int) -> float:
        top = self._point(landmarks[self.MOUTH_VERTICAL[0]], width, height)
        bottom = self._point(landmarks[self.MOUTH_VERTICAL[1]], width, height)
        left = self._point(landmarks[self.MOUTH_HORIZONTAL[0]], width, height)
        right = self._point(landmarks[self.MOUTH_HORIZONTAL[1]], width, height)

        horizontal = np.linalg.norm(left - right)
        if horizontal == 0.0:
            return 0.0
        return float(np.linalg.norm(top - bottom) / horizontal)

    @staticmethod
    def _estimate_head_pose(landmarks) -> Tuple[float, float]:
        nose = landmarks[1]
        left_face = landmarks[234]
        right_face = landmarks[454]
        forehead = landmarks[10]
        chin = landmarks[152]

        face_center_x = (left_face.x + right_face.x) / 2.0
        face_center_y = (forehead.y + chin.y) / 2.0
        yaw = float((nose.x - face_center_x) * 100.0)
        pitch = float((nose.y - face_center_y) * 100.0)
        return yaw, pitch

    def _reset_face_metrics(self) -> None:
        self.state.ear_left = 0.0
        self.state.ear_right = 0.0
        self.state.mar = 0.0
        self.state.head_yaw = 0.0
        self.state.head_pitch = 0.0
        self.state.eyes_closed_duration = 0.0
        self.state.is_fatigued = False
        self.state.is_distracted = False
        self.eyes_closed_start = None
        self.yawn_start = None
        self.prev_eyes_closed = False
        self.prev_yawning = False
        self.prev_distracted = False
        self.smoothed_ear_left = None
        self.smoothed_ear_right = None
        self.smoothed_mar = None
        self.smoothed_head_yaw = None
        self.smoothed_head_pitch = None
        self.last_landmarks = None

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[DriverEvent]]:
        started_at = time.perf_counter()
        wall_now = time.time()
        events: List[DriverEvent] = []
        self.frame_count += 1

        if not self._ensure_face_landmarker_ready():
            self._record_timing("process", (time.perf_counter() - started_at) * 1000.0)
            return frame, events

        detection_frame = frame
        frame_height, frame_width = frame.shape[:2]
        if frame_width > self.detection_max_width:
            resized_height = max(1, int(frame_height * (self.detection_max_width / frame_width)))
            detection_frame = cv2.resize(
                frame,
                (self.detection_max_width, resized_height),
                interpolation=cv2.INTER_AREA,
            )

        detect_height, detect_width = detection_frame.shape[:2]
        try:
            detect_started_at = time.perf_counter()
            results = self._detect_landmarks(detection_frame)
            if not results.face_landmarks:
                enhanced_frame = self._equalize_detection_frame(detection_frame)
                results = self._detect_landmarks(enhanced_frame)
            self._record_timing("detect", (time.perf_counter() - detect_started_at) * 1000.0)
        except Exception:
            logger.exception("FaceLandmarker error.")
            self._record_timing("process", (time.perf_counter() - started_at) * 1000.0)
            return frame, events

        if not results.face_landmarks:
            self.state.face_detected = False
            self.frames_without_face += 1
            if self.last_landmarks is not None and (wall_now - self.last_face_seen_at) <= self.landmark_hold_seconds:
                self._record_timing("process", (time.perf_counter() - started_at) * 1000.0)
                return frame, events
            self._reset_face_metrics()
            self._record_timing("process", (time.perf_counter() - started_at) * 1000.0)
            return frame, events

        landmarks = results.face_landmarks[0]
        self.state.face_detected = True
        self.frames_with_face += 1
        self.last_landmarks = landmarks
        self.last_face_seen_at = wall_now

        raw_ear_left = self._calculate_ear(landmarks, self.LEFT_EYE, detect_width, detect_height)
        raw_ear_right = self._calculate_ear(landmarks, self.RIGHT_EYE, detect_width, detect_height)
        self.smoothed_ear_left = self._smooth_metric(self.smoothed_ear_left, raw_ear_left, self.METRIC_SMOOTHING_ALPHA)
        self.smoothed_ear_right = self._smooth_metric(self.smoothed_ear_right, raw_ear_right, self.METRIC_SMOOTHING_ALPHA)
        self.state.ear_left = self.smoothed_ear_left
        self.state.ear_right = self.smoothed_ear_right
        raw_avg_ear = (raw_ear_left + raw_ear_right) / 2.0

        raw_mar = self._calculate_mar(landmarks, detect_width, detect_height)
        self.smoothed_mar = self._smooth_metric(self.smoothed_mar, raw_mar, self.METRIC_SMOOTHING_ALPHA)
        self.state.mar = self.smoothed_mar

        raw_head_yaw, raw_head_pitch = self._estimate_head_pose(landmarks)
        self.smoothed_head_yaw = self._smooth_metric(self.smoothed_head_yaw, raw_head_yaw, self.METRIC_SMOOTHING_ALPHA)
        self.smoothed_head_pitch = self._smooth_metric(
            self.smoothed_head_pitch,
            raw_head_pitch,
            self.METRIC_SMOOTHING_ALPHA,
        )
        self.state.head_yaw = self.smoothed_head_yaw
        self.state.head_pitch = self.smoothed_head_pitch

        eyes_closed_threshold = self.EAR_OPEN_THRESHOLD if self.prev_eyes_closed else self.EAR_CLOSED_THRESHOLD
        eyes_closed = raw_avg_ear < eyes_closed_threshold
        yawn_threshold = self.MAR_END_THRESHOLD if self.prev_yawning else self.MAR_THRESHOLD
        is_yawning = raw_mar > yawn_threshold

        if eyes_closed:
            if self.eyes_closed_start is None:
                self.eyes_closed_start = wall_now
            self.state.eyes_closed_duration = wall_now - self.eyes_closed_start
        else:
            if self.prev_eyes_closed and self.eyes_closed_start is not None:
                final_duration = wall_now - self.eyes_closed_start
                if final_duration > self.EYES_CLOSED_TIME_THRESHOLD and (wall_now - self.last_fatigue_event) > self.event_cooldown:
                    events.append(
                        DriverEvent(
                            event_type=DriverEventType.FATIGUE,
                            timestamp=wall_now,
                            confidence=0.8,
                            details=f"Eyes closed for {final_duration:.1f}s",
                        )
                    )
                    self.last_fatigue_event = wall_now
            self.eyes_closed_start = None
            self.state.eyes_closed_duration = 0.0

        if is_yawning:
            if self.yawn_start is None:
                self.yawn_start = wall_now
        else:
            if self.prev_yawning and self.yawn_start is not None:
                yawn_duration = wall_now - self.yawn_start
                if yawn_duration > 0.5 and (wall_now - self.last_fatigue_event) > self.event_cooldown:
                    events.append(
                        DriverEvent(
                            event_type=DriverEventType.FATIGUE,
                            timestamp=wall_now,
                            confidence=0.8,
                            details=f"Yawning for {yawn_duration:.1f}s",
                        )
                    )
                    self.last_fatigue_event = wall_now
            self.yawn_start = None

        self.prev_eyes_closed = eyes_closed
        self.prev_yawning = is_yawning
        self.state.is_fatigued = self.state.eyes_closed_duration > self.EYES_CLOSED_TIME_THRESHOLD or is_yawning

        is_distracted = (
            abs(self.state.head_yaw) > self.HEAD_YAW_THRESHOLD
            or abs(self.state.head_pitch) > self.HEAD_PITCH_THRESHOLD
        )
        if is_distracted and not self.prev_distracted and (wall_now - self.last_distraction_event) > self.event_cooldown:
            events.append(
                DriverEvent(
                    event_type=DriverEventType.DISTRACTION,
                    timestamp=wall_now,
                    confidence=0.75,
                    details=f"Head yaw: {self.state.head_yaw:.1f}, pitch: {self.state.head_pitch:.1f}",
                )
            )
            self.last_distraction_event = wall_now

        self.prev_distracted = is_distracted
        self.state.is_distracted = is_distracted
        self._record_timing("process", (time.perf_counter() - started_at) * 1000.0)
        return frame, events

    def get_state_dict(self) -> dict:
        return {
            "face_detected": bool(self.state.face_detected),
            "ear_left": round(self.state.ear_left, 3),
            "ear_right": round(self.state.ear_right, 3),
            "mar": round(self.state.mar, 3),
            "head_yaw": round(self.state.head_yaw, 1),
            "head_pitch": round(self.state.head_pitch, 1),
            "eyes_closed_duration": round(self.state.eyes_closed_duration, 1),
            "is_fatigued": bool(self.state.is_fatigued),
            "is_distracted": bool(self.state.is_distracted),
            "mediapipe_available": bool(MEDIAPIPE_AVAILABLE),
            "detector_ready": bool(self.face_landmarker is not None),
            "status_message": self._get_detector_status_message(),
        }
