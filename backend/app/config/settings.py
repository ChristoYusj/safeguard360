"""
Application Settings
"""
from pydantic_settings import BaseSettings
from typing import Tuple
import os


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    
    # Server
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "ENV_DATABASE_URL"
    
    # Camera
    DEFAULT_CAMERA: str = "webcam"
    CAMERA_RESOLUTION: str = "640,480"
    FPS_LIMIT: int = 15
    
    # Thresholds
    FACE_MATCH_THRESHOLD: float = 0.6
    FATIGUE_EAR_THRESHOLD: float = 0.25
    FATIGUE_CONSECUTIVE_FRAMES: int = 15
    DISTRACTION_HEAD_ANGLE: float = 30.0
    SEATBELT_REQUIRED: bool = True
    
    # Models
    MODELS_DIR: str = "./data/models"
    PPE_MODEL: str = "yolo11n.pt"
    FACE_MODEL: str = "buffalo_l"
    
    # Actuator
    ACTUATOR_TYPE: str = "stub"
    ARDUINO_PORT: str = "ENV_ARDUINO_PORT"
    
    @property
    def camera_resolution_tuple(self) -> Tuple[int, int]:
        w, h = self.CAMERA_RESOLUTION.split(",")
        return (int(w), int(h))
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton settings instance
_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
