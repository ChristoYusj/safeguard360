"""
IP Stream Camera Source (Placeholder)
For phone cameras via DroidCam, IP Webcam, etc.
"""
import cv2
import time
from typing import Optional, Tuple
from app.camera.base import CameraSource, Frame, CameraInfo


class IPStreamSource(CameraSource):
    """
    IP camera stream (MJPEG/RTSP).
    Placeholder for phone camera support.
    """
    
    def __init__(self, url: str, resolution: Tuple[int, int] = (640, 480)):
        self.url = url
        self.resolution = resolution
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.start_time = 0.0
    
    def open(self) -> bool:
        """Open IP stream."""
        # Example URLs:
        # DroidCam: http://192.168.1.x:4747/video
        # IP Webcam: http://192.168.1.x:8080/video
        self.cap = cv2.VideoCapture(self.url)
        if not self.cap.isOpened():
            return False
        
        self.frame_count = 0
        self.start_time = time.time()
        return True
    
    def close(self) -> None:
        """Close IP stream."""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.frame_count = 0
    
    def read(self) -> Optional[Frame]:
        """Read a frame from IP stream."""
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
        """Check if stream is open."""
        return self.cap is not None and self.cap.isOpened()
    
    def get_info(self) -> CameraInfo:
        """Get stream info."""
        fps = 0.0
        if self.start_time > 0 and self.frame_count > 0:
            elapsed = time.time() - self.start_time
            fps = self.frame_count / elapsed if elapsed > 0 else 0.0
        
        return CameraInfo(
            source_type="ip_stream",
            source_id=self.url,
            resolution=self.resolution,
            fps=round(fps, 1),
            is_open=self.is_open()
        )
