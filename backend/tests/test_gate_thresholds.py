"""The gate's decision tunables actually govern the gate (Phase 2a).

Before this, GateAttendanceRecognizer wrote auto_pass_threshold,
review_threshold and required_confirmations in __init__ and then never read
them: the decision path compared against the literals 79, 84 and 85, and one
frame was enough to open the gate. These tests pin the wiring so the numbers
cannot drift back into the loop.
"""
from __future__ import annotations

import inspect
import math
import re

import pytest
from pydantic import ValidationError

from app.api.attendance import _resolve_override_reason_type
from app.config.settings import Settings, get_settings
from app.db.connection import SessionLocal
from app.db.models import Event
from app.services.gate_attendance import GateAttendanceRecognizer
from app.services.gate_compliance import ppe_reason_messages


def _recognizer(**overrides) -> GateAttendanceRecognizer:
    recognizer = GateAttendanceRecognizer()
    for key, value in overrides.items():
        setattr(recognizer, key, value)
    return recognizer


class _Person:
    """Stand-in for a Person row: _find_best_match only reads .id and .name."""

    def __init__(self, person_id: str):
        self.id = person_id
        self.name = person_id


# --- the three bands come from the thresholds, not from literals ------------


def test_bands_at_the_shipped_defaults_match_the_old_literals():
    recognizer = _recognizer()

    assert (recognizer.review_percent, recognizer.auto_pass_percent) == (79, 85)
    assert recognizer._match_band(92) == "auto"
    assert recognizer._match_band(85) == "auto"
    assert recognizer._match_band(84) == "review"
    assert recognizer._match_band(79) == "review"
    assert recognizer._match_band(78) == "below"
    assert recognizer._match_band(0) == "below"


def test_raising_the_auto_pass_threshold_moves_the_band():
    strict = _recognizer(auto_pass_threshold=0.95)

    assert strict.auto_pass_percent == 95
    assert strict._match_band(92) == "review"  # was "auto" at the default
    assert strict._match_band(95) == "auto"


def test_lowering_the_review_threshold_moves_the_band():
    lenient = _recognizer(review_threshold=0.60)

    assert lenient.review_percent == 60
    assert lenient._match_band(65) == "review"  # was "below" at the default
    assert lenient._match_band(59) == "below"


def test_thresholds_and_confirmations_are_read_from_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "GATE_AUTO_PASS_THRESHOLD", 0.90)
    monkeypatch.setattr(settings, "GATE_REVIEW_THRESHOLD", 0.70)
    monkeypatch.setattr(settings, "GATE_CANDIDATE_THRESHOLD", 0.50)
    monkeypatch.setattr(settings, "GATE_REQUIRED_CONFIRMATIONS", 5)
    monkeypatch.setattr(settings, "GATE_MATCH_MARGIN", 0.25)

    recognizer = GateAttendanceRecognizer()

    assert recognizer.auto_pass_threshold == 0.90
    assert recognizer.review_threshold == 0.70
    assert recognizer.candidate_threshold == 0.50
    assert recognizer.required_confirmations == 5
    assert recognizer.match_margin == 0.25
    assert recognizer._match_band(89) == "review"


def test_one_frame_no_longer_decides():
    """The shipped default is 3 agreeing recognitions, not 1."""
    assert GateAttendanceRecognizer().required_confirmations >= 3


def test_quality_floors_come_from_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "GATE_MIN_FACE_AREA_RATIO", 0.02)
    monkeypatch.setattr(settings, "GATE_MAX_YAW_OFFSET", 30.0)

    recognizer = GateAttendanceRecognizer()

    assert recognizer.min_face_area_ratio == 0.02
    assert recognizer.max_yaw_offset == 30.0


def test_the_shipped_quality_defaults_stay_lenient():
    """Changing detection sensitivity needs a webcam to validate, so the
    defaults are the tuned ones and the yaw filter stays off."""
    recognizer = GateAttendanceRecognizer()

    assert math.isinf(recognizer.max_yaw_offset)
    assert recognizer.min_face_area_ratio == 0.001
    assert recognizer.min_det_score == 0.30
    assert recognizer.min_blur_score == 5.0


# --- the winner must beat the runner-up -------------------------------------


def test_best_match_reports_the_runner_up_from_a_different_worker():
    recognizer = _recognizer()
    embedding = [1.0, 0.0, 0.0]
    enrolled = [
        (_Person("nadia"), [[1.0, 0.0, 0.0]]),
        (_Person("omar"), [[0.6, 0.8, 0.0]]),
    ]

    person, score, runner_up = recognizer._find_best_match(embedding, enrolled)

    assert person.id == "nadia"
    assert score == pytest.approx(1.0)
    assert runner_up == pytest.approx(0.6, abs=1e-6)


def test_several_photos_of_one_worker_are_not_a_runner_up():
    """Two enrolled vectors for the same person must collapse to one score."""
    recognizer = _recognizer()
    enrolled = [(_Person("nadia"), [[1.0, 0.0, 0.0], [0.99, 0.141, 0.0]])]

    person, score, runner_up = recognizer._find_best_match([1.0, 0.0, 0.0], enrolled)

    assert person.id == "nadia"
    assert score == pytest.approx(1.0)
    assert runner_up == 0.0


def test_a_close_second_is_ambiguous_and_a_clear_win_is_not():
    recognizer = _recognizer(match_margin=0.10)

    assert recognizer._is_ambiguous_match(0.91, 0.88) is True
    assert recognizer._is_ambiguous_match(0.91, 0.40) is False


