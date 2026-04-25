export function getApiBase() {
  const envBase = import.meta.env.VITE_API_BASE_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }
  return "/api";
}

export function getBackendWsBase() {
  const envBase = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (envBase) {
    return envBase.replace(/\/$/, "");
  }

  if (typeof window === "undefined") {
    return "";
  }

  const { protocol, host } = window.location;
  const wsProtocol = protocol === "https:" ? "wss:" : "ws:";
  return `${wsProtocol}//${host}`;
}

const API_BASE = getApiBase();
const DEFAULT_FETCH_OPTIONS = {
  credentials: "include",
};
let refreshRequest = null;

function buildCameraOwner(moduleName) {
  if (!moduleName) {
    return null;
  }

  if (typeof window === "undefined") {
    return {
      owner_module: moduleName,
      owner_token: `server-${moduleName}`,
    };
  }

  const storageKey = `safeguard360-camera-owner:${moduleName}`;
  let ownerToken =
    window.localStorage.getItem(storageKey) ||
    window.sessionStorage.getItem(storageKey);
  if (!ownerToken) {
    ownerToken = `${moduleName}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
  window.localStorage.setItem(storageKey, ownerToken);
  window.sessionStorage.setItem(storageKey, ownerToken);

  return {
    owner_module: moduleName,
    owner_token: ownerToken,
  };
}

async function readJsonResponse(res) {
  const rawText = await res.text();
  let data = null;

  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      throw new Error(`Backend returned invalid JSON (${res.status})`);
    }
  }

  if (!res.ok) {
    // FastAPI validation errors come back as `{detail: [{loc, msg, type}, ...]}`.
    // Turn those into a readable sentence instead of the default Array→Object
    // stringification that renders as "[object Object]".
    const detail = data?.detail;
    let message = null;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item) => {
          if (!item || typeof item !== "object") return String(item);
          const field = Array.isArray(item.loc)
            ? item.loc.filter((segment) => segment !== "body").join(".")
            : "";
          const base = item.msg || item.type || "Validation error";
          return field ? `${field}: ${base}` : base;
        })
        .join("; ");
    } else if (detail && typeof detail === "object") {
      message = detail.message || JSON.stringify(detail);
    }
    if (!message) {
      message =
        data?.message ||
        data?.error ||
        rawText ||
        `Request failed with status ${res.status}`;
    }
    const error = new Error(message);
    if (data && typeof data === "object") {
      Object.assign(error, data);
    }
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      Object.assign(error, detail);
    }
    error.status = res.status;
    throw error;
  }

  if (data === null) {
    throw new Error("Backend returned an empty response");
  }

  return data;
}

async function refreshOperatorSessionRequest() {
  if (!refreshRequest) {
    refreshRequest = fetch(`${API_BASE}/auth/refresh`, {
      ...DEFAULT_FETCH_OPTIONS,
      method: "POST",
    })
      .then(readJsonResponse)
      .finally(() => {
        refreshRequest = null;
      });
  }

  return refreshRequest;
}

async function fetchJson(path, init = {}, { retryOnAuth = true } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...DEFAULT_FETCH_OPTIONS,
    ...init,
  });

  if (res.status === 401 && retryOnAuth) {
    try {
      await refreshOperatorSessionRequest();
    } catch {
      return readJsonResponse(res);
    }

    const retryResponse = await fetch(`${API_BASE}${path}`, {
      ...DEFAULT_FETCH_OPTIONS,
      ...init,
    });
    return readJsonResponse(retryResponse);
  }

  return readJsonResponse(res);
}

export async function loginOperator(data) {
  return fetchJson("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }, { retryOnAuth: false });
}

export async function registerOperator(data) {
  return fetchJson("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }, { retryOnAuth: false });
}

export async function requestPasswordReset(data) {
  return fetchJson("/auth/password-reset/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }, { retryOnAuth: false });
}

export async function confirmPasswordReset(data) {
  return fetchJson("/auth/password-reset/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }, { retryOnAuth: false });
}

export async function changeOperatorPassword(data) {
  return fetchJson("/auth/password/change", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function verifyTwoFactorLogin(data) {
  return fetchJson("/auth/2fa/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }, { retryOnAuth: false });
}

export async function startTwoFactorSetup() {
  return fetchJson("/auth/2fa/setup", { method: "POST" });
}

export async function confirmTwoFactorEnable(data) {
  return fetchJson("/auth/2fa/enable", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function disableTwoFactorAuth(data) {
  return fetchJson("/auth/2fa/disable", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function getCurrentOperator() {
  return fetchJson("/auth/me", {}, { retryOnAuth: false });
}

export async function refreshOperatorSession() {
  return refreshOperatorSessionRequest();
}

export async function logoutOperator() {
  return fetchJson("/auth/logout", { method: "POST" }, { retryOnAuth: false });
}

export async function getAdminUsers() {
  return fetchJson("/admin/users");
}

export async function getAuditLogs(params = {}) {
  const query = new URLSearchParams();
  if (params.event_type) {
    query.set("event_type", params.event_type);
  }
  if (params.date_from) {
    query.set("date_from", params.date_from);
  }
  if (params.date_to) {
    query.set("date_to", params.date_to);
  }
  if (params.limit) {
    query.set("limit", String(params.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return fetchJson(`/admin/audit-logs${suffix}`);
}

export async function clearAuditLogs() {
  return fetchJson("/admin/audit-logs", {
    method: "DELETE",
  });
}

export async function updateAdminUser(userId, data) {
  return fetchJson(`/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function unlockAdminUser(userId) {
  return fetchJson(`/admin/users/${userId}/unlock`, {
    method: "POST",
  });
}

export async function deleteAdminUser(userId) {
  return fetchJson(`/admin/users/${userId}`, {
    method: "DELETE",
  });
}

// Camera endpoints
export async function getCameraSources() {
  return fetchJson("/camera/sources");
}

export function getCameraOwner(moduleName) {
  return buildCameraOwner(moduleName);
}

export async function startCamera(sourceType, sourceId = "", owner = null) {
  return fetchJson("/camera/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_type: sourceType,
      source_id: sourceId,
      ...(owner || {}),
    }),
  });
}

