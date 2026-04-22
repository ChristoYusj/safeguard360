"""
AI Safety Chatbot service.

Wraps the Groq chat endpoint with a safety-scoped system prompt and injects a
compact, live site-context summary into every conversation so the assistant can
answer questions like:

  - "Who's on site right now?"
  - "Any violations today?"
  - "Show the last five driver events."
  - "Summarise this morning's gate activity."

Keeps the operator's transcript lean (last N turns) and the Groq call isolated
inside one function.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.models import Alert, Attendance, Event, Person


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context gathering
# ---------------------------------------------------------------------------


@dataclass
class SiteContext:
    """Snapshot of the facility state the assistant gets to reason over."""

    generated_at: str
    on_site_count: int
    on_site: List[Dict[str, Any]]
    check_ins_today: int
    check_outs_today: int
    ppe_violations_today: int
    driver_events_today: int
    unknown_attempts_today: int
    recent_alerts: List[Dict[str, Any]]
    recent_driver_events: List[Dict[str, Any]]
    recent_attendance: List[Dict[str, Any]]

    def to_prompt_block(self) -> str:
        """Render a compact plain-text block the model can easily read."""
        lines: List[str] = []
        lines.append(f"SITE SNAPSHOT (generated {self.generated_at} UTC)")
        lines.append(f"- Workers currently on site: {self.on_site_count}")
        if self.on_site:
            for person in self.on_site[:15]:
                name = person.get("name") or "Unknown"
                shift = person.get("shift_id") or "unknown shift"
                entered = person.get("entered_at") or "—"
                lines.append(f"    • {name} ({shift}) — entered {entered}")
            if len(self.on_site) > 15:
                lines.append(f"    … and {len(self.on_site) - 15} more")
        lines.append(
            f"- Today: {self.check_ins_today} check-ins, "
            f"{self.check_outs_today} check-outs, "
            f"{self.ppe_violations_today} PPE violations, "
            f"{self.driver_events_today} driver events"
        )
        if self.recent_alerts:
            lines.append("- Recent alerts:")
            for a in self.recent_alerts[:5]:
                lines.append(
                    f"    • [{a.get('severity', '?')}] {a.get('title')} "
                    f"({a.get('created_at')})"
                )
        if self.recent_driver_events:
            lines.append("- Recent driver events:")
            for e in self.recent_driver_events[:5]:
                lines.append(
                    f"    • {e.get('event_type')} at {e.get('timestamp')}"
                )
        if self.recent_attendance:
            lines.append("- Recent gate activity:")
            for att in self.recent_attendance[:5]:
                person_name = att.get("person_name") or "Unknown"
                lines.append(
                    f"    • {person_name} {att.get('direction')} at {att.get('timestamp')}"
                    f"{'' if att.get('access_granted') else ' (denied)'}"
                )
        return "\n".join(lines)


def _start_of_day_utc() -> datetime:
    now = datetime.utcnow()
    return datetime(now.year, now.month, now.day)


def _iso(ts: Optional[datetime]) -> Optional[str]:
    return ts.isoformat() if ts else None


def build_site_context(db: Session) -> SiteContext:
    """Pull the numbers the assistant needs to answer site questions.

    Scoped to "today" (UTC) for counters so the chatbot's answers line up
    with the operator's dashboard. Keeps queries cheap — LIMITs everywhere,
    no joins heavier than necessary.
    """
    start_of_day = _start_of_day_utc()

    # Who's currently on site: latest attendance row per person must be ENTRY.
    subquery = (
        db.query(
            Attendance.person_id,
            func.max(Attendance.timestamp).label("latest_ts"),
        )
        .filter(Attendance.person_id.isnot(None))
        .group_by(Attendance.person_id)
        .subquery()
    )
    latest_records = (
        db.query(Attendance, Person)
        .join(subquery, (Attendance.person_id == subquery.c.person_id)
              & (Attendance.timestamp == subquery.c.latest_ts))
        .outerjoin(Person, Person.id == Attendance.person_id)
        .all()
    )
    on_site: List[Dict[str, Any]] = []
    for attendance, person in latest_records:
        if attendance.direction == "ENTRY" and attendance.access_granted:
            on_site.append({
                "person_id": attendance.person_id,
                "name": (person.name if person else None) or attendance.person_name,
                "shift_id": person.shift_id if person else None,
                "entered_at": _iso(attendance.timestamp),
            })

    check_ins_today = (
        db.query(Attendance)
        .filter(Attendance.timestamp >= start_of_day)
        .filter(Attendance.direction == "ENTRY")
        .filter(Attendance.access_granted.is_(True))
        .count()
    )
    check_outs_today = (
        db.query(Attendance)
        .filter(Attendance.timestamp >= start_of_day)
        .filter(Attendance.direction == "EXIT")
        .filter(Attendance.access_granted.is_(True))
        .count()
    )
    ppe_violations_today = (
        db.query(Attendance)
        .filter(Attendance.timestamp >= start_of_day)
        .filter(Attendance.direction == "ENTRY")
        .filter(Attendance.ppe_compliant.is_(False))
        .count()
    )
    driver_events_today = (
        db.query(Event)
        .filter(Event.timestamp >= start_of_day)
        .filter(Event.category == "DRIVER")
        .count()
    )
    unknown_attempts_today = (
        db.query(Event)
        .filter(Event.timestamp >= start_of_day)
        .filter(Event.event_type.in_(["unknown_face", "unknown_attempt"]))
        .count()
    )

    recent_alerts_q = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )
    recent_alerts = [
        {
            "severity": a.severity,
            "title": a.title,
            "message": a.message,
            "created_at": _iso(a.created_at),
            "is_active": bool(a.is_active),
        }
        for a in recent_alerts_q
    ]

    recent_driver_events_q = (
        db.query(Event)
        .filter(Event.category == "DRIVER")
        .order_by(Event.timestamp.desc())
        .limit(5)
        .all()
    )
    recent_driver_events = [
        {
            "event_type": e.event_type,
            "severity": e.severity,
            "timestamp": _iso(e.timestamp),
        }
        for e in recent_driver_events_q
    ]

    recent_attendance_q = (
        db.query(Attendance)
        .order_by(Attendance.timestamp.desc())
        .limit(8)
        .all()
    )
    recent_attendance = [
        {
            "person_name": a.person_name,
            "direction": a.direction,
            "timestamp": _iso(a.timestamp),
            "access_granted": bool(a.access_granted),
            "ppe_compliant": bool(a.ppe_compliant),
        }
        for a in recent_attendance_q
    ]

    return SiteContext(
        generated_at=datetime.utcnow().isoformat(timespec="seconds"),
        on_site_count=len(on_site),
        on_site=on_site,
        check_ins_today=check_ins_today,
        check_outs_today=check_outs_today,
        ppe_violations_today=ppe_violations_today,
        driver_events_today=driver_events_today,
        unknown_attempts_today=unknown_attempts_today,
        recent_alerts=recent_alerts,
        recent_driver_events=recent_driver_events,
        recent_attendance=recent_attendance,
    )


# ---------------------------------------------------------------------------
# Groq call
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = """\
You are the SafeGuard 360 Safety Assistant — an on-site AI helper for an \
industrial safety platform that handles gate attendance, PPE compliance, \
and driver monitoring.