def test_a_zero_margin_disables_the_check():
    assert _recognizer(match_margin=0.0)._is_ambiguous_match(0.91, 0.909) is False


def test_an_ambiguous_match_is_its_own_review_reason():
    recognizer = _recognizer()

    reasons = recognizer._build_review_reasons(
        review_band_match=False,
        ppe_details={"status": "compliant"},
        ambiguous_match=True,
    )

    assert reasons == ["ambiguous_match"]
    assert ppe_reason_messages(reasons) == [
        "Two enrolled workers scored too close to tell apart."
    ]
    plain = recognizer._build_review_reasons(
        review_band_match=True, ppe_details={"status": "compliant"}
    )
    assert plain == ["face_confidence"]


def test_both_face_reasons_are_recorded_when_both_apply():
    """A match can be in the review band AND too close to another worker.

    Reporting only one of them loses information the operator needs, and left
    the permanent record with no override reason type.
    """
    reasons = _recognizer()._build_review_reasons(
        review_band_match=True,
        ppe_details={"status": "compliant"},
        ambiguous_match=True,
    )

    assert reasons == ["face_confidence", "ambiguous_match"]
    assert _resolve_override_reason_type(reasons) == "face_confidence"
    assert _resolve_override_reason_type(["ambiguous_match"]) == "face_confidence"
    assert _resolve_override_reason_type(["ambiguous_match", "missing_helmet"]) == "combined"


# --- only qualifying frames count toward a confirmation -----------------------


def test_a_sub_threshold_frame_does_not_count_toward_the_confirmations():
    """The below-band branch used to claim the candidate and set the streak to
    1, so three confirmations could be reached with two qualifying frames."""
    source = inspect.getsource(GateAttendanceRecognizer.process_frame)
    below_branch = source.split('if self._match_band(match_percent) == "below":', 1)[1]
    below_branch = below_branch.split("self.unknown_face_streak = 0", 1)[1]
    below_branch = below_branch.split("return frame, events", 1)[0]

    assert "last_candidate_streak" not in below_branch
    assert "last_candidate_person_id" not in below_branch


# --- the literals cannot come back -------------------------------------------


def test_no_threshold_literal_remains_in_the_decision_path():
    """A guard, not a behaviour test.

    The band helper is small and pure, so the unit tests above would still pass
    if someone put `79 <= match_percent <= 84` back at a call site. This reads
    the source and fails if a bare threshold comparison reappears.
    """
    source = inspect.getsource(GateAttendanceRecognizer.process_frame)
    offenders = re.findall(r"(?:match_percent|overall_percent)\s*[<>=]=?\s*\d+", source)
    offenders += re.findall(r"\d+\s*[<>=]=?\s*(?:match_percent|overall_percent)", source)

    assert offenders == [], f"threshold literals are back in the decision path: {offenders}"


# --- a malformed gate configuration stops the app ------------------------------


def test_an_inverted_threshold_pair_is_refused_at_construction():
    with pytest.raises(ValidationError):
        Settings(GATE_REVIEW_THRESHOLD=0.95, GATE_AUTO_PASS_THRESHOLD=0.85)
    with pytest.raises(ValidationError):
        Settings(GATE_REQUIRED_CONFIRMATIONS=0)
    with pytest.raises(ValidationError):
        Settings(GATE_MATCH_MARGIN=-0.1)


# --- unknown faces leave a record --------------------------------------------


def _unknown_events() -> list[Event]:
    db = SessionLocal()
    try:
        return db.query(Event).filter(Event.event_type == "unknown_face").all()
    finally:
        db.close()


def test_an_unknown_face_writes_one_gate_event(client):
    recognizer = _recognizer(unknown_attempt_cooldown_seconds=30.0)

    assert recognizer._log_unknown_face_attempt(direction="ENTRY", confidence=0.31, now_ts=1000.0) is True

    events = _unknown_events()
    assert len(events) == 1
    assert events[0].category == "GATE"
    assert events[0].severity == "WARNING"
    assert "31%" in (events[0].data or "")
    assert "79%" in (events[0].data or "")
    assert events[0].snapshot_path is None  # no photo of a non-enrolled person


def test_repeat_attempts_are_debounced_then_logged_again(client):
    recognizer = _recognizer(unknown_attempt_cooldown_seconds=30.0)

    assert recognizer._log_unknown_face_attempt(direction="ENTRY", confidence=0.3, now_ts=1000.0) is True
    assert recognizer._log_unknown_face_attempt(direction="ENTRY", confidence=0.3, now_ts=1010.0) is False
    assert recognizer._log_unknown_face_attempt(direction="ENTRY", confidence=0.3, now_ts=1029.9) is False
    assert len(_unknown_events()) == 1

    assert recognizer._log_unknown_face_attempt(direction="ENTRY", confidence=0.3, now_ts=1030.0) is True
    assert len(_unknown_events()) == 2


def test_unknown_attempts_reach_the_assistants_counter(client):
    """build_site_context counts these by event_type; nothing wrote them before."""
    from app.services.chatbot import build_site_context

    _recognizer()._log_unknown_face_attempt(direction="ENTRY", confidence=0.2, now_ts=2000.0)

    db = SessionLocal()
    try:
        assert build_site_context(db).unknown_attempts_today == 1
    finally:
        db.close()
