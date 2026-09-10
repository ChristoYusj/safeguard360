from __future__ import annotations

from datetime import datetime

from app.db.models import Attendance
from app.services.chatbot import build_site_context
from app.services.gate_compliance import serialize_ppe_details


def test_chatbot_context_includes_recent_ppe_violation_details(db_session):
    db_session.add(
        Attendance(
            person_name="Christo",
            direction="ENTRY",
            timestamp=datetime.utcnow(),
            ppe_compliant=False,
            access_granted=False,
            confidence=0.91,
            camera_source_type="webcam",
            camera_source_id="0",
            log_method="AUTO",
            ppe_details=serialize_ppe_details(
                {
                    "status": "non_compliant",
                    "required_items": ["helmet", "vest"],
                    "detected_items": ["helmet"],
                    "missing_items": ["vest"],
                    "detector_available": True,
                    "detector_message": "Vest not detected in entry frame.",
                }
            ),
        )
    )
    db_session.commit()

    context = build_site_context(db_session)
    assert context.ppe_violations_today == 1
    assert context.recent_ppe_violations[0]["person_name"] == "Christo"
    assert context.recent_ppe_violations[0]["missing_items"] == ["vest"]

    prompt_block = context.to_prompt_block()
    assert "Recent PPE violations" in prompt_block
    assert "Christo" in prompt_block
    assert "missing=vest" in prompt_block
    assert "access denied" in prompt_block
