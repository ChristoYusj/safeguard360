"""
Driver Monitoring - Fatigue and Distraction Detection using MediaPipe
"""
import cv2
import numpy as np
import time
from dataclasses import dataclass
from typing import Optional, Tuple, List
from enum import Enum

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe import tasks
    MEDIAPIPE_AVAILABLE = True
except ImportError as e:
    MEDIAPIPE_AVAILABLE = False
    print(f"[DriverDetector] MediaPipe not installed: {e}")


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
    ear_left: float = 0.0  # Eye Aspect Ratio
    ear_right: float = 0.0
    mar: float = 0.0  # Mouth Aspect Ratio (for yawning)
    head_pitch: float = 0.0  # Up/down
    head_yaw: float = 0.0  # Left/right
    eyes_closed_duration: float = 0.0
    is_fatigued: bool = False
    is_distracted: bool = False


class DriverDetector:
    """Detect fatigue and distraction using MediaPipe Face Mesh."""
    
    # MediaPipe Face Mesh landmark indices
    # Left eye
    LEFT_EYE = [362, 385, 387, 263, 373, 380]
    # Right eye
    RIGHT_EYE = [33, 160, 158, 133, 153, 144]
    # Mouth
    MOUTH = [61, 291, 0, 17, 405, 321, 375, 291]
    MOUTH_VERTICAL = [13, 14]  # Top and bottom lip
    MOUTH_HORIZONTAL = [78, 308]  # Left and right corner
    
    # Thresholds
    EAR_THRESHOLD = 0.2  # Eyes considered closed below this
    EYES_CLOSED_TIME_THRESHOLD = 0.8  # Short sustained eye closure = fatigue
    MAR_THRESHOLD = 0.6  # Mouth open (yawning) above this
    HEAD_YAW_THRESHOLD = 30  # Degrees of head turn = distraction
    HEAD_PITCH_THRESHOLD = 20  # Degrees of head tilt = distraction
    
    def __init__(self):
        self.state = DriverState()
        self.eyes_closed_start: Optional[float] = None
        self.yawn_start: Optional[float] = None  # Track yawn start time
        self.last_fatigue_event: float = 0
        self.last_distraction_event: float = 0
        self.event_cooldown = 5.0  # Minimum seconds between same event type

        # Track previous frame state for edge detection (fire on state END)
        self.prev_eyes_closed = False
        self.prev_yawning = False
        self.prev_distracted = False

        # Store duration from completed events (for final logging)
        self.last_eyes_closed_duration = 0.0
        self.last_yawn_duration = 0.0

        self.frame_count = 0
        self.last_log_time = 0
        self.face_landmarker = None
        self.last_landmarks = None
        self.last_face_seen_at = 0.0
        self.landmark_hold_seconds = 0.5
        self.detection_max_width = 256

        print(f"[DriverDetector] MEDIAPIPE_AVAILABLE = {MEDIAPIPE_AVAILABLE}")

        if not MEDIAPIPE_AVAILABLE:
            print("[DriverDetector] Initialized without MediaPipe")
            return

        try:
            # Download model if not present
            import os
            import urllib.request

            model_dir = os.path.join(os.path.dirname(__file__), "models")
            os.makedirs(model_dir, exist_ok=True)
            model_path = os.path.join(model_dir, "face_landmarker.task")

            if not os.path.exists(model_path):
                print("[DriverDetector] Downloading face_landmarker model...")
                model_url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
                urllib.request.urlretrieve(model_url, model_path)
                print(f"[DriverDetector] Model downloaded to {model_path}")

            # Initialize FaceLandmarker with Tasks API
            base_options = mp_python.BaseOptions(model_asset_path=model_path)
            options = mp_vision.FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.3,
                min_face_presence_confidence=0.3,
                min_tracking_confidence=0.3,
                output_face_blendshapes=True
            )
            self.face_landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            print("[DriverDetector] Initialized with MediaPipe FaceLandmarker (Tasks API)")
        except Exception as e:
            print(f"[DriverDetector] Failed to initialize FaceLandmarker: {e}")
            import traceback
            traceback.print_exc()
            self.face_landmarker = None
    
    def _calculate_ear(self, landmarks, eye_indices, w: int, h: int) -> float:
        """Calculate Eye Aspect Ratio."""
        points = []
        for idx in eye_indices:
            lm = landmarks[idx]
            points.append((lm.x * w, lm.y * h))
        
        # Vertical distances
        v1 = np.linalg.norm(np.array(points[1]) - np.array(points[5]))
        v2 = np.linalg.norm(np.array(points[2]) - np.array(points[4]))
        # Horizontal distance
        h1 = np.linalg.norm(np.array(points[0]) - np.array(points[3]))
        
        if h1 == 0:
            return 0.3
        
        ear = (v1 + v2) / (2.0 * h1)
        return ear
    
    def _calculate_mar(self, landmarks, w: int, h: int) -> float:
        """Calculate Mouth Aspect Ratio for yawning detection."""
        top = landmarks[13]
        bottom = landmarks[14]
        left = landmarks[78]
        right = landmarks[308]
        
        vertical = np.linalg.norm(
            np.array([top.x * w, top.y * h]) - 
            np.array([bottom.x * w, bottom.y * h])
        )
        horizontal = np.linalg.norm(
            np.array([left.x * w, left.y * h]) - 
            np.array([right.x * w, right.y * h])
        )
        
        if horizontal == 0:
            return 0.0
        
        return vertical / horizontal
    
    def _estimate_head_pose(self, landmarks, w: int, h: int) -> Tuple[float, float]:
        """Estimate head pose (yaw, pitch) from face landmarks."""
        # Use nose tip and face edges for simple estimation
        nose = landmarks[1]
        left_face = landmarks[234]
        right_face = landmarks[454]
        forehead = landmarks[10]
        chin = landmarks[152]
        
        # Yaw: difference between nose and face center
        face_center_x = (left_face.x + right_face.x) / 2
        yaw = (nose.x - face_center_x) * 100  # Rough degrees
        
        # Pitch: vertical position of nose relative to face
        face_center_y = (forehead.y + chin.y) / 2
        pitch = (nose.y - face_center_y) * 100  # Rough degrees
        
        return yaw, pitch
    
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[DriverEvent]]:
        """Process a frame and return annotated frame + any events."""
        events = []
        self.frame_count += 1
        now = time.time()
        
        # Log every 2 seconds
        if now - self.last_log_time > 2.0:
            print(f"[DriverDetector] Processing frame {self.frame_count}, shape: {frame.shape}, dtype: {frame.dtype}")
            self.last_log_time = now
        
        h, w = frame.shape[:2]
        
        # Draw frame info
        cv2.putText(frame, f"Frame: {w}x{h}", (w - 120, 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        if not MEDIAPIPE_AVAILABLE or self.face_landmarker is None:
            # Draw "MediaPipe not available" message
            cv2.putText(frame, "MediaPipe not installed", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame, events

        # Run detection on a smaller image for smoother driver mode.
        detection_frame = frame
        if w > self.detection_max_width:
            detection_height = max(1, int(h * (self.detection_max_width / w)))
            detection_frame = cv2.resize(
                frame,
                (self.detection_max_width, detection_height),
                interpolation=cv2.INTER_LINEAR,
            )

        # Convert to RGB for MediaPipe
        rgb = cv2.cvtColor(detection_frame, cv2.COLOR_BGR2RGB)

        try:
            # Create MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results = self.face_landmarker.detect(mp_image)
        except Exception as e:
            print(f"[DriverDetector] FaceLandmarker error: {e}")
            cv2.putText(frame, f"Error: {str(e)[:30]}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            return frame, events

        if not results.face_landmarks:
            self.state.face_detected = False
            self.eyes_closed_start = None
            if now - self.last_face_seen_at <= self.landmark_hold_seconds and self.last_landmarks is not None:
                frame = self._draw_annotations(frame, self.last_landmarks, w, h)
                return frame, events
            cv2.putText(frame, "No face detected", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            cv2.putText(frame, "Look at camera", (10, 55),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
            return frame, events

        self.state.face_detected = True
        landmarks = results.face_landmarks[0]  # Tasks API: list of NormalizedLandmark
        self.last_landmarks = landmarks
        self.last_face_seen_at = now
        num_landmarks = len(landmarks)
        
        # Log face detection every 2 seconds
        if now - self.last_log_time > 2.0:
            self.last_log_time = now
            print(f"[DriverDetector] Face detected! Landmarks: {num_landmarks}")
        
        # Calculate metrics
        self.state.ear_left = self._calculate_ear(landmarks, self.LEFT_EYE, w, h)
        self.state.ear_right = self._calculate_ear(landmarks, self.RIGHT_EYE, w, h)
        avg_ear = (self.state.ear_left + self.state.ear_right) / 2
        
        self.state.mar = self._calculate_mar(landmarks, w, h)
        self.state.head_yaw, self.state.head_pitch = self._estimate_head_pose(landmarks, w, h)

        # Log metrics periodically
        if self.frame_count % 60 == 0:
            print(f"[DriverDetector] EAR: {avg_ear:.2f}, MAR: {self.state.mar:.2f}, Yaw: {self.state.head_yaw:.1f}, Pitch: {self.state.head_pitch:.1f}")

        # === FATIGUE DETECTION (fire event when state ENDS) ===

        # Detect current states
        eyes_closed = avg_ear < self.EAR_THRESHOLD
        is_yawning = self.state.mar > self.MAR_THRESHOLD

        # Track eyes-closed duration (for live UI display)
        if eyes_closed:
            if self.eyes_closed_start is None:
                self.eyes_closed_start = now
            self.state.eyes_closed_duration = now - self.eyes_closed_start
        else:
            # Eyes just OPENED - check if we should fire an event
            if self.prev_eyes_closed and self.eyes_closed_start is not None:
                final_duration = now - self.eyes_closed_start
                if final_duration > self.EYES_CLOSED_TIME_THRESHOLD:
                    if (now - self.last_fatigue_event) > self.event_cooldown:
                        events.append(DriverEvent(
                            event_type=DriverEventType.FATIGUE,
                            timestamp=now,
                            confidence=0.8,
                            details=f"Eyes closed for {final_duration:.1f}s"
                        ))
                        self.last_fatigue_event = now
                        print(f"[DriverDetector] Eyes-closed event: {final_duration:.1f}s")
            self.eyes_closed_start = None
            self.state.eyes_closed_duration = 0

        # Track yawning - fire event when yawn ENDS
        if is_yawning:
            if self.yawn_start is None:
                self.yawn_start = now
        else:
            # Yawn just ENDED - fire event if yawn lasted long enough
            if self.prev_yawning and self.yawn_start is not None:
                yawn_duration = now - self.yawn_start
                if yawn_duration > 0.5:  # At least 0.5s to count as a real yawn
                    if (now - self.last_fatigue_event) > self.event_cooldown:
                        events.append(DriverEvent(
                            event_type=DriverEventType.FATIGUE,
                            timestamp=now,
                            confidence=0.8,
                            details=f"Yawning for {yawn_duration:.1f}s"
                        ))
                        self.last_fatigue_event = now
                        print(f"[DriverDetector] Yawn event: {yawn_duration:.1f}s")
            self.yawn_start = None

        # Update previous states for next frame edge detection
        self.prev_eyes_closed = eyes_closed
        self.prev_yawning = is_yawning

        # Update fatigue state flag (for live UI warning)
        eyes_closed_long = self.state.eyes_closed_duration > self.EYES_CLOSED_TIME_THRESHOLD
        self.state.is_fatigued = eyes_closed_long or is_yawning

        # === DISTRACTION DETECTION (fire when looking away, like an alert) ===

        is_distracted = (
            abs(self.state.head_yaw) > self.HEAD_YAW_THRESHOLD or
            abs(self.state.head_pitch) > self.HEAD_PITCH_THRESHOLD
        )

        # Fire distraction event when head first turns away (alert style)
        if is_distracted and not self.prev_distracted:
            if (now - self.last_distraction_event) > self.event_cooldown:
                events.append(DriverEvent(
                    event_type=DriverEventType.DISTRACTION,
                    timestamp=now,
                    confidence=0.75,
                    details=f"Head yaw: {self.state.head_yaw:.1f}, pitch: {self.state.head_pitch:.1f}"
                ))
                self.last_distraction_event = now
                print(f"[DriverDetector] Distraction event")

        self.prev_distracted = is_distracted
        self.state.is_distracted = is_distracted

        # Draw annotations
        frame = self._draw_annotations(frame, landmarks, w, h)

        return frame, events

    def draw_live_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Draw a lightweight overlay from the latest known driver state."""
        now = time.time()
        h, w = frame.shape[:2]
        cv2.putText(frame, f"Frame: {w}x{h}", (w - 120, 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        if not MEDIAPIPE_AVAILABLE or self.face_landmarker is None:
            cv2.putText(frame, "MediaPipe not installed", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame

        if self.last_landmarks is not None and now - self.last_face_seen_at <= self.landmark_hold_seconds:
            return self._draw_annotations(frame, self.last_landmarks, w, h)

        # Status panel background
        cv2.rectangle(frame, (5, 5), (150, 110), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, 5), (150, 110), (255, 255, 255), 1)

        avg_ear = (self.state.ear_left + self.state.ear_right) / 2
        y = 22

        face_label = "FACE OK" if self.state.face_detected else "NO FACE"
        face_color = (0, 255, 0) if self.state.face_detected else (0, 165, 255)
        cv2.putText(frame, face_label, (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, face_color, 1)

        y += 18
        ear_color = (0, 255, 0) if avg_ear > self.EAR_THRESHOLD else (0, 0, 255)
        cv2.putText(frame, f"EAR: {avg_ear:.2f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, ear_color, 1)

        y += 18
        mar_color = (0, 0, 255) if self.state.mar > self.MAR_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"MAR: {self.state.mar:.2f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, mar_color, 1)

        y += 18
        yaw_color = (0, 0, 255) if abs(self.state.head_yaw) > self.HEAD_YAW_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"Yaw: {self.state.head_yaw:.1f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, yaw_color, 1)

        y += 18
        pitch_color = (0, 0, 255) if abs(self.state.head_pitch) > self.HEAD_PITCH_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"Pitch: {self.state.head_pitch:.1f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, pitch_color, 1)

        if self.state.is_fatigued:
            cv2.rectangle(frame, (w - 220, 10), (w - 10, 45), (0, 0, 200), -1)
            cv2.putText(frame, "FATIGUE!", (w - 210, 35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        if self.state.is_distracted:
            cv2.rectangle(frame, (w - 220, 50), (w - 10, 85), (0, 140, 255), -1)
            cv2.putText(frame, "DISTRACTED!", (w - 215, 75),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return frame
    
    def _draw_annotations(self, frame: np.ndarray, landmarks, w: int, h: int) -> np.ndarray:
        """Draw face mesh and status indicators."""
        # Draw face outline (jawline)
        face_outline = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
                       397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
                       172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
        outline_points = []
        for idx in face_outline:
            lm = landmarks[idx]
            outline_points.append((int(lm.x * w), int(lm.y * h)))
        outline_points = np.array(outline_points, np.int32)
        cv2.polylines(frame, [outline_points], True, (0, 255, 255), 2)
        
        # Draw eye contours with thicker lines
        for eye_indices in [self.LEFT_EYE, self.RIGHT_EYE]:
            points = []
            for idx in eye_indices:
                lm = landmarks[idx]
                points.append((int(lm.x * w), int(lm.y * h)))
            points = np.array(points, np.int32)
            cv2.polylines(frame, [points], True, (0, 255, 0), 2)
            # Draw center point
            cx = sum(p[0] for p in points) // len(points)
            cy = sum(p[1] for p in points) // len(points)
            cv2.circle(frame, (cx, cy), 3, (255, 255, 0), -1)
        
        # Draw mouth with more points
        mouth_outer = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
        mouth_pts = []
        for idx in mouth_outer:
            lm = landmarks[idx]
            mouth_pts.append((int(lm.x * w), int(lm.y * h)))
        mouth_pts = np.array(mouth_pts, np.int32)
        cv2.polylines(frame, [mouth_pts], True, (255, 0, 255), 2)
        
        # Draw nose tip
        nose = landmarks[1]
        cv2.circle(frame, (int(nose.x * w), int(nose.y * h)), 5, (255, 128, 0), -1)
        
        # Status panel background
        cv2.rectangle(frame, (5, 5), (150, 110), (0, 0, 0), -1)
        cv2.rectangle(frame, (5, 5), (150, 110), (255, 255, 255), 1)
        
        # Status text
        y = 22
        avg_ear = (self.state.ear_left + self.state.ear_right) / 2
        
        # Face detected indicator
        cv2.putText(frame, "FACE OK", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # EAR indicator
        y += 18
        ear_color = (0, 255, 0) if avg_ear > self.EAR_THRESHOLD else (0, 0, 255)
        cv2.putText(frame, f"EAR: {avg_ear:.2f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, ear_color, 1)
        
        # MAR indicator
        y += 18
        mar_color = (0, 0, 255) if self.state.mar > self.MAR_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"MAR: {self.state.mar:.2f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, mar_color, 1)
        
        # Head pose
        y += 18
        yaw_color = (0, 0, 255) if abs(self.state.head_yaw) > self.HEAD_YAW_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"Yaw: {self.state.head_yaw:.1f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, yaw_color, 1)
        
        y += 18
        pitch_color = (0, 0, 255) if abs(self.state.head_pitch) > self.HEAD_PITCH_THRESHOLD else (0, 255, 0)
        cv2.putText(frame, f"Pitch: {self.state.head_pitch:.1f}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, pitch_color, 1)
        
        # Alert indicators (large, visible)
        if self.state.is_fatigued:
            cv2.rectangle(frame, (w - 220, 10), (w - 10, 45), (0, 0, 200), -1)
            cv2.putText(frame, "FATIGUE!", (w - 210, 35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        if self.state.is_distracted:
            cv2.rectangle(frame, (w - 220, 50), (w - 10, 85), (0, 140, 255), -1)
            cv2.putText(frame, "DISTRACTED!", (w - 215, 75),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return frame
    
    def get_state_dict(self) -> dict:
        """Get current state as dictionary."""
        return {
            "face_detected": self.state.face_detected,
            "ear_left": round(self.state.ear_left, 3),
            "ear_right": round(self.state.ear_right, 3),
            "mar": round(self.state.mar, 3),
            "head_yaw": round(self.state.head_yaw, 1),
            "head_pitch": round(self.state.head_pitch, 1),
            "eyes_closed_duration": round(self.state.eyes_closed_duration, 1),
            "is_fatigued": self.state.is_fatigued,
            "is_distracted": self.state.is_distracted
        }


# Global singleton
driver_detector = DriverDetector()
