"""
Application Settings
"""
from pathlib import Path
from typing import Tuple

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Server
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = ""

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
    ARDUINO_PORT: str = ""

    # CORS / Cookies
    CORS_ALLOWED_ORIGINS: str = ""
    COOKIE_SECURE: bool = False

    # Auth
    JWT_ACCESS_SECRET: str = ""
    JWT_REFRESH_SECRET: str = ""
    JWT_APPROVAL_SECRET: str = ""
    BCRYPT_SALT_ROUNDS: int = 12
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7
    AUTH_MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    AUTH_MAX_FAILED_IP_ATTEMPTS: int = 5
    AUTH_FAILED_LOGIN_WINDOW_MINUTES: int = 15
    AUTH_LOCKOUT_MINUTES: int = 15

    # Admin / Email
    ADMIN_EMAIL: str = ""
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""
    TOTP_ENCRYPTION_KEY: str = ""

    # Bootstrap operator
    BOOTSTRAP_ADMIN_NAME: str = "System Administrator"
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_ADMIN_ROLE: str = "Platform Manager"

    @property
    def camera_resolution_tuple(self) -> Tuple[int, int]:
        w, h = self.CAMERA_RESOLUTION.split(",")
        return (int(w), int(h))

    @property
    def resolved_database_url(self) -> str:
        if self.DATABASE_URL.startswith("sqlite:///./"):
            relative_path = self.DATABASE_URL.replace("sqlite:///./", "", 1)
            return f"sqlite:///{(REPO_ROOT / relative_path).resolve().as_posix()}"
        return self.DATABASE_URL

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def bootstrap_admin_enabled(self) -> bool:
        return bool(self.ADMIN_EMAIL and self.BOOTSTRAP_ADMIN_PASSWORD)

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton settings instance
_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
