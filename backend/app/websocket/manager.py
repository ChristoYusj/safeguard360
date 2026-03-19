"""
WebSocket Connection Manager
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Set
import asyncio
import json


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
    
    async def connect_events(self, websocket: WebSocket):
        await websocket.accept()
        self.events_connections.add(websocket)
        print(f"[WebSocketManager] Events client connected. Total: {len(self.events_connections)}")
    
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


def setup_websocket(app: FastAPI):
    """Setup WebSocket routes."""
    
    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket):
        print("[WebSocket] /ws/live connection request")
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
