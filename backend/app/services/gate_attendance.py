"""
Live gate attendance recognition.
"""
from __future__ import annotations

import logging
from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field
import time
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.connection import SessionLocal
from app.db.models import Attendance, GatePolicy, GateReview, Person
from app.inference.face_recognizer import cosine_similarity, face_recognizer
from app.inference.ppe_detector import ppe_detector
from app.services.attendance_state import get_on_site_person_ids
from app.services.gate_compliance import (
    create_alert_record,
    create_event_record,
    get_or_create_gate_policy,
    get_required_ppe_items,
    is_within_shift,
    normalize_ppe_details,
    normalize_review_reasons,
    ppe_reason_messages,
    serialize_ppe_details,
    serialize_review_reasons,
)
from app.services.persons import (
    calculate_blur_score,
    calculate_face_area_ratio,
    calculate_quality_score,
    parse_embedding_payload,
    write_attendance_snapshot,
)

logger = logging.getLogger(__name__)


@dataclass
class GateRecognitionEvent:
    event_type: str
    timestamp: float
    confidence: float
    details: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    access_granted: bool = False
    ppe_compliant: bool = True
    ppe_status: str = "not_evaluated"
    ppe_details: Dict[str, Any] = field(default_factory=dict)
    review_reasons: List[str] = field(default_factory=list)


