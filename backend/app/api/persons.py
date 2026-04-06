"""
Person enrollment API.
"""
from __future__ import annotations

import json
from typing import List, Literal, Optional

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


class PersonUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    employee_id: Optional[str] = Field(default=None, max_length=50)
    image_data_url: Optional[str] = None
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
    image_bytes, mime_type = parse_image_data_url(image_data_url)
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

    write_person_profile(person.id, {"shift_id": payload.shift_id})
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
    person = _create_person_record(
        db=db,
        name=name,
        employee_id=cleaned_employee_id,
        is_active=is_active,
    )

    media_items = []
    for uploaded_file in files:
        file_bytes = await uploaded_file.read()
        if not file_bytes:
            continue
        media_items.append(
            (
                uploaded_file.filename or f"upload-{len(media_items) + 1}",
                file_bytes,
                uploaded_file.content_type or "application/octet-stream",
            )
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
                detail=f"Enrollment processing failed: {exc}",
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

    write_person_profile(person.id, {"shift_id": shift_id})
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

    media_items = []
    for uploaded_file in files:
        file_bytes = await uploaded_file.read()
        if not file_bytes:
            continue
        media_items.append(
            (
                uploaded_file.filename or f"upload-{len(media_items) + 1}",
                file_bytes,
                uploaded_file.content_type or "application/octet-stream",
            )
        )

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
            detail=f"Enrollment processing failed: {exc}",
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

    write_person_profile(person.id, {"shift_id": shift_id})
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

    if payload.image_data_url:
        _apply_enrollment_image(person, payload.image_data_url)

    write_person_profile(person.id, {"shift_id": payload.shift_id})
    db.commit()
    db.refresh(person)
    _invalidate_gate_cache()
    return serialize_person(person)


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
