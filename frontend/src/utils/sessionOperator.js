const STORAGE_KEY = "safeguard360-session-operator";

const DEFAULT_SESSION_OPERATOR = {
  email: "",
  signedInAt: "",
};

function normalizeSessionOperator(operator = {}) {
  return {
    email: operator.email ?? DEFAULT_SESSION_OPERATOR.email,
    signedInAt: operator.signedInAt ?? DEFAULT_SESSION_OPERATOR.signedInAt,
  };
}

export function readSessionOperator() {
  if (typeof window === "undefined") {
    return { ...DEFAULT_SESSION_OPERATOR };
  }

  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_SESSION_OPERATOR };
    }

    return normalizeSessionOperator(JSON.parse(raw));
  } catch (error) {
    console.error("[sessionOperator] Failed to read storage", error);
    return { ...DEFAULT_SESSION_OPERATOR };
  }
}

export function writeSessionOperator(operator) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(normalizeSessionOperator(operator)),
    );
  } catch (error) {
    console.error("[sessionOperator] Failed to write storage", error);
  }
}

export function clearSessionOperator() {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error("[sessionOperator] Failed to clear storage", error);
  }
}
