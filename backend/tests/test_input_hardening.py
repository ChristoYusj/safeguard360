"""Untrusted input at the API edge (audit findings H1, N44, N47, N49).

Camera sources used to reach cv2.VideoCapture unvalidated (arbitrary local
file read, requests to internal addresses); uploads and data URLs had no size
or type limits; malformed data URLs and CSVs surfaced as 500s.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.camera.manager import camera_manager
from app.config.settings import get_settings
from app.db.connection import SessionLocal
from app.db.models import Person
from tests.helpers import login_admin

PNG = "image/png"


@pytest.fixture()
def start_stub(monkeypatch):
    """Record camera_manager.start() calls instead of opening a device."""
    calls: list[dict] = []

    def fake_start(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(camera_manager, "start", fake_start)
    return calls


def _start(client, source_type: str, source_id: str):
    return client.post(
        "/api/camera/start",
        json={"source_type": source_type, "source_id": source_id, "owner_module": "attendance"},
    )


@pytest.mark.parametrize(
    "source_type,source_id,fragment",
    [
        # An existing absolute file outside VIDEO_SOURCES_DIR on every OS (a
        # Windows-only path is relative on Linux and lands inside the dir).
        ("video_file", str(Path(__file__).resolve()), "inside"),
        ("video_file", "../../backend/main.py", "inside"),
        ("ip_stream", "http://169.254.169.254/latest/meta-data/", "routable"),
        ("ip_stream", "http://127.0.0.1:8000/api/auth/me", "routable"),
        ("ip_stream", "rtsp://localhost/stream", "routable"),
        ("ip_stream", "file:///etc/passwd", "rtsp"),
        ("webcam", "../0", "device index"),
    ],
)
def test_unsafe_camera_sources_are_rejected_before_the_camera_is_touched(
    client, start_stub, source_type, source_id, fragment
):
    login_admin(client)
    response = _start(client, source_type, source_id)
    assert response.status_code == 400, response.text
    assert fragment in response.json()["detail"].lower()
    assert start_stub == []


def test_unknown_source_type_is_a_validation_error(client, start_stub):
    login_admin(client)
    response = client.post(
        "/api/camera/start",
        json={"source_type": "shell", "source_id": "x", "owner_module": "attendance"},
    )
    assert response.status_code == 422
    assert start_stub == []


def test_lan_rtsp_camera_is_allowed(client, start_stub):
    login_admin(client)
    response = _start(client, "ip_stream", "rtsp://admin:pw@192.168.1.20:554/stream1")
    assert response.status_code == 200, response.text
    assert start_stub[0]["source_id"] == "rtsp://admin:pw@192.168.1.20:554/stream1"


def test_stream_allow_list_is_enforced_when_set(client, start_stub, monkeypatch):
    login_admin(client)
    monkeypatch.setattr(get_settings(), "CAMERA_STREAM_ALLOWED_HOSTS", "10.0.0.5, cam.site.local")
    assert _start(client, "ip_stream", "rtsp://10.0.0.6/s").status_code == 400
    assert _start(client, "ip_stream", "rtsp://10.0.0.5/s").status_code == 200
    assert _start(client, "ip_stream", "rtsp://CAM.site.local/s").status_code == 200
    assert len(start_stub) == 2


def test_video_file_inside_the_sources_dir_is_accepted(client, start_stub, tmp_path, monkeypatch):
    login_admin(client)
    monkeypatch.setattr(get_settings(), "VIDEO_SOURCES_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not really a video")

    response = _start(client, "video_file", "clip.mp4")

    assert response.status_code == 200, response.text
    assert start_stub[0]["source_id"] == str(clip.resolve())
    assert _start(client, "video_file", "missing.mp4").status_code == 400


def _enroll(client, files):
    return client.post("/api/persons/enroll-media", data={"name": "Nadia K."}, files=files)


def _person_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Person).count()
    finally:
        db.close()


def test_wrong_upload_type_is_415_and_creates_no_worker(client):
    login_admin(client)
    response = _enroll(client, [("files", ("notes.txt", b"hello", "text/plain"))])
    assert response.status_code == 415
    assert _person_count() == 0


def test_too_many_files_is_413(client):
    login_admin(client)
    files = [("files", (f"f{i}.png", b"\x89PNG", PNG)) for i in range(11)]
    response = _enroll(client, files)
    assert response.status_code == 413
    assert "10 files" in response.json()["detail"]
    assert _person_count() == 0


def test_oversized_upload_is_413(client, monkeypatch):
    login_admin(client)
    monkeypatch.setattr("app.api.persons.MAX_UPLOAD_BYTES", 16)
    response = _enroll(client, [("files", ("big.png", b"x" * 17, PNG))])
    assert response.status_code == 413
    assert _person_count() == 0


def test_malformed_image_data_url_is_400_not_500(client):
    login_admin(client)
    db = SessionLocal()
    try:
        person = Person(name="Nadia K.", employee_id="EMP-1")
        db.add(person)
        db.commit()
        person_id = person.id
    finally:
        db.close()

    response = client.put(
        f"/api/persons/{person_id}",
        json={"name": "Nadia K.", "image_data_url": "image/png;base64,AAAA"},
    )

    assert response.status_code == 400, response.text
    assert "data:image/" in response.json()["detail"]


def test_malformed_snapshot_data_url_is_400_not_500(client):
    login_admin(client)
    response = client.post(
        "/api/attendance",
        json={"person_name": "Ghost", "direction": "ENTRY", "snapshot_data_url": "not-a-data-url"},
    )
    assert response.status_code == 400, response.text


MALFORMED_QUOTE_CSV = "\n".join(
    [
        "name,employee_id",
        # A quote followed by something other than a delimiter: an error only in
        # strict mode; non-strict csv silently merges it into the field.
        '"Nadia" K.,EMP-9',
        "",
    ]
)
# One field beyond csv.field_size_limit() (131072 chars).
OVERSIZED_FIELD_CSV = "name,employee_id\n" + ("x" * 200_000) + ",EMP-9\n"


@pytest.mark.parametrize(
    "csv_text",
    [MALFORMED_QUOTE_CSV, OVERSIZED_FIELD_CSV],
    ids=["malformed-quote", "oversized-field"],
)
def test_broken_csv_is_400_not_500(client, csv_text):
    login_admin(client)
    response = client.post(
        "/api/persons/bulk-import",
        files={"file": ("roster.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 400, response.text
    assert "could not be parsed" in response.json()["detail"]
    assert _person_count() == 0
