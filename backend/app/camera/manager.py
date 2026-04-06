"""
Camera Manager - Simple working implementation
"""
import threading
import time
import base64
import cv2
from typing import Optional, Callable, List, Tuple
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
    owner_module: Optional[str] = None
    state_version: int = 0


@dataclass
class DriverEventData:
    """Driver event data for broadcasting."""
    event_type: str
    timestamp: float
    confidence: float
    details: str


@dataclass
class GateEventData:
    """Gate attendance event data for broadcasting."""
    event_type: str
    timestamp: float
    confidence: float
    details: str
    person_id: str = ""
    person_name: str = ""
    access_granted: bool = False
    ppe_compliant: bool = True


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
        self.latest_frame_b64: Optional[str] = None
        self.latest_frame_sequence = 0
        self.frame_lock = threading.Lock()
        self.preview_processing_thread: Optional[threading.Thread] = None
        self.preview_frame_lock = threading.Lock()
        self.pending_preview_frame = None
        self.pending_preview_frame_sequence = 0
        self.processed_preview_frame_sequence = 0
        
        self.frames_captured = 0
        self.start_time = 0.0
        self.mode = "idle"
        self.source_type = "none"
        self.source_id = ""
        self.error = ""
        self.owner_module: Optional[str] = None
        self.owner_token: Optional[str] = None
        self.state_version = 0

        self.target_fps = 18  # Favor stable capture latency over chasing peak FPS
        self.frame_interval = 1.0 / self.target_fps
        self.preview_fps = 12
        self.preview_frame_interval = 1.0 / self.preview_fps
        self.last_preview_encoded_at = 0.0

        # Detection intervals keep the capture loop responsive under CPU load.
        self.driver_detector = None
        self.driver_state: dict = {}
        self.pending_driver_events: List[DriverEventData] = []
        self.driver_events_lock = threading.Lock()
        self.driver_detection_interval = 0.2
        self.last_driver_detection_at = 0.0
        self.gate_detector = None
        self.gate_state: dict = {}
        self.pending_gate_events: List[GateEventData] = []
        self.gate_events_lock = threading.Lock()
        self.gate_detection_interval = 0.3
        self.last_gate_detection_at = 0.0
        self.gate_processing_thread: Optional[threading.Thread] = None
        self.gate_frame_lock = threading.Lock()
        self.pending_gate_frame = None
        self.pending_gate_frame_sequence = 0
        self.processed_gate_frame_sequence = 0
        
        self._initialized = True
        print("[CameraManager] Initialized")

    def has_control(self, owner_module: Optional[str], owner_token: Optional[str]) -> bool:
        if not self.running:
            return True
        if not self.owner_module and not self.owner_token:
            return True
        if owner_module and self.owner_module == owner_module:
            return True
        return self.owner_module == owner_module and self.owner_token == owner_token

    def get_owner_label(self) -> str:
        return self.owner_module or "another module"

    def _set_owner(self, owner_module: Optional[str], owner_token: Optional[str]) -> None:
        self.owner_module = owner_module
        self.owner_token = owner_token

    def _clear_owner(self) -> None:
        self.owner_module = None
        self.owner_token = None

    def _bump_state_version(self) -> None:
        self.state_version += 1
    
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

    def _ensure_gate_detector(self):
        """Lazy load gate attendance recognizer."""
        if self.gate_detector is None:
            print("[CameraManager] Loading gate attendance recognizer...")
            try:
                from app.services.gate_attendance import gate_attendance_recognizer

                self.gate_detector = gate_attendance_recognizer
                print("[CameraManager] Gate attendance recognizer ready")
            except Exception as e:
                print(f"[CameraManager] Failed to load gate recognizer: {e}")
                import traceback
                traceback.print_exc()

    def _start_gate_processing_worker(self) -> None:
        if self.gate_processing_thread and self.gate_processing_thread.is_alive():
            return

        self.gate_processing_thread = threading.Thread(
            target=self._gate_processing_loop,
            daemon=True,
        )
        self.gate_processing_thread.start()
        print("[CameraManager] Gate processing thread started")

    def _start_preview_processing_worker(self) -> None:
        if self.preview_processing_thread and self.preview_processing_thread.is_alive():
            return

        self.preview_processing_thread = threading.Thread(
            target=self._preview_processing_loop,
            daemon=True,
        )
        self.preview_processing_thread.start()
        print("[CameraManager] Preview processing thread started")

    def _gate_processing_loop(self) -> None:
        print("[CameraManager] Gate processing loop started")

        while self.running:
            if self.mode != "gate":
                time.sleep(0.01)
                continue

            if self.gate_detector is None:
                self._ensure_gate_detector()
                time.sleep(0.02)
                continue

            frame = None
            frame_sequence = 0
            with self.gate_frame_lock:
                if (
                    self.pending_gate_frame is not None
                    and self.pending_gate_frame_sequence > self.processed_gate_frame_sequence
                ):
                    frame = self.pending_gate_frame.copy()
                    frame_sequence = self.pending_gate_frame_sequence

            if frame is None:
                time.sleep(0.01)
                continue

            try:
                _, events = self.gate_detector.process_frame(frame)
                self.gate_state = self.gate_detector.get_state_dict()

                if events:
                    with self.gate_events_lock:
                        for ev in events:
                            self.pending_gate_events.append(
                                GateEventData(
                                    event_type=ev.event_type,
                                    timestamp=ev.timestamp,
                                    confidence=ev.confidence,
                                    details=ev.details,
                                    person_id=ev.person_id or "",
                                    person_name=ev.person_name or "",
                                    access_granted=ev.access_granted,
                                    ppe_compliant=ev.ppe_compliant,
                                )
                            )
                            print(
                                f"[CameraManager] Gate event: {ev.event_type} - {ev.details}"
                            )

                self.processed_gate_frame_sequence = frame_sequence
            except Exception as e:
                print(f"[CameraManager] Gate recognition error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.02)

        print("[CameraManager] Gate processing loop ended")

    def _preview_processing_loop(self) -> None:
        print("[CameraManager] Preview processing loop started")

        while self.running:
            frame = None
            frame_sequence = 0
            with self.preview_frame_lock:
                if (
                    self.pending_preview_frame is not None
                    and self.pending_preview_frame_sequence > self.processed_preview_frame_sequence
                ):
                    frame = self.pending_preview_frame.copy()
                    frame_sequence = self.pending_preview_frame_sequence

            if frame is None:
                time.sleep(0.01)
                continue

            try:
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, 32]
                ret, jpeg = cv2.imencode(".jpg", frame, encode_params)
                if ret:
                    frame_bytes = jpeg.tobytes()
                    frame_b64 = base64.b64encode(frame_bytes).decode("utf-8")
                    with self.frame_lock:
                        self.latest_frame = frame_bytes
                        self.latest_frame_b64 = frame_b64
                        self.latest_frame_sequence = frame_sequence
                    self.processed_preview_frame_sequence = frame_sequence
                else:
                    time.sleep(0.01)
            except Exception as e:
                print(f"[CameraManager] Preview encode error: {e}")
                time.sleep(0.02)

        print("[CameraManager] Preview processing loop ended")
    
    def start(
        self,
        source_type: str = "webcam",
        source_id: str = "0",
        owner_module: Optional[str] = None,
        owner_token: Optional[str] = None,
    ) -> bool:
        """Start camera capture."""
        print(f"[CameraManager] Start requested: {source_type}, {source_id}")
        
        if self.running:
            if not self.has_control(owner_module, owner_token):
                self.error = f"Camera is currently controlled by {self.get_owner_label()}."
                print(f"[CameraManager] {self.error}")
                return False
            print("[CameraManager] Already running, stopping first")
            self.stop()
        
        self.source_type = source_type
        self.source_id = source_id
        self.error = ""
        self.mode = "idle"
        self._set_owner(owner_module, owner_token)
        self._bump_state_version()

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
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            self.cap.set(cv2.CAP_PROP_FPS, 20)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.running = True
        self.frames_captured = 0
        self.start_time = time.time()
        self.latest_frame = None
        self.latest_frame_b64 = None
        self.latest_frame_sequence = 0
        self.last_driver_detection_at = 0.0
        self.last_gate_detection_at = 0.0
        self.last_preview_encoded_at = 0.0
        self.pending_gate_frame = None
        self.pending_gate_frame_sequence = 0
        self.processed_gate_frame_sequence = 0
        self.pending_preview_frame = None
        self.pending_preview_frame_sequence = 0
        self.processed_preview_frame_sequence = 0

        # Start capture thread
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        print("[CameraManager] Capture thread started")
        self._start_gate_processing_worker()
        self._start_preview_processing_worker()

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

        if self.gate_processing_thread:
            self.gate_processing_thread.join(timeout=1.0)
            if self.gate_processing_thread.is_alive():
                print("[CameraManager] Gate processing thread still alive after timeout")
            self.gate_processing_thread = None

        if self.preview_processing_thread:
            self.preview_processing_thread.join(timeout=1.0)
            if self.preview_processing_thread.is_alive():
                print("[CameraManager] Preview processing thread still alive after timeout")
            self.preview_processing_thread = None

        # Clear frame
        with self.frame_lock:
            self.latest_frame = None
            self.latest_frame_b64 = None
            self.latest_frame_sequence = 0
            self.last_preview_encoded_at = 0.0
        with self.gate_frame_lock:
            self.pending_gate_frame = None
            self.pending_gate_frame_sequence = 0
            self.processed_gate_frame_sequence = 0
        with self.preview_frame_lock:
            self.pending_preview_frame = None
            self.pending_preview_frame_sequence = 0
            self.processed_preview_frame_sequence = 0

        if self.gate_detector is not None:
            try:
                self.gate_detector.reset_live_session(
                    clear_pending_reviews=True,
                    reason="Gate camera stopped before the operator resolved the live review.",
                )
                self.gate_state = self.gate_detector.get_state_dict()
            except Exception as e:
                print(f"[CameraManager] Failed to reset gate session: {e}")

        self.mode = "idle"
        self._clear_owner()
        self._bump_state_version()

        print("[CameraManager] Stop completed")
    
    def set_mode(self, mode: str) -> None:
        """Set processing mode."""
        if mode in ["gate", "driver", "idle"]:
            if self.mode == "gate" and mode != "gate" and self.gate_detector is not None:
                try:
                    self.gate_detector.reset_live_session(
                        clear_pending_reviews=True,
                        reason="Recognition mode was disabled before the live review was resolved.",
                    )
                    self.gate_state = self.gate_detector.get_state_dict()
                except Exception as e:
                    print(f"[CameraManager] Failed to clear gate reviews while switching mode: {e}")
            self.mode = mode
            self._bump_state_version()
            print(f"[CameraManager] Mode set to: {mode}")
            if mode == "driver":
                self._ensure_driver_detector()
            elif mode == "gate":
                self._ensure_gate_detector()
    
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
            error=self.error,
            owner_module=self.owner_module,
            state_version=self.state_version,
        )
    
    def get_driver_state(self) -> dict:
        """Get current driver monitoring state."""
        return self.driver_state.copy()

    def get_gate_state(self) -> dict:
        """Get current gate attendance state."""
        return self.gate_state.copy()
    
    def get_pending_driver_events(self) -> List[DriverEventData]:
        """Get and clear pending driver events."""
        with self.driver_events_lock:
            events = self.pending_driver_events.copy()
            self.pending_driver_events.clear()
        return events

    def get_pending_gate_events(self) -> List[GateEventData]:
        """Get and clear pending gate attendance events."""
        with self.gate_events_lock:
            events = self.pending_gate_events.copy()
            self.pending_gate_events.clear()
        return events
    
    def get_latest_frame(self) -> Optional[str]:
        """Get latest frame as base64 string."""
        with self.frame_lock:
            if self.latest_frame_b64:
                return self.latest_frame_b64
        return None

    def get_latest_frame_packet(self) -> Optional[Tuple[int, str]]:
        """Get the latest encoded frame plus a monotonically increasing sequence."""
        with self.frame_lock:
            if self.latest_frame_b64:
                return self.latest_frame_sequence, self.latest_frame_b64
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

            if self.mode == "driver":
                if self.driver_detector is None:
                    self._ensure_driver_detector()

                run_detection = (
                    now - self.last_driver_detection_at
                    >= self.driver_detection_interval
                )

                if self.driver_detector is not None and run_detection:
                    try:
                        self.last_driver_detection_at = now
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
            elif self.mode == "gate":
                if self.gate_detector is None:
                    self._ensure_gate_detector()

                run_detection = (
                    now - self.last_gate_detection_at
                    >= self.gate_detection_interval
                )

                if self.gate_detector is not None and run_detection:
                    self.last_gate_detection_at = now
                    with self.gate_frame_lock:
                        self.pending_gate_frame = frame.copy()
                        self.pending_gate_frame_sequence += 1

                if self.gate_detector is not None:
                    frame = self.gate_detector.draw_live_overlay(frame)

            should_refresh_preview = (
                now - self.last_preview_encoded_at >= self.preview_frame_interval
            )
            if should_refresh_preview:
                with self.preview_frame_lock:
                    self.pending_preview_frame = frame.copy()
                    self.pending_preview_frame_sequence += 1
                self.last_preview_encoded_at = now

            last_frame_time = time.time()

            # Log every 100 frames
            if self.frames_captured % 100 == 0:
                print(f"[CameraManager] Captured {self.frames_captured} frames")

        print("[CameraManager] Capture loop ended")


# Global singleton
camera_manager = CameraManager()
