"""
Webcam Camera Source
"""
import cv2
import time
from typing import Optional, Tuple
from app.camera.base import CameraSource, Frame, CameraInfo


class WebcamSource(CameraSource):
    """Webcam capture using OpenCV."""
    
    def __init__(self, device_id: int = 0, resolution: Tuple[int, int] = (640, 480)):
        self.device_id = device_id
        self.resolution = resolution
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.start_time = 0.0
    
    def open(self) -> bool:
        """Open webcam."""
        self.cap = cv2.VideoCapture(self.device_id)
        if not self.cap.isOpened():
            return False
        
        # Set resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        
        self.frame_count = 0
        self.start_time = time.time()
        return True
    
    def close(self) -> None:
        """Release webcam."""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.frame_count = 0
    
    def read(self) -> Optional[Frame]:
        """Read a frame from webcam."""
        if not self.cap or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        self.frame_count += 1
        
        return Frame(
            data=frame,
            width=frame.shape[1],
            height=frame.shape[0],
            frame_number=self.frame_count,
            timestamp=time.time()
        )
    
    def is_open(self) -> bool:
        """Check if webcam is open."""
        return self.cap is not None and self.cap.isOpened()
    
    def get_info(self) -> CameraInfo:
        """Get webcam info."""
        fps = 0.0
        if self.start_time > 0 and self.frame_count > 0:
            elapsed = time.time() - self.start_time
            fps = self.frame_count / elapsed if elapsed > 0 else 0.0
        
        return CameraInfo(
            source_type="webcam",
            source_id=f"webcam_{self.device_id}",
            resolution=self.resolution,
            fps=round(fps, 1),
            is_open=self.is_open()
        )
