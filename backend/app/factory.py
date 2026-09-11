"""
FastAPI Application Factory
"""
import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.websocket.manager import setup_websocket, manager
from app.db.connection import init_db
from app.camera.manager import camera_manager
from app.config.settings import get_settings
from app.middleware.auth import OperatorAuthMiddleware

logger = logging.getLogger(__name__)

# How long the broadcaster waits between passes when no websocket client is
# connected. Pending camera events are still drained on this slower cadence so
# their queues cannot grow without bound.
IDLE_BROADCAST_INTERVAL = 0.25


async def frame_broadcaster():
    """Background task to broadcast frames and driver events."""
    frame_count = 0
    last_broadcast_sequence = -1
    last_status_sent_at = 0.0
    status_interval_seconds = 0.6
    while True:
        try:
            # Nobody watching means nothing to deliver. The camera keeps
            # capturing and recognising in its own threads either way; this
            # loop just stops waking 50 times a second to find no audience.
            has_clients = bool(manager.live_connections or manager.events_connections)
            if camera_manager.running:
                frame_packet = camera_manager.get_latest_frame_packet()
                if frame_packet and len(manager.live_connections) > 0:
                    frame_sequence, frame_bytes = frame_packet
                    if frame_sequence != last_broadcast_sequence:
                        await manager.broadcast_frame(frame_bytes)
                        last_broadcast_sequence = frame_sequence
                        frame_count += 1

                now = time.monotonic()
                if manager.events_connections and now - last_status_sent_at >= status_interval_seconds:
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

            await asyncio.sleep(0.02 if has_clients else IDLE_BROADCAST_INTERVAL)
        except Exception:
            logger.exception("Frame broadcaster error.")
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own the process-level resources for the app's lifetime.

    Startup: create/migrate the database, then start the frame broadcaster.
    Shutdown: cancel the broadcaster and release the camera. Running this from
    the lifespan (rather than on_event hooks) means TestClient exercises the
    same startup and teardown the real server does.
    """
    init_db()
    broadcaster = asyncio.create_task(frame_broadcaster())
    try:
        yield
    finally:
        broadcaster.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await broadcaster
        camera_manager.stop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    missing_auth_settings = settings.missing_required_auth_settings
    if missing_auth_settings:
        raise RuntimeError(
            "Missing required auth configuration: "
            + ", ".join(sorted(missing_auth_settings))
        )

    app = FastAPI(
        title="SafeGuard 360",
        description="Local-first industrial safety monitoring system",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
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

    return app
