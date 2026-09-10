"""
Application Settings
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Server
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database. Relative sqlite paths resolve against the repo root (see
    # resolved_database_url), so this default matches docs/architecture.md.
    DATABASE_URL: str = "sqlite:///./data/safeguard360.db"

    # Camera. Capture runs unthrottled; FPS_LIMIT paces the preview broadcast.
    FPS_LIMIT: int = 30

    # Models
    MODELS_DIR: str = "./data/models"
    # A PPE-trained checkpoint (see .env.example). Deliberately not a COCO
    # model name: those auto-download via ultralytics and detect people, not
    # helmets, so PPE would read "uncertain" forever without any error.
    PPE_MODEL: str = "construction-safety.pt"
    FACE_MODEL: str = "buffalo_l"

    # AI Safety Chatbot. Groq is the only supported provider for the
    # production chatbot path. Leave GROQ_API_KEY empty to disable it.
    # llama-3.3-70b-versatile was retired for free/developer keys on
    # 2026-08-16; gpt-oss-120b is Groq's documented replacement.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    CHATBOT_MAX_HISTORY: int = 20
    CHATBOT_MAX_TOKENS: int = 600

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
    AUTH_LOCKOUT_MINUTES: int = 5

    # Admin / Email
    ADMIN_EMAIL: str = ""
    MAIL_TRANSPORT: str = ""
    MAIL_LOCAL_OUTBOX_DIR: str = "./backend/data/mail"
    MAIL_EXPOSE_LOCAL_RESET_LINKS: bool = False
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""
    FRONTEND_APP_URL: str = ""
    TOTP_ENCRYPTION_KEY: str = ""

    # Bootstrap operator
    BOOTSTRAP_ADMIN_NAME: str = "System Administrator"
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    @property
    def resolved_database_url(self) -> str:
        if self.DATABASE_URL.startswith("sqlite:///./"):
            relative_path = self.DATABASE_URL.replace("sqlite:///./", "", 1)
            return f"sqlite:///{(REPO_ROOT / relative_path).resolve().as_posix()}"
        return self.DATABASE_URL

    @property
    def resolved_models_dir(self) -> str:
        """Absolute models directory.

        Resolves MODELS_DIR relative to the repo root so inference code works
        the same whether the server was launched from the repo root or from
        ``backend/`` (uvicorn --reload uses different CWDs).
        """
        raw = (self.MODELS_DIR or "").strip() or "./data/models"
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / raw
        return str(candidate.resolve())

    @property
    def resolved_mail_transport(self) -> str:
        raw = (self.MAIL_TRANSPORT or "").strip().lower()
        if raw == "resend":
            return "resend"
        if raw == "local":
            return "local"
        if str(self.RESEND_API_KEY or "").strip() and str(self.RESEND_FROM_EMAIL or "").strip():
            return "resend"
        return "local"

    @property
    def resolved_mail_local_outbox_dir(self) -> str:
        raw = (self.MAIL_LOCAL_OUTBOX_DIR or "").strip() or "./backend/data/mail"
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / raw
        return str(candidate.resolve())

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

    @property
    def missing_required_auth_settings(self) -> list[str]:
        required = {
            "DATABASE_URL": self.DATABASE_URL,
            "JWT_ACCESS_SECRET": self.JWT_ACCESS_SECRET,
            "JWT_REFRESH_SECRET": self.JWT_REFRESH_SECRET,
            "JWT_APPROVAL_SECRET": self.JWT_APPROVAL_SECRET,
            "ADMIN_EMAIL": self.ADMIN_EMAIL,
            "TOTP_ENCRYPTION_KEY": self.TOTP_ENCRYPTION_KEY,
        }
        if self.resolved_mail_transport == "resend":
            required["RESEND_API_KEY"] = self.RESEND_API_KEY
            required["RESEND_FROM_EMAIL"] = self.RESEND_FROM_EMAIL
        return [key for key, value in required.items() if not str(value or "").strip()]

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
