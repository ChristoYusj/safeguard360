"""Camera adapters"""
from app.camera.base import CameraInfo, CameraSource, Frame
from app.camera.manager import CameraManager, camera_manager

__all__ = ["CameraInfo", "CameraSource", "Frame", "CameraManager", "camera_manager"]