export async function stopCamera(owner = null) {
  const requestInit = owner
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(owner),
      }
    : { ...DEFAULT_FETCH_OPTIONS, method: "POST" };
  return fetchJson("/camera/stop", requestInit);
}

export async function getCameraState() {
  return fetchJson("/camera/state");
}

export async function setCameraMode(mode, owner = null) {
  const requestInit = owner
    ? {
        ...DEFAULT_FETCH_OPTIONS,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(owner),
      }
    : { ...DEFAULT_FETCH_OPTIONS, method: "POST" };
  return fetchJson(`/camera/mode/${mode}`, requestInit);
}

export async function getAttendance({ limit = 50, personId } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (personId) {
    params.set("person_id", personId);
  }

  return fetchJson(`/attendance?${params.toString()}`);
}

export async function clearAttendanceLogs() {
  return fetchJson("/attendance/logs", {
    method: "DELETE",
  });
}

export async function getAttendanceReviews(statusFilter = "all", { limit = 50 } = {}) {
  return fetchJson(
    `/attendance/reviews?status_filter=${encodeURIComponent(statusFilter)}&limit=${encodeURIComponent(limit)}`,
  );
}

export async function getAttendanceGateMode() {
  return fetchJson("/attendance/gate-mode");
}

export async function getAttendancePpePolicy() {
  return fetchJson("/attendance/ppe-policy");
}

export async function updateAttendancePpePolicy(data) {
  return fetchJson("/attendance/ppe-policy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function setAttendanceGateMode(directionMode) {
  return fetchJson("/attendance/gate-mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction_mode: directionMode }),
  });
}

export async function decideAttendanceReview(reviewId, data) {
  return fetchJson(`/attendance/reviews/${reviewId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function getEvents(category) {
  const query = new URLSearchParams();
  if (category) {
    query.set("category", category);
  }
  return fetchJson(`/events${query.toString() ? `?${query.toString()}` : ""}`);
}

export async function getAlerts() {
  return fetchJson("/alerts");
}

export async function acknowledgeAlert(id) {
  return fetchJson(`/alerts/${id}/ack`, { method: "POST" });
}

export async function getPersons({ includeInactive = false } = {}) {
  const query = includeInactive ? "?include_inactive=true" : "";
  return fetchJson(`/persons${query}`);
}

export async function getRecognizerStatus() {
  return fetchJson("/persons/recognizer");
}

export async function enrollPerson(data) {
  return fetchJson("/persons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updatePerson(id, data) {
  return fetchJson(`/persons/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function enrollPersonWithMedia({ name, employeeId, shiftId, files }) {
  const formData = new FormData();
  formData.append("name", name);
  if (employeeId) {
    formData.append("employee_id", employeeId);
  }
  if (shiftId) {
    formData.append("shift_id", shiftId);
  }
  for (const file of files) {
    formData.append("files", file, file.name);
  }

  return fetchJson("/persons/enroll-media", {
    method: "POST",
    body: formData,
  });
}

export async function updatePersonEnrollmentMedia({
  personId,
  name,
  employeeId,
  shiftId,
  mergeMode,
  files,
}) {
  const formData = new FormData();
  formData.append("name", name);
  formData.append("employee_id", employeeId || "");
  if (shiftId) {
    formData.append("shift_id", shiftId);
  }
  formData.append("merge_mode", mergeMode || "append");
  for (const file of files) {
    formData.append("files", file, file.name);
  }

  return fetchJson(`/persons/${personId}/enroll-media`, {
    method: "POST",
    body: formData,
  });
}

export async function deletePerson(id) {
  return fetchJson(`/persons/${id}`, { method: "DELETE" });
}

export async function bulkImportPersons(file) {
  const formData = new FormData();
  formData.append("file", file, file.name);
  return fetchJson("/persons/bulk-import", {
    method: "POST",
    body: formData,
  });
}

// AI Safety Chatbot endpoints
export async function getChatbotStatus() {
  return fetchJson("/chatbot/status");
}

export async function getChatbotContext() {
  return fetchJson("/chatbot/context");
}

export async function sendChatbotMessage(messages, clientContext = {}) {
  return fetchJson("/chatbot/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, client_context: clientContext }),
  });
}
