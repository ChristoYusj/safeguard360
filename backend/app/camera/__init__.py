"""Camera runtime.

The process-wide CameraManager owns the single physical camera and feeds the
gate and driver pipelines. A CameraSource adapter hierarchy (webcam, IP stream,
video file) used to live here but was never wired in: the manager drives
cv2.VideoCapture directly. It has been removed rather than left as scaffolding.
"""
from app.camera.manager import CameraManager, camera_manager

__all__ = ["CameraManager", "camera_manager"]
