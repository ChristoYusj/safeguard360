"""
Live gate attendance recognition.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field
import time
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2

from app.config.settings import get_settings
from app.db.connection import SessionLocal
from app.db.models import Attendance, GatePolicy, GateReview, Person
from app.inference.face_recognizer import cosine_similarity, face_recognizer
from app.inference.ppe_detector import ppe_detector
from app.services.gate_compliance import (
    create_alert_record,
    create_event_record,
    get_or_create_gate_policy,
    get_required_ppe_items,
    normalize_ppe_details,
    normalize_review_reasons,
    ppe_reason_messages,
    serialize_ppe_details,
    serialize_review_reasons,
)
from app.services.persons import parse_embedding_payload, write_attendance_snapshot


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
        self.auto_pass_threshold = 0.85
        self.review_threshold = 0.79
        self.candidate_threshold = 0.45
        self.required_confirmations = 1
        self.min_direction_gap_seconds = 45.0
        self.rearm_after_absence_seconds = 2.5
        self.gate_direction_mode = "ENTRY"
        self.analysis_max_width = 384
        self.overlay_hold_seconds = 1.1
        self.unknown_overlay_hold_seconds = 0.75
        self.recent_match_hold_seconds = 1.1
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
        self.gate_state: Dict[str, object] = self._build_gate_state(
            match_status="idle",
            message="Waiting for gate recognition.",
        )

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
        best_person = None
        best_score = 0.0
        for person, vectors in enrolled_people:
            person_score = max(cosine_similarity(embedding, vector) for vector in vectors)
            if person_score > best_score:
                best_score = person_score
                best_person = person
        return best_person, best_score

    def _get_on_site_person_ids(self, now: datetime) -> set[str]:
        now_ts = time.time()
        if (
            self.on_site_cache_loaded_at > 0
            and now_ts - self.on_site_cache_loaded_at < self.on_site_cache_ttl_seconds
        ):
            return set(self.on_site_cache_ids)

        db = SessionLocal()
        try:
            records = (
                db.query(Attendance)
                .filter(
                    Attendance.person_id.isnot(None),
                )
                .order_by(Attendance.timestamp.desc())
                .all()
            )
            latest_by_person: Dict[str, Attendance] = {}
            for record in records:
                if not record.person_id or record.person_id in latest_by_person:
                    continue
                latest_by_person[record.person_id] = record

            on_site_ids = {
                person_id
                for person_id, record in latest_by_person.items()
                if record.access_granted and record.direction == "ENTRY"
            }
            self.on_site_cache_ids = on_site_ids
            self.on_site_cache_loaded_at = now_ts
            return set(on_site_ids)
        finally:
            db.close()

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

    def _summarize_ppe_details(self, details: Dict[str, Any]) -> str:
        missing_items = details.get("missing_items") or []
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
    ) -> Dict[str, Any]:
        details = normalize_ppe_details(raw_details)
        raw_status = details.get("status")
        if raw_status in {"skipped", "unavailable", "not_evaluated"}:
            self._clear_ppe_history()
            return details

        if self.active_ppe_person_id != person_id:
            self.active_ppe_person_id = person_id
            self.ppe_history.clear()

        self.ppe_history.append(deepcopy(details))
        status_counts = Counter(
            item.get("status")
            for item in self.ppe_history
            if item.get("status") in {"compliant", "non_compliant", "uncertain"}
        )

        final_status = raw_status
        if status_counts.get("non_compliant", 0) >= 2:
            final_status = "non_compliant"
        elif status_counts.get("compliant", 0) >= 2 and status_counts.get("non_compliant", 0) == 0:
            final_status = "compliant"
        elif status_counts.get("uncertain", 0) >= 2:
            final_status = "uncertain"
        elif len(self.ppe_history) >= 2 and raw_status != "compliant":
            final_status = "uncertain"

        details["status"] = final_status
        if final_status == "compliant":
            details["missing_items"] = []
            details["detector_message"] = "Required PPE detected."
        elif not details.get("detector_message"):
            details["detector_message"] = self._summarize_ppe_details(details)
        return details

    def _evaluate_ppe_for_candidate(
        self,
        *,
        person_id: str,
        direction: str,
        frame,
        face_bbox,
        policy: GatePolicy,
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
        details = self._smooth_ppe_status(person_id=person_id, raw_details=details)
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
    ) -> List[str]:
        reasons: List[str] = []
        if review_band_match:
            reasons.append("face_confidence")

        ppe_status = ppe_details.get("status")
        if ppe_status == "uncertain":
            reasons.append("uncertain_ppe")
        elif ppe_status == "non_compliant":
            for missing_item in ppe_details.get("missing_items") or []:
                reason = f"missing_{str(missing_item).replace(' ', '_')}"
                if reason not in reasons:
                    reasons.append(reason)

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
        return ppe_details.get("status") in {"non_compliant", "uncertain"}

    def _log_attendance(
        self,
        person: Person,
        direction: str,
        confidence: float,
        timestamp: datetime,
        *,
        ppe_compliant: bool,
        ppe_details: Optional[Dict[str, Any]] = None,
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
            return record
        finally:
            db.close()

    def _encode_snapshot(self, frame) -> Optional[Tuple[bytes, str]]:
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 72],
        )
        if not ok:
            return None
        return encoded.tobytes(), "image/jpeg"

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
                existing_review.confidence = max(existing_review.confidence or 0.0, confidence)
                existing_review.review_reasons = serialize_review_reasons(review_reasons)
                existing_review.ppe_details = serialize_ppe_details(ppe_details)
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
        shift_id, shift_started_at = self._get_current_shift_window(now)
        last_record = self._get_last_attendance_in_shift(person.id, shift_started_at)

        if last_record is not None:
            last_timestamp = last_record.timestamp or now
            if (now - last_timestamp).total_seconds() < self.min_direction_gap_seconds:
                return None, (
                    f"{person.name} was already logged recently during the {shift_id} shift."
                )

        if self.gate_direction_mode == "EXIT":
            latest_record = self._get_latest_attendance(person.id)
            if latest_record is None:
                return None, f"{person.name} is not currently on site."

            latest_timestamp = latest_record.timestamp or now
            if (now - latest_timestamp).total_seconds() < self.min_direction_gap_seconds:
                return None, f"{person.name} was already logged recently."

            if latest_record.direction == "EXIT" or not latest_record.access_granted:
                return None, f"{person.name} is already checked out."

            return "EXIT", f"{person.name} checked out from the site."

        if last_record is None:
            return "ENTRY", f"{person.name} checked in during the {shift_id} shift."

        if last_record.direction == "ENTRY":
            return None, f"{person.name} is already checked in for the {shift_id} shift."

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

    def draw_live_overlay(self, frame):
        if (
            self.last_overlay_bbox is not None
            and time.time() - self.last_overlay_seen_at <= self.last_overlay_hold_seconds
        ):
            self._draw_match_box(
                frame,
                self.last_overlay_bbox,
                self.last_overlay_label,
                self.last_overlay_color,
            )
        return frame

    def process_frame(self, frame):
        """Recognize a worker from the current frame and log attendance."""
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
        detected_faces = [
            {
                **face,
                "bbox": self._scale_bbox(face["bbox"], scale_x, scale_y),
            }
            for face in face_recognizer.analyze_faces(analysis_frame)
        ]
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
            self._clear_ppe_history()
            if self._has_recent_overlay(now_ts):
                self.gate_state = {
                    **self.gate_state,
                    "last_seen_at": now_ts,
                    "faces_detected": 0,
                    "message": "Holding the last face box while the camera reacquires the worker.",
                }
                return frame, events
            self._clear_overlay()
            self.last_candidate_person_id = None
            self.last_candidate_streak = 0
            self.unknown_face_streak = 0
            self.gate_state = self._build_gate_state(
                match_status="no_face",
                message="No face detected.",
                last_seen_at=now_ts,
                faces_detected=0,
            )
            return frame, events

        best_face = max(
            detected_faces,
            key=lambda face: (face["bbox"][2] - face["bbox"][0]) * (face["bbox"][3] - face["bbox"][1]),
        )
        faces_detected = len(detected_faces)
        now_dt = datetime.now()
        policy = self._get_gate_policy()
        candidate_scope = "all_enrolled"
        on_site_ids: set[str] = set()
        overall_person, overall_score = self._find_best_match(best_face["embedding"], enrolled_people)
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
                and overall_percent >= 79
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

        person, score = self._find_best_match(best_face["embedding"], candidate_people)
        match_percent = self._get_match_percent(score)

        if person is None or score < self.candidate_threshold:
            self._clear_ppe_history()
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
            return frame, events

        if match_percent < 79:
            self._clear_ppe_history()
            self.unknown_face_streak = 0
            self.last_match_state_seen_at = now_ts
            self.last_candidate_person_id = person.id
            self.last_candidate_streak = 1
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
        if self.last_candidate_person_id == person.id:
            self.last_candidate_streak += 1
        else:
            self.last_candidate_person_id = person.id
            self.last_candidate_streak = 1

        confirmed = self.last_candidate_streak >= self.required_confirmations
        review_band_match = 79 <= match_percent <= 84
        direction: Optional[str] = None
        details = f"{person.name} recognized at the gate."
        ppe_details = normalize_ppe_details({})
        review_reasons: List[str] = []
        ppe_blocked = False

        if confirmed:
            direction, details = self._plan_attendance_action(person, now_dt)
            if direction is not None:
                ppe_details = self._evaluate_ppe_for_candidate(
                    person_id=person.id,
                    direction=direction,
                    frame=frame,
                    face_bbox=best_face["bbox"],
                    policy=policy,
                )
                review_reasons = self._build_review_reasons(
                    review_band_match=review_band_match,
                    ppe_details=ppe_details,
                )
                ppe_blocked = self._should_block_for_ppe(
                    direction=direction,
                    policy=policy,
                    ppe_details=ppe_details,
                )
            else:
                self._clear_ppe_history()

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
            if not needs_review and self.active_match_person_id == person.id:
                self.active_match_last_seen_at = now_ts
                return frame, events
            if needs_review and self.active_review_person_id == person.id:
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
                "unavailable",
                "not_evaluated",
            }
            self._log_attendance(
                person,
                direction,
                score,
                now_dt,
                ppe_compliant=ppe_compliant,
                ppe_details=ppe_details,
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
