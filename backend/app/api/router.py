"""
Main API Router
"""
from fastapi import APIRouter
from app.api.alerts import router as alerts_router
from app.api.status import router as status_router
from app.api.camera import router as camera_router
from app.api.persons import router as persons_router
from app.api.attendance import router as attendance_router
from app.api.events import router as events_router

api_router = APIRouter()

# Include sub-routers
api_router.include_router(status_router, tags=["status"])
api_router.include_router(camera_router, prefix="/camera", tags=["camera"])
api_router.include_router(persons_router, prefix="/persons", tags=["persons"])
api_router.include_router(attendance_router, prefix="/attendance", tags=["attendance"])
api_router.include_router(events_router, prefix="/events", tags=["events"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
