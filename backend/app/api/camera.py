"""
Camera API Endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import cv2

from app.camera.manager import camera_manager

router = APIRouter()


class CameraStartRequest(BaseModel):
    source_type: str = "webcam"
    source_id: Optional[str] = "0"


class CameraStateResponse(BaseModel):
    active: bool
    source_type: str
    source_id: str
    fps: float
    frames_captured: int
    mode: str
    error: str = ""


class CameraSourceInfo(BaseModel):
    source_type: str
    source_id: str
    name: str


@router.get("/sources", response_model=List[CameraSourceInfo])
async def list_camera_sources():
    """List available camera sources."""
    print("[API] GET /camera/sources - scanning indices 0-5...")
    sources = []
    
    # Check for webcams (check indices 0-5)
    for i in range(6):
        print(f"[API] Testing camera index {i}...", end=" ")
        try:
            # Try DirectShow first (Windows)
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            opened = cap.isOpened()
            
            if opened:
                # Try to read a frame to confirm it works
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    print(f"OK ({w}x{h})")
                    sources.append(CameraSourceInfo(
                        source_type="webcam",
                        source_id=str(i),
                        name=f"Webcam {i}"
                    ))
                else:
                    print("opened but no frame")
                cap.release()
            else:
                print("not available")
        except Exception as e:
            print(f"error: {e}")
    
    print(f"[API] Found {len(sources)} webcam(s)")
    
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
    
    print(f"[API] Total sources: {len(sources)}")
    for s in sources:
        print(f"[API]   - {s.name} ({s.source_type}:{s.source_id})")
    
    return sources


@router.post("/start", response_model=CameraStateResponse)
async def start_camera(request: CameraStartRequest):
    """Start camera capture."""
    print(f"[API] POST /camera/start: {request.source_type}, {request.source_id}")
    
    success = camera_manager.start(
        source_type=request.source_type,
        source_id=request.source_id or "0"
    )
    
    if not success:
        state = camera_manager.get_state()
        print(f"[API] Camera start failed: {state.error}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to start camera: {state.error}"
        )
    
    state = camera_manager.get_state()
    print(f"[API] Camera started successfully")
    return CameraStateResponse(**state.__dict__)


@router.post("/stop", response_model=CameraStateResponse)
async def stop_camera():
    """Stop camera capture."""
    print("[API] POST /camera/stop")
    camera_manager.stop()
    state = camera_manager.get_state()
    return CameraStateResponse(**state.__dict__)


@router.get("/state", response_model=CameraStateResponse)
async def get_camera_state():
    """Get current camera state."""
    state = camera_manager.get_state()
    return CameraStateResponse(**state.__dict__)


@router.post("/mode/{mode}", response_model=CameraStateResponse)
async def set_camera_mode(mode: str):
    """Set processing mode (gate/driver/idle)."""
    print(f"[API] POST /camera/mode/{mode}")
    if mode not in ["gate", "driver", "idle"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Must be gate, driver, or idle."
        )
    
    camera_manager.set_mode(mode)
    state = camera_manager.get_state()
    return CameraStateResponse(**state.__dict__)
