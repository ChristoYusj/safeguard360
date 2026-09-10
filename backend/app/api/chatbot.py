"""
AI Safety Chatbot API.

Thin wrapper over app.services.chatbot. The frontend hits three endpoints:

  - GET  /api/chatbot/status   → whether the provider is configured and the
                                 configured model is actually offered
  - GET  /api/chatbot/context  → the live site snapshot (debug / preview)
  - POST /api/chatbot/message  → send a conversation, get a reply

Authentication follows the same middleware pattern as the other routes —
the global auth middleware attaches `request.state.user` before this
module sees the call. Request sizes are bounded here so an operator cannot
push arbitrary token volume at the shared provider quota.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import User
from app.services.chatbot import (
    ChatbotError,
    ChatbotInvalidConversation,
    ChatbotNotConfigured,
    ChatbotRateLimited,
    build_site_context,
    enforce_rate_limit,
    send_chat,
    status_payload,
)


router = APIRouter()
logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4000
MAX_MESSAGES = 40
MAX_CLIENT_CONTEXT_CHARS = 16_000


class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list, max_length=MAX_MESSAGES)
    client_context: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("client_context")
    @classmethod
    def _bounded_client_context(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if len(json.dumps(value, default=str)) > MAX_CLIENT_CONTEXT_CHARS:
            raise ValueError(f"client_context must serialise to at most {MAX_CLIENT_CONTEXT_CHARS} characters.")
        return value


class ChatResponse(BaseModel):
    reply: str
    model: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatStatusResponse(BaseModel):
    configured: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    missing_key_hint: str
    # Filled only when configured: does the provider answer, and is the
    # configured model id one it currently offers to this account?
    reachable: Optional[bool] = None
    model_available: Optional[bool] = None
    detail: Optional[str] = None


@router.get("/status", response_model=ChatStatusResponse)
def get_status():
    return status_payload()


@router.get("/context")
def get_context(db: Session = Depends(get_db)):
    """Return the site snapshot the assistant will see. Useful for the UI
    to show "I know about X workers, Y violations..." badges.
    """
    try:
        ctx = build_site_context(db)
    except Exception as exc:
        logger.exception("Chatbot: context build failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not build site context.",
        ) from exc
    return {
        "generated_at": ctx.generated_at,
        "on_site_count": ctx.on_site_count,
        "check_ins_today": ctx.check_ins_today,
        "check_outs_today": ctx.check_outs_today,
        "ppe_violations_today": ctx.ppe_violations_today,
        "driver_events_today": ctx.driver_events_today,
        "unknown_attempts_today": ctx.unknown_attempts_today,
        "recent_alerts": ctx.recent_alerts,
        "recent_driver_events": ctx.recent_driver_events,
        "recent_ppe_violations": ctx.recent_ppe_violations,
        "recent_attendance": ctx.recent_attendance,
        "on_site": ctx.on_site,
    }


@router.post("/message", response_model=ChatResponse)
def post_message(payload: ChatRequest, request: Request, db: Session = Depends(get_db)):
    if not payload.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one message is required.",
        )
    user = getattr(request.state, "user", None)
    if not isinstance(user, User):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    try:
        enforce_rate_limit(user.email)
    except ChatbotRateLimited as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    msg_dicts = [m.model_dump() for m in payload.messages]

    try:
        result = send_chat(msg_dicts, db, client_context=payload.client_context)
    except ChatbotNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ChatbotInvalidConversation as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ChatbotError as exc:
        # str(exc) is one of llm_client's fixed operator-facing messages; the
        # provider's own error text stays in the server log.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return result
