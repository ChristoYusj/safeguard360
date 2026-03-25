const API_BASE = "/api";

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

export async function startCamera(sourceType, sourceId = "") {
  const res = await fetch(`${API_BASE}/camera/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_type: sourceType, source_id: sourceId }),
  });
  return readJsonResponse(res);
}

export async function stopCamera() {
  const res = await fetch(`${API_BASE}/camera/stop`, { method: "POST" });
  return readJsonResponse(res);
}

export async function getCameraState() {
  const res = await fetch(`${API_BASE}/camera/state`);
  return readJsonResponse(res);
}

export async function setCameraMode(mode) {
  const res = await fetch(`${API_BASE}/camera/mode/${mode}`, { method: "POST" });
  return readJsonResponse(res);
}

export async function getAttendance() {
  const res = await fetch(`${API_BASE}/attendance`);
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

export async function enrollPerson(data) {
  const res = await fetch(`${API_BASE}/persons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return readJsonResponse(res);
}
