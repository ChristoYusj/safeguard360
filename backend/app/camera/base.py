"""
Camera Source Base Class
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np


@dataclass
class Frame:
    """A captured video frame."""
    data: np.ndarray
    width: int
    height: int
    frame_number: int
    timestamp: float


@dataclass 
class CameraInfo:
    """Camera source information."""
    source_type: str
    source_id: str
    resolution: Tuple[int, int]
    fps: float
    is_open: bool


class CameraSource(ABC):
    """Abstract base class for camera sources."""
    
    @abstractmethod
    def open(self) -> bool:
        """Open the camera source. Returns True if successful."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the camera source."""
        pass
    
    @abstractmethod
    def read(self) -> Optional[Frame]:
        """Read a frame. Returns None if no frame available."""
        pass
    
    @abstractmethod
    def is_open(self) -> bool:
        """Check if camera is open."""
        pass
    
    @abstractmethod
    def get_info(self) -> CameraInfo:
        """Get camera information."""
        pass
