"""
The one seam between SafeGuard 360 and its language-model provider.

Every model call in the backend goes through LLMClient so that:

* the model id, endpoint and key come from configuration only. Groq retires
  model ids every few months (llama-3.3-70b-versatile went on 2026-08-16); a
  retirement is a .env change here, never a code change;
* provider errors are logged in full but never reach an operator verbatim;
* tests substitute a fake SDK object and need neither a key nor a network;
* /api/chatbot/status can say whether the configured model is actually offered
  to this account (models.list), cached so the UI's polling does not spend the
  free-tier quota.

Groq's OpenAI-compatible SDK is the only provider today. LLM_BASE_URL lets a
self-hosted OpenAI-compatible gateway be pointed at without touching code.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config.settings import get_settings

try:  # pinned in requirements.txt; the guard keeps a broken install readable
    import groq as _groq
except ImportError:  # pragma: no cover
    _groq = None

logger = logging.getLogger(__name__)

PROVIDER_NAME = "groq"
REQUEST_TIMEOUT_SECONDS = 30.0
HEALTH_TIMEOUT_SECONDS = 5.0
HEALTH_CACHE_SECONDS = 60.0

# Operator-facing messages. None of them carries provider text.
NOT_CONFIGURED = "Set GROQ_API_KEY in backend/.env to enable the assistant."
GENERIC_FAILURE = "The assistant's language-model provider returned an error. Try again shortly."
RATE_LIMITED = "The language-model provider is rate-limiting this site. Wait a minute and try again."
KEY_REJECTED = "The language-model provider rejected the API key. Check GROQ_API_KEY."
MODEL_REJECTED = (
    "The provider rejected the configured model. Pick a current id from the provider's "
    "model list and set GROQ_MODEL."
)
UNREACHABLE = "The language-model provider could not be reached or rejected the API key."


class LLMError(Exception):
    """A provider call failed. str(exc) is safe to show to an operator."""


class LLMNotConfigured(LLMError):
    """No API key (or no model id) is configured."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text exactly as returned; the caller validates it


@dataclass
class ChatResult:
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    model: str = ""
    finish_reason: Optional[str] = None


@dataclass
class HealthStatus:
    reachable: bool
    model_available: Optional[bool]
    detail: str
    checked_at: float  # time.monotonic()


class LLMClient:
    """Thin, synchronous wrapper over the provider SDK.

    ``sdk`` is any object exposing ``chat.completions.create(**kwargs)`` and
    ``models.list(timeout=...)``; tests pass a fake, production builds the real
    Groq client lazily on first use.
    """

    def __init__(self, *, api_key: str, model: str, base_url: str = "", sdk: Any = None) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.base_url = (base_url or "").strip()
        self._sdk = sdk
        self._lock = threading.Lock()
        self._health: Optional[HealthStatus] = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _client(self) -> Any:
        if self._sdk is None:
            if not self.configured:
                raise LLMNotConfigured(NOT_CONFIGURED)
            if _groq is None:
                raise LLMError("The 'groq' package is not installed.")
            kwargs: Dict[str, Any] = {"api_key": self.api_key, "max_retries": 1}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._sdk = _groq.Groq(**kwargs)
        return self._sdk

    # -- chat ---------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.4,
    ) -> ChatResult:
        if not self.configured:
            raise LLMNotConfigured(NOT_CONFIGURED)

        request: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "timeout": REQUEST_TIMEOUT_SECONDS,
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        if tools:
            request["tools"] = tools
            request["tool_choice"] = tool_choice or "auto"
        if response_format is not None:
            request["response_format"] = response_format

        try:
            response = self._client().chat.completions.create(**request)
        except LLMError:
            raise
        except Exception as exc:
            logger.exception("LLM: %s request for model %r failed.", PROVIDER_NAME, self.model)
            raise LLMError(self._describe_failure(exc)) from exc
        return self._parse(response)

    @staticmethod
    def _error_code(exc: Exception) -> Optional[str]:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                return str(code) if code else None
        return None

    def _describe_failure(self, exc: Exception) -> str:
        if _groq is not None:
            if isinstance(exc, _groq.RateLimitError):
                return RATE_LIMITED
            if isinstance(exc, (_groq.AuthenticationError, _groq.PermissionDeniedError)):
                return KEY_REJECTED
            if isinstance(exc, _groq.NotFoundError):
                return MODEL_REJECTED
        if self._error_code(exc) in {"model_decommissioned", "model_not_found"}:
            return MODEL_REJECTED
        return GENERIC_FAILURE

    def _parse(self, response: Any) -> ChatResult:
        try:
            choice = response.choices[0]
            message = choice.message
            raw_calls = getattr(message, "tool_calls", None) or []
            tool_calls = [
                ToolCall(id=str(call.id), name=call.function.name, arguments=call.function.arguments or "{}")
                for call in raw_calls
            ]
            return ChatResult(
                content=message.content or "",
                tool_calls=tool_calls,
                model=getattr(response, "model", None) or self.model,
                finish_reason=getattr(choice, "finish_reason", None),
            )
        except (AttributeError, IndexError, TypeError) as exc:
            logger.exception("LLM: unexpected response shape from %s.", PROVIDER_NAME)
            raise LLMError(GENERIC_FAILURE) from exc

    # -- health -------------------------------------------------------------

    def health(self, *, force: bool = False) -> HealthStatus:
        """Is the provider reachable, and does it offer the configured model?

        Cached for HEALTH_CACHE_SECONDS: the assistant page polls status.
        """
        now = time.monotonic()
        with self._lock:
            cached = self._health
            if cached is not None and not force and now - cached.checked_at < HEALTH_CACHE_SECONDS:
                return cached

            if not self.configured:
                status = HealthStatus(False, None, NOT_CONFIGURED, now)
            else:
                try:
                    listing = self._client().models.list(timeout=HEALTH_TIMEOUT_SECONDS)
                    ids = {getattr(item, "id", None) for item in (getattr(listing, "data", None) or [])}
                    available = self.model in ids
                    detail = (
                        f"Model '{self.model}' is available."
                        if available
                        else f"Model '{self.model}' is not offered to this account. Pick a current id "
                        "from the provider's model list and set GROQ_MODEL."
                    )
                    status = HealthStatus(True, available, detail, now)
                except Exception:
                    logger.exception("LLM: health check against %s failed.", PROVIDER_NAME)
                    status = HealthStatus(False, None, UNREACHABLE, now)
            self._health = status
            return status


# -- process-wide client ----------------------------------------------------

_CLIENT: Optional[LLMClient] = None
_CLIENT_KEY: Optional[tuple] = None
_CLIENT_LOCK = threading.Lock()


def get_llm_client() -> LLMClient:
    """The client for the current settings; rebuilt when key/model/URL change."""
    global _CLIENT, _CLIENT_KEY
    settings = get_settings()
    key = (settings.GROQ_API_KEY or "", settings.GROQ_MODEL or "", settings.LLM_BASE_URL or "")
    with _CLIENT_LOCK:
        if _CLIENT is None or _CLIENT_KEY != key:
            _CLIENT = LLMClient(api_key=key[0], model=key[1], base_url=key[2])
            _CLIENT_KEY = key
        return _CLIENT


def reset_llm_client() -> None:
    global _CLIENT, _CLIENT_KEY
    with _CLIENT_LOCK:
        _CLIENT = None
        _CLIENT_KEY = None
