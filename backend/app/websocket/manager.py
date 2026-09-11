"""
WebSocket Connection Manager
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from http.cookies import SimpleCookie
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.db.connection import SessionLocal
from app.services.auth import ACCESS_COOKIE_NAME, get_user_by_access_token
from app.services.rbac import role_can_see_domain

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.live_connections: Set[WebSocket] = set()
        self.events_connections: Set[WebSocket] = set()
        self.live_connection_roles: Dict[WebSocket, str] = {}
        self.events_connection_roles: Dict[WebSocket, str] = {}
        self.live_frame_send_timeout_seconds = 0.05
        self.live_frame_send_last_ms = 0.0
        self.live_frame_send_avg_ms = 0.0
        self.live_frame_slow_drop_count = 0
        self.live_frame_sent_count = 0

    def _record_live_send_duration(self, duration_ms: float, *, alpha: float = 0.18) -> None:
        self.live_frame_send_last_ms = round(duration_ms, 3)
        if self.live_frame_send_avg_ms == 0.0:
            self.live_frame_send_avg_ms = round(duration_ms, 3)
        else:
            self.live_frame_send_avg_ms = round(
                (self.live_frame_send_avg_ms * (1.0 - alpha)) + (duration_ms * alpha),
                3,
            )

    def get_live_debug_snapshot(self) -> dict:
        return {
            "live_connections": len(self.live_connections),
            "events_connections": len(self.events_connections),
            "frame_send_ms_last": self.live_frame_send_last_ms,
            "frame_send_ms_avg": self.live_frame_send_avg_ms,
            "frame_slow_drop_count": self.live_frame_slow_drop_count,
            "frame_sent_count": self.live_frame_sent_count,
        }

    @staticmethod
    def _can_receive_domain(role: str | None, domain: str) -> bool:
        if domain == "generic":
            return True
        return role_can_see_domain(role, domain)

    @staticmethod
    def _classify_status_domain(status: dict) -> str:
        # The owning module decides the domain even while the mode is still
        # "idle" (between start and the mode call, or with recognition paused);
        # classifying by mode alone streamed the gate camera to fleet operators
        # during those windows.
        owner_module = (status or {}).get("owner_module")
        if owner_module == "attendance":
            return "gate"
        if owner_module == "drivers":
            return "driver"
        mode = (status or {}).get("mode")
        if mode == "driver":
            return "driver"
        if mode == "gate":
            return "gate"
        return "generic"

    @staticmethod
    def _classify_event_domain(event: dict) -> str:
        event_type = (event or {}).get("type")
        if event_type == "driver_event":
            return "driver"
        if event_type == "attendance_match":
            return "gate"
        return "generic"
    
    async def connect_live(self, websocket: WebSocket, role: str | None):
        await websocket.accept()
        self.live_connections.add(websocket)
        self.live_connection_roles[websocket] = role or ""
        try:
            from app.camera.manager import camera_manager

            latest_frame = camera_manager.get_latest_frame()
            current_domain = self._classify_status_domain(
                {"mode": camera_manager.mode, "owner_module": camera_manager.owner_module}
            )
            if latest_frame and self._can_receive_domain(role, current_domain):
                await websocket.send_bytes(latest_frame)
        except Exception:
            logger.exception("Failed to send initial live frame.")

    async def connect_events(self, websocket: WebSocket, role: str | None):
        await websocket.accept()
        self.events_connections.add(websocket)
        self.events_connection_roles[websocket] = role or ""
        try:
            from app.camera.manager import camera_manager

            state = camera_manager.get_state().__dict__.copy()
            if camera_manager.mode == "driver":
                state["driver"] = camera_manager.get_driver_state()
            elif camera_manager.mode == "gate":
                state["gate"] = camera_manager.get_gate_state()
            if self._can_receive_domain(role, self._classify_status_domain(state)):
                await websocket.send_text(json.dumps({
                    "type": "status",
                    "camera": state,
                }))
        except Exception:
            logger.exception("Failed to send initial status.")
    
    def disconnect_live(self, websocket: WebSocket):
        self.live_connections.discard(websocket)
        self.live_connection_roles.pop(websocket, None)

    def disconnect_events(self, websocket: WebSocket):
        self.events_connections.discard(websocket)
        self.events_connection_roles.pop(websocket, None)

    def _drop_live(self, dead: Set[WebSocket]) -> None:
        """Forget sockets that failed a send, roles included.

        The role maps used to keep an entry for every socket ever dropped
        mid-broadcast, because only the connection set was pruned. On a long
        shift that is a slow leak keyed by dead WebSocket objects.
        """
        for websocket in dead:
            self.disconnect_live(websocket)

    def _drop_events(self, dead: Set[WebSocket]) -> None:
        for websocket in dead:
            self.disconnect_events(websocket)

    async def broadcast_frame(self, frame_bytes: bytes):
        """Broadcast a raw JPEG frame to all live connections."""
        if not self.live_connections:
            return

        from app.camera.manager import camera_manager
        frame_domain = self._classify_status_domain(
                {"mode": camera_manager.mode, "owner_module": camera_manager.owner_module}
            )

        dead = set()
        # Iterate a snapshot: every send below awaits, and a client that
        # disconnects during one of those awaits mutates this set from the
        # endpoint coroutine, which used to raise "Set changed size during
        # iteration" and abort the whole broadcast for everyone else.
        for ws in list(self.live_connections):
            try:
                role = self.live_connection_roles.get(ws)
                if not self._can_receive_domain(role, frame_domain):
                    continue
                started_at = time.perf_counter()
                await asyncio.wait_for(
                    ws.send_bytes(frame_bytes),
                    timeout=self.live_frame_send_timeout_seconds,
                )
                self._record_live_send_duration((time.perf_counter() - started_at) * 1000.0)
                self.live_frame_sent_count += 1
            except asyncio.TimeoutError:
                logger.warning("Dropping slow live WebSocket client during frame broadcast.")
                self.live_frame_slow_drop_count += 1
                dead.add(ws)
            except Exception:
                logger.exception("WebSocket live send error.")
                dead.add(ws)
        
        self._drop_live(dead)
    
    async def broadcast_status(self, status: dict):
        """Broadcast status to events connections."""
        if not self.events_connections:
            return

        domain = self._classify_status_domain(status)
        
        message = json.dumps({
            "type": "status",
            "camera": status
        })
        
        dead = set()
        # Snapshot for the same reason as broadcast_frame: send_text awaits.
        for ws in list(self.events_connections):
            try:
                role = self.events_connection_roles.get(ws)
                if not self._can_receive_domain(role, domain):
                    continue
                await ws.send_text(message)
            except Exception:
                logger.exception("WebSocket status send error.")
                dead.add(ws)

        self._drop_events(dead)
    
    async def broadcast_event(self, event: dict):
        """Broadcast an event to events connections."""
        if not self.events_connections:
            return

        domain = self._classify_event_domain(event)
        
        message = json.dumps(event)
        
        dead = set()
        for ws in list(self.events_connections):
            try:
                role = self.events_connection_roles.get(ws)
                if not self._can_receive_domain(role, domain):
                    continue
                await ws.send_text(message)
            except Exception:
                logger.exception("WebSocket event send error.")
                dead.add(ws)

        self._drop_events(dead)


# Global manager
manager = ConnectionManager()


async def _authenticate_websocket(websocket: WebSocket) -> str | None:
    cookie_header = websocket.headers.get("cookie", "")
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(ACCESS_COOKIE_NAME)
    token = morsel.value if morsel else None

    db = SessionLocal()
    try:
        user, _ = get_user_by_access_token(db, token)
        return getattr(user, "role", None)
    except Exception:
        await websocket.close(code=1008, reason="Authentication required.")
        return None
    finally:
        db.close()


def setup_websocket(app: FastAPI):
    """Setup WebSocket routes."""
    
    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket):
        role = await _authenticate_websocket(websocket)
        if not role:
            return
        await manager.connect_live(websocket, role)
        try:
            while True:
                # Use receive() to handle any message type (text, bytes, ping/pong)
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Live websocket error.")
        finally:
            manager.disconnect_live(websocket)
    
    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        role = await _authenticate_websocket(websocket)
        if not role:
            return
        await manager.connect_events(websocket, role)
        try:
            while True:
                # Use receive() to handle any message type (text, bytes, ping/pong)
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Events websocket error.")
        finally:
            manager.disconnect_events(websocket)
