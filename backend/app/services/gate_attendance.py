"""
Live gate attendance recognition.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import cv2

from app.config.settings import get_settings
from app.db.connection import SessionLocal
from app.db.models import Attendance, GateReview, Person
from app.inference.face_recognizer import cosine_similarity, face_recognizer
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


class GateAttendanceRecognizer:
    """Recognize enrolled workers from the gate camera."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.auto_pass_threshold = 0.825
        self.review_threshold = 0.65
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
    ) -> Dict[str, object]:
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

    def _log_attendance(
        self,
        person: Person,
        direction: str,
        confidence: float,
        timestamp: datetime,
    ) -> Attendance:
        db = SessionLocal()
        try:
            record = Attendance(
                person_id=person.id,
                person_name=person.name,
                direction=direction,
                ppe_compliant=True,
                access_granted=True,
                confidence=confidence,
                timestamp=timestamp,
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

    def resolve_review(self, person_id: Optional[str], approved: bool) -> None:
        self._clear_active_review()
        if approved and person_id:
            self.active_match_person_id = person_id
            self.active_match_last_seen_at = time.time()

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
                db.refresh(existing_review)
                return existing_review, False

            review = GateReview(
                person_id=person.id,
                person_name=person.name,
                suggested_direction=direction,
                confidence=confidence,
                timestamp=timestamp,
                status="PENDING",
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
        candidate_scope = "all_enrolled"
        on_site_ids: set[str] = set()
        overall_person, overall_score = self._find_best_match(best_face["embedding"], enrolled_people)
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
                and overall_score >= self.review_threshold
            ):
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
            return frame, events

        if score < self.review_threshold:
            self.unknown_face_streak = 0
            self.last_match_state_seen_at = now_ts
            self.last_candidate_person_id = person.id
            self.last_candidate_streak = 1
            label = f"{person.name} {int(score * 100)}%"
            self.gate_state = self._build_gate_state(
                match_status="possible_match",
                person_id=person.id,
                person_name=person.name,
                confidence=score,
                last_seen_at=now_ts,
                faces_detected=faces_detected,
                message=(
                    f"Possible match: {person.name} at {int(score * 100)}%. "
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
        review_band_match = self.review_threshold <= score < self.auto_pass_threshold
        color = (
            (245, 158, 11)
            if review_band_match
            else (34, 197, 94)
            if confirmed
            else (59, 130, 246)
        )
        label = (
            f"{person.name} review {int(score * 100)}%"
            if review_band_match
            else f"{person.name} {int(score * 100)}%"
        )
        self.gate_state = self._build_gate_state(
            match_status=(
                "review_required"
                if confirmed and review_band_match
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
                f"{person.name} needs operator review."
                if confirmed and review_band_match
                else f"{person.name} recognized at the gate."
                if confirmed
                else f"Matching {person.name}..."
            ),
            bbox=best_face["bbox"],
            overlay_label=label,
            overlay_tone=(
                "warning"
                if review_band_match
                else "success"
                if confirmed
                else "info"
            ),
            candidate_scope=candidate_scope,
        )
        self._set_overlay(best_face["bbox"], label, color, now_ts)
        self._draw_match_box(frame, best_face["bbox"], label, color)

        if confirmed:
            if not review_band_match and self.active_match_person_id == person.id:
                self.active_match_last_seen_at = now_ts
                return frame, events
            if review_band_match and self.active_review_person_id == person.id:
                self.active_review_last_seen_at = now_ts
                self.gate_state["message"] = f"{person.name} is waiting for operator review."
                return frame, events

            if not review_band_match:
                self._mark_pending_reviews_superseded(person.id)
                self._clear_active_review()
                self.active_match_person_id = person.id
                self.active_match_last_seen_at = now_ts

            direction, details = self._plan_attendance_action(person, now_dt)

            if direction is None:
                self.gate_state["message"] = details
                return frame, events

            if review_band_match:
                review, created = self._create_or_get_pending_review(
                    person=person,
                    direction=direction,
                    confidence=score,
                    timestamp=now_dt,
                    frame=frame,
                )
                self.active_review_person_id = person.id
                self.active_review_id = review.id
                self.active_review_last_seen_at = now_ts
                self.gate_state["message"] = (
                    f"{person.name} matched at {int(score * 100)}%. Waiting for operator approval."
                )
                if created:
                    events.append(
                        GateRecognitionEvent(
                            event_type="attendance_review_required",
                            timestamp=now_ts,
                            confidence=score,
                            details=(
                                f"{person.name} matched at {int(score * 100)}% and needs operator review."
                            ),
                            person_id=person.id,
                            person_name=person.name,
                            access_granted=False,
                            ppe_compliant=True,
                        )
                    )
                return frame, events

            self._log_attendance(person, direction, score, now_dt)
            events.append(
                GateRecognitionEvent(
                    event_type="attendance_check_in" if direction == "ENTRY" else "attendance_check_out",
                    timestamp=now_ts,
                    confidence=score,
                    details=details,
                    person_id=person.id,
                    person_name=person.name,
                    access_granted=True,
                    ppe_compliant=True,
                )
            )
            self.gate_state["message"] = details

        return frame, events


gate_attendance_recognizer = GateAttendanceRecognizer()
