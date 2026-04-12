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
    const message =
      data?.detail ||
      data?.message ||
      data?.error ||
      rawText ||
      `Request failed with status ${res.status}`;
    throw new Error(message);
  }

  if (data === null) {
    throw new Error("Backend returned an empty response");
  }

  return data;
}

export async function getStatus() {
  const res = await fetch(`${API_BASE}/status`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export async function loginOperator(data) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
}

export async function getCurrentOperator() {
  const res = await fetch(`${API_BASE}/auth/me`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export async function logoutOperator() {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
  });
  return readJsonResponse(res);
}

export async function switchMode(mode) {
  const res = await fetch(`${API_BASE}/mode`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  return readJsonResponse(res);
}

// Camera endpoints
export async function getCameraSources() {
  const res = await fetch(`${API_BASE}/camera/sources`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export function getCameraOwner(moduleName) {
  return buildCameraOwner(moduleName);
}

export async function startCamera(sourceType, sourceId = "", owner = null) {
  const res = await fetch(`${API_BASE}/camera/start`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_type: sourceType,
      source_id: sourceId,
      ...(owner || {}),
    }),
  });
  return readJsonResponse(res);
}

export async function stopCamera(owner = null) {
  const requestInit = owner
    ? {
        ...DEFAULT_FETCH_OPTIONS,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(owner),
      }
    : { ...DEFAULT_FETCH_OPTIONS, method: "POST" };
  const res = await fetch(`${API_BASE}/camera/stop`, requestInit);
  return readJsonResponse(res);
}

export async function getCameraState() {
  const res = await fetch(`${API_BASE}/camera/state`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
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
  const res = await fetch(`${API_BASE}/camera/mode/${mode}`, requestInit);
  return readJsonResponse(res);
}

export async function getAttendance({ limit = 50, personId } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (personId) {
    params.set("person_id", personId);
  }

  const res = await fetch(
    `${API_BASE}/attendance?${params.toString()}`,
    DEFAULT_FETCH_OPTIONS,
  );
  return readJsonResponse(res);
}

export async function getAttendanceReviews(statusFilter = "all", { limit = 50 } = {}) {
  const res = await fetch(
    `${API_BASE}/attendance/reviews?status_filter=${encodeURIComponent(statusFilter)}&limit=${encodeURIComponent(limit)}`,
    DEFAULT_FETCH_OPTIONS,
  );
  return readJsonResponse(res);
}

export async function getAttendanceGateMode() {
  const res = await fetch(`${API_BASE}/attendance/gate-mode`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export async function getAttendancePpePolicy() {
  const res = await fetch(`${API_BASE}/attendance/ppe-policy`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export async function updateAttendancePpePolicy(data) {
  const res = await fetch(`${API_BASE}/attendance/ppe-policy`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
}

export async function setAttendanceGateMode(directionMode) {
  const res = await fetch(`${API_BASE}/attendance/gate-mode`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction_mode: directionMode }),
  });
  return readJsonResponse(res);
}

export async function decideAttendanceReview(reviewId, data) {
  const res = await fetch(`${API_BASE}/attendance/reviews/${reviewId}/decision`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
}

export async function getEvents(category) {
  const query = new URLSearchParams();
  if (category) {
    query.set("category", category);
  }
  const res = await fetch(
    `${API_BASE}/events${query.toString() ? `?${query.toString()}` : ""}`,
    DEFAULT_FETCH_OPTIONS,
  );
  return readJsonResponse(res);
}

export async function getAlerts() {
  const res = await fetch(`${API_BASE}/alerts`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export async function acknowledgeAlert(id) {
  const res = await fetch(`${API_BASE}/alerts/${id}/ack`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
  });
  return readJsonResponse(res);
}

export async function getPersons() {
  const res = await fetch(`${API_BASE}/persons`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export async function getRecognizerStatus() {
  const res = await fetch(`${API_BASE}/persons/recognizer`, DEFAULT_FETCH_OPTIONS);
  return readJsonResponse(res);
}

export async function enrollPerson(data) {
  const res = await fetch(`${API_BASE}/persons`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
}

export async function updatePerson(id, data) {
  const res = await fetch(`${API_BASE}/persons/${id}`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
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

  const res = await fetch(`${API_BASE}/persons/enroll-media`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    body: formData,
  });
  return readJsonResponse(res);
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

  const res = await fetch(`${API_BASE}/persons/${personId}/enroll-media`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "POST",
    body: formData,
  });
  return readJsonResponse(res);
}

export async function deletePerson(id) {
  const res = await fetch(`${API_BASE}/persons/${id}`, {
    ...DEFAULT_FETCH_OPTIONS,
    method: "DELETE",
  });
  return readJsonResponse(res);
}
