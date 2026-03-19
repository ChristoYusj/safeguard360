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
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("[DriverDetector] MediaPipe not installed")


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
    EYES_CLOSED_TIME_THRESHOLD = 2.0  # Seconds of closed eyes = fatigue
    MAR_THRESHOLD = 0.6  # Mouth open (yawning) above this
    HEAD_YAW_THRESHOLD = 30  # Degrees of head turn = distraction
    HEAD_PITCH_THRESHOLD = 20  # Degrees of head tilt = distraction
    
    def __init__(self):
        self.state = DriverState()
        self.eyes_closed_start: Optional[float] = None
        self.last_fatigue_event: float = 0
        self.last_distraction_event: float = 0
        self.event_cooldown = 3.0  # Seconds between same event type
        self.frame_count = 0
        self.last_log_time = 0
        
        print(f"[DriverDetector] MEDIAPIPE_AVAILABLE = {MEDIAPIPE_AVAILABLE}")
        
        if not MEDIAPIPE_AVAILABLE:
            self.face_mesh = None
            print("[DriverDetector] Initialized without MediaPipe")
            return
        
        try:
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.3,  # Lower threshold for better detection
                min_tracking_confidence=0.3
            )
            print("[DriverDetector] Initialized with MediaPipe FaceMesh")
        except Exception as e:
            print(f"[DriverDetector] Failed to initialize FaceMesh: {e}")
            self.face_mesh = None
    
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
        
        if not MEDIAPIPE_AVAILABLE or self.face_mesh is None:
            # Draw "MediaPipe not available" message
            cv2.putText(frame, "MediaPipe not installed", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame, events
        
        # Convert to RGB for MediaPipe
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        try:
            results = self.face_mesh.process(rgb)
        except Exception as e:
            print(f"[DriverDetector] FaceMesh error: {e}")
            cv2.putText(frame, f"Error: {str(e)[:30]}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            return frame, events
        
        if not results.multi_face_landmarks:
            self.state.face_detected = False
            self.eyes_closed_start = None
            cv2.putText(frame, "No face detected", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            cv2.putText(frame, "Look at camera", (10, 55),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
            return frame, events
        
        self.state.face_detected = True
        landmarks = results.multi_face_landmarks[0].landmark
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
        
        # Fatigue detection: eyes closed
        eyes_closed = avg_ear < self.EAR_THRESHOLD
        if eyes_closed:
            if self.eyes_closed_start is None:
                self.eyes_closed_start = now
            self.state.eyes_closed_duration = now - self.eyes_closed_start
        else:
            self.eyes_closed_start = None
            self.state.eyes_closed_duration = 0
        
        # Check for fatigue event
        is_fatigued = (
            self.state.eyes_closed_duration > self.EYES_CLOSED_TIME_THRESHOLD or
            self.state.mar > self.MAR_THRESHOLD
        )
        self.state.is_fatigued = is_fatigued
        
        if is_fatigued and (now - self.last_fatigue_event) > self.event_cooldown:
            detail = "Eyes closed" if self.state.eyes_closed_duration > self.EYES_CLOSED_TIME_THRESHOLD else "Yawning"
            events.append(DriverEvent(
                event_type=DriverEventType.FATIGUE,
                timestamp=now,
                confidence=0.8,
                details=detail
            ))
            self.last_fatigue_event = now
        
        # Distraction detection: head pose
        is_distracted = (
            abs(self.state.head_yaw) > self.HEAD_YAW_THRESHOLD or
            abs(self.state.head_pitch) > self.HEAD_PITCH_THRESHOLD
        )
        self.state.is_distracted = is_distracted
        
        if is_distracted and (now - self.last_distraction_event) > self.event_cooldown:
            events.append(DriverEvent(
                event_type=DriverEventType.DISTRACTION,
                timestamp=now,
                confidence=0.75,
                details=f"Head yaw: {self.state.head_yaw:.1f}, pitch: {self.state.head_pitch:.1f}"
            ))
            self.last_distraction_event = now
        
        # Draw annotations
        frame = self._draw_annotations(frame, landmarks, w, h)
        
        return frame, events
    
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
