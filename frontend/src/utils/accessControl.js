export const ROLES = {
  ADMIN: "admin",
  FLEET_OPERATOR: "fleet_operator",
  SAFETY_OPERATOR: "safety_operator",
  GENERAL_MANAGER: "general_manager",
};

export const ROLE_LABELS = {
  [ROLES.ADMIN]: "Admin",
  [ROLES.FLEET_OPERATOR]: "Fleet Operator",
  [ROLES.SAFETY_OPERATOR]: "Safety Operator",
  [ROLES.GENERAL_MANAGER]: "General Manager",
};

export const REGISTRATION_ROLE_OPTIONS = [
  { value: ROLES.FLEET_OPERATOR, label: ROLE_LABELS[ROLES.FLEET_OPERATOR] },
  { value: ROLES.SAFETY_OPERATOR, label: ROLE_LABELS[ROLES.SAFETY_OPERATOR] },
  { value: ROLES.GENERAL_MANAGER, label: ROLE_LABELS[ROLES.GENERAL_MANAGER] },
];

export function getRoleLabel(role) {
  return ROLE_LABELS[role] || "Operator";
}

export function getDefaultRouteForRole(role) {
  if (role === ROLES.FLEET_OPERATOR) {
    return "/drivers";
  }
  if (role === ROLES.SAFETY_OPERATOR) {
    return "/attendance";
  }
  return "/modules";
}

export function canAccessDrivers(role) {
  return [ROLES.ADMIN, ROLES.FLEET_OPERATOR, ROLES.GENERAL_MANAGER].includes(role);
}

export function canAccessAttendance(role) {
  return [ROLES.ADMIN, ROLES.SAFETY_OPERATOR, ROLES.GENERAL_MANAGER].includes(role);
}

export function canAccessLogs(role) {
  return [
    ROLES.ADMIN,
    ROLES.FLEET_OPERATOR,
    ROLES.SAFETY_OPERATOR,
    ROLES.GENERAL_MANAGER,
  ].includes(role);
}

export function canAccessSettings(role) {
  return Boolean(role);
}

export function canAccessAdminSettings(role) {
  return role === ROLES.ADMIN;
}

export function canAccessEnrollment(role) {
  return role === ROLES.ADMIN;
}

export function canAccessUserManagement(role) {
  return role === ROLES.ADMIN;
}

// Mirrors backend/app/services/rbac.py (the enforcing copy): the assistant's
// snapshot names individual workers, so only roles that may read the roster
// and attendance log in full get it.
export function canAccessChatbot(role) {
  return role === ROLES.ADMIN || role === ROLES.GENERAL_MANAGER;
}

// Mirrors backend/app/api/attendance.py update_ppe_policy: switching PPE
// enforcement off is a management decision, not a shift-floor one.
export function canChangePpePolicy(role) {
  return role === ROLES.ADMIN || role === ROLES.GENERAL_MANAGER;
}

export function canAccessPath(role, path) {
  if (!role) {
    return false;
  }
  if (path === "/modules") {
    return true;
  }
  if (path === "/drivers" || path.startsWith("/drivers/")) {
    return canAccessDrivers(role);
  }
  if (path === "/attendance" || path.startsWith("/attendance/") || path === "/ppe") {
    return canAccessAttendance(role);
  }
  if (path === "/logs" || path.startsWith("/logs/")) {
    return canAccessLogs(role);
  }
  if (path === "/settings" || path.startsWith("/settings/")) {
    return canAccessSettings(role);
  }
  if (path === "/enrollment" || path.startsWith("/enrollment/")) {
    return canAccessEnrollment(role);
  }
  if (path === "/user-management" || path.startsWith("/user-management/")) {
    return canAccessUserManagement(role);
  }
  if (path === "/ai-chatbot" || path.startsWith("/ai-chatbot/")) {
    return canAccessChatbot(role);
  }
  // Unknown paths are denied; a new page must be added here deliberately.
  return false;
}
