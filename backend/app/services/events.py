"""
Event Service
Creates and publishes events.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import uuid


@dataclass
class Event:
    """System event."""
    id: str
    category: str  # CAMERA, PPE, DRIVER, GATE, SYSTEM
    event_type: str
    severity: str  # INFO, WARNING, ALERT, CRITICAL
    timestamp: str
    message: str
    data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventService:
    """Creates and manages events."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.listeners = []
        self._initialized = True
    
    def create_event(
        self,
        category: str,
        event_type: str,
        message: str,
        severity: str = "INFO",
        data: Optional[Dict[str, Any]] = None
    ) -> Event:
        """Create a new event."""
        event = Event(
            id=str(uuid.uuid4()),
            category=category,
            event_type=event_type,
            severity=severity,
            timestamp=datetime.utcnow().isoformat(),
            message=message,
            data=data or {}
        )
        
        # Notify listeners
        for listener in self.listeners:
            try:
                listener(event)
            except Exception:
                pass
        
        return event
    
    def add_listener(self, callback) -> None:
        """Add event listener."""
        self.listeners.append(callback)
    
    def remove_listener(self, callback) -> None:
        """Remove event listener."""
        if callback in self.listeners:
            self.listeners.remove(callback)
    
    # Convenience methods
    def camera_started(self, source_type: str, source_id: str) -> Event:
        return self.create_event(
            category="CAMERA",
            event_type="CAMERA_STARTED",
            message=f"Camera started: {source_type}",
            data={"source_type": source_type, "source_id": source_id}
        )
    
    def camera_stopped(self) -> Event:
        return self.create_event(
            category="CAMERA",
            event_type="CAMERA_STOPPED",
            message="Camera stopped"
        )
    
    def camera_error(self, error: str) -> Event:
        return self.create_event(
            category="CAMERA",
            event_type="CAMERA_ERROR",
            message=f"Camera error: {error}",
            severity="WARNING",
            data={"error": error}
        )
    
    def mode_changed(self, mode: str) -> Event:
        return self.create_event(
            category="SYSTEM",
            event_type="MODE_CHANGED",
            message=f"Mode changed to: {mode}",
            data={"mode": mode}
        )
    
    def frame_received(self, frame_number: int) -> Event:
        """Create frame event (for debugging, usually not broadcast)."""
        return self.create_event(
            category="CAMERA",
            event_type="FRAME_RECEIVED",
            message=f"Frame {frame_number} received",
            data={"frame_number": frame_number}
        )


# Global instance
event_service = EventService()
