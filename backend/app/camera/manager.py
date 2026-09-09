"""
Camera Manager - Simple working implementation
"""
import logging
import threading
import time
import cv2
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.config.settings import get_settings


logger = logging.getLogger(__name__)


def _json_safe_value(value):
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]

    module_name = type(value).__module__
    if module_name.startswith("numpy"):
        try:
            return value.item()
        except Exception:
            return str(value)

    return value


@dataclass
class WebcamProbeResult:
    device_id: int
    brightness: float
    contrast: float
    backend: str

    @property
    def score(self) -> float:
        return (self.brightness * 0.7) + (self.contrast * 0.3)


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
    ppe_status: str = "not_evaluated"
    ppe_details: dict = None
    review_reasons: List[str] = None


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
        self.lifecycle_lock = threading.RLock()
        self.stop_event = threading.Event()
        
        self.latest_frame: Optional[bytes] = None  # JPEG encoded
        self.latest_frame_sequence = 0
        self.frame_lock = threading.Lock()
        self.preview_processing_thread: Optional[threading.Thread] = None
        self.debug_lock = threading.Lock()
        self.debug_metrics: dict[str, object] = {}

        # Single shared slot holding the most recent raw capture frame.
        # Consumers (preview overlay, gate recognition, driver detection)
        # pull from this on their own cadence — the capture thread stays
        # lean so cap.read() can hit the device's native FPS.
        self.raw_frame_lock = threading.Lock()
        self.latest_raw_frame = None
        self.latest_raw_frame_sequence = 0
        
        self.frames_captured = 0
        self.start_time = 0.0
        self.mode = "idle"
        self.source_type = "none"
        self.source_id = ""
        self.error = ""
        self.owner_module: Optional[str] = None
        self.owner_token: Optional[str] = None
        self.state_version = 0

        _settings = get_settings()
        self.target_fps = max(10, _settings.FPS_LIMIT)
        self.preview_fps = self.target_fps  # preview broadcast matches capture rate
        self.preview_frame_interval = 1.0 / self.preview_fps
        self.preview_jpeg_quality = 55
        self.last_preview_encoded_at = 0.0

        # Detection intervals keep the capture loop responsive under CPU load.
        self.driver_detector = None
        self.driver_state: dict = {}
        self.pending_driver_events: List[DriverEventData] = []
        self.driver_events_lock = threading.Lock()
        self.driver_detection_interval = 0.12
        self.last_driver_detection_at = 0.0
        self.driver_processing_max_width = 256
        self.driver_preview_fps = min(self.target_fps, 15)
        self.driver_preview_frame_interval = 1.0 / self.driver_preview_fps
        self.driver_preview_max_width = 480
        self.driver_preview_jpeg_quality = 45
        # Driver processing runs in its own thread (mirrors gate pattern)
        self.driver_processing_thread: Optional[threading.Thread] = None
        self.gate_detector = None
        self.gate_state: dict = {}
        self.pending_gate_events: List[GateEventData] = []
        self.gate_events_lock = threading.Lock()
        self.gate_detection_interval = 0.15
        self.last_gate_detection_at = 0.0
        self.gate_processing_thread: Optional[threading.Thread] = None
        
        self._initialized = True

    def _record_debug_metric(self, name: str, value: float, *, alpha: float = 0.18) -> None:
        with self.debug_lock:
            self.debug_metrics[f"{name}_last"] = round(float(value), 3)
            average_key = f"{name}_avg"
            previous_average = self.debug_metrics.get(average_key)
            if previous_average is None:
                next_average = float(value)
            else:
                next_average = (float(previous_average) * (1.0 - alpha)) + (float(value) * alpha)
            self.debug_metrics[average_key] = round(next_average, 3)

    def _set_debug_value(self, name: str, value) -> None:
        with self.debug_lock:
            if isinstance(value, float):
                self.debug_metrics[name] = round(value, 3)
            else:
                self.debug_metrics[name] = value

    def _get_debug_snapshot(self) -> dict:
        with self.debug_lock:
            return dict(self.debug_metrics)

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
            try:
                from app.camera.driver_runtime import DriverDetectorClient

                self.driver_detector = DriverDetectorClient()
                self.driver_state = self.driver_detector.get_state_dict()
            except Exception:
                logger.exception("Failed to load driver detector.")

    def _ensure_gate_detector(self):
        """Lazy load gate attendance recognizer."""
        if self.gate_detector is None:
            try:
                from app.services.gate_attendance import gate_attendance_recognizer

                self.gate_detector = gate_attendance_recognizer
            except Exception:
                logger.exception("Failed to load gate attendance recognizer.")

    def _start_gate_processing_worker(self) -> None:
        if self.gate_processing_thread and self.gate_processing_thread.is_alive():
            return

        self.gate_processing_thread = threading.Thread(
            target=self._gate_processing_loop,
            daemon=True,
        )
        self.gate_processing_thread.start()

    def _start_preview_processing_worker(self) -> None:
        if self.preview_processing_thread and self.preview_processing_thread.is_alive():
            return

        self.preview_processing_thread = threading.Thread(
            target=self._preview_processing_loop,
            daemon=True,
        )
        self.preview_processing_thread.start()

    def _start_driver_processing_worker(self) -> None:
        if self.driver_processing_thread and self.driver_processing_thread.is_alive():
            return

        self.driver_processing_thread = threading.Thread(
            target=self._driver_processing_loop,
            daemon=True,
        )
        self.driver_processing_thread.start()

    def _wait_for_stop(self, timeout: float) -> bool:
        return self.stop_event.wait(max(0.0, timeout))

    def _join_thread(
        self,
        thread: Optional[threading.Thread],
        *,
        name: str,
        timeout: float = 1.5,
    ) -> None:
        if thread is None:
            return
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("%s thread did not exit cleanly during camera stop.", name)

    def _resize_frame_to_max_width(self, frame, max_width: int):
        if frame is None or max_width <= 0:
            return frame

        height, width = frame.shape[:2]
        if width <= max_width:
            return frame

        scaled_height = max(1, int(height * (max_width / width)))
        return cv2.resize(frame, (max_width, scaled_height), interpolation=cv2.INTER_AREA)

    def _open_webcam_capture(self, device_id: int) -> tuple[Optional[cv2.VideoCapture], str]:
        cap = cv2.VideoCapture(device_id, cv2.CAP_MSMF)
        backend = "MSMF"
        if not cap or not cap.isOpened():
            if cap:
                cap.release()
            cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
            backend = "DSHOW"
        if not cap or not cap.isOpened():
            if cap:
                cap.release()
            return None, backend
        return cap, backend

    def _probe_webcam_source(self, device_id: int) -> Optional[WebcamProbeResult]:
        cap, backend = self._open_webcam_capture(device_id)
        if cap is None:
            return None

        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            frames = []
            for _ in range(12):
                ok, frame = cap.read()
                if ok and frame is not None:
                    frames.append(frame)
                time.sleep(0.02)
            if not frames:
                return None

            gray = cv2.cvtColor(frames[-1], cv2.COLOR_BGR2GRAY)
            brightness = float(gray.mean())
            contrast = float(gray.std())
            return WebcamProbeResult(
                device_id=device_id,
                brightness=brightness,
                contrast=contrast,
                backend=backend,
            )
        finally:
            cap.release()

    def _select_driver_webcam_source(self, requested_device_id: int) -> int:
        candidate_ids = [requested_device_id] + [idx for idx in range(6) if idx != requested_device_id]
        best_probe: Optional[WebcamProbeResult] = None
        requested_probe: Optional[WebcamProbeResult] = None

        for candidate_id in candidate_ids:
            probe = self._probe_webcam_source(candidate_id)
            if probe is None:
                continue
            if candidate_id == requested_device_id:
                requested_probe = probe
            if best_probe is None or probe.score > best_probe.score:
                best_probe = probe

        if best_probe is None:
            return requested_device_id

        if requested_probe is None:
            logger.info(
                "Fleet camera probe selected webcam %s (%s, brightness %.1f, contrast %.1f).",
                best_probe.device_id,
                best_probe.backend,
                best_probe.brightness,
                best_probe.contrast,
            )
            return best_probe.device_id

        if requested_probe.brightness < 45.0 and best_probe.score > (requested_probe.score + 25.0):
            logger.info(
                "Fleet camera probe switched webcam %s -> %s because source %s was too dark "
                "(brightness %.1f vs %.1f).",
                requested_device_id,
                best_probe.device_id,
                requested_device_id,
                requested_probe.brightness,
                best_probe.brightness,
            )
            return best_probe.device_id

        return requested_device_id

    def _get_preview_profile(self) -> tuple[float, int, int]:
        if self.mode == "driver":
            return (
                self.driver_preview_frame_interval,
                self.driver_preview_max_width,
                self.driver_preview_jpeg_quality,
            )
        return (
            self.preview_frame_interval,
            0,
            self.preview_jpeg_quality,
        )

    def _driver_processing_loop(self) -> None:
        """Run driver inference on a timer by pulling from the shared
        raw-frame slot — mirrors the gate pattern.
        """
        last_seq = -1
        while not self.stop_event.is_set():
            if self.mode != "driver":
                if self._wait_for_stop(0.02):
                    break
                continue

            if self.driver_detector is None:
                self._ensure_driver_detector()
                if self._wait_for_stop(0.02):
                    break
                continue

            self.driver_state = self.driver_detector.get_state_dict()

            now = time.time()
            if now - self.last_driver_detection_at < self.driver_detection_interval:
                if self._wait_for_stop(
                    max(0.005, self.driver_detection_interval - (now - self.last_driver_detection_at))
                ):
                    break
                continue

            frame = None
            frame_sequence = 0
            with self.raw_frame_lock:
                if (
                    self.latest_raw_frame is not None
                    and self.latest_raw_frame_sequence != last_seq
                ):
                    frame = self.latest_raw_frame.copy()
                    frame_sequence = self.latest_raw_frame_sequence
                    last_seq = frame_sequence

            if frame is None:
                if self._wait_for_stop(0.005):
                    break
                continue

            self._set_debug_value("driver_latest_frame_sequence", frame_sequence)

            frame = self._resize_frame_to_max_width(
                frame,
                self.driver_processing_max_width,
            )
            self.last_driver_detection_at = time.time()

            try:
                started_at = time.perf_counter()
                _, events = self.driver_detector.process_frame(frame)
                self._record_debug_metric(
                    "driver_process_ms",
                    (time.perf_counter() - started_at) * 1000.0,
                )
                self.driver_state = self.driver_detector.get_state_dict()

                if events:
                    with self.driver_events_lock:
                        for ev in events:
                            if isinstance(ev, dict):
                                event_type = ev.get("event_type") or "INFO"
                                timestamp = float(ev.get("timestamp", time.time()))
                                confidence = float(ev.get("confidence", 0.0))
                                details = ev.get("details", "")
                            else:
                                event_type = ev.event_type.value
                                timestamp = ev.timestamp
                                confidence = ev.confidence
                                details = ev.details
                            self.pending_driver_events.append(DriverEventData(
                                event_type=event_type,
                                timestamp=timestamp,
                                confidence=confidence,
                                details=details,
                            ))

            except Exception:
                logger.exception("Driver detection error.")
                if self._wait_for_stop(0.02):
                    break

    def _gate_processing_loop(self) -> None:
        """Run ArcFace recognition at gate_detection_interval, updating
        the identity + similarity label state. Pulls directly from the
        shared raw-frame slot, so it never blocks the capture thread.
        """
        last_seq = -1
        while not self.stop_event.is_set():
            if self.mode != "gate":
                if self._wait_for_stop(0.02):
                    break
                continue

            if self.gate_detector is None:
                self._ensure_gate_detector()
                if self._wait_for_stop(0.02):
                    break
                continue

            now = time.time()
            if now - self.last_gate_detection_at < self.gate_detection_interval:
                if self._wait_for_stop(
                    max(0.005, self.gate_detection_interval - (now - self.last_gate_detection_at))
                ):
                    break
                continue

            frame = None
            frame_sequence = 0
            with self.raw_frame_lock:
                if (
                    self.latest_raw_frame is not None
                    and self.latest_raw_frame_sequence != last_seq
                ):
                    frame = self.latest_raw_frame.copy()
                    frame_sequence = self.latest_raw_frame_sequence
                    last_seq = frame_sequence

            if frame is None:
                if self._wait_for_stop(0.005):
                    break
                continue

            self.last_gate_detection_at = time.time()

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
                                    ppe_status=ev.ppe_status,
                                    ppe_details=ev.ppe_details or {},
                                    review_reasons=ev.review_reasons or [],
                                )
                            )

            except Exception:
                logger.exception("Gate recognition error.")
                if self._wait_for_stop(0.02):
                    break

    def _preview_processing_loop(self) -> None:
        """Pull the latest raw frame, render the live overlay, JPEG encode,
        broadcast. Runs at the configured preview FPS. This is where the
        user-visible overlay work happens — capture thread is untouched.
        """
        last_seq = -1
        while not self.stop_event.is_set():
            preview_frame_interval, preview_max_width, jpeg_quality = self._get_preview_profile()
            # Pace preview rate independently of capture rate.
            now = time.time()
            if now - self.last_preview_encoded_at < preview_frame_interval:
                if self._wait_for_stop(
                    max(0.0, preview_frame_interval - (now - self.last_preview_encoded_at))
                ):
                    break
                continue

            frame = None
            frame_sequence = 0
            with self.raw_frame_lock:
                if (
                    self.latest_raw_frame is not None
                    and self.latest_raw_frame_sequence != last_seq
                ):
                    # Copy once so we can render on our own buffer.
                    frame = self.latest_raw_frame.copy()
                    frame_sequence = self.latest_raw_frame_sequence
                    last_seq = frame_sequence

            if frame is None:
                if self._wait_for_stop(0.005):
                    break
                continue

            if preview_max_width > 0:
                frame = self._resize_frame_to_max_width(
                    frame,
                    preview_max_width,
                )

            # Render live overlay for the current mode. This is where
            # MediaPipe face tracking + label drawing happens — every
            # preview frame gets a fresh bbox glued to the face.
            try:
                overlay_started_at = time.perf_counter()
                if self.mode == "gate":
                    if self.gate_detector is None:
                        self._ensure_gate_detector()
                    if self.gate_detector is not None:
                        frame = self.gate_detector.draw_live_overlay(frame)
                elif self.mode == "driver":
                    if self.driver_detector is None:
                        self._ensure_driver_detector()
                    if self.driver_detector is not None:
                        frame = self.driver_detector.draw_live_overlay(frame)
                self._record_debug_metric(
                    "preview_overlay_ms",
                    (time.perf_counter() - overlay_started_at) * 1000.0,
                )
            except Exception:
                logger.exception("Preview overlay render error.")

            try:
                encode_started_at = time.perf_counter()
                ret, jpeg = cv2.imencode(
                    ".jpg",
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
                )
                self._record_debug_metric(
                    "preview_encode_ms",
                    (time.perf_counter() - encode_started_at) * 1000.0,
                )
                if ret:
                    frame_bytes = jpeg.tobytes()
                    with self.frame_lock:
                        self.latest_frame = frame_bytes
                        self.latest_frame_sequence = frame_sequence
                    self.last_preview_encoded_at = time.time()
                    self._record_debug_metric(
                        "preview_total_ms",
                        (time.perf_counter() - overlay_started_at) * 1000.0,
                    )
                    self._set_debug_value("preview_frame_bytes", len(frame_bytes))
                    self._set_debug_value("preview_frame_sequence", frame_sequence)
                else:
                    if self._wait_for_stop(0.005):
                        break
            except Exception:
                logger.exception("Preview encode error.")
                if self._wait_for_stop(0.01):
                    break
    
    def start(
        self,
        source_type: str = "webcam",
        source_id: str = "0",
        owner_module: Optional[str] = None,
        owner_token: Optional[str] = None,
    ) -> bool:
        """Start camera capture."""
        with self.lifecycle_lock:
            if self.running:
                if not self.has_control(owner_module, owner_token):
                    self.error = f"Camera is currently controlled by {self.get_owner_label()}."
                    return False
                self._stop_locked()

            self.source_type = source_type
            self.source_id = source_id
            self.error = ""
            self.mode = "idle"
            self._set_owner(owner_module, owner_token)
            self._bump_state_version()

            # Open camera. On Windows we try MSMF first (faster cap.read latency
            # on modern builds), fall back to DSHOW if MSMF can't open the device.
            try:
                if source_type == "webcam":
                    requested_device_id = int(source_id) if source_id.isdigit() else 0
                    if owner_module == "drivers":
                        device_id = self._select_driver_webcam_source(requested_device_id)
                    else:
                        device_id = requested_device_id
                    self.source_id = str(device_id)
                    cap, _ = self._open_webcam_capture(device_id)
                    self.cap = cap
                elif source_type == "video_file":
                    self.cap = cv2.VideoCapture(source_id)
                elif source_type == "ip_stream":
                    self.cap = cv2.VideoCapture(source_id)
                else:
                    self.error = f"Unknown source type: {source_type}"
                    return False
            except Exception as e:
                self.error = f"Exception opening camera: {e}"
                logger.exception("Exception opening camera.")
                return False

            if not self.cap or not self.cap.isOpened():
                self.error = "Failed to open camera"
                if self.cap:
                    self.cap.release()
                self.cap = None
                return False

            if source_type == "webcam":
                # Order matters: set codec BEFORE resolution, else some drivers
                # silently ignore the resolution request.
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 30)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                # CRITICAL on Windows: auto-exposure lets the driver drop the
                # sensor rate to 10 FPS in typical indoor light. Force manual
                # mode and a fast exposure so the driver has no reason to slow
                # down. Values: 0.25 = manual on DSHOW/MSMF, -5 ≈ 1/32s shutter.
                try:
                    self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                    self.cap.set(cv2.CAP_PROP_EXPOSURE, -5)
                except Exception:
                    logger.debug("Camera did not accept manual exposure settings.")
                # Log what the driver actually negotiated so we can diagnose if
                # the reported FPS stays low.
                try:
                    actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
                    actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                    actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                    logger.info(
                        "Camera negotiated: %sx%s @ %s FPS (driver reports).",
                        actual_w, actual_h, actual_fps,
                    )
                except Exception:
                    pass

            warmup_started_at = time.time()
            warmup_success = False
            while time.time() - warmup_started_at < 2.5:
                try:
                    ret, frame = self.cap.read()
                except Exception as e:
                    self.error = f"Exception warming up camera: {e}"
                    logger.exception("Exception warming up camera.")
                    break

                if ret and frame is not None:
                    warmup_success = True
                    break

                time.sleep(0.05)

            if not warmup_success:
                self.error = self.error or "Camera opened but did not deliver frames."
                self.cap.release()
                self.cap = None
                self._clear_owner()
                self._bump_state_version()
                return False

            self.stop_event.clear()
            self.running = True
            self.frames_captured = 0
            self.start_time = time.time()
            self.latest_frame = None
            self.latest_frame_sequence = 0
            with self.debug_lock:
                self.debug_metrics.clear()
            self.last_driver_detection_at = 0.0
            self.last_gate_detection_at = 0.0
            self.last_preview_encoded_at = 0.0
            with self.raw_frame_lock:
                self.latest_raw_frame = None
                self.latest_raw_frame_sequence = 0

            # Start capture thread and all worker threads
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
            self._start_gate_processing_worker()
            self._start_driver_processing_worker()
            self._start_preview_processing_worker()

            return True

    def stop(self) -> None:
        """Stop camera capture."""
        with self.lifecycle_lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        self.stop_event.set()
        self.running = False

        cap = self.cap
        self.cap = None

        capture_thread = self.thread
        gate_thread = self.gate_processing_thread
        driver_thread = self.driver_processing_thread
        preview_thread = self.preview_processing_thread

        self.thread = None
        self.gate_processing_thread = None
        self.driver_processing_thread = None
        self.preview_processing_thread = None

        if cap:
            try:
                cap.release()
            except Exception:
                logger.exception("Release error.")

        self._join_thread(capture_thread, name="capture")
        self._join_thread(gate_thread, name="gate")
        self._join_thread(driver_thread, name="driver")
        self._join_thread(preview_thread, name="preview")

        # Clear frame buffers
        with self.frame_lock:
            self.latest_frame = None
            self.latest_frame_sequence = 0
            self.last_preview_encoded_at = 0.0
        with self.raw_frame_lock:
            self.latest_raw_frame = None
            self.latest_raw_frame_sequence = 0
        with self.driver_events_lock:
            self.pending_driver_events.clear()
        with self.gate_events_lock:
            self.pending_gate_events.clear()

        if self.gate_detector is not None:
            try:
                self.gate_detector.reset_live_session(
                    clear_pending_reviews=True,
                    reason="Gate camera stopped before the operator resolved the live review.",
                )
                self.gate_state = self.gate_detector.get_state_dict()
            except Exception:
                logger.exception("Failed to reset gate session.")

        if self.driver_detector is not None:
            try:
                self.driver_detector.reset_live_state()
                self.driver_state = self.driver_detector.get_state_dict()
            except Exception:
                logger.exception("Failed to reset driver session.")
            try:
                shutdown = getattr(self.driver_detector, "shutdown", None)
                if callable(shutdown):
                    shutdown()
            except Exception:
                logger.exception("Failed to stop driver detector worker.")
            self.driver_detector = None

        self.mode = "idle"
        self.error = ""
        self._clear_owner()
        self._bump_state_version()

    def set_mode(self, mode: str) -> None:
        """Set processing mode."""
        if mode in ["gate", "driver", "idle"]:
            with self.lifecycle_lock:
                if self.mode == "gate" and mode != "gate" and self.gate_detector is not None:
                    try:
                        self.gate_detector.reset_live_session(
                            clear_pending_reviews=True,
                            reason="Recognition mode was disabled before the live review was resolved.",
                        )
                        self.gate_state = self.gate_detector.get_state_dict()
                    except Exception:
                        logger.exception("Failed to clear gate reviews while switching mode.")
                if self.mode == "driver" and mode != "driver" and self.driver_detector is not None:
                    try:
                        self.driver_detector.reset_live_state()
                        self.driver_state = self.driver_detector.get_state_dict()
                    except Exception:
                        logger.exception("Failed to clear driver monitoring state while switching mode.")
                self.mode = mode
                self._bump_state_version()
                if mode == "driver":
                    self._ensure_driver_detector()
                    if self.driver_detector is not None:
                        self.driver_state = self.driver_detector.get_state_dict()
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
        state = self.driver_state.copy()
        debug_payload = state.get("debug", {}).copy() if isinstance(state.get("debug"), dict) else {}
        debug_payload["manager"] = self._get_debug_snapshot()
        try:
            from app.websocket.manager import manager as websocket_manager

            debug_payload["websocket"] = websocket_manager.get_live_debug_snapshot()
        except Exception:
            logger.exception("Failed to collect live websocket debug snapshot.")
        state["debug"] = debug_payload
        return _json_safe_value(state)

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
    
    def get_latest_frame(self) -> Optional[bytes]:
        """Get latest frame as raw JPEG bytes."""
        with self.frame_lock:
            if self.latest_frame:
                return self.latest_frame
        return None

    def get_latest_frame_packet(self) -> Optional[Tuple[int, bytes]]:
        """Get the latest encoded JPEG frame plus a monotonically increasing sequence."""
        with self.frame_lock:
            if self.latest_frame:
                return self.latest_frame_sequence, self.latest_frame
        return None
    
    def _capture_loop(self) -> None:
        """Minimal capture loop: pull frames from the device as fast as
        the hardware allows and publish them to a single shared slot.

        NO rate limiting here — cap.read() already blocks to the camera's
        negotiated frame rate, so adding our own sleep only caps us BELOW
        the device's native FPS. All per-frame processing work lives in
        consumer threads (preview / gate / driver), so this loop stays
        CPU-cheap and lets the driver deliver its rated FPS.
        """
        consecutive_failures = 0

        while not self.stop_event.is_set():
            cap = self.cap
            if not cap:
                break

            try:
                read_started_at = time.perf_counter()
                ret, frame = cap.read()
                self._record_debug_metric(
                    "capture_read_ms",
                    (time.perf_counter() - read_started_at) * 1000.0,
                )
            except Exception:
                logger.exception("Read exception while capturing frame.")
                break

            if not ret or frame is None:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    self.error = "Too many frame read failures"
                    break
                if self._wait_for_stop(0.02):
                    break
                continue

            consecutive_failures = 0
            self.error = ""
            self.frames_captured += 1

            # Publish — consumers pick it up on their own cadence.
            with self.raw_frame_lock:
                self.latest_raw_frame = frame
                self.latest_raw_frame_sequence += 1
                latest_sequence = self.latest_raw_frame_sequence
            self._set_debug_value("capture_frame_sequence", latest_sequence)


# Global singleton
camera_manager = CameraManager()
