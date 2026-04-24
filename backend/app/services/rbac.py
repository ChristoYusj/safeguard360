"""
Role-based access control helpers.
"""
from __future__ import annotations

from app.config.settings import get_settings


ADMIN_ROLE = "admin"
FLEET_OPERATOR_ROLE = "fleet_operator"
SAFETY_OPERATOR_ROLE = "safety_operator"
GENERAL_MANAGER_ROLE = "general_manager"

ALL_USER_ROLES = {
    ADMIN_ROLE,
    FLEET_OPERATOR_ROLE,
    SAFETY_OPERATOR_ROLE,
    GENERAL_MANAGER_ROLE,
}

SELF_SERVICE_REGISTRATION_ROLES = {
    FLEET_OPERATOR_ROLE,
    SAFETY_OPERATOR_ROLE,
    GENERAL_MANAGER_ROLE,
}

USER_STATUS_PENDING = "pending"
USER_STATUS_ACTIVE = "active"
USER_STATUS_REJECTED = "rejected"
USER_STATUS_RESTRICTED = "restricted"

ALL_USER_STATUSES = {
    USER_STATUS_PENDING,
    USER_STATUS_ACTIVE,
    USER_STATUS_REJECTED,
    USER_STATUS_RESTRICTED,
}

ROLE_LABELS = {
    ADMIN_ROLE: "Admin",
    FLEET_OPERATOR_ROLE: "Fleet Operator",
    SAFETY_OPERATOR_ROLE: "Safety Operator",
    GENERAL_MANAGER_ROLE: "General Manager",
}

def normalize_user_role(role: str | None) -> str | None:
    normalized = (role or "").strip().lower()
    return normalized or None


def normalize_user_status(status: str | None) -> str | None:
    normalized = (status or "").strip().lower()
    return normalized or None


def is_valid_self_service_role(role: str | None) -> bool:
    return normalize_user_role(role) in SELF_SERVICE_REGISTRATION_ROLES


def get_role_label(role: str | None) -> str:
    normalized = normalize_user_role(role)
    return ROLE_LABELS.get(normalized, "Operator")


def derive_legacy_role(role: str | None, email: str | None) -> str:
    normalized_role = normalize_user_role(role)
    normalized_email = (email or "").strip().lower()
    if normalized_email and normalized_email == (get_settings().ADMIN_EMAIL or "").strip().lower():
        return ADMIN_ROLE
    if normalized_role in ALL_USER_ROLES:
        return normalized_role

    legacy = (role or "").strip().lower()
    if "fleet" in legacy or "driver" in legacy or "transport" in legacy:
        return FLEET_OPERATOR_ROLE
    if "safety" in legacy or "attendance" in legacy or "security" in legacy:
        return SAFETY_OPERATOR_ROLE
    if "manager" in legacy or "supervisor" in legacy or "operations" in legacy:
        return GENERAL_MANAGER_ROLE
    return GENERAL_MANAGER_ROLE


def has_api_role_access(role: str | None, path: str, method: str) -> bool:
    normalized_role = normalize_user_role(role)
    if normalized_role not in ALL_USER_ROLES:
        return False
    if normalized_role == ADMIN_ROLE:
        return True

    upper_method = (method or "GET").upper()

    if path.startswith("/api/admin/"):
        return False

    if path.startswith("/api/auth/"):
        return True

    if path.startswith("/api/camera/"):
        return True

    if path.startswith("/api/attendance"):
        return normalized_role in {SAFETY_OPERATOR_ROLE, GENERAL_MANAGER_ROLE}

    if path.startswith("/api/persons/recognizer"):
        return normalized_role in {SAFETY_OPERATOR_ROLE, GENERAL_MANAGER_ROLE}

    if path == "/api/persons":
        if upper_method == "GET":
            return normalized_role in {SAFETY_OPERATOR_ROLE, GENERAL_MANAGER_ROLE}
        return False

    if path.startswith("/api/persons/"):
        return False

    if path.startswith("/api/events") or path.startswith("/api/alerts"):
        return normalized_role in {FLEET_OPERATOR_ROLE, GENERAL_MANAGER_ROLE}

    # AI Safety Assistant is available to any authenticated operator — it
    # only reads aggregate site state (counts + recent events) and never
    # mutates anything.
    if path.startswith("/api/chatbot"):
        return True

    return False
