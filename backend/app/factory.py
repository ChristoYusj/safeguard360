"""
FastAPI Application Factory
"""
import asyncio
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.websocket.manager import setup_websocket, manager
from app.db.connection import init_db
from app.camera.manager import camera_manager
from app.config.settings import get_settings
from app.middleware.auth import OperatorAuthMiddleware


async def frame_broadcaster():
    """Background task to broadcast frames and driver events."""
    print("[Broadcaster] Started")
    frame_count = 0
    last_broadcast_sequence = -1
    last_status_sent_at = 0.0
    status_interval_seconds = 0.6
    while True:
        try:
            if camera_manager.running:
                frame_packet = camera_manager.get_latest_frame_packet()
                if frame_packet and len(manager.live_connections) > 0:
                    frame_sequence, frame_b64 = frame_packet
                    if frame_sequence != last_broadcast_sequence:
                        await manager.broadcast_frame(frame_b64)
                        last_broadcast_sequence = frame_sequence
                        frame_count += 1
                        if frame_count % 100 == 0:
                            print(f"[Broadcaster] Sent {frame_count} frames")

                now = time.monotonic()
                if now - last_status_sent_at >= status_interval_seconds:
                    state = camera_manager.get_state()
                    status_data = state.__dict__.copy()

                    # Include driver state if in driver mode
                    if camera_manager.mode == "driver":
                        status_data["driver"] = camera_manager.get_driver_state()
                    elif camera_manager.mode == "gate":
                        status_data["gate"] = camera_manager.get_gate_state()

                    await manager.broadcast_status(status_data)
                    last_status_sent_at = now

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

                gate_events = camera_manager.get_pending_gate_events()
                for event in gate_events:
                    await manager.broadcast_event({
                        "type": "attendance_match",
                        "event_type": event.event_type,
                        "timestamp": event.timestamp,
                        "confidence": event.confidence,
                        "details": event.details,
                        "person_id": event.person_id,
                        "person_name": event.person_name,
                        "access_granted": event.access_granted,
                        "ppe_compliant": event.ppe_compliant,
                        "ppe_status": event.ppe_status,
                        "ppe_details": event.ppe_details,
                        "review_reasons": event.review_reasons,
                    })

            await asyncio.sleep(0.02)
        except Exception as e:
            print(f"[Broadcaster] Error: {e}")
            await asyncio.sleep(1)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    print("[App] Creating FastAPI application")
    settings = get_settings()

    app = FastAPI(
        title="SafeGuard 360",
        description="Local-first industrial safety monitoring system",
        version="0.1.0"
    )

    app.add_middleware(OperatorAuthMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
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
