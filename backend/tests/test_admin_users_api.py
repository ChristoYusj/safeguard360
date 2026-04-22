from __future__ import annotations

from types import SimpleNamespace

from app.api.admin_users import AdminUserUpdateRequest, update_user_account
from app.db.models import AuditLog, User
from app.services.auth import hash_password
from app.services.rbac import ADMIN_ROLE, USER_STATUS_ACTIVE, USER_STATUS_RESTRICTED


def build_request(user: User):
    return SimpleNamespace(
        state=SimpleNamespace(user=user),
        client=SimpleNamespace(host="127.0.0.1"),
    )


def test_admin_can_toggle_operator_access_and_record_audit(db_session):
    admin = User(
        full_name="System Administrator",
        email="admin@example.com",
        role=ADMIN_ROLE,
        role_department="Admin",
        password_hash=hash_password("Admin123!"),
        status=USER_STATUS_ACTIVE,
    )
    operator = User(
        full_name="Safety Operator",
        email="operator@example.com",
        role="safety_operator",
        role_department="Safety Operator",
        password_hash=hash_password("Operator123!"),
        status=USER_STATUS_ACTIVE,
    )
    db_session.add_all([admin, operator])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(operator)

    response = update_user_account(
        operator.id,
        AdminUserUpdateRequest(status=USER_STATUS_RESTRICTED),
        build_request(admin),
        db_session,
    )

    assert response["user"]["status"] == USER_STATUS_RESTRICTED
    updated = db_session.query(User).filter(User.id == operator.id).first()
    assert updated is not None
    assert updated.status == USER_STATUS_RESTRICTED

    audit_entry = db_session.query(AuditLog).filter(AuditLog.operator_email == operator.email).first()
    assert audit_entry is not None
    assert audit_entry.event_type == "account_deactivated"
