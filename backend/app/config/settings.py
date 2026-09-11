"""
Application Settings
"""
from pathlib import Path

from pydantic import model_validator
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
    # Directory that `video_file` camera sources must live in. Operators pick a
    # file by name; the API refuses anything that resolves outside this tree.
    VIDEO_SOURCES_DIR: str = "./data/video"
    # Optional allow-list for `ip_stream` sources: comma-separated hostnames or
    # IPs. Empty = any host except loopback, link-local, multicast, unspecified.
    CAMERA_STREAM_ALLOWED_HOSTS: str = ""

    # Gate recognition. These decide who the gate lets through, so they are
    # configuration rather than literals buried in the recognition loop.
    # Scores are ArcFace cosine similarity in [0, 1]; the UI shows them as a
    # percentage, round(score * 100).
    #   >= GATE_AUTO_PASS_THRESHOLD   the gate decides on its own
    #   >= GATE_REVIEW_THRESHOLD      the match goes to the operator queue
    #   >= GATE_CANDIDATE_THRESHOLD   the face is named on screen as a maybe
    #   below that                    the face is unknown
    GATE_AUTO_PASS_THRESHOLD: float = 0.85
    GATE_REVIEW_THRESHOLD: float = 0.79
    GATE_CANDIDATE_THRESHOLD: float = 0.45
    # Consecutive recognitions naming the same worker before the gate acts.
    # At the 0.15 s recognition interval, 3 confirmations cost about 0.45 s.
    GATE_REQUIRED_CONFIRMATIONS: int = 3
    # The winning score must beat the runner-up worker's by this much to be
    # decided automatically. A closer pair is an ambiguous identity and goes
    # to the operator instead. 0 disables the check.
    GATE_MATCH_MARGIN: float = 0.10
    # Face-quality floors for live recognition. The defaults are deliberately
    # lenient (Apr 2026 operator feedback: the stricter values produced false
    # "face is turned / too far" rejections at a real gate) and the yaw check
    # is off by default at inf. Tighten them per site; docs/attendance-gate.md
    # explains what each one costs.
    GATE_MIN_DET_SCORE: float = 0.30
    GATE_MIN_BLUR_SCORE: float = 5.0
    GATE_MIN_FACE_AREA_RATIO: float = 0.001
    GATE_MAX_YAW_OFFSET: float = float("inf")

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
    # Optional OpenAI-compatible endpoint (self-hosted gateway or proxy).
    # Empty = the provider's default.
    LLM_BASE_URL: str = ""
    CHATBOT_MAX_HISTORY: int = 20
    CHATBOT_MAX_TOKENS: int = 600
    # Assistant requests per signed-in user per minute. The free Groq tier
    # allows 30 requests/minute for the whole key.
    CHATBOT_RATE_LIMIT_PER_MINUTE: int = 20

    # CORS / Cookies
    CORS_ALLOWED_ORIGINS: str = ""
    COOKIE_SECURE: bool = False
    # Reverse proxies whose X-Forwarded-For header may be trusted (IPs or
    # CIDRs, comma-separated). Empty = the header is ignored and the TCP peer
    # address is used for lockouts and audit rows.
    TRUSTED_PROXIES: str = ""

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
    # Origin used in emailed links (password reset, account approval). Required:
    # it is never derived from request headers, which the sender controls.
    FRONTEND_APP_URL: str = ""
    # Origin the backend API is reachable at from a browser. Only needed when it
    # differs from FRONTEND_APP_URL (the Vite dev proxy and same-origin serving
    # make them identical).
    PUBLIC_API_BASE_URL: str = ""
    TOTP_ENCRYPTION_KEY: str = ""

    # Bootstrap operator
    BOOTSTRAP_ADMIN_NAME: str = "System Administrator"
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    @model_validator(mode="after")
    def _check_gate_thresholds(self) -> "Settings":
        """Refuse to boot on a gate configuration that cannot mean anything.

        An inverted pair would silently turn one of the three bands into dead
        code, which is exactly the class of bug these settings replace.
        """
        if not 0.0 < self.GATE_AUTO_PASS_THRESHOLD <= 1.0:
            raise ValueError("GATE_AUTO_PASS_THRESHOLD must be between 0 and 1.")
        if not self.GATE_CANDIDATE_THRESHOLD <= self.GATE_REVIEW_THRESHOLD <= self.GATE_AUTO_PASS_THRESHOLD:
            raise ValueError(
                "Gate thresholds must be ordered: "
                "GATE_CANDIDATE_THRESHOLD <= GATE_REVIEW_THRESHOLD <= GATE_AUTO_PASS_THRESHOLD."
            )
        if self.GATE_REQUIRED_CONFIRMATIONS < 1:
            raise ValueError("GATE_REQUIRED_CONFIRMATIONS must be at least 1.")
        if self.GATE_MATCH_MARGIN < 0:
            raise ValueError("GATE_MATCH_MARGIN cannot be negative.")
        return self

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
    def resolved_video_sources_dir(self) -> Path:
        raw = (self.VIDEO_SOURCES_DIR or "").strip() or "./data/video"
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / raw
        return candidate.resolve()

    @property
    def camera_stream_allowed_hosts(self) -> set[str]:
        return {
            host.strip().lower()
            for host in (self.CAMERA_STREAM_ALLOWED_HOSTS or "").split(",")
            if host.strip()
        }

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
    def trusted_proxies(self) -> list[str]:
        return [
            entry.strip()
            for entry in (self.TRUSTED_PROXIES or "").split(",")
            if entry.strip()
        ]

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def resolved_public_api_base_url(self) -> str:
        raw = (self.PUBLIC_API_BASE_URL or "").strip() or (self.FRONTEND_APP_URL or "").strip()
        return raw.rstrip("/")

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
            "FRONTEND_APP_URL": self.FRONTEND_APP_URL,
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
