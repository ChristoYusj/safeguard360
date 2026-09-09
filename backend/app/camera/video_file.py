"""
Video File Camera Source
"""
import cv2
import time
from typing import Optional
from app.camera.base import CameraSource, Frame, CameraInfo


class VideoFileSource(CameraSource):
    """Video file playback using OpenCV."""
    
    def __init__(self, file_path: str, loop: bool = True):
        self.file_path = file_path
        self.loop = loop
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.start_time = 0.0
        self.total_frames = 0
        self.native_fps = 30.0
    
    def open(self) -> bool:
        """Open video file."""
        self.cap = cv2.VideoCapture(self.file_path)
        if not self.cap.isOpened():
            return False
        
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.native_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = 0
        self.start_time = time.time()
        return True
    
    def close(self) -> None:
        """Release video file."""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.frame_count = 0
    
    def read(self) -> Optional[Frame]:
        """Read a frame from video file."""
        if not self.cap or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        
        # Loop video if enabled
        if not ret and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
        
        if not ret:
            return None
        
        self.frame_count += 1
        
        # Throttle to native FPS
        expected_time = self.start_time + (self.frame_count / self.native_fps)
        sleep_time = expected_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)
        
        return Frame(
            data=frame,
            width=frame.shape[1],
            height=frame.shape[0],
            frame_number=self.frame_count,
            timestamp=time.time()
        )
    
    def is_open(self) -> bool:
        """Check if video file is open."""
        return self.cap is not None and self.cap.isOpened()
    
    def get_info(self) -> CameraInfo:
        """Get video file info."""
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self.cap else 0
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self.cap else 0
        
        return CameraInfo(
            source_type="video_file",
            source_id=self.file_path,
            resolution=(width, height),
            fps=round(self.native_fps, 1),
            is_open=self.is_open()
        )
