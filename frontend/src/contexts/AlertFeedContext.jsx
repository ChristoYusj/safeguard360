/*
 * Global alert feed — a single WebSocket subscription to /ws/events
 * that surfaces severe driver / attendance / PPE events site-wide as
 * red-flash toasts, no matter which page the operator is viewing.
 *
 * Per-page notifications (Dashboard, Attendance) continue to work as
 * before; this layer adds coverage for moments when the operator is
 * on a different page (Logs, Settings, Chatbot, etc.).
 *
 * Sound playback is suppressed when the corresponding page is active
 * so we don't double-beep on the pages that already play their own.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useLocation } from "react-router-dom";
import { getBackendWsBase } from "../services/api";
import { useAuth } from "./AuthContext";

const AlertFeedContext = createContext({
  alerts: [],
  flashSeverity: null,
  dismissAlert: () => {},
});

const MAX_VISIBLE = 5;
const AUTO_DISMISS_MS = 7000;
const FLASH_MS = 900;
const DEDUPE_WINDOW_MS = 1500;

function playTone(severity) {
  if (typeof window === "undefined") return;
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const now = ctx.currentTime;

    const fire = (freq, offset, duration) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.22, now + offset);
      gain.gain.exponentialRampToValueAtTime(0.0008, now + offset + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + offset);
      osc.stop(now + offset + duration);
    };

    if (severity === "danger") {
      fire(880, 0, 0.22);
      fire(1175, 0.18, 0.22);
    } else if (severity === "warning") {
      fire(660, 0, 0.3);
    } else {
      fire(520, 0, 0.22);
    }

    // Release the context shortly after the tones finish.
    setTimeout(() => {
      try {
        ctx.close();
      } catch {
        /* ignore */
      }
    }, 800);
  } catch {
    // Browser may block autoplay until first user gesture — silent fail.
  }
}

function normalizeDriverEvent(msg) {
  const eventType = (msg.event_type || "").toLowerCase();
  if (eventType.includes("fatigue") || eventType.includes("drowsy")) {
    return {
      severity: "danger",
      title: "Driver fatigue detected",
      message: msg.details || "Signs of fatigue observed on driver feed.",
      category: "driver",
    };
  }
  if (eventType.includes("distract")) {
    return {
      severity: "warning",
      title: "Driver distraction",
      message: msg.details || "Driver attention has shifted off the road.",
      category: "driver",
    };
  }
  if (eventType.includes("seatbelt") || eventType.includes("phone")) {
    return {
      severity: "warning",
      title: `Driver event · ${msg.event_type}`,
      message: msg.details || "",
      category: "driver",
    };
  }
  return null;
}

function normalizeAttendanceEvent(msg) {
  const missing = msg?.ppe_details?.missing_items || [];
  if (msg.ppe_status === "non_compliant") {
    const subject = msg.person_name || "Worker";
    const missingLabel = missing.length ? missing.join(", ") : "PPE";
    return {
      severity: "danger",
      title: "PPE violation",
      message: `${subject} missing ${missingLabel}.`,
      category: "attendance",
    };
  }
  const eventType = (msg.event_type || "").toLowerCase();
  if (
    !msg.access_granted &&
    (eventType.includes("unknown") || eventType === "attempt_denied")
  ) {
    return {
      severity: "warning",
      title: "Unknown person at gate",
      message: "An unrecognised face attempted to enter.",
      category: "attendance",
    };
  }
  if (!msg.access_granted && msg.review_reasons?.length) {
    return {
      severity: "warning",
      title: "Gate review required",
      message: msg.review_reasons.join(" · "),
      category: "attendance",
    };
  }
  return null;
}

export function AlertFeedProvider({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  const [alerts, setAlerts] = useState([]);
  const [flashSeverity, setFlashSeverity] = useState(null);

  const flashTimerRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const locationRef = useRef(location.pathname);
  const lastFireRef = useRef(new Map()); // dedupe key -> timestamp
  const dismissTimersRef = useRef(new Map()); // alert id -> timeout handle

  useEffect(() => {
    locationRef.current = location.pathname;
  }, [location.pathname]);

  const dismissAlert = useCallback((id) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    const timer = dismissTimersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      dismissTimersRef.current.delete(id);
    }
  }, []);

  const addAlert = useCallback(
    (alert) => {
      if (!alert) return;
      // Dedupe bursts — same (category + severity + title) within 1.5s collapses.
      const dedupeKey = `${alert.category}|${alert.severity}|${alert.title}`;
      const now = Date.now();
      const dedupe = lastFireRef.current;
      const last = dedupe.get(dedupeKey) || 0;
      if (now - last < DEDUPE_WINDOW_MS) {
        return;
      }
      dedupe.set(dedupeKey, now);

      // Trim stale dedupe keys so long-lived sessions don't accumulate memory.
      if (dedupe.size > 64) {
        for (const [key, ts] of dedupe) {
          if (now - ts > DEDUPE_WINDOW_MS * 20) dedupe.delete(key);
        }
      }

      const id = `${now}-${Math.random().toString(16).slice(2)}`;
      const entry = { id, receivedAt: now, ...alert };
      setAlerts((prev) => [entry, ...prev].slice(0, MAX_VISIBLE));
      const timer = setTimeout(() => dismissAlert(id), AUTO_DISMISS_MS);
      dismissTimersRef.current.set(id, timer);

      if (alert.severity === "danger" || alert.severity === "warning") {
        setFlashSeverity(alert.severity);
        if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
        flashTimerRef.current = setTimeout(() => setFlashSeverity(null), FLASH_MS);
      }

      // Skip sound on pages that already handle their own (avoids double-beep).
      const path = locationRef.current;
      const pageHandlesCategory =
        (alert.category === "driver" && path === "/drivers") ||
        (alert.category === "attendance" && path === "/attendance");
      if (!pageHandlesCategory) {
        playTone(alert.severity);
      }
    },
    [dismissAlert],
  );

  useEffect(() => {
    if (!user) return undefined;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const wsBase = getBackendWsBase();
      if (!wsBase) return;

      let ws;
      try {
        ws = new WebSocket(`${wsBase}/ws/events`);
      } catch {
        reconnectTimerRef.current = setTimeout(connect, 3000);
        return;
      }
      wsRef.current = ws;

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          let alert = null;
          if (msg.type === "driver_event") {
            alert = normalizeDriverEvent(msg);
          } else if (msg.type === "attendance_match") {
            alert = normalizeAttendanceEvent(msg);
          }
          if (alert) addAlert(alert);
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        reconnectTimerRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        try {
          ws.close();
        } catch {
          /* ignore */
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          /* ignore */
        }
      }
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
      for (const timer of dismissTimersRef.current.values()) {
        clearTimeout(timer);
      }
      dismissTimersRef.current.clear();
    };
  }, [user, addAlert]);

  return (
    <AlertFeedContext.Provider value={{ alerts, flashSeverity, dismissAlert }}>
      {children}
    </AlertFeedContext.Provider>
  );
}

export function useAlertFeed() {
  return useContext(AlertFeedContext);
}
