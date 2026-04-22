"""
Tests for pure-logic helpers in app.services.gate_compliance.
No camera / ML dependencies loaded.
"""
from __future__ import annotations

import json

from app.services.gate_compliance import (
    DEFAULT_GATE_POLICY,
    DEFAULT_PPE_DETAILS,
    create_alert_record,
    create_event_record,
    get_or_create_gate_policy,
    get_required_ppe_items,
    normalize_ppe_details,
    normalize_review_reasons,
    ppe_reason_messages,
    serialize_gate_policy,
    serialize_ppe_details,
    serialize_review_reasons,
)


# ---------- review_reasons ----------

def test_normalize_review_reasons_dedupes_and_strips():
    result = normalize_review_reasons(["face_confidence", " face_confidence ", "", None, "missing_helmet"])
    assert result == ["face_confidence", "missing_helmet"]


def test_normalize_review_reasons_handles_json_string():
    raw = json.dumps(["uncertain_ppe", "missing_vest"])
    assert normalize_review_reasons(raw) == ["uncertain_ppe", "missing_vest"]


def test_normalize_review_reasons_invalid_inputs():
    assert normalize_review_reasons(None) == []
    assert normalize_review_reasons("not json") == []
    assert normalize_review_reasons(json.dumps({"not": "a list"})) == []


def test_serialize_review_reasons_roundtrip():
    payload = serialize_review_reasons(["missing_helmet", "missing_helmet", ""])
    assert json.loads(payload) == ["missing_helmet"]


# ---------- ppe_details ----------

def test_normalize_ppe_details_fills_defaults():
    result = normalize_ppe_details(None)
    for key in DEFAULT_PPE_DETAILS:
        assert key in result


def test_normalize_ppe_details_coerces_types():
    result = normalize_ppe_details({
        "status": "  ok  ",
        "required_items": ["helmet", "", "vest"],
        "detected_items": None,
        "detector_confidences": {"helmet": "0.92", "vest": None},
        "override_used": 1,
        "detector_available": "yes",
    })
    assert result["status"] == "ok"
    assert result["required_items"] == ["helmet", "vest"]
    assert result["detected_items"] == []
    assert result["detector_confidences"] == {"helmet": 0.92}
    assert result["override_used"] is True
    assert result["detector_available"] is True


def test_serialize_ppe_details_produces_json():
    encoded = serialize_ppe_details({"status": "ok"})
    decoded = json.loads(encoded)
    assert decoded["status"] == "ok"
    assert decoded["required_items"] == []


# ---------- required ppe ----------

def test_get_required_ppe_items_both():
    class P:
        require_helmet = True
        require_vest = True
    assert get_required_ppe_items(P()) == ["helmet", "vest"]


def test_get_required_ppe_items_helmet_only():
    class P:
        require_helmet = True
        require_vest = False
    assert get_required_ppe_items(P()) == ["helmet"]


def test_get_required_ppe_items_none():
    class P:
        require_helmet = False
        require_vest = False
    assert get_required_ppe_items(P()) == []


# ---------- reason messages ----------

def test_ppe_reason_messages_known_reasons():
    msgs = ppe_reason_messages(["face_confidence", "uncertain_ppe", "missing_helmet", "missing_vest"])
    assert any("Face confidence" in m for m in msgs)
    assert any("PPE status is uncertain" in m for m in msgs)
    assert any("Missing helmet" in m for m in msgs)
    assert any("Missing vest" in m for m in msgs)


def test_ppe_reason_messages_unknown_reason_ignored():
    assert ppe_reason_messages(["something_else"]) == []


# ---------- DB-backed helpers ----------

def test_get_or_create_gate_policy_creates_then_reuses(db_session):
    policy_a = get_or_create_gate_policy(db_session)
    db_session.commit()
    policy_b = get_or_create_gate_policy(db_session)
    assert policy_a.id == policy_b.id
    for key, value in DEFAULT_GATE_POLICY.items():
        assert getattr(policy_a, key) == value


def test_serialize_gate_policy_shape(db_session):
    policy = get_or_create_gate_policy(db_session)
    db_session.commit()
    data = serialize_gate_policy(policy)
    assert {"id", "require_helmet", "require_vest", "enforce_stage"}.issubset(data.keys())
    assert data["enforce_stage"] == DEFAULT_GATE_POLICY["enforce_stage"]


def test_create_event_and_alert_records(db_session):
    event = create_event_record(
        db_session,
        category="PPE",
        event_type="missing_helmet",
        severity="WARN",
        message="no helmet",
        data={"confidence": 0.8},
    )
    alert = create_alert_record(
        db_session,
        event=event,
        severity="WARN",
        title="PPE Violation",
        message="Helmet missing",
    )
    db_session.commit()
    assert event.id is not None
    assert alert.event_id == event.id
    assert json.loads(event.data)["confidence"] == 0.8
