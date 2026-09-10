"""
Role-based access control helpers.
"""
from __future__ import annotations


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
    """Canonical role for a stored role/department value.

    The stored role wins. Matching ADMIN_EMAIL used to force `admin` here on
    every call, so a bootstrap admin an administrator had deliberately demoted
    was reported (and re-written at the next restart) as admin. The bootstrap
    account gets its role once, when it is seeded. ``email`` is kept for
    call-site compatibility and no longer influences the result.
    """
    normalized_role = normalize_user_role(role)
    if normalized_role in ALL_USER_ROLES:
        return normalized_role

    legacy = (role or "").strip().lower()
    if "admin" in legacy:
        return ADMIN_ROLE
    if "fleet" in legacy or "driver" in legacy or "transport" in legacy:
        return FLEET_OPERATOR_ROLE
    if "safety" in legacy or "attendance" in legacy or "security" in legacy:
        return SAFETY_OPERATOR_ROLE
    if "manager" in legacy or "supervisor" in legacy or "operations" in legacy:
        return GENERAL_MANAGER_ROLE
    return GENERAL_MANAGER_ROLE


# Event/alert domains. Every persisted event today is gate-side ("PPE");
# driver-side events use category "DRIVER". Safety operators see the gate
# domain, fleet operators the driver domain, managers and admins both.
DRIVER_EVENT_CATEGORIES = frozenset({"DRIVER"})


def event_category_domain(category: str | None) -> str:
    return "driver" if (category or "").strip().upper() in DRIVER_EVENT_CATEGORIES else "gate"


def role_can_see_domain(role: str | None, domain: str) -> bool:
    normalized_role = normalize_user_role(role)
    if normalized_role in {ADMIN_ROLE, GENERAL_MANAGER_ROLE}:
        return True
    if domain == "driver":
        return normalized_role == FLEET_OPERATOR_ROLE
    if domain == "gate":
        return normalized_role == SAFETY_OPERATOR_ROLE
    return False


def visible_event_domains(role: str | None) -> frozenset[str]:
    return frozenset(d for d in ("gate", "driver") if role_can_see_domain(role, d))


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

    # Events and alerts are readable by every operator role; the handlers
    # restrict the rows to the caller's domain (gate vs driver) and check the
    # domain again before an acknowledgement. The old rule granted these to
    # fleet operators and denied safety operators, although every persisted
    # event was a gate-side PPE event.
    if path.startswith("/api/events") or path.startswith("/api/alerts"):
        return True

    # The assistant's site snapshot names individual workers (who is on site,
    # recent gate activity), so it is limited to the roles that may read the
    # roster and attendance log in full.
    if path.startswith("/api/chatbot"):
        return normalized_role == GENERAL_MANAGER_ROLE

    return False
