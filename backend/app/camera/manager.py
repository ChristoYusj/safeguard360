"""
Camera Manager - Simple working implementation
"""
import threading
import time
import base64
import cv2
from typing import Optional, Callable, List
from dataclasses import dataclass, asdict


@dataclass
class CameraState:
    """Current camera state."""
    active: bool
    source_type: str
    source_id: str
    fps: float
    frames_captured: int
    mode: str
    error: str = ""


@dataclass
class DriverEventData:
    """Driver event data for broadcasting."""
    event_type: str
    timestamp: float
    confidence: float
    details: str


class CameraManager:
    """Simple camera manager with background capture."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        self.latest_frame: Optional[bytes] = None  # JPEG encoded
        self.frame_lock = threading.Lock()
        
        self.frames_captured = 0
        self.start_time = 0.0
        self.mode = "idle"
        self.source_type = "none"
        self.source_id = ""
        self.error = ""

        self.target_fps = 20  # Favor stable capture latency over chasing peak FPS
        self.frame_interval = 1.0 / self.target_fps

        # Driver detection (run every Nth frame for performance)
        self.driver_detector = None
        self.driver_state: dict = {}
        self.pending_driver_events: List[DriverEventData] = []
        self.driver_events_lock = threading.Lock()
        self.detection_skip = 3  # Run detection every 3rd frame for smoother driver updates
        
        self._initialized = True
        print("[CameraManager] Initialized")
    
    def _ensure_driver_detector(self):
        """Lazy load driver detector."""
        if self.driver_detector is None:
            print("[CameraManager] Loading driver detector...")
            try:
                from app.inference.driver import driver_detector
                self.driver_detector = driver_detector
                print(f"[CameraManager] Driver detector loaded: {self.driver_detector}")
                print(f"[CameraManager] FaceLandmarker available: {self.driver_detector.face_landmarker is not None}")
            except Exception as e:
                print(f"[CameraManager] Failed to load driver detector: {e}")
                import traceback
                traceback.print_exc()
    
    def start(self, source_type: str = "webcam", source_id: str = "0") -> bool:
        """Start camera capture."""
        print(f"[CameraManager] Start requested: {source_type}, {source_id}")
        
        if self.running:
            print("[CameraManager] Already running, stopping first")
            self.stop()
        
        self.source_type = source_type
        self.source_id = source_id
        self.error = ""

        # Open camera
        try:
            if source_type == "webcam":
                device_id = int(source_id) if source_id.isdigit() else 0
                print(f"[CameraManager] Opening webcam {device_id}")
                self.cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
            elif source_type == "video_file":
                print(f"[CameraManager] Opening video file: {source_id}")
                self.cap = cv2.VideoCapture(source_id)
            elif source_type == "ip_stream":
                print(f"[CameraManager] Opening IP stream: {source_id}")
                self.cap = cv2.VideoCapture(source_id)
            else:
                self.error = f"Unknown source type: {source_type}"
                print(f"[CameraManager] Error: {self.error}")
                return False
        except Exception as e:
            self.error = f"Exception opening camera: {e}"
            print(f"[CameraManager] Exception: {e}")
            return False

        if not self.cap or not self.cap.isOpened():
            self.error = "Failed to open camera"
            print(f"[CameraManager] Failed to open camera")
            if self.cap:
                self.cap.release()
            self.cap = None
            return False

        print("[CameraManager] Camera opened successfully")

        # Set lower resolution for webcam (faster capture + processing)
        if source_type == "webcam":
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
        
        self.running = True
        self.frames_captured = 0
        self.start_time = time.time()
        self.latest_frame = None
        
        # Start capture thread
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        print("[CameraManager] Capture thread started")
        
        return True
    
    def stop(self) -> None:
        """Stop camera capture."""
        print("[CameraManager] Stop requested")
        
        # Set flag first to signal capture loop to exit
        self.running = False
        
        # Give capture loop time to notice the flag
        time.sleep(0.1)
        
        # Release camera first (this unblocks cap.read())
        print("[CameraManager] Releasing camera")
        cap = self.cap
        self.cap = None
        if cap:
            try:
                cap.release()
            except Exception as e:
                print(f"[CameraManager] Release error: {e}")
        
        # Now join thread with short timeout
        print("[CameraManager] Joining thread")
        if self.thread:
            self.thread.join(timeout=1.0)
            if self.thread.is_alive():
                print("[CameraManager] Thread still alive after timeout, continuing anyway")
            self.thread = None
        
        # Clear frame
        with self.frame_lock:
            self.latest_frame = None
        
        print("[CameraManager] Stop completed")
    
    def set_mode(self, mode: str) -> None:
        """Set processing mode."""
        if mode in ["gate", "driver", "idle"]:
            self.mode = mode
            print(f"[CameraManager] Mode set to: {mode}")
            if mode == "driver":
                self._ensure_driver_detector()
    
    def get_state(self) -> CameraState:
        """Get current state."""
        fps = 0.0
        if self.running and self.start_time > 0:
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                fps = round(self.frames_captured / elapsed, 1)
        
        return CameraState(
            active=self.running,
            source_type=self.source_type,
            source_id=self.source_id,
            fps=fps,
            frames_captured=self.frames_captured,
            mode=self.mode,
            error=self.error
        )
    
    def get_driver_state(self) -> dict:
        """Get current driver monitoring state."""
        return self.driver_state.copy()
    
    def get_pending_driver_events(self) -> List[DriverEventData]:
        """Get and clear pending driver events."""
        with self.driver_events_lock:
            events = self.pending_driver_events.copy()
            self.pending_driver_events.clear()
        return events
    
    def get_latest_frame(self) -> Optional[str]:
        """Get latest frame as base64 string."""
        with self.frame_lock:
            if self.latest_frame:
                return base64.b64encode(self.latest_frame).decode('utf-8')
        return None
    
    def _capture_loop(self) -> None:
        """Background capture loop."""
        print("[CameraManager] Capture loop started")
        last_frame_time = 0.0
        consecutive_failures = 0

        while self.running:
            # Check if camera still exists
            cap = self.cap
            if not cap:
                print("[CameraManager] Camera released, exiting loop")
                break

            # Rate limiting
            now = time.time()
            elapsed = now - last_frame_time
            if elapsed < self.frame_interval:
                time.sleep(0.005)  # Shorter sleep for responsiveness
                continue

            # Read frame directly
            try:
                ret, frame = cap.read()
            except Exception as e:
                print(f"[CameraManager] Read exception: {e}")
                break

            if not ret or frame is None:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    self.error = "Too many frame read failures"
                    print(f"[CameraManager] {self.error}")
                    break
                time.sleep(0.05)
                continue

            consecutive_failures = 0
            self.error = ""
            self.frames_captured += 1

            # Process frame based on mode (skip detection on most frames for perf)
            run_detection = (self.frames_captured % self.detection_skip == 0)

            if self.mode == "driver":
                if self.driver_detector is None:
                    self._ensure_driver_detector()

                if self.driver_detector is not None and run_detection:
                    try:
                        frame, events = self.driver_detector.process_frame(frame)
                        self.driver_state = self.driver_detector.get_state_dict()

                        # Queue any driver events
                        if events:
                            with self.driver_events_lock:
                                for ev in events:
                                    self.pending_driver_events.append(DriverEventData(
                                        event_type=ev.event_type.value,
                                        timestamp=ev.timestamp,
                                        confidence=ev.confidence,
                                        details=ev.details
                                    ))
                                    print(f"[CameraManager] Driver event: {ev.event_type.value} - {ev.details}")
                    except Exception as e:
                        print(f"[CameraManager] Driver detection error: {e}")
                        import traceback
                        traceback.print_exc()
                elif self.driver_detector is not None:
                    frame = self.driver_detector.draw_live_overlay(frame)

            # Encode as JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 50]
            ret, jpeg = cv2.imencode('.jpg', frame, encode_params)

            if not ret:
                continue

            # Store latest frame
            with self.frame_lock:
                self.latest_frame = jpeg.tobytes()

            last_frame_time = time.time()

            # Log every 100 frames
            if self.frames_captured % 100 == 0:
                print(f"[CameraManager] Captured {self.frames_captured} frames")

        print("[CameraManager] Capture loop ended")


# Global singleton
camera_manager = CameraManager()
