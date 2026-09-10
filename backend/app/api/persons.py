"""
Person enrollment API.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import Person
from app.inference.face_recognizer import face_recognizer
from app.services.persons import (
    build_embedding_payload_from_image,
    build_embedding_payload_from_media_items,
    parse_embedding_payload,
    parse_image_data_url,
    serialize_person,
    write_person_thumbnail,
    write_person_profile,
)

router = APIRouter()


def _invalidate_gate_cache() -> None:
    try:
        from app.services.gate_attendance import gate_attendance_recognizer

        gate_attendance_recognizer.invalidate_cache()
    except Exception:
        pass


# Upload limits. Everything is buffered in memory before the face pipeline
# runs, so unbounded bodies were an easy way to take the gate offline.
MAX_UPLOAD_FILES = 10
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_IMAGE_DATA_URL_CHARS = 10_000_000  # ~7.5 MB of base64 image
ALLOWED_UPLOAD_PREFIXES = ("image/", "video/")


async def _read_upload_capped(uploaded_file: UploadFile) -> bytes:
    """Read one upload, rejecting the wrong type before reading and oversize
    bodies without holding more than the cap in memory."""
    content_type = (uploaded_file.content_type or "").lower()
    if not content_type.startswith(ALLOWED_UPLOAD_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported upload type '{content_type or 'unknown'}'; send an image or video.",
        )
    data = await uploaded_file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Each upload must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.",
        )
    return data


async def _collect_media_items(files: List[UploadFile]) -> list:
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"At most {MAX_UPLOAD_FILES} files per enrollment request.",
        )
    media_items = []
    for uploaded_file in files:
        file_bytes = await _read_upload_capped(uploaded_file)
        if not file_bytes:
            continue
        media_items.append(
            (
                uploaded_file.filename or f"upload-{len(media_items) + 1}",
                file_bytes,
                uploaded_file.content_type or "application/octet-stream",
            )
        )
    return media_items


class PersonUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    employee_id: Optional[str] = Field(default=None, max_length=50)
    image_data_url: Optional[str] = Field(default=None, max_length=MAX_IMAGE_DATA_URL_CHARS)
    shift_id: Optional[str] = Field(default=None, pattern="^(day|swing|night)$")
    is_active: bool = True


class PersonResponse(BaseModel):
    id: str
    name: str
    employee_id: Optional[str] = None
    shift_id: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool
    thumbnail_path: Optional[str] = None
    thumbnail_data_url: Optional[str] = None
    has_embedding: bool
    embedding_count: int
    sample_count: int = 0
    embedding_status: Optional[str] = None
    embedding_message: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    selection_strategy: Optional[str] = None
    discarded_media: List[str] = []


class RecognizerStatusResponse(BaseModel):
    available: bool
    provider: str
    model: str
    message: str
    import_error: Optional[str] = None


def _find_employee_id_conflict(
    db: Session,
    employee_id: Optional[str],
    exclude_person_id: Optional[str] = None,
) -> Optional[Person]:
    if not employee_id:
        return None

    query = db.query(Person).filter(Person.employee_id == employee_id)
    if exclude_person_id:
        query = query.filter(Person.id != exclude_person_id)
    return query.first()


def _apply_enrollment_image(person: Person, image_data_url: str) -> None:
    try:
        image_bytes, mime_type = parse_image_data_url(image_data_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    embedding_payload = build_embedding_payload_from_image(image_bytes)

    if embedding_payload["status"] == "no_face_detected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=embedding_payload["message"],
        )

    person.thumbnail_path = write_person_thumbnail(person.id, image_bytes, mime_type)
    person.embedding = json.dumps(embedding_payload)


def _raise_for_enrollment_status(embedding_payload: dict) -> None:
    if embedding_payload["status"] == "no_face_detected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=embedding_payload["message"],
        )

    if embedding_payload["status"] == "recognizer_unavailable":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=embedding_payload["message"],
        )


def _create_person_record(
    db: Session,
    name: str,
    employee_id: Optional[str],
    is_active: bool,
) -> Person:
    conflict = _find_employee_id_conflict(db, employee_id)
    if conflict:
        if not conflict.is_active:
            conflict.name = name.strip()
            conflict.employee_id = employee_id
            conflict.is_active = is_active
            conflict.embedding = None
            conflict.thumbnail_path = None
            db.flush()
            return conflict

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee ID '{employee_id}' is already enrolled.",
        )

    person = Person(
        name=name.strip(),
        employee_id=employee_id,
        is_active=is_active,
    )
    db.add(person)
    db.flush()
    return person


@router.get("", response_model=List[PersonResponse])
def list_persons(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    query = db.query(Person).order_by(Person.created_at.desc())
    if not include_inactive:
        query = query.filter(Person.is_active.is_(True))
    return [serialize_person(person) for person in query.all()]


@router.get("/recognizer", response_model=RecognizerStatusResponse)
def get_recognizer_status():
    return face_recognizer.describe()


@router.post("", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
def create_person(payload: PersonUpsertRequest, db: Session = Depends(get_db)):
    employee_id = payload.employee_id.strip() if payload.employee_id else None
    person = _create_person_record(
        db=db,
        name=payload.name,
        employee_id=employee_id,
        is_active=payload.is_active,
    )

    if payload.image_data_url:
        _apply_enrollment_image(person, payload.image_data_url)
    else:
        person.embedding = json.dumps(parse_embedding_payload(None))

    valid_shift = payload.shift_id if payload.shift_id in {"day", "swing", "night"} else None
    person.shift_id = valid_shift
    write_person_profile(person.id, {"shift_id": valid_shift})
    db.commit()
    db.refresh(person)
    _invalidate_gate_cache()
    return serialize_person(person)


@router.post("/enroll-media", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
async def create_person_from_media(
    name: str = Form(...),
    employee_id: Optional[str] = Form(default=None),
    shift_id: Optional[str] = Form(default=None),
    is_active: bool = Form(default=True),
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    cleaned_employee_id = employee_id.strip() if employee_id else None
    # Validate the uploads before touching the database, so a rejected request
    # never leaves a half-created worker behind.
    media_items = await _collect_media_items(files)
    person = _create_person_record(
        db=db,
        name=name,
        employee_id=cleaned_employee_id,
        is_active=is_active,
    )

    if media_items:
        try:
            embedding_payload, best_sample = build_embedding_payload_from_media_items(
                media_items,
                merge_mode="replace",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Enrollment processing failed.",
            ) from exc

        _raise_for_enrollment_status(embedding_payload)

        if best_sample is not None:
            person.thumbnail_path = write_person_thumbnail(
                person.id,
                best_sample.image_bytes,
                best_sample.mime_type,
            )
        person.embedding = json.dumps(embedding_payload)
    else:
        person.embedding = json.dumps(parse_embedding_payload(None))

    valid_shift = shift_id if shift_id in {"day", "swing", "night"} else None
    person.shift_id = valid_shift
    write_person_profile(person.id, {"shift_id": valid_shift})
    db.commit()
    db.refresh(person)
    _invalidate_gate_cache()
    return serialize_person(person)


@router.post("/{person_id}/enroll-media", response_model=PersonResponse)
async def update_person_from_media(
    person_id: str,
    name: str = Form(...),
    employee_id: Optional[str] = Form(default=None),
    shift_id: Optional[str] = Form(default=None),
    merge_mode: Literal["append", "replace"] = Form(default="append"),
    files: List[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")

    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Worker name is required.",
        )

    cleaned_employee_id = employee_id.strip() if employee_id else None
    conflict = _find_employee_id_conflict(db, cleaned_employee_id, exclude_person_id=person_id)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee ID '{cleaned_employee_id}' is already enrolled.",
        )

    media_items = await _collect_media_items(files)

    if not media_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one image or video to update this worker.",
        )

    try:
        embedding_payload, thumbnail_sample = build_embedding_payload_from_media_items(
            media_items,
            existing_payload=person.embedding,
            merge_mode=merge_mode,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enrollment processing failed.",
        ) from exc

    _raise_for_enrollment_status(embedding_payload)

    person.name = cleaned_name
    person.employee_id = cleaned_employee_id
    person.embedding = json.dumps(embedding_payload)

    if thumbnail_sample is not None:
        person.thumbnail_path = write_person_thumbnail(
            person.id,
            thumbnail_sample.image_bytes,
            thumbnail_sample.mime_type,
        )

    valid_shift = shift_id if shift_id in {"day", "swing", "night"} else None
    person.shift_id = valid_shift
    write_person_profile(person.id, {"shift_id": valid_shift})
    db.commit()
    db.refresh(person)
    _invalidate_gate_cache()
    return serialize_person(person)


@router.put("/{person_id}", response_model=PersonResponse)
def update_person(
    person_id: str,
    payload: PersonUpsertRequest,
    db: Session = Depends(get_db),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")

    employee_id = payload.employee_id.strip() if payload.employee_id else None
    conflict = _find_employee_id_conflict(db, employee_id, exclude_person_id=person_id)
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee ID '{employee_id}' is already enrolled.",
        )

    person.name = payload.name.strip()
    person.employee_id = employee_id
    person.is_active = payload.is_active
    valid_shift = payload.shift_id if payload.shift_id in {"day", "swing", "night"} else None
    person.shift_id = valid_shift

    if payload.image_data_url:
        _apply_enrollment_image(person, payload.image_data_url)

    write_person_profile(person.id, {"shift_id": valid_shift})
    db.commit()
    db.refresh(person)
    _invalidate_gate_cache()
    return serialize_person(person)


VALID_SHIFTS = {"day", "swing", "night"}


def _normalize_shift(value: Optional[str]) -> Optional[str]:
    """Map common shift spellings onto the canonical id set."""
    if not value:
        return None
    token = value.strip().lower()
    if not token:
        return None
    if token in VALID_SHIFTS:
        return token
    # Forgiving aliases so spreadsheets don't require exact casing.
    if "night" in token or "late" in token:
        return "night"
    if "swing" in token or "mid" in token or "evening" in token:
        return "swing"
    if "day" in token or "morning" in token or "early" in token:
        return "day"
    return None


def _truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    token = str(value).strip().lower()
    if not token:
        return default
    if token in {"1", "true", "yes", "y", "active", "on", "enabled"}:
        return True
    if token in {"0", "false", "no", "n", "inactive", "off", "disabled"}:
        return False
    return default


class BulkImportSummary(BaseModel):
    created: int
    updated: int
    # Existing rows whose is_active flipped False -> True because the file said
    # so. Reported separately so an unintended re-activation is visible.
    reactivated: int = 0
    skipped: int
    errors: List[Dict[str, Any]]
    total_rows: int


@router.post("/bulk-import", response_model=BulkImportSummary)
async def bulk_import_persons(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upsert a worker roster from a CSV file.

    Expected columns (case-insensitive, any subset):
        name (required)
        employee_id
        shift_id       -- day|swing|night (or "morning"/"late"/"evening"/"mid")
        is_active      -- truthy flag, defaults to True

    Rows matched to existing workers by employee_id update in place;
    otherwise a new metadata-only record is created (no face embedding —
    enrollment media still has to be uploaded separately).
    """
    raw = await file.read(MAX_CSV_BYTES + 1)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty.",
        )
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Roster CSV must be {MAX_CSV_BYTES // (1024 * 1024)} MB or smaller.",
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    # strict: a malformed quote is an error, not a silently merged row.
    reader = csv.DictReader(io.StringIO(text), strict=True)
    try:
        fieldnames = reader.fieldnames
        rows = list(reader)
    except csv.Error as exc:
        # Unterminated quotes, oversized fields, and similar produced a 500.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV could not be parsed near line {reader.line_num}: {exc}",
        ) from exc
    if not fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV is missing a header row.",
        )

    # Normalise headers so callers don't have to match our exact casing.
    header_map = {
        (h or "").strip().lower().replace(" ", "_"): h for h in fieldnames
    }
    if "name" not in header_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must include a 'name' column.",
        )

    def pick(row: Dict[str, Any], key: str) -> Optional[str]:
        source = header_map.get(key)
        if not source:
            return None
        value = row.get(source)
        return value.strip() if isinstance(value, str) else value

    created = 0
    updated = 0
    reactivated = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []
    total_rows = 0

    for index, row in enumerate(rows, start=2):  # line 1 is header
        total_rows += 1
        name = pick(row, "name")
        if not name:
            skipped += 1
            errors.append({"line": index, "reason": "Missing name."})
            continue

        employee_id = pick(row, "employee_id") or None
        shift_id = _normalize_shift(pick(row, "shift_id"))
        is_active = _truthy(pick(row, "is_active"), default=True)

        existing: Optional[Person] = None
        if employee_id:
            existing = (
                db.query(Person).filter(Person.employee_id == employee_id).first()
            )

        try:
            if existing:
                # Only columns present in the file may change an existing row.
                # A name-only correction file used to null shift_id and set
                # is_active=True, silently re-activating offboarded workers.
                existing.name = name
                if "shift_id" in header_map:
                    existing.shift_id = shift_id
                    write_person_profile(existing.id, {"shift_id": shift_id})
                if "is_active" in header_map:
                    if is_active and not existing.is_active:
                        reactivated += 1
                    existing.is_active = is_active
                updated += 1
            else:
                person = Person(
                    name=name,
                    employee_id=employee_id,
                    shift_id=shift_id,
                    is_active=is_active,
                )
                person.embedding = json.dumps(parse_embedding_payload(None))
                db.add(person)
                db.flush()
                write_person_profile(person.id, {"shift_id": shift_id})
                created += 1
        except Exception as exc:  # pragma: no cover - defensive
            db.rollback()
            skipped += 1
            errors.append({"line": index, "reason": str(exc)[:200]})
            continue

    db.commit()
    _invalidate_gate_cache()
    return BulkImportSummary(
        created=created,
        updated=updated,
        reactivated=reactivated,
        skipped=skipped,
        errors=errors,
        total_rows=total_rows,
    )


@router.delete("/{person_id}", response_model=PersonResponse)
def deactivate_person(person_id: str, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")

    person.is_active = False
    db.commit()
    db.refresh(person)
    _invalidate_gate_cache()
    return serialize_person(person)
