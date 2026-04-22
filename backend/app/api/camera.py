"""
Camera API Endpoints
"""
from __future__ import annotations

import logging
from typing import List, Optional

import cv2
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from app.camera.manager import camera_manager
from app.services.rbac import ADMIN_ROLE, FLEET_OPERATOR_ROLE, GENERAL_MANAGER_ROLE, SAFETY_OPERATOR_ROLE

router = APIRouter()
logger = logging.getLogger(__name__)


class CameraStartRequest(BaseModel):
    source_type: str = "webcam"
    source_id: Optional[str] = "0"
    owner_module: Optional[str] = None
    owner_token: Optional[str] = None


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


def _build_camera_response():
    state = camera_manager.get_state()
    payload = state.__dict__.copy()
    if state.mode == "gate":
        payload["gate"] = camera_manager.get_gate_state()
    elif state.mode == "driver":
        payload["driver"] = camera_manager.get_driver_state()

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


@router.get("/sources", response_model=List[CameraSourceInfo])
async def list_camera_sources():
    """List available camera sources."""
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
        except Exception as e:
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


@router.post("/start", response_model=CameraStateResponse)
async def start_camera(request: Request, payload: CameraStartRequest):
    """Start camera capture."""
    _assert_camera_access(request, owner_module=payload.owner_module)
    
    success = camera_manager.start(
        source_type=payload.source_type,
        source_id=payload.source_id or "0",
        owner_module=payload.owner_module,
        owner_token=payload.owner_token,
    )
    
    if not success:
        state = camera_manager.get_state()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to start camera: {state.error}"
        )

    return _build_camera_response()


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
    camera_manager.stop()
    return _build_camera_response()


@router.get("/state", response_model=CameraStateResponse)
async def get_camera_state():
    """Get current camera state."""
    return _build_camera_response()


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
    
    camera_manager.set_mode(mode)
    return _build_camera_response()
