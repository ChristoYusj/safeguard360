"""
Camera API Endpoints
"""
from __future__ import annotations

import ipaddress
import logging
from pathlib import Path
from typing import List, Literal, Optional
from urllib.parse import urlsplit

import cv2
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.camera.manager import camera_manager
from app.config.settings import get_settings
from app.services.rbac import ADMIN_ROLE, FLEET_OPERATOR_ROLE, GENERAL_MANAGER_ROLE, SAFETY_OPERATOR_ROLE

router = APIRouter()
logger = logging.getLogger(__name__)


class CameraStartRequest(BaseModel):
    source_type: Literal["webcam", "video_file", "ip_stream"] = "webcam"
    source_id: Optional[str] = Field(default="0", max_length=2048)
    owner_module: Optional[str] = None
    owner_token: Optional[str] = None


STREAM_SCHEMES = {"rtsp", "rtsps", "http", "https"}


def _reject(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def validate_camera_source(source_type: str, source_id: str) -> str:
    """Return a safe source_id for cv2.VideoCapture or raise 400.

    The raw value used to go straight into VideoCapture, which accepts any
    local path or URL: an operator could stream an arbitrary file on the server
    or make it fetch internal addresses. Webcams are device indexes, video files
    must live under VIDEO_SOURCES_DIR, and streams must use a media scheme and
    a routable host (optionally restricted to CAMERA_STREAM_ALLOWED_HOSTS).
    """
    settings = get_settings()
    value = (source_id or "").strip()

    if source_type == "webcam":
        if not value.isdigit():
            raise _reject("Webcam source_id must be a device index.")
        return value

    if source_type == "video_file":
        base = settings.resolved_video_sources_dir
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = base / value
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise _reject("Invalid video file path.") from exc
        if not resolved.is_relative_to(base):
            raise _reject(f"Video files must be inside {base}.")
        if not resolved.is_file():
            raise _reject("Video file not found.")
        return str(resolved)

    # ip_stream
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise _reject("Invalid stream URL.") from exc
    if parsed.scheme.lower() not in STREAM_SCHEMES or not parsed.hostname:
        raise _reject("Stream URL must use rtsp(s):// or http(s):// and name a host.")
    host = parsed.hostname.lower()
    allowed_hosts = settings.camera_stream_allowed_hosts
    if allowed_hosts and host not in allowed_hosts:
        raise _reject("Stream host is not in CAMERA_STREAM_ALLOWED_HOSTS.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None  # a hostname; resolution happens inside OpenCV
    if host in {"localhost", "localhost.localdomain"} or (
        address is not None
        and (
            address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        )
    ):
        raise _reject("Stream host must be a routable camera address.")
    return value


class CameraControlRequest(BaseModel):
    owner_module: Optional[str] = None
    owner_token: Optional[str] = None


class CameraStateResponse(BaseModel):
    active: bool
    source_type: str
    source_id: str
    fps: float
    frames_captured: int
    mode: str
    error: str = ""
    owner_module: Optional[str] = None
    state_version: int = 0
    gate: Optional[dict] = None
    driver: Optional[dict] = None


class CameraSourceInfo(BaseModel):
    source_type: str
    source_id: str
    name: str


def _redact_source_id(source_id: str) -> str:
    """Hide credentials embedded in stream URLs (rtsp://user:pass@host/...)."""
    if "://" in source_id and "@" in source_id:
        scheme, rest = source_id.split("://", 1)
        _userinfo, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"
    return source_id


def _build_camera_response(role: str | None = None):
    """Camera state as the given role is allowed to see it.

    Managers and admins get everything. A fleet operator never receives the
    gate payload (worker identity, PPE verdict) and a safety operator never
    receives the driver payload; neither sees stream credentials.
    """
    state = camera_manager.get_state()
    payload = state.__dict__.copy()
    if state.mode == "gate":
        payload["gate"] = camera_manager.get_gate_state()
    elif state.mode == "driver":
        payload["driver"] = camera_manager.get_driver_state()

    if role not in {ADMIN_ROLE, GENERAL_MANAGER_ROLE}:
        if role != SAFETY_OPERATOR_ROLE:
            payload.pop("gate", None)
        if role != FLEET_OPERATOR_ROLE:
            payload.pop("driver", None)
        payload["source_id"] = _redact_source_id(str(payload.get("source_id") or ""))

    return CameraStateResponse(**payload)


def _get_request_role(request: Request) -> str | None:
    current_user = getattr(request.state, "user", None)
    return getattr(current_user, "role", None)


def _assert_camera_access(request: Request, *, owner_module: Optional[str], mode: Optional[str] = None) -> None:
    role = _get_request_role(request)
    if role in {GENERAL_MANAGER_ROLE, ADMIN_ROLE}:
        return

    if role == FLEET_OPERATOR_ROLE:
        if owner_module != "drivers":
            raise HTTPException(status_code=403, detail="Forbidden.")
        if mode is not None and mode not in {"driver", "idle"}:
            raise HTTPException(status_code=403, detail="Forbidden.")
        return

    if role == SAFETY_OPERATOR_ROLE:
        if owner_module != "attendance":
            raise HTTPException(status_code=403, detail="Forbidden.")
        if mode is not None and mode not in {"gate", "idle"}:
            raise HTTPException(status_code=403, detail="Forbidden.")
        return

    # Fail closed: an unknown or missing role never controls the camera.
    raise HTTPException(status_code=403, detail="Forbidden.")


def _probe_camera_sources() -> List[CameraSourceInfo]:
    """Open every webcam index in turn to see which ones deliver a frame.

    Seconds of blocking OpenCV work. It runs on a worker thread, never on the
    event loop: while this sat in an `async def` the whole server stopped
    answering, and the live websocket clients were dropped as "slow" by their
    own send timeout.
    """
    sources = []
    
    # Check for webcams (check indices 0-5)
    for i in range(6):
        try:
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            opened = cap.isOpened()
            
            if opened:
                # Try to read a frame to confirm it works
                ret, frame = cap.read()
                if ret and frame is not None:
                    sources.append(CameraSourceInfo(
                        source_type="webcam",
                        source_id=str(i),
                        name=f"Webcam {i}"
                    ))
                cap.release()
        except Exception:
            logger.exception("Camera source probe failed for index %s.", i)
    
    # Add video file option
    sources.append(CameraSourceInfo(
        source_type="video_file",
        source_id="",
        name="Video File (provide path)"
    ))
    
    # Add IP stream option
    sources.append(CameraSourceInfo(
        source_type="ip_stream",
        source_id="",
        name="IP Stream (provide URL)"
    ))

    return sources


@router.get("/sources", response_model=List[CameraSourceInfo])
async def list_camera_sources():
    """List available camera sources."""
    return await run_in_threadpool(_probe_camera_sources)


@router.post("/start", response_model=CameraStateResponse)
async def start_camera(request: Request, payload: CameraStartRequest):
    """Start camera capture."""
    _assert_camera_access(request, owner_module=payload.owner_module)
    source_id = validate_camera_source(payload.source_type, payload.source_id or "0")

    # Opening a device includes a warm-up read loop of up to ~2.5 s.
    success = await run_in_threadpool(
        camera_manager.start,
        source_type=payload.source_type,
        source_id=source_id,
        owner_module=payload.owner_module,
        owner_token=payload.owner_token,
    )
    
    if not success:
        state = camera_manager.get_state()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to start camera: {state.error}"
        )

    return _build_camera_response(_get_request_role(request))


@router.post("/stop", response_model=CameraStateResponse)
async def stop_camera(
    request: Request,
    payload: Optional[CameraControlRequest] = Body(default=None),
):
    """Stop camera capture."""
    control_request = payload or CameraControlRequest(
        owner_module=camera_manager.owner_module,
        owner_token=camera_manager.owner_token,
    )
    _assert_camera_access(request, owner_module=control_request.owner_module, mode="idle")
    if camera_manager.running and not camera_manager.has_control(
        control_request.owner_module,
        control_request.owner_token,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Camera is currently controlled by {camera_manager.get_owner_label()}.",
        )
    # stop() joins the capture and worker threads, which can take seconds
    # when a read is stuck against a disconnected device.
    await run_in_threadpool(camera_manager.stop)
    return _build_camera_response(_get_request_role(request))


@router.get("/state", response_model=CameraStateResponse)
async def get_camera_state(request: Request):
    """Get current camera state, scoped to the caller's role."""
    return _build_camera_response(_get_request_role(request))


@router.post("/mode/{mode}", response_model=CameraStateResponse)
async def set_camera_mode(
    http_request: Request,
    mode: str,
    request: Optional[CameraControlRequest] = Body(default=None),
):
    """Set processing mode (gate/driver/idle)."""
    if mode not in ["gate", "driver", "idle"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Must be gate, driver, or idle."
        )

    control_request = request or CameraControlRequest()
    _assert_camera_access(
        http_request,
        owner_module=control_request.owner_module or camera_manager.owner_module,
        mode=mode,
    )

    if mode != "idle" and not camera_manager.running:
        raise HTTPException(
            status_code=409,
            detail="Start the camera feed before enabling recognition mode.",
        )
    if camera_manager.running and not camera_manager.has_control(
        control_request.owner_module,
        control_request.owner_token,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Camera is currently controlled by {camera_manager.get_owner_label()}.",
        )
    
    # set_mode takes the lifecycle lock, which a stop() may be holding.
    await run_in_threadpool(camera_manager.set_mode, mode)
    # Scoped to the caller's role like every other camera response. This one
    # passed no role at all, which fell through to the strictest branch and
    # stripped the gate payload from the safety operator who had just asked
    # for gate mode -- the UI got a reply with gate: null and had to wait for
    # the next poll to see the state it had just switched on.
    return _build_camera_response(_get_request_role(http_request))