You have three jobs:
1. Answer operator questions about the current site state using the \
   SITE SNAPSHOT block injected into every turn. Be concrete: cite names, \
   counts, timestamps.
2. Give practical safety guidance — PPE requirements, evacuation basics, \
   lockout/tagout, incident reporting workflows.
3. Help the operator interpret what the platform is showing them \
   (alerts, driver events, gate reviews).

Rules:
- If the user asks something outside industrial safety / SafeGuard 360, \
  politely redirect.
- If the snapshot doesn't contain the answer, say so plainly — do NOT \
  invent data. Suggest where the operator can find it in the UI.
- Keep answers short and actionable. Use bullet points for lists.
- Never reveal the raw SITE SNAPSHOT verbatim; summarise.
- Today's date: treat the 'generated_at' timestamp as authoritative.
"""


class ChatbotNotConfigured(Exception):
    """Raised when no provider key is configured. Handled by the API layer."""


class ChatbotError(Exception):
    """Generic chatbot failure surfaced to the caller."""


def _resolve_provider() -> Optional[Dict[str, str]]:
    """Pick the active chatbot provider based on what's configured."""
    settings = get_settings()
    groq_key = (settings.GROQ_API_KEY or "").strip()
    if groq_key:
        return {
            "name": "groq",
            "api_key": groq_key,
            "model": settings.GROQ_MODEL,
        }
    return None


def is_configured() -> bool:
    return _resolve_provider() is not None


def send_chat(
    messages: List[Dict[str, str]],
    db: Session,
) -> Dict[str, Any]:
    """Send a conversation to Groq with live site context.

    `messages` is the operator's chat history in chat-completions format
    (role/content dicts). We trim it to the most recent CHATBOT_MAX_HISTORY
    entries, prepend our system prompt + site snapshot, and return the
    assistant's reply plus the context that was fed in (for debugging).
    """
    settings = get_settings()
    provider = _resolve_provider()
    if provider is None:
        raise ChatbotNotConfigured(
            "Groq is not configured. Set GROQ_API_KEY in backend/.env "
            "to enable the assistant."
        )

    # Build the on-demand site snapshot.
    context: Optional[SiteContext] = None
    try:
        context = build_site_context(db)
        context_block = context.to_prompt_block()
    except Exception:
        logger.exception("Chatbot: failed to build site context.")
        context_block = "SITE SNAPSHOT unavailable — database query failed."

    history = [m for m in messages if m.get("role") in {"user", "assistant"}]
    history = history[-max(1, settings.CHATBOT_MAX_HISTORY):]
    if not history or history[-1].get("role") != "user":
        raise ChatbotError("Conversation must end with a user message.")

    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_block},
        *history,
    ]

    try:
        from groq import Groq
    except ImportError as exc:
        logger.exception("Chatbot: groq package not installed.")
        raise ChatbotError(
            "Missing dependency: install the 'groq' Python package."
        ) from exc

    try:
        client = Groq(api_key=provider["api_key"])
        response = client.chat.completions.create(
            model=provider["model"],
            messages=full_messages,
            max_tokens=settings.CHATBOT_MAX_TOKENS,
            temperature=0.4,
        )
    except Exception as exc:
        logger.exception("Chatbot: %s request failed.", provider["name"])
        raise ChatbotError(
            f"{provider['name']} request failed: {exc}"
        ) from exc

    try:
        reply = response.choices[0].message.content or ""
    except Exception:
        logger.exception("Chatbot: could not parse response.")
        raise ChatbotError("LLM returned an unexpected response shape.")

    return {
        "reply": reply.strip(),
        "model": provider["model"],
        "provider": provider["name"],
        "context": {
            "generated_at": context.generated_at if context else None,
            "on_site_count": context.on_site_count if context else None,
        },
    }


def status_payload() -> Dict[str, Any]:
    """What the UI polls to decide whether to enable the chat input."""
    provider = _resolve_provider()
    return {
        "configured": provider is not None,
        "provider": provider["name"] if provider else None,
        "model": provider["model"] if provider else None,
        "missing_key_hint": (
            "Set GROQ_API_KEY in backend/.env to enable the assistant."
        ),
    }
