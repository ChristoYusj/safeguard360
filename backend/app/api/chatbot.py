"""
AI Safety Chatbot API.

Thin wrapper over app.services.chatbot. The frontend hits three endpoints:

  - GET  /api/chatbot/status   → whether Groq is configured
  - GET  /api/chatbot/context  → the live site snapshot (debug / preview)
  - POST /api/chatbot/message  → send a conversation, get a reply

Authentication follows the same middleware pattern as the other routes —
the global auth middleware attaches `request.state.user` before this
module sees the call.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.services.chatbot import (
    ChatbotError,
    ChatbotNotConfigured,
    build_site_context,
    send_chat,
    status_payload,
)


router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    client_context: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    model: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatStatusResponse(BaseModel):
    configured: bool
    model: Optional[str] = None
    missing_key_hint: str


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
    except Exception:
        logger.exception("Chatbot: context build failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not build site context.",
        )
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
def post_message(payload: ChatRequest, db: Session = Depends(get_db)):
    if not payload.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one message is required.",
        )
    msg_dicts = [m.model_dump() for m in payload.messages]

    try:
        result = send_chat(msg_dicts, db, client_context=payload.client_context)
    except ChatbotNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except ChatbotError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    return result