class GateAttendanceRecognizer:
    """Recognize enrolled workers from the gate camera."""

    def __init__(self) -> None:
        self.settings = get_settings()
        # These four used to be written here and then ignored: the decision
        # path compared against the literals 79, 84 and 85 instead, and one
        # confirmation was enough to open the gate. They are now the only
        # source of those numbers, and they come from configuration.
        self.auto_pass_threshold = self.settings.GATE_AUTO_PASS_THRESHOLD
        self.review_threshold = self.settings.GATE_REVIEW_THRESHOLD
        self.candidate_threshold = self.settings.GATE_CANDIDATE_THRESHOLD
        self.required_confirmations = self.settings.GATE_REQUIRED_CONFIRMATIONS
        # How far ahead of the runner-up enrolled worker the winner must be to
        # be decided automatically. Two people scoring within this margin is
        # an ambiguous identity, not a match.
        self.match_margin = self.settings.GATE_MATCH_MARGIN
        self.min_direction_gap_seconds = 45.0
        self.rearm_after_absence_seconds = 2.5
        self.gate_direction_mode = "ENTRY"
        self.analysis_max_width = 384
        # NOTE: these now govern how long the LABEL (name + percentage)
        # persists on the live bbox when ArcFace hasn't produced a fresh
        # result yet. Bbox itself is re-detected every frame by MediaPipe.
        # The match label hold is generous (~3s) so short ArcFace gaps don't
        # cause the overlay to flicker between "Christo 92%" and the MediaPipe
        # "Detected 88%" fallback. Unknown overlays clear faster so the UI
        # doesn't keep showing an "Unknown face" tag after the face leaves.
        self.overlay_hold_seconds = 3.0
        self.unknown_overlay_hold_seconds = 0.8
        # Extended grace window used specifically for "named match" labels
        # (anything ending in a "%" from ArcFace). If the bbox is still live
        # and we saw a named match recently, keep that label on-screen even
        # past overlay_hold_seconds rather than flickering back to MediaPipe's
        # generic "Detected XX%" tag.
        self.named_match_hold_seconds = 5.0
        self.recent_match_hold_seconds = 1.5
        self.unknown_face_confirmations = 1
        self.last_candidate_person_id: Optional[str] = None
        self.last_candidate_streak = 0
        self.last_match_state_seen_at: float = 0.0
        self.unknown_face_streak = 0
        self.active_match_person_id: Optional[str] = None
        self.active_match_last_seen_at: float = 0.0
        self.active_review_person_id: Optional[str] = None
        self.active_review_id: Optional[str] = None
        self.active_review_last_seen_at: float = 0.0
        self.resolved_review_person_id: Optional[str] = None
        self.resolved_review_decision: Optional[str] = None
        self.resolved_review_last_seen_at: float = 0.0
        self.last_overlay_bbox: Optional[List[float]] = None
        self.last_overlay_label = ""
        self.last_overlay_color = (59, 130, 246)
        self.last_overlay_seen_at: float = 0.0
        self.last_overlay_hold_seconds = self.overlay_hold_seconds
        self.cached_people: List[Tuple[Person, List[List[float]]]] = []
        self.cache_loaded_at: float = 0.0
        self.cache_ttl_seconds = 60.0
        self.on_site_cache_ids: set[str] = set()
        self.on_site_cache_loaded_at: float = 0.0
        self.on_site_cache_ttl_seconds = 3.0
        self.policy_cache: Optional[GatePolicy] = None
        self.policy_cache_loaded_at: float = 0.0
        self.policy_cache_ttl_seconds = 5.0
        self.active_ppe_person_id: Optional[str] = None
        self.ppe_history: Deque[Dict[str, Any]] = deque(maxlen=4)
        self.ppe_item_detection_counts: Counter[str] = Counter()
        self.ppe_locked_items: set[str] = set()
        self.ppe_best_confidences: Dict[str, float] = {}
        self.ppe_last_details: Dict[str, Any] = normalize_ppe_details({})
        self.ppe_last_seen_at: float = 0.0
        self.ppe_lock_required_hits = 3
        self.ppe_hold_seconds = 3.0
        # Face quality thresholds for live recognition.
        # NOTE: operator feedback (Apr 2026) — the quality gate was producing
        # too many false "face is turned / too far" rejections at live gates,
        # so the yaw check is disabled and the blur/area floors are kept very
        # lenient. The ArcFace match threshold itself is the real filter; if a
        # face is too poor to embed, it simply won't match any enrolled worker.
        # They are settings now (defaults unchanged), so a site can tighten
        # them from .env without a code change, and docs/attendance-gate.md
        # states what is switched off.
        self.min_det_score = self.settings.GATE_MIN_DET_SCORE
        self.min_blur_score = self.settings.GATE_MIN_BLUR_SCORE
        self.min_face_area_ratio = self.settings.GATE_MIN_FACE_AREA_RATIO
        # Default inf = the yaw filter is off; the plumbing stays so the field
        # remains visible in the overlay payload for debugging.
        self.max_yaw_offset = self.settings.GATE_MAX_YAW_OFFSET
        # Unknown-face attempt logging cooldown (prevents flooding the review queue)
        self.last_unknown_attempt_logged_at: float = 0.0
        self.unknown_attempt_cooldown_seconds: float = 30.0
        self.gate_state: Dict[str, object] = self._build_gate_state(
            match_status="idle",
            message="Waiting for gate recognition.",
        )
        # Lightweight live face detector (MediaPipe) used only to track the
        # bbox smoothly between full ArcFace recognitions.
        self._live_detector = None
        self._live_detector_failed = False
        self._last_live_bbox: Optional[List[float]] = None
        self._last_live_bbox_at: float = 0.0
        # Most recent MediaPipe detection confidence (0..1). Used for the
        # "Detected XX%" tag shown before ArcFace provides a match label.
        self._last_live_bbox_confidence: float = 0.0
        # How long to carry a bbox when MediaPipe misses a single frame.
        # Keep this short (≈3 frames at 20 FPS) so the box doesn't look
        # "stuck"; just enough to cover one-frame detection misses.
        self._live_bbox_persist_s: float = 0.15

    def get_state_dict(self) -> Dict[str, object]:
        return dict(self.gate_state)

    def invalidate_cache(self) -> None:
        self.cached_people = []
        self.cache_loaded_at = 0.0
        self.on_site_cache_ids = set()
        self.on_site_cache_loaded_at = 0.0
        self.policy_cache = None
        self.policy_cache_loaded_at = 0.0

    def _get_match_percent(self, score: float) -> int:
        return int(round(max(0.0, score) * 100))

    @property
    def auto_pass_percent(self) -> int:
        """The on-screen percentage at which the gate decides on its own."""
        return self._get_match_percent(self.auto_pass_threshold)

    @property
    def review_percent(self) -> int:
        """The on-screen percentage at which a match goes to the operator."""
        return self._get_match_percent(self.review_threshold)

    def _match_band(self, match_percent: int) -> str:
        """Which band a match percentage falls in: auto, review or below.

        The single place the thresholds are compared. Before this existed the
        same three numbers were spelled out as literals at three call sites,
        so changing auto_pass_threshold changed nothing.
        """
        if match_percent >= self.auto_pass_percent:
            return "auto"
        if match_percent >= self.review_percent:
            return "review"
        return "below"

    def _is_ambiguous_match(self, score: float, runner_up_score: float) -> bool:
        """True when a second enrolled worker scores too close to the winner.

        Without this the top cosine score won outright, so two people whose
        embeddings sit a hair apart (or the same person enrolled twice) could
        be let through under the wrong name. An ambiguous pair is sent to the
        operator; it never denies entry on its own.
        """
        if self.match_margin <= 0:
            return False
        return (score - runner_up_score) < self.match_margin

    def get_gate_direction_mode(self) -> str:
        return self.gate_direction_mode

    def set_gate_direction_mode(self, direction_mode: str) -> str:
        normalized_mode = direction_mode.upper()
        if normalized_mode not in {"ENTRY", "EXIT"}:
            raise ValueError("Gate direction mode must be ENTRY or EXIT.")
        if self.gate_direction_mode != normalized_mode:
            self.reset_live_session(
                clear_pending_reviews=True,
                reason="Gate direction changed before the live review was resolved.",
            )
        self.gate_direction_mode = normalized_mode
        self.on_site_cache_ids = set()
        self.on_site_cache_loaded_at = 0.0
        return self.gate_direction_mode

    def _build_gate_state(
        self,
        *,
        match_status: str,
        message: str,
        person_id: Optional[str] = None,
        person_name: Optional[str] = None,
        confidence: float = 0.0,
        last_seen_at: Optional[float] = None,
        faces_detected: int = 0,
        bbox: Optional[List[float]] = None,
        overlay_label: Optional[str] = None,
        overlay_tone: str = "info",
        candidate_scope: Optional[str] = None,
        ppe_details: Optional[Dict[str, Any]] = None,
        review_reasons: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        normalized_ppe = normalize_ppe_details(ppe_details)
        normalized_review_reasons = normalize_review_reasons(review_reasons)
        return {
            "match_status": match_status,
            "person_id": person_id,
            "person_name": person_name,
            "confidence": confidence,
            "last_seen_at": last_seen_at,
            "faces_detected": faces_detected,
            "message": message,
            "bbox": [float(value) for value in bbox] if bbox is not None else None,
            "overlay_label": overlay_label,
            "overlay_tone": overlay_tone,
            "direction_mode": self.gate_direction_mode,
            "candidate_scope": candidate_scope
            or ("checked_in_only" if self.gate_direction_mode == "EXIT" else "all_enrolled"),
            "ppe_status": normalized_ppe.get("status"),
            "ppe_compliant": normalized_ppe.get("status")
            in {"compliant", "skipped", "unavailable", "not_evaluated"},
            "required_items": normalized_ppe.get("required_items"),
            "detected_items": normalized_ppe.get("detected_items"),
            "missing_items": normalized_ppe.get("missing_items"),
            "detector_confidences": normalized_ppe.get("detector_confidences"),
            "ppe_message": normalized_ppe.get("detector_message"),
            "ppe_details": normalized_ppe,
            "review_reasons": normalized_review_reasons,
        }

    def _load_enrolled_people(self, force_refresh: bool = False) -> List[Tuple[Person, List[List[float]]]]:
        now = time.time()
        if (
            not force_refresh
            and self.cached_people
            and now - self.cache_loaded_at < self.cache_ttl_seconds
        ):
            return self.cached_people

        db = SessionLocal()
        try:
            people = (
                db.query(Person)
                .filter(Person.is_active.is_(True))
                .order_by(Person.created_at.asc())
                .all()
            )
            loaded_people = []
            for person in people:
                payload = parse_embedding_payload(person.embedding)
                vectors = payload.get("vectors") or []
                if vectors:
                    loaded_people.append((person, vectors))
            self.cached_people = loaded_people
            self.cache_loaded_at = now
            return loaded_people
        finally:
            db.close()

    def _find_best_match(self, embedding, enrolled_people):
        """Best enrolled worker for this face, plus the runner-up's score.

        The runner-up is the best score from a *different* person, so the
        caller can tell a clear identification from a coin flip between two
        workers. Several enrolled photos of one worker collapse to that
        worker's best score and never count as a runner-up.
        """
        best_person = None
        best_score = 0.0
        runner_up_score = 0.0
        for person, vectors in enrolled_people:
            person_score = max(cosine_similarity(embedding, vector) for vector in vectors)
            if person_score > best_score:
                runner_up_score = best_score
                best_score = person_score
                best_person = person
            elif person_score > runner_up_score:
                runner_up_score = person_score
        return best_person, best_score, runner_up_score

    def _get_on_site_person_ids(self, now: datetime) -> set[str]:
        now_ts = time.time()
        if (
            self.on_site_cache_loaded_at > 0
            and now_ts - self.on_site_cache_loaded_at < self.on_site_cache_ttl_seconds
        ):
            return set(self.on_site_cache_ids)

        db = SessionLocal()
        try:
            # One owner for this answer (app.services.attendance_state); the
            # gate keeps only its short cache. This used to load the entire
            # attendance table on every miss and fold it in Python.
            on_site_ids = get_on_site_person_ids(db)
            self.on_site_cache_ids = on_site_ids
            self.on_site_cache_loaded_at = now_ts
            return set(on_site_ids)
        finally:
            db.close()

    def _are_all_enrolled_workers_on_site(self, enrolled_people, on_site_ids: set[str]) -> bool:
        enrolled_ids = {
            person.id
            for person, _vectors in enrolled_people
            if getattr(person, "id", None)
        }
        return bool(enrolled_ids) and enrolled_ids.issubset(on_site_ids)

    def _get_gate_policy(self) -> GatePolicy:
        now_ts = time.time()
        if (
            self.policy_cache is not None
            and now_ts - self.policy_cache_loaded_at < self.policy_cache_ttl_seconds
        ):
            return self.policy_cache

        db = SessionLocal()
        try:
            policy = get_or_create_gate_policy(db)
            db.commit()
            db.refresh(policy)
            db.expunge(policy)
            self.policy_cache = policy
            self.policy_cache_loaded_at = now_ts
            return policy
        finally:
            db.close()

    def _clear_ppe_history(self) -> None:
        self.active_ppe_person_id = None
        self.ppe_history.clear()
        self.ppe_item_detection_counts.clear()
        self.ppe_locked_items.clear()
        self.ppe_best_confidences.clear()
        self.ppe_last_details = normalize_ppe_details({})
        self.ppe_last_seen_at = 0.0

    def _has_live_ppe_session(self, now_ts: float, *, person_id: Optional[str] = None) -> bool:
        if not self.active_ppe_person_id or self.ppe_last_seen_at <= 0:
            return False
        if person_id is not None and self.active_ppe_person_id != person_id:
            return False
        return now_ts - self.ppe_last_seen_at <= self.ppe_hold_seconds

    def _get_live_ppe_details(
        self,
        now_ts: float,
        *,
        person_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._has_live_ppe_session(now_ts, person_id=person_id):
            return normalize_ppe_details({})
        return normalize_ppe_details(self.ppe_last_details)

    def _summarize_ppe_details(self, details: Dict[str, Any]) -> str:
        missing_items = details.get("missing_items") or []
        latched_items = details.get("latched_items") or []
        if latched_items and not missing_items:
            return "Required PPE confirmed and locked in."
        if latched_items and missing_items:
            return (
                f"Locked: {', '.join(latched_items)}. "
                f"Still checking {', '.join(item.replace('_', ' ') for item in missing_items)}."
            )
        if missing_items:
            return f"Missing {', '.join(item.replace('_', ' ') for item in missing_items)}."
        if details.get("status") == "uncertain":
            return "PPE could not be confirmed from the current frame."
        return details.get("detector_message") or "PPE status updated."

    def _smooth_ppe_status(
        self,
        *,
        person_id: str,
        raw_details: Dict[str, Any],
        now_ts: float,
    ) -> Dict[str, Any]:
        details = normalize_ppe_details(raw_details)
        raw_status = details.get("status")
        if raw_status in {"skipped", "unavailable", "not_evaluated"}:
            self._clear_ppe_history()
            return details

        if self.active_ppe_person_id != person_id:
            self.active_ppe_person_id = person_id
            self.ppe_history.clear()
            self.ppe_item_detection_counts.clear()
            self.ppe_locked_items.clear()
            self.ppe_best_confidences.clear()

        self.ppe_history.append(deepcopy(details))
        required_items = list(details.get("required_items") or [])
        detected_items = set(details.get("detected_items") or [])

        for item, confidence in (details.get("detector_confidences") or {}).items():
            current_confidence = self.ppe_best_confidences.get(item, 0.0)
            self.ppe_best_confidences[item] = max(current_confidence, float(confidence or 0.0))

        for item in detected_items:
            self.ppe_item_detection_counts[item] += 1
            if self.ppe_item_detection_counts[item] >= self.ppe_lock_required_hits:
                self.ppe_locked_items.add(item)

        merged_detected_items = sorted(detected_items.union(self.ppe_locked_items))
        merged_missing_items = [
            item for item in required_items if item not in merged_detected_items
        ]
        status_counts = Counter(
            item.get("status")
            for item in self.ppe_history
            if item.get("status") in {"compliant", "non_compliant", "uncertain"}
        )

        final_status = raw_status
        if required_items and len(merged_missing_items) == 0:
            final_status = "compliant"
        elif status_counts.get("non_compliant", 0) >= 2:
            final_status = "non_compliant"
        elif status_counts.get("compliant", 0) >= 2 and status_counts.get("non_compliant", 0) == 0:
            final_status = "compliant"
        elif status_counts.get("uncertain", 0) >= 2:
            final_status = "uncertain"
        elif self.ppe_locked_items and merged_missing_items:
            final_status = "non_compliant"
        elif len(self.ppe_history) >= 2 and raw_status != "compliant":
            final_status = "uncertain"

        details["detected_items"] = merged_detected_items
        details["missing_items"] = merged_missing_items
        details["detector_confidences"] = {
            item: self.ppe_best_confidences[item]
            for item in sorted(self.ppe_best_confidences)
        }
        details["latched_items"] = sorted(self.ppe_locked_items)
        details["status"] = final_status
        if final_status == "compliant":
            details["missing_items"] = []
            details["detector_message"] = "Required PPE confirmed and locked in."
        elif not details.get("detector_message"):
            details["detector_message"] = self._summarize_ppe_details(details)
        self.ppe_last_details = normalize_ppe_details(details)
        self.ppe_last_details["latched_items"] = list(details.get("latched_items") or [])
        self.ppe_last_seen_at = now_ts
        return details

    def _evaluate_ppe_for_candidate(
        self,
        *,
        person_id: str,
        direction: str,
        frame,
        face_bbox,
        policy: GatePolicy,
        now_ts: float,
    ) -> Dict[str, Any]:
        if direction != "ENTRY" or (policy.enforce_stage or "ENTRY_ONLY") != "ENTRY_ONLY":
            self._clear_ppe_history()
            return normalize_ppe_details(
                {
                    "status": "skipped",
                    "required_items": [],
                    "detected_items": [],
                    "missing_items": [],
                    "detector_confidences": {},
                    "detector_available": ppe_detector.available,
                    "detector_message": None,
                }
            )

        details = ppe_detector.analyze_subject(
            frame,
            face_bbox,
            get_required_ppe_items(policy),
        )
        details = self._smooth_ppe_status(
            person_id=person_id,
            raw_details=details,
            now_ts=now_ts,
        )
        if details.get("status") == "unavailable":
            details["detector_message"] = (
                details.get("detector_message")
                or "PPE detector is unavailable. Face recognition remains active."
            )
        return details

    def _build_review_reasons(
        self,
        *,
        review_band_match: bool,
        ppe_details: Dict[str, Any],
        person: Optional[Person] = None,
        direction: Optional[str] = None,
        ambiguous_match: bool = False,
    ) -> List[str]:
        reasons: List[str] = []
        # Both can be true at once, and both must be recorded: a match that is
        # in the review band AND too close to another worker is two separate
        # things for the operator to weigh, and dropping either one loses the
        # override reason stamped on the permanent record.
        if review_band_match:
            reasons.append("face_confidence")
        if ambiguous_match:
            reasons.append("ambiguous_match")

        ppe_status = ppe_details.get("status")
        if ppe_status == "uncertain":
            reasons.append("uncertain_ppe")
        elif ppe_status == "non_compliant":
            for missing_item in ppe_details.get("missing_items") or []:
                reason = f"missing_{str(missing_item).replace(' ', '_')}"
                if reason not in reasons:
                    reasons.append(reason)

        # Flag entries that happen outside the worker's scheduled shift.
        # Only applies on ENTRY — exits can be any time.
        if (
            direction == "ENTRY"
            and person is not None
            and getattr(person, "shift_id", None)
            and not is_within_shift(person.shift_id)
        ):
            reasons.append(f"off_shift_{person.shift_id}")

        return reasons

    def _should_block_for_ppe(
        self,
        *,
        direction: str,
        policy: GatePolicy,
        ppe_details: Dict[str, Any],
    ) -> bool:
        if direction != "ENTRY" or not policy.deny_non_compliant_entry:
            return False
        # Block on non-compliant, uncertain, OR unavailable — if enforce mode is
        # active the detector must be able to confirm compliance; an unavailable
        # detector is not a free pass.
        return ppe_details.get("status") in {"non_compliant", "uncertain", "unavailable"}

    def _log_unknown_face_attempt(
        self,
        *,
        direction: str,
        confidence: float,
        now_ts: float,
    ) -> bool:
        """Record an unrecognised face at the gate, at most once per cooldown.

        An unknown face used to leave nothing behind at all: the overlay said
        "Unknown face", the gate refused, and afterwards there was no way to
        tell whether one person had tried once or fifty times. This writes a
        gate-domain Event instead of the pending GateReview the earlier
        version of this method created (that flooded the operator's queue with
        phantom "Unknown" sessions, which is why it was abandoned unused).

        No snapshot is stored. The person is by definition not enrolled, so
        keeping their photo would collect biometric data on someone who never
        consented to it; the time, the direction and the best score are the
        security-relevant facts.

        Returns True when an Event was written.
        """
        if now_ts - self.last_unknown_attempt_logged_at < self.unknown_attempt_cooldown_seconds:
            return False
        self.last_unknown_attempt_logged_at = now_ts

        message = (
            f"Unrecognised face at the gate ({direction.lower()} mode); "
            f"best match {self._get_match_percent(confidence)}%, below the "
            f"{self.review_percent}% review threshold."
        )
        db = SessionLocal()
        try:
            create_event_record(
                db,
                category="GATE",
                event_type="unknown_face",
                severity="WARNING",
                message=message,
                data={
                    "message": message,
                    "direction": direction,
                    "best_score": round(float(confidence), 4),
                    "review_threshold": self.review_threshold,
                    "cooldown_seconds": self.unknown_attempt_cooldown_seconds,
                },
                is_resolved=False,
            )
            db.commit()
            return True
        except Exception:
            logger.exception("Failed to record an unknown-face gate attempt.")
            db.rollback()
            return False
        finally:
            db.close()

    def _log_attendance(
        self,
        person: Person,
        direction: str,
        confidence: float,
        timestamp: datetime,
        *,
        ppe_compliant: bool,
        ppe_details: Optional[Dict[str, Any]] = None,
        frame=None,
    ) -> Attendance:
        db = SessionLocal()
        try:
            try:
                from app.camera.manager import camera_manager

                camera_source_type = camera_manager.source_type or None
                camera_source_id = camera_manager.source_id or None
            except Exception:
                camera_source_type = None
                camera_source_id = None

            record = Attendance(
                person_id=person.id,
                person_name=person.name,
                direction=direction,
                ppe_compliant=ppe_compliant,
                access_granted=True,
                confidence=confidence,
                timestamp=timestamp,
                ppe_details=serialize_ppe_details(ppe_details),
                camera_source_type=camera_source_type,
                camera_source_id=camera_source_id,
                log_method="AUTO",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            self.on_site_cache_ids = set()
            self.on_site_cache_loaded_at = 0.0

            # Capture and save an audit snapshot for this attendance event
            if frame is not None:
                try:
                    snapshot = self._encode_snapshot(frame)
                    if snapshot:
                        image_bytes, mime_type = snapshot
                        snapshot_path = write_attendance_snapshot(record.id, image_bytes, mime_type)
                        record.snapshot_path = snapshot_path
                        db.commit()
                except Exception:
                    pass  # Snapshot failure must never block attendance logging

            self._record_ppe_pass_event(
                db=db,
                person=person,
                direction=direction,
                attendance=record,
                ppe_details=ppe_details,
            )
            db.commit()

            return record
        finally:
            db.close()

    def _record_ppe_pass_event(
        self,
        *,
        db: Session,
        person: Person,
        direction: str,
        attendance: Attendance,
        ppe_details: Optional[Dict[str, Any]],
    ) -> None:
        details = normalize_ppe_details(ppe_details)
        required_items = details.get("required_items") or []
        if direction != "ENTRY" or not required_items or details.get("status") != "compliant":
            return

        create_event_record(
            db,
            category="PPE",
            event_type="PPE_ENTRY_OK",
            severity="INFO",
            message=f"{person.name} cleared the PPE check.",
            data={
                "message": f"{person.name} cleared the PPE check.",
                "person_id": person.id,
                "person_name": person.name,
                "attendance_id": attendance.id,
                "direction": direction,
                "timestamp": attendance.timestamp.isoformat() if attendance.timestamp else None,
                "required_items": details.get("required_items") or [],
                "detected_items": details.get("detected_items") or [],
                "latched_items": details.get("latched_items") or [],
                "ppe_details": details,
            },
            snapshot_path=attendance.snapshot_path,
            is_resolved=True,
        )

    def _encode_snapshot(self, frame) -> Optional[Tuple[bytes, str]]:
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 72],
        )
        if not ok:
            return None
        return encoded.tobytes(), "image/jpeg"

    @staticmethod
    def _compute_yaw_offset(face: Dict[str, Any]) -> Optional[float]:
        """Estimate how much the face is turned away from the camera.

        Uses InsightFace's 106-point landmark mean-x relative to the face
        bbox centre. When the subject looks straight at the camera the
        landmark centroid sits near the bbox centre; when they turn their
        head, the centroid skews toward the visible side. Value is
        normalised to the bbox width so it's resolution-independent.

        Returns a float in [0, ~0.5], or None if landmarks are unavailable.
        0.0 = perfectly frontal. ~0.2+ = noticeable yaw.
        """
        landmarks = face.get("landmark_2d_106")
        bbox = face.get("bbox")
        if landmarks is None or bbox is None:
            return None
        try:
            xs = [float(pt[0]) for pt in landmarks]
            if not xs:
                return None
            mean_x = sum(xs) / len(xs)
            x1, _y1, x2, _y2 = bbox
            width = max(float(x2) - float(x1), 1.0)
            centre_x = (float(x1) + float(x2)) / 2.0
            return abs(mean_x - centre_x) / width
        except Exception:
            return None

    def _clear_active_review(self) -> None:
        self.active_review_person_id = None
        self.active_review_id = None
        self.active_review_last_seen_at = 0.0

    def _clear_resolved_review(self) -> None:
        self.resolved_review_person_id = None
        self.resolved_review_decision = None
        self.resolved_review_last_seen_at = 0.0

    def resolve_review(self, person_id: Optional[str], approved: bool) -> None:
        self._clear_active_review()
        self._clear_ppe_history()
        if person_id:
            self.resolved_review_person_id = person_id
            self.resolved_review_decision = "APPROVED" if approved else "DENIED"
            self.resolved_review_last_seen_at = time.time()
            if approved:
                self.active_match_person_id = person_id
                self.active_match_last_seen_at = self.resolved_review_last_seen_at

    def _dismiss_pending_reviews(self, reason: str, person_id: Optional[str] = None) -> None:
        db = SessionLocal()
        try:
            query = db.query(GateReview).filter(GateReview.status == "PENDING")
            if person_id:
                query = query.filter(GateReview.person_id == person_id)

            pending_reviews = query.all()
            if not pending_reviews:
                return

            now = datetime.utcnow()
            for review in pending_reviews:
                review.status = "CANCELLED"
                review.decided_at = now
                review.decided_by = "system"
                review.decision_note = reason
            db.commit()
        finally:
            db.close()

    def reset_live_session(self, clear_pending_reviews: bool = False, reason: Optional[str] = None) -> None:
        if clear_pending_reviews:
            self._dismiss_pending_reviews(reason or "Live gate session ended before operator review.")
        self.last_candidate_person_id = None
        self.last_candidate_streak = 0
        self.last_match_state_seen_at = 0.0
        self.unknown_face_streak = 0
        self.active_match_person_id = None
        self.active_match_last_seen_at = 0.0
        self._clear_active_review()
        self._clear_resolved_review()
        self._clear_ppe_history()
        self._clear_overlay()
        self.gate_state = self._build_gate_state(
            match_status="idle",
            message="Waiting for gate recognition.",
        )

    def _mark_pending_reviews_superseded(self, person_id: str) -> None:
        db = SessionLocal()
        try:
            pending_reviews = (
                db.query(GateReview)
                .filter(
                    GateReview.person_id == person_id,
                    GateReview.status == "PENDING",
                )
                .all()
            )
            if not pending_reviews:
                return

            now = datetime.utcnow()
            for review in pending_reviews:
                review.status = "SUPERSEDED"
                review.decided_at = now
                review.decided_by = "system"
                review.decision_note = "Superseded by a higher-confidence auto match."
            db.commit()
        finally:
            db.close()

    def _create_or_get_pending_review(
        self,
        *,
        person: Person,
        direction: str,
        confidence: float,
        timestamp: datetime,
        frame,
        review_reasons: List[str],
        ppe_details: Dict[str, Any],
    ) -> Tuple[GateReview, bool]:
        db = SessionLocal()
        try:
            existing_review = (
                db.query(GateReview)
                .filter(
                    GateReview.person_id == person.id,
                    GateReview.status == "PENDING",
                )
                .order_by(GateReview.timestamp.desc())
                .first()
            )
            if existing_review:
                next_confidence = max(existing_review.confidence or 0.0, confidence)
                next_review_reasons = normalize_review_reasons(review_reasons)
                next_ppe_details = normalize_ppe_details(ppe_details)
                should_update = (
                    next_confidence != (existing_review.confidence or 0.0)
                    or normalize_review_reasons(existing_review.review_reasons) != next_review_reasons
                    or normalize_ppe_details(existing_review.ppe_details) != next_ppe_details
                )
                if should_update:
                    existing_review.confidence = next_confidence
                    existing_review.review_reasons = serialize_review_reasons(next_review_reasons)
                    existing_review.ppe_details = serialize_ppe_details(next_ppe_details)
                    db.commit()
                    db.refresh(existing_review)
                return existing_review, False

            review = GateReview(
                person_id=person.id,
                person_name=person.name,
                suggested_direction=direction,
                confidence=confidence,
                timestamp=timestamp,
                status="PENDING",
                review_reasons=serialize_review_reasons(review_reasons),
                ppe_details=serialize_ppe_details(ppe_details),
            )
            db.add(review)
            db.flush()

            snapshot = self._encode_snapshot(frame)
            if snapshot is not None:
                image_bytes, mime_type = snapshot
                review.snapshot_path = write_attendance_snapshot(
                    review.id,
                    image_bytes,
                    mime_type,
                )

            db.commit()
            db.refresh(review)
            return review, True
        finally:
            db.close()

    def _record_ppe_incident(
        self,
        *,
        person: Person,
        direction: str,
        review: GateReview,
        review_reasons: List[str],
        ppe_details: Dict[str, Any],
    ) -> None:
        if not any(
            reason == "uncertain_ppe" or reason.startswith("missing_")
            for reason in review_reasons
        ):
            return

        db = SessionLocal()
        try:
            reason_messages = ppe_reason_messages(review_reasons)
            event = create_event_record(
                db,
                category="PPE",
                event_type="PPE_ENTRY_BLOCKED",
                severity="ALERT"
                if ppe_details.get("status") == "non_compliant"
                else "WARNING",
                message=f"{person.name} was held at the gate for PPE review.",
                data={
                    "message": f"{person.name} was held at the gate for PPE review.",
                    "person_id": person.id,
                    "person_name": person.name,
                    "direction": direction,
                    "review_id": review.id,
                    "review_reasons": review_reasons,
                    "reason_messages": reason_messages,
                    "ppe_details": ppe_details,
                },
                snapshot_path=review.snapshot_path,
                is_resolved=False,
            )
            create_alert_record(
                db,
                event=event,
                severity=event.severity,
                title=f"PPE gate review for {person.name}",
                message=" ".join(reason_messages) or "PPE review required.",
                is_active=True,
            )
            db.commit()
        finally:
            db.close()

    def _get_current_shift_window(self, now: datetime) -> Tuple[str, datetime]:
        day_start = now.replace(hour=6, minute=0, second=0, microsecond=0)
        swing_start = now.replace(hour=14, minute=0, second=0, microsecond=0)
        night_start = now.replace(hour=22, minute=0, second=0, microsecond=0)

        if day_start <= now < swing_start:
            return "day", day_start
        if swing_start <= now < night_start:
            return "swing", swing_start
        if now >= night_start:
            return "night", night_start
        return "night", (day_start - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)

    def _get_last_attendance_in_shift(
        self,
        person_id: str,
        shift_started_at: datetime,
    ) -> Optional[Attendance]:
        db = SessionLocal()
        try:
            return (
                db.query(Attendance)
                .filter(
                    Attendance.person_id == person_id,
                    Attendance.timestamp >= shift_started_at,
                )
                .order_by(Attendance.timestamp.desc())
                .first()
            )
        finally:
            db.close()

    def _get_latest_attendance(self, person_id: str) -> Optional[Attendance]:
        db = SessionLocal()
        try:
            return (
                db.query(Attendance)
                .filter(Attendance.person_id == person_id)
                .order_by(Attendance.timestamp.desc())
                .first()
            )
        finally:
            db.close()

    def _plan_attendance_action(
        self,
        person: Person,
        now: datetime,
    ) -> Tuple[Optional[str], str]:
        """Decide whether the current face match should log ENTRY, EXIT, or
        nothing at all.

        The `min_direction_gap_seconds` debounce is only applied when the
        prospective action would be the SAME direction as the person's most
        recent record. Cross-direction transitions (e.g. they just checked in
        and now are checking out) must NOT be blocked by the debounce —
        otherwise a demo walk-in-walk-out cycle eats the checkout silently
        and leaves the gate "just keeps scanning" with no log written.
        """
        shift_id, shift_started_at = self._get_current_shift_window(now)
        last_record = self._get_last_attendance_in_shift(person.id, shift_started_at)

        if self.gate_direction_mode == "EXIT":
            latest_record = self._get_latest_attendance(person.id)
            if latest_record is None:
                return None, f"{person.name} is not currently on site."

            if latest_record.direction == "EXIT" or not latest_record.access_granted:
                # Only debounce a *second* EXIT within the gap window; if the
                # person genuinely isn't on site we always say so regardless
                # of time gap.
                latest_timestamp = latest_record.timestamp or now
                if (now - latest_timestamp).total_seconds() < self.min_direction_gap_seconds:
                    return None, f"{person.name} was just checked out."
                return None, f"{person.name} is already checked out."

            # Last record is an ENTRY — legitimate checkout. No debounce
            # across direction transitions; the check above already guarantees
            # we're not repeating an EXIT.
            return "EXIT", f"{person.name} checked out from the site."

        # ENTRY path
        if last_record is None:
            return "ENTRY", f"{person.name} checked in during the {shift_id} shift."

        if last_record.direction == "ENTRY":
            # Same-direction debounce: only block a duplicate ENTRY if it
            # lands within the gap window.
            last_timestamp = last_record.timestamp or now
            if (now - last_timestamp).total_seconds() < self.min_direction_gap_seconds:
                return None, (
                    f"{person.name} is already checked in."
                )
            return None, f"{person.name} is already checked in."

        # Last was EXIT within this shift — allow re-entry.
        return "ENTRY", f"{person.name} checked in during the {shift_id} shift."

    def _draw_match_box(self, frame, bbox, label, color):
        frame_height, frame_width = frame.shape[:2]
        x1, y1, x2, y2 = [int(value) for value in bbox]
        x1 = max(0, min(frame_width - 2, x1))
        y1 = max(0, min(frame_height - 2, y1))
        x2 = max(x1 + 2, min(frame_width - 1, x2))
        y2 = max(y1 + 2, min(frame_height - 1, y2))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        cv2.rectangle(frame, (x1, max(0, y1 - 30)), (x2, y1), color, -1)
        cv2.putText(
            frame,
            label,
            (x1 + 6, max(18, y1 - 9)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    def _set_overlay(self, bbox, label: str, color, now_ts: float, hold_seconds: Optional[float] = None) -> None:
        self.last_overlay_bbox = [float(value) for value in bbox]
        self.last_overlay_label = label
        self.last_overlay_color = color
        self.last_overlay_seen_at = now_ts
        self.last_overlay_hold_seconds = hold_seconds or self.overlay_hold_seconds

    def _clear_overlay(self) -> None:
        self.last_overlay_bbox = None
        self.last_overlay_label = ""
        self.last_overlay_hold_seconds = self.overlay_hold_seconds

    def _has_recent_match_state(self, now_ts: float) -> bool:
        return (
            self.gate_state.get("match_status") in {
                "matching",
                "confirmed_match",
                "review_required",
                "possible_match",
                "unknown_face",
            }
            and now_ts - self.last_match_state_seen_at <= self.recent_match_hold_seconds
        )

    def _has_recent_overlay(self, now_ts: float) -> bool:
        return (
            self.last_overlay_bbox is not None
            and now_ts - self.last_overlay_seen_at <= self.last_overlay_hold_seconds
        )

    def _prepare_analysis_frame(self, frame):
        height, width = frame.shape[:2]
        if width <= self.analysis_max_width:
            return frame, 1.0, 1.0

        scale = self.analysis_max_width / float(width)
        resized = cv2.resize(
            frame,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        return resized, width / resized.shape[1], height / resized.shape[0]

    def _scale_bbox(self, bbox, scale_x: float, scale_y: float):
        return [
            float(bbox[0] * scale_x),
            float(bbox[1] * scale_y),
            float(bbox[2] * scale_x),
            float(bbox[3] * scale_y),
        ]

    def _ensure_live_detector(self):
        """Return a MediaPipe face detector used for live bbox tracking.

        Much cheaper than InsightFace (~3-5ms per frame) so we can run it on
        every preview frame to keep the overlay glued to the face. Identity +
        similarity percentage still come from the ArcFace run in the gate
        processing thread; this detector only supplies live coordinates.
        """
        if self._live_detector is not None or self._live_detector_failed:
            return self._live_detector
        try:
            import mediapipe as mp
            # Lower confidence → fewer missed detections on motion / off-angle
            # frames, so the square doesn't blink. False positives aren't a
            # concern: we only use the bbox, identity still comes from
            # ArcFace.
            self._live_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.25,
            )
        except Exception:
            logger.exception("Gate live face detector init failed.")
            self._live_detector_failed = True
        return self._live_detector

    def _detect_live_bbox(self, frame) -> Optional[List[float]]:
        """Return (bbox, mediapipe_confidence) for the largest detected face.

        Stored together in self._last_live_bbox_confidence so the overlay can
        show a live "Detected XX%" tag before ArcFace completes its first
        recognition pass.
        """
        detector = self._ensure_live_detector()
        if detector is None or frame is None:
            return None
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = detector.process(rgb)
        except Exception:
            logger.exception("Gate live face detection failed.")
            return None
        detections = getattr(results, "detections", None) or []
        if not detections:
            return None
        h, w = frame.shape[:2]
        best = max(
            detections,
            key=lambda d: d.location_data.relative_bounding_box.width
            * d.location_data.relative_bounding_box.height,
        )
        box = best.location_data.relative_bounding_box
        x1 = max(0.0, box.xmin * w)
        y1 = max(0.0, box.ymin * h)
        x2 = min(float(w), (box.xmin + box.width) * w)
        y2 = min(float(h), (box.ymin + box.height) * h)
        if x2 <= x1 or y2 <= y1:
            return None
        # MediaPipe exposes detection confidence via `score` (a list with one
        # float). Default to 0 if absent so the overlay still shows a bbox.
        score_list = getattr(best, "score", None) or [0.0]
        try:
            self._last_live_bbox_confidence = float(score_list[0])
        except Exception:
            self._last_live_bbox_confidence = 0.0
        return [float(x1), float(y1), float(x2), float(y2)]

    def _smoothed_live_bbox(self, frame) -> Optional[List[float]]:
        """Return the live bbox with a tiny temporal smoothing window.

        MediaPipe occasionally drops a detection on a single frame (motion
        blur, eyes closed, sharp turn). Without smoothing this shows up as
        a 50-150ms gap where the square vanishes — the "flicker" the user
        sees. We keep the most recent bbox for up to _live_bbox_persist_s
        (≈150ms) to cover single-frame misses, then fall back to nothing.
        This is not a "hold" — if the face is gone for longer the square
        disappears. Position still tracks live on every frame that does
        detect.
        """
        now_ts = time.time()
        detected = self._detect_live_bbox(frame)
        if detected is not None:
            # Slight exponential smoothing on position so small MediaPipe
            # jitter between frames doesn't look jerky.
            if (
                self._last_live_bbox is not None
                and now_ts - self._last_live_bbox_at <= self._live_bbox_persist_s
            ):
                alpha = 0.55  # heavier weight on the new reading
                detected = [
                    alpha * detected[i] + (1 - alpha) * self._last_live_bbox[i]
                    for i in range(4)
                ]
            self._last_live_bbox = detected
            self._last_live_bbox_at = now_ts
            return detected
        # Carry the last bbox for a very short window to cover single-frame
        # MediaPipe misses without freezing.
        if (
            self._last_live_bbox is not None
            and now_ts - self._last_live_bbox_at <= self._live_bbox_persist_s
        ):
            return self._last_live_bbox
        self._last_live_bbox = None
        return None

    def draw_live_overlay(self, frame):
        """Render the gate overlay using a live bbox on every preview frame.

        The bbox is detected fresh each call (with tiny smoothing to hide
        single-frame MediaPipe misses); the label + similarity percentage
        reuse the most recent ArcFace recognition result so the percentage
        updates as fast as the gate processing thread produces it. When the
        face is truly gone (>150ms without any detection), nothing is drawn.
        """
        live_bbox = self._smoothed_live_bbox(frame)
        if live_bbox is None:
            return frame

        now_ts = time.time()
        label_age = now_ts - self.last_overlay_seen_at

        # Treat a label as a "named match" if it ends in "NN%" — that's the
        # format ArcFace produces ("Christo 92%", "Unknown face", etc). Named
        # matches get an extended hold so an ArcFace skip doesn't flicker the
        # label back to the MediaPipe "Detected XX%" tag. Generic overlay
        # labels (no trailing percentage) still clear at overlay_hold_seconds.
        def _looks_like_named_match(s: str) -> bool:
            if not s:
                return False
            stripped = s.rstrip()
            if not stripped.endswith("%"):
                return False
            # Grab the digits before the trailing "%" to confirm.
            tail = stripped[:-1].rstrip()
            last_token = tail.split()[-1] if tail.split() else ""
            return last_token.isdigit()

        is_named = _looks_like_named_match(self.last_overlay_label)
        effective_hold = (
            max(self.last_overlay_hold_seconds, self.named_match_hold_seconds)
            if is_named
            else self.last_overlay_hold_seconds
        )

        if self.last_overlay_label and label_age <= effective_hold:
            # ArcFace has produced a recent match label (e.g. "John Doe 92%").
            label = self.last_overlay_label
            color = self.last_overlay_color
        else:
            # No fresh ArcFace result yet — show MediaPipe detection confidence
            # so the operator sees a live percentage next to the face box
            # instead of a generic "Analyzing…" with no feedback.
            confidence_pct = int(round(self._last_live_bbox_confidence * 100))
            confidence_pct = max(0, min(100, confidence_pct))
            if confidence_pct > 0:
                label = f"Detected {confidence_pct}%"
            else:
                label = "Detecting…"
            color = (148, 163, 184)

        self._draw_match_box(frame, live_bbox, label, color)
        return frame

    def process_frame(self, frame, direction_hint: Optional[str] = None):
        events: List[GateRecognitionEvent] = []
        now_ts = time.time()

        if not face_recognizer.available:
            self.gate_state = self._build_gate_state(
                match_status="recognizer_unavailable",
                message="InsightFace is not available.",
                last_seen_at=now_ts,
                overlay_tone="warning",
            )
            self._clear_overlay()
            return frame, events

        enrolled_people = self._load_enrolled_people()
        if not enrolled_people:
            self.gate_state = self._build_gate_state(
                match_status="no_enrolled_people",
                message="No enrolled workers with embeddings yet.",
                last_seen_at=now_ts,
                overlay_tone="warning",
            )
            self._clear_overlay()
            return frame, events

        analysis_frame, scale_x, scale_y = self._prepare_analysis_frame(frame)
        detected_faces = []
        for face in face_recognizer.analyze_faces(analysis_frame):
            # Compute yaw in ANALYSIS-frame coords where the bbox and
            # landmark_2d_106 landmarks still share a coordinate space.
            # Mixing analysis-scale landmarks with the upscaled bbox gave a
            # bogus centroid-vs-centre delta and made the gate permanently
            # report "face is turned".
            yaw_offset = self._compute_yaw_offset(face)
            detected_faces.append(
                {
                    **face,
                    "bbox": self._scale_bbox(face["bbox"], scale_x, scale_y),
                    "_precomputed_yaw": yaw_offset,
                }
            )
        if not detected_faces:
            if (
                self.active_match_person_id is not None
                and now_ts - self.active_match_last_seen_at >= self.rearm_after_absence_seconds
            ):
                self.active_match_person_id = None
            if (
                self.active_review_person_id is not None
                and now_ts - self.active_review_last_seen_at >= self.rearm_after_absence_seconds
            ):
                self._clear_active_review()
            if (
                self.resolved_review_person_id is not None
                and now_ts - self.resolved_review_last_seen_at >= self.rearm_after_absence_seconds
            ):
                self._clear_resolved_review()
            if self._has_recent_overlay(now_ts):
                self.gate_state = {
                    **self.gate_state,
                    "last_seen_at": now_ts,
                    "faces_detected": 0,
                    "message": "Holding the last face box while the camera reacquires the worker.",
                }
                return frame, events
            held_ppe_details = self._get_live_ppe_details(now_ts)
            if not self._has_live_ppe_session(now_ts):
                self._clear_ppe_history()
            self._clear_overlay()
            self.last_candidate_person_id = None
            self.last_candidate_streak = 0
            self.unknown_face_streak = 0
            self.gate_state = self._build_gate_state(
                match_status="no_face",
                message="No face detected.",
                last_seen_at=now_ts,
                faces_detected=0,
                ppe_details=held_ppe_details,
            )
            return frame, events

        # Score each detected face and filter out low-quality detections.
        # Yaw (face-turn) is computed from landmark symmetry so the gate
        # can ask the worker to face the camera directly instead of burning
        # a bad match on a side-profile embedding.
        scored_faces = []
        for face in detected_faces:
            blur = calculate_blur_score(frame, face["bbox"])
            area_ratio = calculate_face_area_ratio(frame, face["bbox"])
            det = float(face.get("det_score", 0.0))
            quality = calculate_quality_score(det, area_ratio, blur)
            yaw_offset = face.get("_precomputed_yaw")
            scored_faces.append({
                **face,
                "_blur": blur,
                "_area_ratio": area_ratio,
                "_det": det,
                "_quality": quality,
                "_yaw": yaw_offset,
            })

        # Categorise failures so the live overlay can give a targeted hint
        # ("move closer" vs "face the camera" vs "hold still").
        def _face_issue(f):
            if f["_det"] < self.min_det_score:
                return "unclear"
            if f["_area_ratio"] < self.min_face_area_ratio:
                return "too_far"
            if f["_blur"] < self.min_blur_score:
                return "blurry"
            if f["_yaw"] is not None and f["_yaw"] > self.max_yaw_offset:
                return "turned"
            return None

        passing_faces = [f for f in scored_faces if _face_issue(f) is None]

        if not passing_faces:
            # Pick the most prominent failing face to describe what's wrong.
            worst = max(scored_faces, key=lambda f: f["_area_ratio"])
            issue = _face_issue(worst) or "unclear"
            guidance = {
                "too_far": "Face is too far — move closer to the gate camera.",
                "blurry": "Motion blur detected — hold still and face the camera.",
                "turned": "Face is turned — look directly at the gate camera.",
                "unclear": "Face too unclear — move closer or face the camera directly.",
            }[issue]

            # Hold the last overlay briefly so the face box doesn't flicker on
            # every slightly-blurry frame — only clear if quality stays bad.
            if self._has_recent_overlay(now_ts):
                self.gate_state = {
                    **self.gate_state,
                    "last_seen_at": now_ts,
                    "faces_detected": len(detected_faces),
                    "message": guidance,
                }
                return frame, events
            self._clear_overlay()
            held_ppe_details = self._get_live_ppe_details(now_ts)
            if not self._has_live_ppe_session(now_ts):
                self._clear_ppe_history()
            self.gate_state = self._build_gate_state(
                match_status="low_quality_face",
                message=guidance,
                last_seen_at=now_ts,
                faces_detected=len(detected_faces),
                ppe_details=held_ppe_details,
            )
            return frame, events

        best_face = max(passing_faces, key=lambda f: f["_quality"])
        faces_detected = len(detected_faces)
        now_dt = datetime.now()
        policy = self._get_gate_policy()
        candidate_scope = "all_enrolled"
        on_site_ids: set[str] = set()
        overall_person, overall_score, _ = self._find_best_match(best_face["embedding"], enrolled_people)
        overall_percent = self._get_match_percent(overall_score)
        candidate_people = enrolled_people

        if self.gate_direction_mode == "EXIT":
            on_site_ids = self._get_on_site_person_ids(now_dt)
            candidate_people = [
                (person, vectors)
                for person, vectors in enrolled_people
                if person.id in on_site_ids
            ]
            candidate_scope = "checked_in_only"

            if not candidate_people:
                self._clear_ppe_history()
                self.last_match_state_seen_at = now_ts
                self.gate_state = self._build_gate_state(
                    match_status="no_checkout_candidates",
                    message="Exit mode is active, but no workers are currently on site.",
                    last_seen_at=now_ts,
                    faces_detected=faces_detected,
                    bbox=best_face["bbox"],
                    overlay_label="No workers on site",
                    overlay_tone="info",
                    candidate_scope=candidate_scope,
                )
                self._set_overlay(
                    best_face["bbox"],
                    "No workers on site",
                    (59, 130, 246),
                    now_ts,
                    hold_seconds=self.overlay_hold_seconds,
                )
                self._draw_match_box(frame, best_face["bbox"], "No workers on site", (59, 130, 246))
                return frame, events

            if (
                overall_person is not None
                and overall_person.id not in on_site_ids
                and self._match_band(overall_percent) != "below"
            ):
                self._clear_ppe_history()
                self.last_candidate_person_id = overall_person.id
                self.last_candidate_streak = 1
                self.last_match_state_seen_at = now_ts
                label = f"{overall_person.name} not on site"
                self.gate_state = self._build_gate_state(
                    match_status="not_checked_in",
                    person_id=overall_person.id,
                    person_name=overall_person.name,
                    confidence=overall_score,
                    last_seen_at=now_ts,
                    faces_detected=faces_detected,
                    message=(
                        f"{overall_person.name} is not currently checked in, "
                        "so exit cannot be approved yet."
                    ),
                    bbox=best_face["bbox"],
                    overlay_label=label,
                    overlay_tone="warning",
                    candidate_scope=candidate_scope,
                )
                self._set_overlay(
                    best_face["bbox"],
                    label,
                    (245, 158, 11),
                    now_ts,
                    hold_seconds=self.overlay_hold_seconds,
                )
                self._draw_match_box(frame, best_face["bbox"], label, (245, 158, 11))
                return frame, events

        person, score, runner_up_score = self._find_best_match(best_face["embedding"], candidate_people)
        match_percent = self._get_match_percent(score)

        if person is None or score < self.candidate_threshold:
            self.unknown_face_streak += 1
            if self._has_recent_overlay(now_ts) and self._has_recent_match_state(now_ts):
                self.gate_state = {
                    **self.gate_state,
                    "last_seen_at": now_ts,
                    "faces_detected": faces_detected,
                    "message": "Holding the last face box while the face angle stabilizes.",
                }
                return frame, events
            if self.unknown_face_streak < self.unknown_face_confirmations:
                return frame, events
            self.last_candidate_person_id = None
            self.last_candidate_streak = 0
            self.last_match_state_seen_at = now_ts
            self.gate_state = self._build_gate_state(
                match_status="unknown_face",
                message="Face detected but no enrolled worker matched.",
                confidence=score,
                last_seen_at=now_ts,
                faces_detected=faces_detected,
                bbox=best_face["bbox"],
                overlay_label="Unknown face",
                overlay_tone="warning",
                candidate_scope=candidate_scope,
            )
            self._set_overlay(
                best_face["bbox"],
                "Unknown face",
                (0, 165, 255),
                now_ts,
                hold_seconds=self.unknown_overlay_hold_seconds,
            )
            self._draw_match_box(frame, best_face["bbox"], "Unknown face", (0, 165, 255))

            # Still not a pending GateReview: those bloated the operator queue
            # with phantom "Unknown" sessions someone had to approve. A
            # gate-domain Event, debounced to one per cooldown, records that
            # somebody tried without adding work — and it is what makes the
            # assistant's "unknown attempts today" counter real.
            self._log_unknown_face_attempt(
                direction=self.gate_direction_mode,
                confidence=score,
                now_ts=now_ts,
            )

            return frame, events

        if self._match_band(match_percent) == "below":
            held_ppe_details = self._get_live_ppe_details(now_ts, person_id=person.id)
            self.unknown_face_streak = 0
            self.last_match_state_seen_at = now_ts
            # This frame did not clear the review threshold, so it is not
            # evidence and must not count toward the confirmation streak. It
            # used to claim the candidate and set the streak to 1, which meant
            # "three confirmations" could be satisfied by two qualifying frames
            # preceded by a weak one. It does not reset the streak either: a
            # single blurred frame should not throw away a run of good ones.
            label = f"{person.name} {match_percent}%"
            self.gate_state = self._build_gate_state(
                match_status="possible_match",
                person_id=person.id,
                person_name=person.name,
                confidence=score,
                last_seen_at=now_ts,
                faces_detected=faces_detected,
                message=(
                    f"Possible match: {person.name} at {match_percent}%. "
                    "Move closer to the camera or face it more directly."
                ),
                bbox=best_face["bbox"],
                overlay_label=label,
                overlay_tone="warning",
                candidate_scope=candidate_scope,
                ppe_details=held_ppe_details,
            )
            self._set_overlay(
                best_face["bbox"],
                label,
                (234, 179, 8),
                now_ts,
                hold_seconds=self.overlay_hold_seconds,
            )
            self._draw_match_box(frame, best_face["bbox"], label, (234, 179, 8))
            return frame, events

        self.unknown_face_streak = 0
        self.last_match_state_seen_at = now_ts
        entry_on_site_ids: set[str] = set()
        all_enrolled_on_site = False
        if self.gate_direction_mode == "ENTRY":
            entry_on_site_ids = self._get_on_site_person_ids(now_dt)
            all_enrolled_on_site = self._are_all_enrolled_workers_on_site(
                enrolled_people,
                entry_on_site_ids,
            )
            if all_enrolled_on_site:
                label = "All workers on site"
                self.gate_state = self._build_gate_state(
                    match_status="already_checked_in",
                    person_id=person.id,
                    person_name=person.name,
                    confidence=score,
                    last_seen_at=now_ts,
                    faces_detected=faces_detected,
                    message="All workers on site.",
                    bbox=best_face["bbox"],
                    overlay_label=label,
                    overlay_tone="info",
                    candidate_scope=candidate_scope,
                    ppe_details=self._get_live_ppe_details(now_ts, person_id=person.id),
                )
                self._set_overlay(
                    best_face["bbox"],
                    label,
                    (59, 130, 246),
                    now_ts,
                    hold_seconds=self.overlay_hold_seconds,
                )
                self._draw_match_box(frame, best_face["bbox"], label, (59, 130, 246))
                return frame, events
            if person.id in entry_on_site_ids:
                label = f"{person.name} checked in"
                self.gate_state = self._build_gate_state(
                    match_status="already_checked_in",
                    person_id=person.id,
                    person_name=person.name,
                    confidence=score,
                    last_seen_at=now_ts,
                    faces_detected=faces_detected,
                    message=f"{person.name} checked in.",
                    bbox=best_face["bbox"],
                    overlay_label=label,
                    overlay_tone="info",
                    candidate_scope=candidate_scope,
                    ppe_details=self._get_live_ppe_details(now_ts, person_id=person.id),
                )
                self._set_overlay(
                    best_face["bbox"],
                    label,
                    (59, 130, 246),
                    now_ts,
                    hold_seconds=self.overlay_hold_seconds,
                )
                self._draw_match_box(frame, best_face["bbox"], label, (59, 130, 246))
                return frame, events

        if self.last_candidate_person_id == person.id:
            self.last_candidate_streak += 1
        else:
            self.last_candidate_person_id = person.id
            self.last_candidate_streak = 1

        confirmed = self.last_candidate_streak >= self.required_confirmations
        ambiguous_match = self._is_ambiguous_match(score, runner_up_score)
        in_review_band = self._match_band(match_percent) == "review"
        # Either condition sends the decision to the operator, but they are
        # reported separately (see _build_review_reasons).
        review_band_match = in_review_band or ambiguous_match
        direction: Optional[str] = None
        details = f"{person.name} recognized at the gate."
        ppe_details = normalize_ppe_details({})
        review_reasons: List[str] = []
        ppe_blocked = False

        # --- LIVE PPE SCANNING ---
        # Run PPE detection on every frame the moment the face match is
        # plausible (>=79%, i.e. review band or higher), not only when the
        # match is fully confirmed. The operator sees helmet/vest status
        # updating live while the match is still being verified, and the
        # eventual check-in decision has fresh PPE data instead of a single
        # snapshot from the confirmation frame.
        required_items = get_required_ppe_items(policy)
        if (
            required_items
            and ppe_detector.available
            and self.gate_direction_mode == "ENTRY"
            and (policy.enforce_stage or "ENTRY_ONLY") == "ENTRY_ONLY"
        ):
            ppe_details = self._evaluate_ppe_for_candidate(
                person_id=person.id,
                direction="ENTRY",
                frame=frame,
                face_bbox=best_face["bbox"],
                policy=policy,
                now_ts=now_ts,
            )

        if confirmed:
            direction, details = self._plan_attendance_action(person, now_dt)
            if direction is not None:
                # Re-run only if the live scan above was skipped (e.g. EXIT
                # direction, or enforce_stage changed). Otherwise reuse the
                # already-scanned `ppe_details` so we don't pay double
                # inference cost.
                if not ppe_details.get("detected_items") and direction == "ENTRY":
                    ppe_details = self._evaluate_ppe_for_candidate(
                        person_id=person.id,
                        direction=direction,
                        frame=frame,
                        face_bbox=best_face["bbox"],
                        policy=policy,
                        now_ts=now_ts,
                    )
                review_reasons = self._build_review_reasons(
                    review_band_match=in_review_band,
                    ppe_details=ppe_details,
                    person=person,
                    direction=direction,
                    ambiguous_match=ambiguous_match,
                )
                ppe_blocked = self._should_block_for_ppe(
                    direction=direction,
                    policy=policy,
                    ppe_details=ppe_details,
                )

            if self.resolved_review_person_id == person.id and (
                review_band_match or ppe_blocked
            ):
                self.resolved_review_last_seen_at = now_ts
                approved = self.resolved_review_decision == "APPROVED"
                label = f"{person.name} {'approved' if approved else 'denied'}"
                self.gate_state = self._build_gate_state(
                    match_status="confirmed_match" if approved else "review_resolved",
                    person_id=person.id,
                    person_name=person.name,
                    confidence=score,
                    last_seen_at=now_ts,
                    faces_detected=faces_detected,
                    message=(
                        f"{person.name} was approved by the operator. Move away from the gate camera before the next scan."
                        if approved
                        else f"{person.name} was denied by the operator. Move away from the gate camera before rescanning."
                    ),
                    bbox=best_face["bbox"],
                    overlay_label=label,
                    overlay_tone="success" if approved else "warning",
                    candidate_scope=candidate_scope,
                    ppe_details=ppe_details,
                    review_reasons=review_reasons,
                )
                self._set_overlay(
                    best_face["bbox"],
                    label,
                    (34, 197, 94) if approved else (239, 68, 68),
                    now_ts,
                    hold_seconds=self.overlay_hold_seconds,
                )
                self._draw_match_box(
                    frame,
                    best_face["bbox"],
                    label,
                    (34, 197, 94) if approved else (239, 68, 68),
                )
                return frame, events

        needs_review = confirmed and (review_band_match or ppe_blocked)
        color = (
            (245, 158, 11)
            if needs_review
            else (34, 197, 94)
            if confirmed
            else (59, 130, 246)
        )
        label = (
            f"{person.name} review {match_percent}%"
            if needs_review
            else f"{person.name} {match_percent}%"
        )
        self.gate_state = self._build_gate_state(
            match_status=(
                "review_required"
                if needs_review
                else "confirmed_match"
                if confirmed
                else "matching"
            ),
            person_id=person.id,
            person_name=person.name,
            confidence=score,
            last_seen_at=now_ts,
            faces_detected=faces_detected,
            message=(
                (
                    f"{person.name} needs operator review for PPE and gate approval."
                    if ppe_blocked
                    else f"{person.name} needs operator review."
                )
                if needs_review
                else f"{person.name} recognized at the gate."
                if confirmed
                else f"Matching {person.name}..."
            ),
            bbox=best_face["bbox"],
            overlay_label=label,
            overlay_tone=(
                "warning"
                if needs_review
                else "success"
                if confirmed
                else "info"
            ),
            candidate_scope=candidate_scope,
            ppe_details=ppe_details,
            review_reasons=review_reasons,
        )
        self._set_overlay(best_face["bbox"], label, color, now_ts)
        self._draw_match_box(frame, best_face["bbox"], label, color)

        if confirmed:
            # Debounce: if this person is already our active match AND
            # _plan_attendance_action decided there's nothing new to log
            # (direction is None), short-circuit so we don't spam events.
            # BUT if direction is set (e.g. user just switched ENTRY→EXIT
            # and this is a legitimate checkout), fall through and let the
            # log path run — otherwise the checkout silently disappears
            # while the overlay just keeps scanning.
            if (
                not needs_review
                and self.active_match_person_id == person.id
                and direction is None
            ):
                self.active_match_last_seen_at = now_ts
                return frame, events
            if needs_review and self.active_review_person_id == person.id:
                if direction is not None:
                    review, _ = self._create_or_get_pending_review(
                        person=person,
                        direction=direction,
                        confidence=score,
                        timestamp=now_dt,
                        frame=frame,
                        review_reasons=review_reasons,
                        ppe_details=ppe_details,
                    )
                    self.active_review_id = review.id
                self.active_review_last_seen_at = now_ts
                self.gate_state["message"] = (
                    f"{person.name} is waiting for operator review. "
                    f"{self._summarize_ppe_details(ppe_details)}"
                    if ppe_blocked
                    else f"{person.name} is waiting for operator review."
                )
                return frame, events

            if not needs_review:
                self._mark_pending_reviews_superseded(person.id)
                self._clear_active_review()
                self.active_match_person_id = person.id
                self.active_match_last_seen_at = now_ts

            if direction is None:
                self.gate_state["message"] = details
                return frame, events

            if needs_review:
                review, created = self._create_or_get_pending_review(
                    person=person,
                    direction=direction,
                    confidence=score,
                    timestamp=now_dt,
                    frame=frame,
                    review_reasons=review_reasons,
                    ppe_details=ppe_details,
                )
                self.active_review_person_id = person.id
                self.active_review_id = review.id
                self.active_review_last_seen_at = now_ts
                self.gate_state["message"] = (
                    f"{person.name} matched at {match_percent}%. "
                    f"Waiting for operator approval. {self._summarize_ppe_details(ppe_details)}"
                    if ppe_blocked
                    else f"{person.name} matched at {match_percent}%. Waiting for operator approval."
                )
                if created:
                    if ppe_blocked:
                        self._record_ppe_incident(
                            person=person,
                            direction=direction,
                            review=review,
                            review_reasons=review_reasons,
                            ppe_details=ppe_details,
                        )
                    events.append(
                        GateRecognitionEvent(
                            event_type="attendance_review_required",
                            timestamp=now_ts,
                            confidence=score,
                            details=(
                                f"{person.name} matched at {match_percent}% and needs operator review."
                                if not ppe_blocked
                                else (
                                    f"{person.name} matched at {match_percent}% and "
                                    f"needs PPE review: {self._summarize_ppe_details(ppe_details)}"
                                )
                            ),
                            person_id=person.id,
                            person_name=person.name,
                            access_granted=False,
                            ppe_compliant=not ppe_blocked,
                            ppe_status=ppe_details.get("status") or "not_evaluated",
                            ppe_details=ppe_details,
                            review_reasons=review_reasons,
                        )
                    )
                return frame, events

            ppe_compliant = ppe_details.get("status") in {
                "compliant",
                "skipped",
                "not_evaluated",
            }
            self._log_attendance(
                person,
                direction,
                score,
                now_dt,
                ppe_compliant=ppe_compliant,
                ppe_details=ppe_details,
                frame=frame,
            )
            events.append(
                GateRecognitionEvent(
                    event_type="attendance_check_in" if direction == "ENTRY" else "attendance_check_out",
                    timestamp=now_ts,
                    confidence=score,
                    details=details,
                    person_id=person.id,
                    person_name=person.name,
                    access_granted=True,
                    ppe_compliant=ppe_compliant,
                    ppe_status=ppe_details.get("status") or "not_evaluated",
                    ppe_details=ppe_details,
                    review_reasons=review_reasons,
                )
            )
            self.gate_state["message"] = details

        return frame, events


gate_attendance_recognizer = GateAttendanceRecognizer()
