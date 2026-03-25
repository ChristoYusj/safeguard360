"""
FastAPI Application Factory
"""
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.websocket.manager import setup_websocket, manager
from app.db.connection import init_db
from app.camera.manager import camera_manager


async def frame_broadcaster():
    """Background task to broadcast frames and driver events."""
    print("[Broadcaster] Started")
    frame_count = 0
    while True:
        try:
            if camera_manager.running:
                frame_b64 = camera_manager.get_latest_frame()
                if frame_b64 and len(manager.live_connections) > 0:
                    await manager.broadcast_frame(frame_b64)
                    frame_count += 1
                    if frame_count % 100 == 0:
                        print(f"[Broadcaster] Sent {frame_count} frames")

                # Broadcast camera status less frequently (every 4th frame)
                if frame_count % 4 == 0:
                    state = camera_manager.get_state()
                    status_data = state.__dict__.copy()

                    # Include driver state if in driver mode
                    if camera_manager.mode == "driver":
                        status_data["driver"] = camera_manager.get_driver_state()

                    await manager.broadcast_status(status_data)

                # Broadcast any pending driver events
                driver_events = camera_manager.get_pending_driver_events()
                for event in driver_events:
                    await manager.broadcast_event({
                        "type": "driver_event",
                        "event_type": event.event_type,
                        "timestamp": event.timestamp,
                        "confidence": event.confidence,
                        "details": event.details
                    })

            await asyncio.sleep(0.033)  # ~30 FPS broadcast rate
        except Exception as e:
            print(f"[Broadcaster] Error: {e}")
            await asyncio.sleep(1)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    print("[App] Creating FastAPI application")
    
    app = FastAPI(
        title="SafeGuard 360",
        description="Local-first industrial safety monitoring system",
        version="0.1.0"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(api_router, prefix="/api")
    
    # Setup WebSocket
    setup_websocket(app)
    
    @app.on_event("startup")
    async def startup():
        print("[App] Startup event")
        init_db()
        # Start frame broadcaster
        asyncio.create_task(frame_broadcaster())
        print("[App] Ready")
    
    @app.on_event("shutdown")
    async def shutdown():
        print("[App] Shutdown event")
        camera_manager.stop()
    
    return app
