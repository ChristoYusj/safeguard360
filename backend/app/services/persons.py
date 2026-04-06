"""
Person enrollment helpers.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.db.models import Person
from app.inference.face_recognizer import cosine_similarity, face_recognizer

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FACES_DIR = BACKEND_ROOT / "data" / "faces"
ATTENDANCE_SNAPSHOTS_DIR = BACKEND_ROOT / "data" / "attendance"
TMP_DIR = BACKEND_ROOT / "data" / "tmp"
PERSON_PROFILE_FILENAME = "profile.json"


@dataclass
class EnrollmentSample:
    vector: List[float]
    image_bytes: bytes
    mime_type: str
    quality_score: float
    det_score: float
    blur_score: float
    face_area_ratio: float
    bbox: List[float]
    source_kind: str
    source_name: str
    frame_index: Optional[int] = None
    timestamp_ms: Optional[int] = None


def ensure_runtime_dirs() -> None:
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    ATTENDANCE_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def normalize_person_profile(profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = profile or {}
    shift_id = profile.get("shift_id")
    if shift_id not in {"day", "swing", "night"}:
        shift_id = None

    return {
        "shift_id": shift_id,
    }


def _get_person_dir(person_id: str) -> Path:
    return FACES_DIR / person_id


def read_person_profile(person_id: str) -> Dict[str, Any]:
    ensure_runtime_dirs()
    profile_path = _get_person_dir(person_id) / PERSON_PROFILE_FILENAME
    if not profile_path.exists():
        return normalize_person_profile()

    try:
        return normalize_person_profile(json.loads(profile_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return normalize_person_profile()


def write_person_profile(person_id: str, profile: Optional[Dict[str, Any]] = None) -> None:
    ensure_runtime_dirs()
    person_dir = _get_person_dir(person_id)
    person_dir.mkdir(parents=True, exist_ok=True)
    profile_path = person_dir / PERSON_PROFILE_FILENAME
    normalized_profile = normalize_person_profile(profile)
    profile_path.write_text(
        json.dumps(normalized_profile, indent=2),
        encoding="utf-8",
    )


def parse_image_data_url(data_url: str) -> Tuple[bytes, str]:
    """Decode a data URL into raw bytes and a MIME type."""
    if not data_url or "," not in data_url:
        raise ValueError("Expected a valid image data URL.")

    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("Image data URL must be base64-encoded.")

    mime_type = header.split(":", 1)[1].split(";", 1)[0]
    try:
        image_bytes = base64.b64decode(encoded)
    except Exception as exc:
        raise ValueError("Image data URL could not be decoded.") from exc

    return image_bytes, mime_type


def _suffix_from_mime_type(mime_type: str) -> str:
    suffix = mimetypes.guess_extension(mime_type) or ".png"
    return ".jpg" if suffix == ".jpe" else suffix


def decode_image_bytes(image_bytes: bytes):
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(image_array, cv2.IMREAD_COLOR)


def encode_frame_as_jpeg(frame) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise ValueError("Failed to encode enrollment frame.")
    return encoded.tobytes()


def calculate_blur_score(image_bgr, bbox: Sequence[float]) -> float:
    x1, y1, x2, y2 = [max(0, int(value)) for value in bbox]
    h, w = image_bgr.shape[:2]
    x2 = min(w, x2)
    y2 = min(h, y2)
    face_crop = image_bgr[y1:y2, x1:x2]
    if face_crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def calculate_face_area_ratio(image_bgr, bbox: Sequence[float]) -> float:
    h, w = image_bgr.shape[:2]
    frame_area = max(float(h * w), 1.0)
    x1, y1, x2, y2 = bbox
    face_area = max((x2 - x1) * (y2 - y1), 0.0)
    return float(face_area / frame_area)


def calculate_quality_score(det_score: float, face_area_ratio: float, blur_score: float) -> float:
    normalized_area = min(face_area_ratio / 0.16, 1.0)
    normalized_blur = min(blur_score / 260.0, 1.0)
    return float(det_score * 0.55 + normalized_area * 0.25 + normalized_blur * 0.20)


def create_sample_from_face(
    image_bgr,
    face: Dict[str, Any],
    source_kind: str,
    source_name: str,
    mime_type: str,
    image_bytes: bytes,
    frame_index: Optional[int] = None,
    timestamp_ms: Optional[int] = None,
) -> EnrollmentSample:
    bbox = face["bbox"]
    det_score = float(face.get("det_score", 0.0))
    blur_score = calculate_blur_score(image_bgr, bbox)
    face_area_ratio = calculate_face_area_ratio(image_bgr, bbox)
    quality_score = calculate_quality_score(det_score, face_area_ratio, blur_score)

    return EnrollmentSample(
        vector=face["embedding"].astype("float32").tolist(),
        image_bytes=image_bytes,
        mime_type=mime_type,
        quality_score=quality_score,
        det_score=det_score,
        blur_score=blur_score,
        face_area_ratio=face_area_ratio,
        bbox=[float(value) for value in bbox],
        source_kind=source_kind,
        source_name=source_name,
        frame_index=frame_index,
        timestamp_ms=timestamp_ms,
    )


def extract_samples_from_image_bytes(
    image_bytes: bytes,
    mime_type: str,
    source_name: str,
) -> List[EnrollmentSample]:
    image_bgr = decode_image_bytes(image_bytes)
    if image_bgr is None:
        return []

    faces = face_recognizer.analyze_faces(image_bgr)
    if not faces:
        return []

    best_face = max(
        faces,
        key=lambda face: (
            face.get("det_score", 0.0),
            calculate_face_area_ratio(image_bgr, face["bbox"]),
        ),
    )
    return [
        create_sample_from_face(
            image_bgr=image_bgr,
            face=best_face,
            source_kind="image",
            source_name=source_name,
            mime_type=mime_type,
            image_bytes=image_bytes,
        )
    ]


def extract_samples_from_video_bytes(
    video_bytes: bytes,
    mime_type: str,
    source_name: str,
    max_scanned_frames: int = 240,
) -> List[EnrollmentSample]:
    ensure_runtime_dirs()
    suffix = _suffix_from_mime_type(mime_type or "video/mp4")
    temp_path = None
    samples: List[EnrollmentSample] = []

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            dir=TMP_DIR,
            suffix=suffix or ".mp4",
        ) as handle:
            handle.write(video_bytes)
            temp_path = Path(handle.name)

        capture = cv2.VideoCapture(str(temp_path))
        if not capture.isOpened():
            return []

        fps = capture.get(cv2.CAP_PROP_FPS) or 12.0
        sample_step = max(int(round(fps / 2.0)), 5)
        frame_index = 0
        sampled_count = 0

        while frame_index < max_scanned_frames:
            ok, frame = capture.read()
            if not ok or frame is None:
                break

            if frame_index % sample_step == 0:
                faces = face_recognizer.analyze_faces(frame)
                if faces:
                    best_face = max(
                        faces,
                        key=lambda face: (
                            face.get("det_score", 0.0),
                            calculate_face_area_ratio(frame, face["bbox"]),
                        ),
                    )
                    samples.append(
                        create_sample_from_face(
                            image_bgr=frame,
                            face=best_face,
                            source_kind="video",
                            source_name=source_name,
                            mime_type="image/jpeg",
                            image_bytes=encode_frame_as_jpeg(frame),
                            frame_index=frame_index,
                            timestamp_ms=int((frame_index / max(fps, 1.0)) * 1000),
                        )
                    )
                    sampled_count += 1
                    if sampled_count >= 20:
                        break

            frame_index += 1

        capture.release()
        return samples
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def select_enrollment_samples(
    samples: Sequence[EnrollmentSample],
    max_samples: int = 8,
    duplicate_similarity_threshold: float = 0.985,
) -> List[EnrollmentSample]:
    sorted_samples = sorted(
        samples,
        key=lambda sample: (
            sample.quality_score,
            sample.det_score,
            sample.face_area_ratio,
            sample.blur_score,
        ),
        reverse=True,
    )

    selected: List[EnrollmentSample] = []
    for sample in sorted_samples:
        is_duplicate = any(
            cosine_similarity(sample.vector, existing.vector)
            >= duplicate_similarity_threshold
            for existing in selected
        )
        if is_duplicate:
            continue

        selected.append(sample)
        if len(selected) >= max_samples:
            break

    return selected


def reconstruct_samples_from_payload(raw_payload: Optional[str]) -> List[EnrollmentSample]:
    payload = parse_embedding_payload(raw_payload)
    vectors = payload.get("vectors") or []
    metadata_items = payload.get("samples") or []
    restored_samples: List[EnrollmentSample] = []

    for index, vector in enumerate(vectors):
        metadata = metadata_items[index] if index < len(metadata_items) else {}
        bbox = metadata.get("bbox") if isinstance(metadata, dict) else None
        normalized_bbox = (
            [float(value) for value in bbox[:4]]
            if isinstance(bbox, list) and len(bbox) >= 4
            else [0.0, 0.0, 0.0, 0.0]
        )

        restored_samples.append(
            EnrollmentSample(
                vector=[float(value) for value in vector],
                image_bytes=b"",
                mime_type="image/jpeg",
                quality_score=float(metadata.get("quality_score", 0.0)) if isinstance(metadata, dict) else 0.0,
                det_score=float(metadata.get("det_score", 0.0)) if isinstance(metadata, dict) else 0.0,
                blur_score=float(metadata.get("blur_score", 0.0)) if isinstance(metadata, dict) else 0.0,
                face_area_ratio=float(metadata.get("face_area_ratio", 0.0)) if isinstance(metadata, dict) else 0.0,
                bbox=normalized_bbox,
                source_kind=metadata.get("source_kind", "existing") if isinstance(metadata, dict) else "existing",
                source_name=metadata.get("source_name", f"existing-{index + 1}") if isinstance(metadata, dict) else f"existing-{index + 1}",
                frame_index=metadata.get("frame_index") if isinstance(metadata, dict) else None,
                timestamp_ms=metadata.get("timestamp_ms") if isinstance(metadata, dict) else None,
            )
        )

    return restored_samples


def build_embedding_payload_from_samples(
    selected_samples: Sequence[EnrollmentSample],
    total_samples_found: int,
    total_media_items: int,
    discarded_media: Sequence[str],
    selection_strategy: str = "quality+dedupe",
    message: Optional[str] = None,
    existing_sample_count: int = 0,
) -> Dict[str, Any]:
    if not selected_samples:
        return {
            "version": 2,
            "status": "no_face_detected",
            "provider": "insightface",
            "model": face_recognizer.describe()["model"],
            "message": "No usable face samples were found in the uploaded media.",
            "vectors": [],
            "sample_count": 0,
            "embedding_count": 0,
            "ready": False,
            "total_samples_found": total_samples_found,
            "total_media_items": total_media_items,
            "discarded_media": list(discarded_media),
            "selection_strategy": selection_strategy,
            "existing_sample_count": existing_sample_count,
            "samples": [],
        }

    return {
        "version": 2,
        "status": "ready",
        "provider": "insightface",
        "model": face_recognizer.describe()["model"],
        "message": message
        or (
            f"Stored {len(selected_samples)} representative enrollment views "
            f"from {total_media_items} uploaded media item(s)."
        ),
        "vectors": [sample.vector for sample in selected_samples],
        "sample_count": len(selected_samples),
        "embedding_count": len(selected_samples),
        "ready": True,
        "total_samples_found": total_samples_found,
        "total_media_items": total_media_items,
        "discarded_media": list(discarded_media),
        "selection_strategy": selection_strategy,
        "existing_sample_count": existing_sample_count,
        "samples": [
            {
                "quality_score": sample.quality_score,
                "det_score": sample.det_score,
                "blur_score": sample.blur_score,
                "face_area_ratio": sample.face_area_ratio,
                "bbox": sample.bbox,
                "source_kind": sample.source_kind,
                "source_name": sample.source_name,
                "frame_index": sample.frame_index,
                "timestamp_ms": sample.timestamp_ms,
            }
            for sample in selected_samples
        ],
    }


def build_embedding_payload_from_image(image_bytes: bytes) -> Dict[str, Any]:
    samples = extract_samples_from_image_bytes(
        image_bytes=image_bytes,
        mime_type="image/png",
        source_name="image_data_url",
    )
    selected_samples = select_enrollment_samples(samples)
    return build_embedding_payload_from_samples(
        selected_samples=selected_samples,
        total_samples_found=len(samples),
        total_media_items=1,
        discarded_media=[],
    )


def build_embedding_payload_from_media_items(
    media_items: Sequence[Tuple[str, bytes, str]],
    existing_payload: Optional[str] = None,
    merge_mode: Literal["replace", "append"] = "replace",
) -> Tuple[Dict[str, Any], Optional[EnrollmentSample]]:
    if not face_recognizer.available:
        description = face_recognizer.describe()
        return (
            {
                "version": 2,
                "status": "recognizer_unavailable",
                "provider": description["provider"],
                "model": description["model"],
                "message": description["message"],
                "vectors": [],
                "sample_count": 0,
                "embedding_count": 0,
                "ready": False,
                "discarded_media": [],
                "selection_strategy": "quality+dedupe",
                "existing_sample_count": 0,
                "samples": [],
            },
            None,
        )

    new_samples: List[EnrollmentSample] = []
    discarded_media: List[str] = []

    for source_name, file_bytes, mime_type in media_items:
        normalized_mime = (mime_type or "").lower()
        if normalized_mime.startswith("image/"):
            samples = extract_samples_from_image_bytes(
                image_bytes=file_bytes,
                mime_type=normalized_mime,
                source_name=source_name,
            )
        elif normalized_mime.startswith("video/"):
            samples = extract_samples_from_video_bytes(
                video_bytes=file_bytes,
                mime_type=normalized_mime,
                source_name=source_name,
            )
        else:
            discarded_media.append(f"{source_name}: unsupported type {mime_type or 'unknown'}")
            continue

        if not samples:
            discarded_media.append(f"{source_name}: no usable face found")
            continue

        new_samples.extend(samples)

    if not new_samples:
        payload = build_embedding_payload_from_samples(
            selected_samples=[],
            total_samples_found=0,
            total_media_items=len(media_items),
            discarded_media=discarded_media,
            selection_strategy="append+quality+dedupe"
            if merge_mode == "append"
            else "quality+dedupe",
        )
        return payload, None

    existing_samples = (
        reconstruct_samples_from_payload(existing_payload)
        if merge_mode == "append"
        else []
    )
    candidate_samples = existing_samples + new_samples
    selected_samples = select_enrollment_samples(candidate_samples)
    selected_thumbnail = selected_samples[0] if selected_samples and selected_samples[0].image_bytes else None
    message = (
        f"Merged {len(new_samples)} new enrollment view(s) with {len(existing_samples)} "
        f"existing view(s) and kept {len(selected_samples)} representative views."
        if merge_mode == "append"
        else (
            f"Stored {len(selected_samples)} representative enrollment views "
            f"from {len(media_items)} uploaded media item(s)."
        )
    )
    payload = build_embedding_payload_from_samples(
        selected_samples=selected_samples,
        total_samples_found=len(new_samples),
        total_media_items=len(media_items),
        discarded_media=discarded_media,
        selection_strategy="append+quality+dedupe"
        if merge_mode == "append"
        else "quality+dedupe",
        message=message,
        existing_sample_count=len(existing_samples),
    )
    return payload, selected_thumbnail


def write_person_thumbnail(person_id: str, image_bytes: bytes, mime_type: str) -> str:
    ensure_runtime_dirs()
    person_dir = _get_person_dir(person_id)
    person_dir.mkdir(parents=True, exist_ok=True)
    suffix = _suffix_from_mime_type(mime_type)
    image_path = person_dir / f"thumbnail{suffix}"
    image_path.write_bytes(image_bytes)
    return str(image_path.relative_to(BACKEND_ROOT))


def write_attendance_snapshot(record_id: str, image_bytes: bytes, mime_type: str) -> str:
    ensure_runtime_dirs()
    record_dir = ATTENDANCE_SNAPSHOTS_DIR / record_id
    record_dir.mkdir(parents=True, exist_ok=True)
    suffix = _suffix_from_mime_type(mime_type)
    image_path = record_dir / f"snapshot{suffix}"
    image_path.write_bytes(image_bytes)
    return str(image_path.relative_to(BACKEND_ROOT))


def _resolve_runtime_path(path_value: Optional[str]) -> Optional[Path]:
    if not path_value:
        return None
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return BACKEND_ROOT / candidate


def read_image_data_url(path_value: Optional[str]) -> Optional[str]:
    image_path = _resolve_runtime_path(path_value)
    if image_path is None or not image_path.exists():
        return None

    mime_type, _ = mimetypes.guess_type(image_path.name)
    mime_type = mime_type or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def parse_embedding_payload(raw_payload: Optional[str]) -> Dict[str, Any]:
    if not raw_payload:
        return {
            "version": 2,
            "status": "missing_enrollment_image",
            "provider": "none",
            "model": "",
            "message": "No enrollment media has been stored yet.",
            "vectors": [],
            "embedding_count": 0,
            "sample_count": 0,
            "ready": False,
            "samples": [],
        }

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {
            "version": 2,
            "status": "invalid_embedding_payload",
            "provider": "none",
            "model": "",
            "message": "Stored embedding payload is invalid JSON.",
            "vectors": [],
            "embedding_count": 0,
            "sample_count": 0,
            "ready": False,
            "samples": [],
        }

    vectors = payload.get("vectors") or []
    samples = payload.get("samples") or []
    payload["embedding_count"] = len(vectors)
    payload["sample_count"] = payload.get("sample_count", len(samples) or len(vectors))
    payload["ready"] = bool(vectors)
    return payload


def serialize_person(person: Person) -> Dict[str, Any]:
    embedding_payload = parse_embedding_payload(person.embedding)
    profile = read_person_profile(person.id)
    return {
        "id": person.id,
        "name": person.name,
        "employee_id": person.employee_id,
        "created_at": person.created_at.isoformat() if person.created_at else None,
        "is_active": person.is_active,
        "thumbnail_path": person.thumbnail_path,
        "thumbnail_data_url": read_image_data_url(person.thumbnail_path),
        "has_embedding": embedding_payload["ready"],
        "embedding_count": embedding_payload["embedding_count"],
        "sample_count": embedding_payload["sample_count"],
        "embedding_status": embedding_payload.get("status"),
        "embedding_message": embedding_payload.get("message"),
        "embedding_provider": embedding_payload.get("provider"),
        "embedding_model": embedding_payload.get("model"),
        "selection_strategy": embedding_payload.get("selection_strategy"),
        "discarded_media": embedding_payload.get("discarded_media", []),
        "shift_id": profile.get("shift_id"),
    }
