"""
Status and Health Endpoints
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter()


class SystemStatus(BaseModel):
    status: str
    mode: str
    camera_active: bool
    version: str
    timestamp: str


class ModeSwitch(BaseModel):
    mode: str  # gate, driver, idle


# Current system state (in-memory for now)
_current_mode = "idle"
_camera_active = False


@router.get("/status", response_model=SystemStatus)
async def get_status():
    """Get current system status."""
    return SystemStatus(
        status="ok",
        mode=_current_mode,
        camera_active=_camera_active,
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat()
    )


@router.post("/mode", response_model=SystemStatus)
async def switch_mode(mode_switch: ModeSwitch):
    """Switch system mode (gate/driver/idle)."""
    global _current_mode
    
    if mode_switch.mode not in ["gate", "driver", "idle"]:
        raise ValueError(f"Invalid mode: {mode_switch.mode}")
    
    _current_mode = mode_switch.mode
    
    return SystemStatus(
        status="ok",
        mode=_current_mode,
        camera_active=_camera_active,
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy"}
