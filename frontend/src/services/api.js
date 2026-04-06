function getLocalBackendOrigin() {
  if (typeof window === "undefined") {
    return "ENV_BACKEND_HTTP_ORIGIN";
  }

  const { hostname, port, protocol, host } = window.location;
  const isLocalHost = hostname === "127.0.0.1" || hostname === "localhost";

  if (isLocalHost && port !== "8000") {
    return `${protocol}//${hostname}:8000`;
  }

  return `${protocol}//${host}`;
}

export function getApiBase() {
  return `${getLocalBackendOrigin()}/api`;
}

export function getBackendWsBase() {
  if (typeof window === "undefined") {
    return "ENV_BACKEND_WS_ORIGIN";
  }

  const { hostname, port, protocol, host } = window.location;
  const wsProtocol = protocol === "https:" ? "wss:" : "ws:";
  const isLocalHost = hostname === "127.0.0.1" || hostname === "localhost";

  if (isLocalHost && port !== "8000") {
    return `${wsProtocol}//${hostname}:8000`;
  }

  return `${wsProtocol}//${host}`;
}

const API_BASE = getApiBase();

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
  const res = await fetch(`${API_BASE}/status`);
  return readJsonResponse(res);
}

export async function switchMode(mode) {
  const res = await fetch(`${API_BASE}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  return readJsonResponse(res);
}

// Camera endpoints
export async function getCameraSources() {
  const res = await fetch(`${API_BASE}/camera/sources`);
  return readJsonResponse(res);
}

export function getCameraOwner(moduleName) {
  return buildCameraOwner(moduleName);
}

export async function startCamera(sourceType, sourceId = "", owner = null) {
  const res = await fetch(`${API_BASE}/camera/start`, {
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
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(owner),
      }
    : { method: "POST" };
  const res = await fetch(`${API_BASE}/camera/stop`, requestInit);
  return readJsonResponse(res);
}

export async function getCameraState() {
  const res = await fetch(`${API_BASE}/camera/state`);
  return readJsonResponse(res);
}

export async function setCameraMode(mode, owner = null) {
  const requestInit = owner
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(owner),
      }
    : { method: "POST" };
  const res = await fetch(`${API_BASE}/camera/mode/${mode}`, requestInit);
  return readJsonResponse(res);
}

export async function getAttendance() {
  const res = await fetch(`${API_BASE}/attendance`);
  return readJsonResponse(res);
}

export async function getAttendanceReviews(statusFilter = "all") {
  const res = await fetch(
    `${API_BASE}/attendance/reviews?status_filter=${encodeURIComponent(statusFilter)}`,
  );
  return readJsonResponse(res);
}

export async function getAttendanceGateMode() {
  const res = await fetch(`${API_BASE}/attendance/gate-mode`);
  return readJsonResponse(res);
}

export async function setAttendanceGateMode(directionMode) {
  const res = await fetch(`${API_BASE}/attendance/gate-mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction_mode: directionMode }),
  });
  return readJsonResponse(res);
}

export async function decideAttendanceReview(reviewId, data) {
  const res = await fetch(`${API_BASE}/attendance/reviews/${reviewId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
}

export async function getEvents(category) {
  const res = await fetch(`${API_BASE}/events?category=${category}`);
  return readJsonResponse(res);
}

export async function getAlerts() {
  const res = await fetch(`${API_BASE}/alerts`);
  return readJsonResponse(res);
}

export async function acknowledgeAlert(id) {
  const res = await fetch(`${API_BASE}/alerts/${id}/ack`, { method: "POST" });
  return readJsonResponse(res);
}

export async function getPersons() {
  const res = await fetch(`${API_BASE}/persons`);
  return readJsonResponse(res);
}

export async function getRecognizerStatus() {
  const res = await fetch(`${API_BASE}/persons/recognizer`);
  return readJsonResponse(res);
}

export async function enrollPerson(data) {
  const res = await fetch(`${API_BASE}/persons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
}

export async function updatePerson(id, data) {
  const res = await fetch(`${API_BASE}/persons/${id}`, {
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
    method: "POST",
    body: formData,
  });
  return readJsonResponse(res);
}

export async function deletePerson(id) {
  const res = await fetch(`${API_BASE}/persons/${id}`, {
    method: "DELETE",
  });
  return readJsonResponse(res);
}
