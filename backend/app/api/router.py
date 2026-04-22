"""
Main API Router
"""
from fastapi import APIRouter
from app.api.admin_audit import router as admin_audit_router
from app.api.admin_users import router as admin_users_router
from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.camera import router as camera_router
from app.api.chatbot import router as chatbot_router
from app.api.persons import router as persons_router
from app.api.attendance import router as attendance_router
from app.api.events import router as events_router

api_router = APIRouter()

# Include sub-routers
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(admin_users_router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_audit_router, prefix="/admin", tags=["admin"])
api_router.include_router(camera_router, prefix="/camera", tags=["camera"])
api_router.include_router(persons_router, prefix="/persons", tags=["persons"])
api_router.include_router(attendance_router, prefix="/attendance", tags=["attendance"])
api_router.include_router(events_router, prefix="/events", tags=["events"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["alerts"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
