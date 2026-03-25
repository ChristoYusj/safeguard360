const STORAGE_KEY = "safeguard360-platform-logs";

function createDefaultStore() {
  return {
    fleet: {
      sessions: [],
      activeSessionId: null,
    },
    attendance: {
      sessions: [],
    },
    gatePpe: {
      sessions: [],
    },
  };
}

function safeRead() {
  if (typeof window === "undefined") {
    return createDefaultStore();
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return createDefaultStore();
    }
    return { ...createDefaultStore(), ...JSON.parse(raw) };
  } catch (error) {
    console.error("[platformLogs] Failed to read storage", error);
    return createDefaultStore();
  }
}

function safeWrite(store) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch (error) {
    console.error("[platformLogs] Failed to write storage", error);
  }
}

export function readPlatformLogs() {
  return safeRead();
}

export function beginFleetSession({ driverName, truckId, sourceLabel }) {
  const store = safeRead();
  const sessionId = `fleet-${Date.now()}`;
  const newSession = {
    id: sessionId,
    driverName,
    truckId,
    sourceLabel,
    startedAt: Date.now(),
    endedAt: null,
    events: [],
  };

  store.fleet.sessions = [newSession, ...(store.fleet.sessions || [])].slice(0, 20);
  store.fleet.activeSessionId = sessionId;
  safeWrite(store);
  return sessionId;
}

export function endFleetSession(sessionId) {
  if (!sessionId) {
    return;
  }

  const store = safeRead();
  store.fleet.sessions = (store.fleet.sessions || []).map((session) =>
    session.id === sessionId && !session.endedAt ? { ...session, endedAt: Date.now() } : session,
  );
  if (store.fleet.activeSessionId === sessionId) {
    store.fleet.activeSessionId = null;
  }
  safeWrite(store);
}

export function appendFleetEvent(sessionId, event) {
  if (!sessionId) {
    return;
  }

  const store = safeRead();
  store.fleet.sessions = (store.fleet.sessions || []).map((session) => {
    if (session.id !== sessionId) {
      return session;
    }

    const existing = (session.events || []).some((item) => item.id === event.id);
    if (existing) {
      return session;
    }

    return {
      ...session,
      events: [...(session.events || []), event],
    };
  });
  safeWrite(store);
}

