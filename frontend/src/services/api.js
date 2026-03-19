const API_BASE = "/api";

export async function getStatus() {
  const res = await fetch(`${API_BASE}/status`);
  return res.json();
}

export async function switchMode(mode) {
  const res = await fetch(`${API_BASE}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  return res.json();
}

// Camera endpoints
export async function getCameraSources() {
  const res = await fetch(`${API_BASE}/camera/sources`);
  return res.json();
}

export async function startCamera(sourceType, sourceId = "") {
  const res = await fetch(`${API_BASE}/camera/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_type: sourceType, source_id: sourceId }),
  });
  return res.json();
}

export async function stopCamera() {
  const res = await fetch(`${API_BASE}/camera/stop`, { method: "POST" });
  return res.json();
}

export async function getCameraState() {
  const res = await fetch(`${API_BASE}/camera/state`);
  return res.json();
}

export async function setCameraMode(mode) {
  const res = await fetch(`${API_BASE}/camera/mode/${mode}`, { method: "POST" });
  return res.json();
}

export async function getAttendance() {
  const res = await fetch(`${API_BASE}/attendance`);
  return res.json();
}

export async function getEvents(category) {
  const res = await fetch(`${API_BASE}/events?category=${category}`);
  return res.json();
}

export async function getAlerts() {
  const res = await fetch(`${API_BASE}/alerts`);
  return res.json();
}

export async function acknowledgeAlert(id) {
  const res = await fetch(`${API_BASE}/alerts/${id}/ack`, { method: "POST" });
  return res.json();
}

export async function getPersons() {
  const res = await fetch(`${API_BASE}/persons`);
  return res.json();
}

export async function enrollPerson(data) {
  const res = await fetch(`${API_BASE}/persons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}
