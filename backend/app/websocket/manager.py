"""
WebSocket Connection Manager
"""
from http.cookies import SimpleCookie
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Set
import asyncio
import json

from app.db.connection import SessionLocal
from app.services.auth import ACCESS_COOKIE_NAME, get_user_by_access_token


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.live_connections: Set[WebSocket] = set()
        self.events_connections: Set[WebSocket] = set()
        print("[WebSocketManager] Initialized")
    
    async def connect_live(self, websocket: WebSocket):
        await websocket.accept()
        self.live_connections.add(websocket)
        print(f"[WebSocketManager] Live client connected. Total: {len(self.live_connections)}")
        try:
            from app.camera.manager import camera_manager

            latest_frame = camera_manager.get_latest_frame()
            if latest_frame:
                await websocket.send_text(json.dumps({
                    "type": "frame",
                    "data": latest_frame,
                }))
        except Exception as e:
            print(f"[WebSocketManager] Failed to send initial live frame: {e}")

    async def connect_events(self, websocket: WebSocket):
        await websocket.accept()
        self.events_connections.add(websocket)
        print(f"[WebSocketManager] Events client connected. Total: {len(self.events_connections)}")
        try:
            from app.camera.manager import camera_manager

            state = camera_manager.get_state().__dict__.copy()
            if camera_manager.mode == "driver":
                state["driver"] = camera_manager.get_driver_state()
            elif camera_manager.mode == "gate":
                state["gate"] = camera_manager.get_gate_state()
            await websocket.send_text(json.dumps({
                "type": "status",
                "camera": state,
            }))
        except Exception as e:
            print(f"[WebSocketManager] Failed to send initial status: {e}")
    
    def disconnect_live(self, websocket: WebSocket):
        self.live_connections.discard(websocket)
        print(f"[WebSocketManager] Live client disconnected. Total: {len(self.live_connections)}")
    
    def disconnect_events(self, websocket: WebSocket):
        self.events_connections.discard(websocket)
        print(f"[WebSocketManager] Events client disconnected. Total: {len(self.events_connections)}")
    
    async def broadcast_frame(self, frame_b64: str):
        """Broadcast frame to all live connections."""
        if not self.live_connections:
            return
        
        message = json.dumps({
            "type": "frame",
            "data": frame_b64
        })
        
        dead = set()
        for ws in self.live_connections:
            try:
                await ws.send_text(message)
            except Exception as e:
                print(f"[WebSocketManager] Send error: {e}")
                dead.add(ws)
        
        self.live_connections -= dead
    
    async def broadcast_status(self, status: dict):
        """Broadcast status to events connections."""
        if not self.events_connections:
            return
        
        message = json.dumps({
            "type": "status",
            "camera": status
        })
        
        dead = set()
        for ws in self.events_connections:
            try:
                await ws.send_text(message)
            except Exception as e:
                print(f"[WebSocketManager] Send error: {e}")
                dead.add(ws)
        
        self.events_connections -= dead
    
    async def broadcast_event(self, event: dict):
        """Broadcast an event to events connections."""
        if not self.events_connections:
            return
        
        message = json.dumps(event)
        print(f"[WebSocketManager] Broadcasting event: {event.get('type', 'unknown')}")
        
        dead = set()
        for ws in self.events_connections:
            try:
                await ws.send_text(message)
            except Exception as e:
                print(f"[WebSocketManager] Send error: {e}")
                dead.add(ws)
        
        self.events_connections -= dead


# Global manager
manager = ConnectionManager()


async def _authenticate_websocket(websocket: WebSocket) -> bool:
    cookie_header = websocket.headers.get("cookie", "")
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(ACCESS_COOKIE_NAME)
    token = morsel.value if morsel else None

    db = SessionLocal()
    try:
        get_user_by_access_token(db, token)
        return True
    except Exception:
        await websocket.close(code=1008, reason="Authentication required.")
        return False
    finally:
        db.close()


def setup_websocket(app: FastAPI):
    """Setup WebSocket routes."""
    
    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket):
        print("[WebSocket] /ws/live connection request")
        if not await _authenticate_websocket(websocket):
            return
        await manager.connect_live(websocket)
        try:
            while True:
                # Use receive() to handle any message type (text, bytes, ping/pong)
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[WebSocket] Live error: {e}")
        finally:
            manager.disconnect_live(websocket)
    
    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        print("[WebSocket] /ws/events connection request")
        if not await _authenticate_websocket(websocket):
            return
        await manager.connect_events(websocket)
        try:
            while True:
                # Use receive() to handle any message type (text, bytes, ping/pong)
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[WebSocket] Events error: {e}")
        finally:
            manager.disconnect_events(websocket)
