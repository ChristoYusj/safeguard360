/*
 * SafeGuard 360 - Attendance Page
 * "Precision Command" Design System
 */

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import {
  decideAttendanceReview,
  getAttendance,
  getAttendanceGateMode,
  getAttendancePpePolicy,
  getAttendanceReviews,
  getBackendWsBase,
  getCameraOwner,
  getCameraSources,
  getCameraState,
  getPersons,
  setAttendanceGateMode as updateAttendanceGateMode,
  setCameraMode,
  startCamera,
  stopCamera,
  updateAttendancePpePolicy,
} from "../services/api";
import { canChangePpePolicy } from "../utils/accessControl";
import {
  AlertTriangleIcon,
  CameraIcon,
  CheckCircleIcon,
  RefreshIcon,
  ShieldIcon,
  UsersIcon,
  VideoIcon,
} from "../components/icons";
import {
  buildAttendanceSessionState,
  getShiftIdForTimestamp,
  parseBackendTimestamp,
} from "../utils/attendanceSessions";

const SHIFT_BLOCKS = [
  {
    id: "day",
    label: "Day Shift",
    window: "06:00 - 14:00",
    startHour: 6,
    endHour: 14,
  },
  {
    id: "swing",
    label: "Swing Shift",
    window: "14:00 - 22:00",
    startHour: 14,
    endHour: 22,
  },
  {
    id: "night",
    label: "Night Shift",
    window: "22:00 - 06:00",
    startHour: 22,
    endHour: 6,
  },
];

const SHIFT_LATE_GRACE_MINUTES = 20;

const cardVariants = {
  hidden: { opacity: 0, y: 18 },
  visible: (index = 0) => ({
    opacity: 1,
    y: 0,
    transition: {
      delay: 0.08 + index * 0.05,
      duration: 0.42,
      ease: [0.2, 0.65, 0.3, 0.9],
    },
  }),
};

function getSourceId(source) {
  return `${source.source_type}:${source.source_id}`;
}

function parseSourceId(sourceId) {
  const index = sourceId.indexOf(":");
  if (index === -1) {
    return { type: sourceId, id: "0" };
  }

  return {
    type: sourceId.slice(0, index),
    id: sourceId.slice(index + 1),
  };
}

function normalizePpeDetails(details) {
  return {
    status: "not_evaluated",
    required_items: [],
    detected_items: [],
    missing_items: [],
    detector_confidences: {},
    override_used: false,
    override_reason_type: null,
    detector_available: false,
    detector_message: null,
    ...(details || {}),
  };
}

function formatPpeStatusLabel(details) {
  const ppe = normalizePpeDetails(details);
  if (
    ppe.override_used &&
    ["ppe_non_compliance", "combined"].includes(ppe.override_reason_type)
  ) {
    return "Override Granted";
  }
  if (ppe.status === "compliant") return "PPE Clear";
  if (ppe.status === "non_compliant") return "PPE Missing";
  if (ppe.status === "uncertain") return "PPE Review";
  if (ppe.status === "unavailable") return "Detector Offline";
  if (ppe.status === "skipped") return "PPE Skipped";
  return null;
}

function getPpeBadgeClass(details) {
  const ppe = normalizePpeDetails(details);
  if (
    ppe.override_used &&
    ["ppe_non_compliance", "combined"].includes(ppe.override_reason_type)
  ) {
    return "badge badge-warning";
  }
  if (ppe.status === "compliant") return "badge badge-success";
  if (ppe.status === "non_compliant" || ppe.status === "uncertain") {
    return "badge badge-warning";
  }
  return "badge badge-info";
}

function getCompactPpeSummary(details, registeredViolations = []) {
  if (registeredViolations.length > 0) {
    const missingItems =
      normalizePpeDetails(registeredViolations[0].ppeDetails).missing_items || [];
    return {
      label: "Flagged",
      description: registeredViolations[0].summary,
      missingItems,
    };
  }

  const ppe = normalizePpeDetails(details);
  if (ppe.status === "compliant") {
    return {
      label: "Compliant",
      description: "Required PPE confirmed.",
      missingItems: [],
    };
  }
  if (ppe.status === "non_compliant") {
    return {
      label: "Flagged",
      description:
        ppe.missing_items?.length > 0
          ? `Missing ${ppe.missing_items.join(", ")}`
          : "Required PPE was not detected.",
      missingItems: ppe.missing_items || [],
    };
  }
  if (ppe.status === "uncertain") {
    return {
      label: "Flagged",
      description: "PPE needs operator review.",
      missingItems: ppe.missing_items || [],
    };
  }
  if (ppe.status === "unavailable") {
    return {
      label: "Flagged",
      description: "PPE detector unavailable.",
      missingItems: [],
    };
  }
  if (ppe.status === "skipped") {
    return {
      label: "Compliant",
      description: "No PPE issue recorded.",
      missingItems: [],
    };
  }
  return null;
}

function formatReviewReasons(review) {
  const reviewReasons = Array.isArray(review?.review_reasons)
    ? review.review_reasons
    : [];
  const labels = [];

  const KNOWN_REASONS = {
    face_confidence: "Face confidence needs approval",
    ambiguous_match: "Two workers scored too close to tell apart",
    uncertain_ppe: "PPE status is uncertain",
  };

  reviewReasons.forEach((reason) => {
    if (KNOWN_REASONS[reason]) {
      labels.push(KNOWN_REASONS[reason]);
      return;
    }
    if (typeof reason === "string" && reason.startsWith("missing_")) {
      labels.push(`Missing ${reason.slice("missing_".length).replace(/_/g, " ")}`);
      return;
    }
    if (typeof reason === "string" && reason.startsWith("off_shift_")) {
      labels.push(
        `Arriving outside ${reason.slice("off_shift_".length).replace(/_/g, " ")} shift`,
      );
      return;
    }
    // Never render a review with a blank reason strip: an operator who cannot
    // see why a decision is pending cannot make it.
    if (typeof reason === "string" && reason) {
      labels.push(reason.replace(/_/g, " "));
    }
  });

  return labels;
}

function getEffectivePendingReview(review, gateStatus) {
  if (!gateStatus?.person_id || gateStatus.person_id !== review.person_id) {
    return review;
  }

  const confidence =
    gateStatus.confidence != null
      ? Math.max(review.confidence || 0, gateStatus.confidence)
      : review.confidence;
  const reviewReasons = Array.isArray(gateStatus.review_reasons)
    ? gateStatus.review_reasons
    : Array.isArray(review.review_reasons)
      ? review.review_reasons
      : [];

  // The server owns the thresholds (GATE_REVIEW_THRESHOLD and friends) and
  // puts its decision in review_reasons. This used to re-apply a hardcoded
  // 0.85 here and strip "face_confidence" from the server's answer, so the
  // operator saw a review whose stated reason had been edited away in the
  // browser -- and it went stale the moment a site tuned the real threshold.
  // The live gate status is still preferred over the stored row because it is
  // fresher, but its reasons are passed through untouched.
  const livePpeDetails = normalizePpeDetails(gateStatus.ppe_details);
  const hasLivePpeSignal =
    Boolean(gateStatus.ppe_details) &&
    (livePpeDetails.status !== "not_evaluated" ||
      livePpeDetails.required_items.length > 0 ||
      livePpeDetails.missing_items.length > 0);

  return {
    ...review,
    confidence,
    review_reasons: reviewReasons,
    ppe_details: hasLivePpeSignal ? gateStatus.ppe_details : review.ppe_details,
  };
}

function ToggleSwitch({ checked, disabled = false, ariaLabel, onClick }) {
  // NOTE: we deliberately do NOT set the HTML `disabled` attribute here so the
  // onClick still fires when the toggle is in a "soft-disabled" state. That
  // lets the handler surface a helpful error (e.g. "Start the feed before
  // enabling recognition mode.") instead of the switch silently doing nothing.
  return (
    <button
      type="button"
      role="switch"
      aria-label={ariaLabel}
      aria-checked={checked}
      aria-disabled={disabled}
      onClick={onClick}
      className={`relative inline-flex h-8 w-14 shrink-0 items-center rounded-full border p-1 transition-colors ${
        checked
          ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary)]"
          : "border-[var(--color-border-emphasis)] bg-[var(--color-bg-card)]"
      } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
    >
      <motion.span
        initial={false}
        animate={{ x: checked ? 24 : 0 }}
        transition={{
          type: "spring",
          stiffness: 500,
          damping: 30,
        }}
        className="inline-block h-6 w-6 rounded-full bg-white shadow-md"
      />
    </button>
  );
}

function formatEventTime(value) {
  if (!value) {
    return "--";
  }

  const parsed = parseBackendTimestamp(value);
  if (!parsed) {
    return "--";
  }

  return parsed.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatEventTimestamp(value) {
  if (!value) {
    return "--";
  }

  const parsed = parseBackendTimestamp(value);
  if (!parsed) {
    return "--";
  }

  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatCameraSourceLabel(sourceType, sourceId) {
  if (!sourceType && !sourceId) {
    return "--";
  }

  if (sourceType === "webcam") {
    return `Webcam ${sourceId ?? "--"}`;
  }

  if (sourceType === "ip_stream") {
    return sourceId || "IP Stream";
  }

  if (sourceType === "video_file") {
    return sourceId || "Video File";
  }

  return [sourceType, sourceId].filter(Boolean).join(":");
}

function formatLogMethodLabel(logMethod) {
  if (logMethod === "MANUAL") return "Manual";
  if (logMethod === "AUTO") return "Auto";
  return "--";
}

function formatFaceMatchLabel(confidence) {
  if (confidence == null) {
    return "--";
  }
  return `${Math.round(confidence * 100)}%`;
}

function addMinutes(date, minutes) {
  return new Date(date.getTime() + minutes * 60 * 1000);
}

function getShiftBlock(shiftId) {
  return SHIFT_BLOCKS.find((shift) => shift.id === shiftId) || SHIFT_BLOCKS[0];
}

function getShiftLabel(shiftId) {
  return getShiftBlock(shiftId).label;
}

function buildShiftWindow(shiftId, anchorDate) {
  const shift = getShiftBlock(shiftId);
  const start = new Date(anchorDate);
  start.setHours(shift.startHour, 0, 0, 0);

  const end = new Date(start);
  if (shift.endHour <= shift.startHour) {
    end.setDate(end.getDate() + 1);
  }
  end.setHours(shift.endHour, 0, 0, 0);

  return { shiftId, start, end };
}

function isDateInShiftWindow(date, shiftWindow) {
  return date >= shiftWindow.start && date < shiftWindow.end;
}

function getRelevantShiftWindow(shiftId, now = new Date()) {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);

  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const candidates = [yesterday, today, tomorrow].map((anchorDate) =>
    buildShiftWindow(shiftId, anchorDate),
  );

  const activeWindow = candidates.find((candidate) =>
    isDateInShiftWindow(now, candidate),
  );
  if (activeWindow) {
    return {
      ...activeWindow,
      isActive: true,
      hasStarted: true,
      lateCutoff: addMinutes(activeWindow.start, SHIFT_LATE_GRACE_MINUTES),
    };
  }

  const upcomingToday = candidates.find(
    (candidate) =>
      candidate.start > now &&
      candidate.start.toDateString() === now.toDateString(),
  );
  const previousWindow = [...candidates]
    .filter((candidate) => candidate.start <= now)
    .sort((left, right) => right.start - left.start)[0];
  const selectedWindow = upcomingToday || previousWindow || candidates[1];

  return {
    ...selectedWindow,
    isActive: false,
    hasStarted: now >= selectedWindow.start,
    lateCutoff: addMinutes(selectedWindow.start, SHIFT_LATE_GRACE_MINUTES),
  };
}

function isRecordInShiftWindow(record, shiftWindow) {
  if (!record?.timestamp) {
    return false;
  }

  const recordTime = new Date(record.timestamp);
  return isDateInShiftWindow(recordTime, shiftWindow);
}

function getReviewShiftId(review, personsById) {
  if (!review) {
    return null;
  }

  const assignedShiftId = review.person_id
    ? personsById.get(review.person_id)?.shift_id || null
    : null;

  if (review.person_id) {
    return assignedShiftId;
  }

  return getShiftIdForTimestamp(review.timestamp || review.decided_at);
}

function buildWorkerRecords(
  persons,
  activeSessions,
  gateReviews,
  selectedSourceLabel,
  selectedShiftWindow,
  liveGateStatus,
  gateModeEnabled,
  gateDirectionMode,
) {
  const pendingReviewsByPersonId = new Map();
  const personsById = new Map(persons.map((person) => [person.id, person]));

  gateReviews.forEach((review) => {
    const reviewShiftId = getReviewShiftId(review, personsById);
    if (
      review.status !== "PENDING" ||
      !review.person_id ||
      (reviewShiftId && reviewShiftId !== selectedShiftWindow.shiftId)
    ) {
      return;
    }

    const currentReview = pendingReviewsByPersonId.get(review.person_id);
    if (!currentReview || new Date(review.timestamp) > new Date(currentReview.timestamp)) {
      pendingReviewsByPersonId.set(review.person_id, review);
    }
  });

  return activeSessions.map((session) => {
    const person = session.personId ? personsById.get(session.personId) : null;
    const pendingReview = session.personId
      ? pendingReviewsByPersonId.get(session.personId) || null
      : null;
    const allowLiveRescan = gateDirectionMode === "EXIT";
    const liveGateApplies =
      allowLiveRescan &&
      Boolean(gateModeEnabled) &&
      liveGateStatus?.person_id === session.personId &&
      [
        "matching",
        "possible_match",
        "review_required",
        "confirmed_match",
        "not_checked_in",
      ].includes(liveGateStatus?.match_status);
    const liveConfidence =
      liveGateApplies && liveGateStatus?.confidence != null
        ? Math.round(liveGateStatus.confidence * 100)
        : null;
    const effectivePendingReview =
      gateModeEnabled &&
      pendingReview &&
      !(liveGateApplies && liveGateStatus?.match_status === "confirmed_match")
        ? pendingReview
        : null;
    const lastEntryRecord = session.checkIn || null;
    const effectivePpeDetails = liveGateApplies
      ? normalizePpeDetails(liveGateStatus?.ppe_details)
      : effectivePendingReview
        ? normalizePpeDetails(effectivePendingReview.ppe_details)
        : normalizePpeDetails(lastEntryRecord?.ppe_details);
    const isHeld =
      Boolean(effectivePendingReview) ||
      (liveGateApplies &&
        ["review_required", "possible_match", "not_checked_in"].includes(
          liveGateStatus?.match_status,
        ));
    const attendanceState = isHeld ? "held" : "verified";
    const shiftLabel = getShiftLabel(
      session.shiftId || person?.shift_id || selectedShiftWindow.shiftId,
    );
    const manualOverrideLabel = session.hasManualOverride
      ? ` Manual override used during ${session.manualOverrideDirections.join(" and ")}.`
      : "";
    const reviewReasonLabels = effectivePendingReview
      ? formatReviewReasons(effectivePendingReview)
      : [];
    const note = effectivePendingReview
      ? reviewReasonLabels.length > 0
        ? `${reviewReasonLabels.join(" • ")}. Waiting for operator approval.`
        : "Waiting for operator approval."
      : `Checked in for ${shiftLabel} at ${formatEventTime(lastEntryRecord?.timestamp)}.${manualOverrideLabel}`;

    return {
      id: session.personId || session.id,
      shiftId: session.shiftId || person?.shift_id || null,
      name: session.personName || person?.name || "Unknown worker",
      role: session.employeeId || person?.employee_id || "Enrolled worker",
      company: session.shiftId
        ? `${getShiftLabel(session.shiftId)} assigned`
        : "No shift assigned",
      attendanceState,
      matchState:
        liveGateApplies && liveGateStatus?.match_status === "confirmed_match"
          ? "matched"
          : effectivePendingReview
          ? "review"
          : "matched",
      cameraSource: selectedSourceLabel,
      lastCheckIn: lastEntryRecord?.timestamp
        ? formatEventTime(lastEntryRecord.timestamp)
        : null,
      confidence:
        liveConfidence != null
          ? liveConfidence
          : effectivePendingReview?.confidence != null
            ? Math.round(effectivePendingReview.confidence * 100)
            : lastEntryRecord?.confidence != null
              ? Math.round(lastEntryRecord.confidence * 100)
              : null,
      pendingReview: effectivePendingReview,
      hasManualOverride: session.hasManualOverride,
      riskLabel: liveGateApplies && liveGateStatus?.message ? liveGateStatus.message : note,
      ppeDetails: effectivePpeDetails,
      ppeStatusLabel: formatPpeStatusLabel(effectivePpeDetails),
    };
  });
}

function StatCard({ icon: Icon, label, value, helper, tone = "accent" }) {
  const toneStyles = {
    accent: {
      bg: "var(--color-accent-primary-muted)",
      color: "var(--color-accent-primary)",
    },
    success: {
      bg: "var(--color-success-muted)",
      color: "var(--color-success)",
    },
    warning: {
      bg: "var(--color-warning-muted)",
      color: "var(--color-warning)",
    },
    info: {
      bg: "var(--color-info-muted)",
      color: "var(--color-info)",
    },
  };

  return (
    <div className="stat-card relative overflow-hidden">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-24 opacity-80"
        style={{
          background: `linear-gradient(180deg, ${toneStyles[tone].bg}, transparent)`,
        }}
      />
      <div className="relative flex items-start justify-between gap-4">
        <div>
          <p className="stat-card__label">{label}</p>
          <p className="stat-card__value">{value}</p>
          {helper ? <p className="mt-3 text-sm text-secondary">{helper}</p> : null}
        </div>
        <div
          className="flex h-12 w-12 items-center justify-center rounded-2xl border border-default"
          style={{
            backgroundColor: toneStyles[tone].bg,
            color: toneStyles[tone].color,
          }}
        >
          <Icon size={22} />
        </div>
      </div>
    </div>
  );
}

function Attendance() {
  const { user } = useAuth();
  const { t } = useAppLanguage();
  const canEditPpePolicy = canChangePpePolicy(user?.role);
  const [selectedShiftId, setSelectedShiftId] = useState("day");
  const [cameraState, setCameraState] = useState(null);
  const [sources, setSources] = useState([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [gateDirectionMode, setGateDirectionMode] = useState("ENTRY");
  const [hasLiveFrame, setHasLiveFrame] = useState(false);
  const [error, setError] = useState(null);
  const [personsData, setPersonsData] = useState([]);
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [gateReviews, setGateReviews] = useState([]);
  const [gateStatus, setGateStatus] = useState(null);
  const [attendanceRefreshTick, setAttendanceRefreshTick] = useState(0);
  const [streamSession, setStreamSession] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isRecoveringFeed, setIsRecoveringFeed] = useState(false);
  const [isChangingRecognitionMode, setIsChangingRecognitionMode] = useState(false);
  const [isChangingGateDirection, setIsChangingGateDirection] = useState(false);
  const [isChangingPpePolicy, setIsChangingPpePolicy] = useState(false);
  const [ppePolicy, setPpePolicy] = useState({
    require_helmet: true,
    require_vest: true,
    deny_non_compliant_entry: true,
  });
  const [liveFps, setLiveFps] = useState(0);
  const [decisionInFlightId, setDecisionInFlightId] = useState(null);
  const [alertNotifications, setAlertNotifications] = useState([]);

  const liveWsRef = useRef(null);
  const eventsWsRef = useRef(null);
  const cameraOwnerRef = useRef(getCameraOwner("attendance"));
  const latestCameraStateVersionRef = useRef(-1);
  const liveReconnectRef = useRef(null);
  const eventsReconnectRef = useRef(null);
  const liveImageRef = useRef(null);
  const hasLiveFrameRef = useRef(false);
  const pendingFramePayloadRef = useRef(null);
  const frameDecodeInFlightRef = useRef(false);
  const activeFrameUrlRef = useRef("");
  const loadingFrameUrlRef = useRef("");
  const lastFrameTsRef = useRef(null);
  const smoothedFpsRef = useRef(0);
  const lastFpsUiUpdateRef = useRef(0);
  const lastEnabledPpePolicyRef = useRef({
    require_helmet: true,
    require_vest: true,
    deny_non_compliant_entry: true,
  });

  // Plays a short beep using Web Audio API (no external file needed)
  const playAlertSound = (type = "warning") => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = type === "danger" ? 880 : 660;
      osc.type = "sine";
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.4);
    } catch (_) { /* AudioContext may be unavailable in some contexts */ }
  };

  const pushNotification = (message, type = "warning") => {
    const id = `${Date.now()}-${Math.random()}`;
    setAlertNotifications((prev) => [{ id, message, type }, ...prev].slice(0, 5));
    playAlertSound(type);
    setTimeout(() => {
      setAlertNotifications((prev) => prev.filter((n) => n.id !== id));
    }, 6000);
  };

  const releaseFrameUrl = (url) => {
    if (typeof url === "string" && url.startsWith("blob:")) {
      window.URL.revokeObjectURL(url);
    }
  };

  const updateDisplayedFps = () => {
    const now = performance.now();
    if (lastFrameTsRef.current !== null) {
      const deltaMs = now - lastFrameTsRef.current;
      if (deltaMs > 0) {
        const instantFps = 1000 / deltaMs;
        smoothedFpsRef.current =
          smoothedFpsRef.current === 0
            ? instantFps
            : smoothedFpsRef.current * 0.84 + instantFps * 0.16;
        if (now - lastFpsUiUpdateRef.current >= 500) {
          setLiveFps(smoothedFpsRef.current);
          lastFpsUiUpdateRef.current = now;
        }
      }
    }
    lastFrameTsRef.current = now;
  };

  const flushLiveFrame = () => {
    if (frameDecodeInFlightRef.current) {
      return;
    }

    const payload = pendingFramePayloadRef.current;
    const image = liveImageRef.current;
    if (!payload || !image) {
      return;
    }

    pendingFramePayloadRef.current = null;
    frameDecodeInFlightRef.current = true;

    const nextSrc =
      payload.type === "blob"
        ? window.URL.createObjectURL(payload.blob)
        : payload.src;

    if (payload.type === "blob") {
      loadingFrameUrlRef.current = nextSrc;
    } else {
      loadingFrameUrlRef.current = "";
    }

    const finish = (loaded) => {
      image.onload = null;
      image.onerror = null;
      frameDecodeInFlightRef.current = false;

      if (loaded) {
        const previousActive = activeFrameUrlRef.current;
        activeFrameUrlRef.current = loadingFrameUrlRef.current || activeFrameUrlRef.current;
        if (previousActive && previousActive !== activeFrameUrlRef.current) {
          releaseFrameUrl(previousActive);
        }
        updateDisplayedFps();
        if (!hasLiveFrameRef.current) {
          hasLiveFrameRef.current = true;
          setHasLiveFrame(true);
        }
      } else {
        releaseFrameUrl(loadingFrameUrlRef.current);
      }

      loadingFrameUrlRef.current = "";
      if (pendingFramePayloadRef.current) {
        flushLiveFrame();
      }
    };

    image.onload = () => finish(true);
    image.onerror = () => finish(false);
    image.src = nextSrc;
  };

  const queueLiveFrame = (payload) => {
    pendingFramePayloadRef.current = payload;
    flushLiveFrame();
  };

  const clearLivePreview = () => {
    pendingFramePayloadRef.current = null;
    frameDecodeInFlightRef.current = false;
    if (liveImageRef.current) {
      liveImageRef.current.onload = null;
      liveImageRef.current.onerror = null;
      liveImageRef.current.removeAttribute("src");
    }
    releaseFrameUrl(activeFrameUrlRef.current);
    releaseFrameUrl(loadingFrameUrlRef.current);
    activeFrameUrlRef.current = "";
    loadingFrameUrlRef.current = "";
    hasLiveFrameRef.current = false;
    setHasLiveFrame(false);
  };

  const resetLiveMetrics = () => {
    clearLivePreview();
    setLiveFps(0);
    lastFrameTsRef.current = null;
    smoothedFpsRef.current = 0;
    lastFpsUiUpdateRef.current = 0;
  };

  const syncGateStateFromCamera = (nextState) => {
    if (nextState?.mode === "gate" && nextState?.gate) {
      setGateStatus(nextState.gate);
      if (nextState.gate.direction_mode) {
        setGateDirectionMode(nextState.gate.direction_mode);
      }
    } else {
      setGateStatus(null);
    }
  };

  const applyCameraState = (nextState) => {
    const nextVersion = nextState?.state_version ?? 0;
    if (nextVersion < latestCameraStateVersionRef.current) {
      return false;
    }
    latestCameraStateVersionRef.current = nextVersion;
    setCameraState(nextState);
    syncGateStateFromCamera(nextState);
    return true;
  };

  useEffect(() => {
    let disposed = false;
    const wsBase = getBackendWsBase();

    const connectLive = () => {
      if (disposed) return;
      const ws = new WebSocket(`${wsBase}/ws/live`);
      ws.binaryType = "blob";

      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        clearLivePreview();
        if (!disposed) {
          liveReconnectRef.current = setTimeout(connectLive, 2000);
        }
      };
      ws.onerror = () => setWsConnected(false);
      ws.onmessage = (event) => {
        try {
          if (typeof event.data === "string") {
            const payload = JSON.parse(event.data);
            if (payload.type !== "frame" || !payload.data) return;
            const byteString = window.atob(payload.data);
            const bytes = new Uint8Array(byteString.length);
            for (let index = 0; index < byteString.length; index += 1) {
              bytes[index] = byteString.charCodeAt(index);
            }
            queueLiveFrame({
              type: "blob",
              blob: new Blob([bytes], { type: "image/jpeg" }),
            });
          } else {
            const frameBlob =
              event.data instanceof Blob
                ? event.data
                : new Blob([event.data], { type: "image/jpeg" });
            queueLiveFrame({
              type: "blob",
              blob: frameBlob,
            });
          }
        } catch (wsError) {
          console.error("[Attendance] Live WS parse error", wsError);
        }
      };

      liveWsRef.current = ws;
    };

    const connectEvents = () => {
      if (disposed) return;
      const ws = new WebSocket(`${wsBase}/ws/events`);

      ws.onclose = () => {
        if (!disposed) {
          eventsReconnectRef.current = setTimeout(connectEvents, 2000);
        }
      };
      ws.onerror = (event) =>
        console.error("[Attendance] Events WS error", event);
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "status" && payload.camera) {
            const applied = applyCameraState(payload.camera);
            if (!applied) {
              return;
            }
          } else if (
            payload.type === "attendance_match" ||
            payload.type === "attendance_check_in" ||
            payload.type === "attendance_check_out"
          ) {
            setAttendanceRefreshTick((current) => current + 1);

            // Fire alert notification for PPE violations
            if (payload.ppe_compliant === false || payload.ppe_status === "non_compliant") {
              const name = payload.person_name || "A worker";
              const missing = payload.ppe_details?.missing_items?.join(", ");
              pushNotification(
                missing
                  ? `⚠️ PPE Violation — ${name} missing: ${missing}`
                  : `⚠️ PPE Violation — ${name} did not meet PPE requirements`,
                "danger",
              );
            }
          }
        } catch (wsError) {
          console.error("[Attendance] Events WS parse error", wsError);
        }
      };

      eventsWsRef.current = ws;
    };

    connectLive();
    connectEvents();

    return () => {
      disposed = true;
      if (liveReconnectRef.current) clearTimeout(liveReconnectRef.current);
      if (eventsReconnectRef.current) clearTimeout(eventsReconnectRef.current);
      clearLivePreview();
      if (liveWsRef.current) liveWsRef.current.close();
      if (eventsWsRef.current) eventsWsRef.current.close();
    };
  }, [streamSession]);

  useEffect(() => {
    let cancelled = false;

    getCameraState()
      .then((state) => {
        if (cancelled) return;
        applyCameraState(state);
        if (state?.source_type && state.source_type !== "none") {
          setSelectedSourceId((current) => current || `${state.source_type}:${state.source_id}`);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          console.error("[Attendance] Failed to load camera state", loadError);
        }
      });

    getCameraSources()
      .then((data) => {
        if (cancelled) return;
        setSources(data || []);
        setSelectedSourceId((current) =>
          current || (data?.length ? getSourceId(data[0]) : current),
        );
      })
      .catch((loadError) => {
        if (!cancelled) {
          console.error("[Attendance] Failed to load sources", loadError);
        }
      });

    getAttendanceGateMode()
      .then((gateMode) => {
        if (cancelled) return;
        if (gateMode?.direction_mode) {
          setGateDirectionMode(gateMode.direction_mode);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          console.error("[Attendance] Failed to load gate direction mode", loadError);
        }
      });

    getAttendancePpePolicy()
      .then((policy) => {
        if (cancelled) return;
        setPpePolicy(policy);
        if (policy?.require_helmet || policy?.require_vest || policy?.deny_non_compliant_entry) {
          lastEnabledPpePolicyRef.current = {
            require_helmet: Boolean(policy.require_helmet),
            require_vest: Boolean(policy.require_vest),
            deny_non_compliant_entry: Boolean(policy.deny_non_compliant_entry),
          };
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          console.error("[Attendance] Failed to load PPE policy", loadError);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!cameraState?.active) {
      return undefined;
    }

    let cancelled = false;
    const pollState = async () => {
      try {
        const state = await getCameraState();
        if (!cancelled) {
          applyCameraState(state);
        }
      } catch (pollError) {
        if (!cancelled) {
          console.error("[Attendance] Failed to poll camera state", pollError);
        }
      }
    };

    const timer = window.setInterval(
      pollState,
      cameraState?.mode === "gate" ? 700 : 1200,
    );
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [cameraState?.active, cameraState?.mode]);

  const selectedSourceLabel =
    sources.find((source) => getSourceId(source) === selectedSourceId)?.name ||
    "No camera selected";
  const selectedShift =
    SHIFT_BLOCKS.find((shift) => shift.id === selectedShiftId) || SHIFT_BLOCKS[0];
  const selectedShiftWindow = getRelevantShiftWindow(selectedShift.id);
  const gateModeEnabled = Boolean(cameraState?.active) && cameraState?.mode === "gate";
  const personsById = new Map(personsData.map((person) => [person.id, person]));
  const scopedGateReviews = gateReviews.filter((review) =>
    review.status === "PENDING"
      ? !getReviewShiftId(review, personsById) ||
        getReviewShiftId(review, personsById) === selectedShift.id
      : isRecordInShiftWindow(
          { timestamp: review.timestamp || review.decided_at },
          selectedShiftWindow,
        ),
  );
  const { activeSessions: rawActiveSessions, rosterCards } = buildAttendanceSessionState({
    persons: personsData,
    attendanceRecords,
    gateReviews,
  });
  // Drop "Unknown"/null-person sessions from the on-site count so leftover
  // phantom entries from the old unknown-approval flow can't block mode swaps.
  const activeSessions = rawActiveSessions.filter(
    (session) => Boolean(session.personId),
  );
  const pendingReviews = gateModeEnabled
    ? scopedGateReviews
        .filter((review) => review.status === "PENDING")
        .filter(
          (review) =>
            !(
              gateStatus?.person_id &&
              gateStatus.person_id === review.person_id &&
              gateStatus.match_status === "confirmed_match"
            ),
        )
        .map((review) => getEffectivePendingReview(review, gateStatus))
    : [];
  // Split reviews: known workers (low-confidence match) vs unrecognised faces
  const knownWorkerReviews = pendingReviews.filter((r) => r.person_id != null);
  const unknownAttempts = pendingReviews.filter((r) => r.person_id == null);

  const rosterEntries = rosterCards
    .filter((card) => !card.shiftId || card.shiftId === selectedShift.id)
    .map((card) => ({
      ...card,
      registeredViolations: (card.registeredViolations || []).filter(
        (violation) => !violation.shiftId || violation.shiftId === selectedShift.id,
      ),
    }));
  const registeredWorkers = personsData.filter(
    (person) =>
      person.is_active !== false &&
      (!person.shift_id || person.shift_id === selectedShift.id),
  );
  const registeredWorkerIds = new Set(
    registeredWorkers.map((person) => person.id).filter(Boolean),
  );
  const activeShiftSessions = activeSessions.filter(
    (session) => !session.shiftId || session.shiftId === selectedShift.id,
  );
  const activeSessionPersonIds = new Set(
    activeSessions
      .map((session) => session.personId)
      .filter(Boolean),
  );
  const redundantEntryScanActive =
    gateDirectionMode === "ENTRY" &&
    gateStatus?.person_id &&
    activeSessionPersonIds.has(gateStatus.person_id);
  const onSiteCount = activeShiftSessions.length;
  const checkInCandidateCount = Math.max(registeredWorkers.length - onSiteCount, 0);
  const allRegisteredWorkersOnSite =
    registeredWorkers.length > 0 && onSiteCount >= registeredWorkers.length;
  const noWorkersOnSite = onSiteCount === 0;
  const checkoutModeLocked =
    gateDirectionMode === "EXIT" && allRegisteredWorkersOnSite;
  const checkInModeLocked =
    gateDirectionMode === "ENTRY" && noWorkersOnSite;
  const canUseCheckIn = !isChangingGateDirection && !checkoutModeLocked;
  const canUseCheckOut = !isChangingGateDirection && !checkInModeLocked;

  const onSiteValue =
    registeredWorkers.length > 0
      ? `${onSiteCount}/${registeredWorkers.length}`
      : "No records";
  const ppeSystemEnabled = Boolean(
    ppePolicy?.require_helmet ||
      ppePolicy?.require_vest ||
      ppePolicy?.deny_non_compliant_entry,
  );
  const ppeMode = (() => {
    // Three operating modes mapped onto the three underlying flags:
    //  off     — nothing is required, PPE detector never fires at the gate.
    //  monitor — helmet+vest required, detections logged, entry still granted.
    //  enforce — helmet+vest required AND non-compliant workers are blocked.
    const itemsRequired = Boolean(
      ppePolicy?.require_helmet || ppePolicy?.require_vest,
    );
    const enforceBlock = Boolean(ppePolicy?.deny_non_compliant_entry);
    if (!itemsRequired && !enforceBlock) return "off";
    if (!enforceBlock) return "monitor";
    return "enforce";
  })();
  const canToggleGateMode =
    Boolean(cameraState?.active) &&
    hasLiveFrame &&
    !isChangingRecognitionMode &&
    !isStarting;
  const entryModeNeedsManualCheckout =
    gateModeEnabled && gateDirectionMode === "ENTRY" && allRegisteredWorkersOnSite;
  const siteFullKnownWorkerDetected =
    entryModeNeedsManualCheckout &&
    gateStatus?.person_id &&
    registeredWorkerIds.has(gateStatus.person_id);
  const siteFullUnknownDetected =
    entryModeNeedsManualCheckout &&
    !gateStatus?.person_id &&
    gateStatus?.match_status === "unknown_face";
  const recognitionStatusDetail = !cameraState?.active
    ? null
    : !hasLiveFrame
      ? "Waiting for a stable live frame before recognition can be enabled."
      : !gateModeEnabled
        ? null
        : siteFullKnownWorkerDetected
          ? "All registered workers on site."
          : siteFullUnknownDetected
            ? "Unknown face."
            : gateStatus?.message ||
              (redundantEntryScanActive
                ? `${gateStatus?.person_name || "Worker"} is already checked in.`
                : null) ||
              (gateDirectionMode === "EXIT"
                ? "Recognition is scanning checked-in workers for checkout."
                : "Recognition is scanning enrolled workers for check-in.");
  const livePpeDetails = normalizePpeDetails(gateStatus?.ppe_details);
  const livePpeSummary = !ppeSystemEnabled
    ? "PPE detection is turned off — workers are admitted on face match alone."
    : !cameraState?.active
      ? "Start the live feed to begin scanning helmets and vests."
      : !gateModeEnabled
        ? "Enable recognition to start scanning PPE on matched workers."
        : gateDirectionMode === "EXIT"
          ? "PPE checks are skipped on check-out — the worker has already entered."
          : gateStatus?.ppe_message ||
            livePpeDetails.detector_message ||
            (ppeMode === "enforce"
              ? "Enforce mode: helmet + vest required before entry."
              : "Monitor mode: helmet + vest are logged but entry is still granted.");
  const liveHealthLabel = cameraState?.active
    ? !hasLiveFrame
      ? "Waiting for video"
      : gateModeEnabled
      ? "Recognition active"
      : "Live camera, matching paused"
    : "Camera offline";
  const displayError =
    error &&
    !(
      cameraState?.active &&
      cameraState?.owner_module === "attendance" &&
      /controlled by attendance/i.test(error)
    )
      ? error
      : null;

  useEffect(() => {
    let cancelled = false;

    const loadAttendanceData = async () => {
      try {
        const [persons, attendanceRecords, reviews] = await Promise.all([
          getPersons(),
          getAttendance({ limit: 500 }),
          getAttendanceReviews("all", { limit: 500 }),
        ]);

        if (cancelled) {
          return;
        }

        setPersonsData(persons || []);
        setAttendanceRecords(attendanceRecords || []);
        setGateReviews(reviews || []);
      } catch (loadError) {
        if (!cancelled) {
          console.error("[Attendance] Failed to load attendance data", loadError);
        }
      }
    };

    loadAttendanceData();
    const refreshTimer = setInterval(
      loadAttendanceData,
      cameraState?.active ? 3000 : 10000,
    );

    return () => {
      cancelled = true;
      clearInterval(refreshTimer);
    };
  }, [attendanceRefreshTick, cameraState?.active]);

  useEffect(() => {
    if (!cameraState?.active || hasLiveFrame) {
      return undefined;
    }

    const reconnectTimer = window.setTimeout(() => {
      if (!hasLiveFrameRef.current) {
        setStreamSession((current) => current + 1);
      }
    }, 2500);

    return () => window.clearTimeout(reconnectTimer);
  }, [cameraState?.active, hasLiveFrame, streamSession]);

  const refreshSources = async () => {
    if (cameraState?.active) {
      const activeSourceId =
        cameraState.source_type && cameraState.source_type !== "none"
          ? `${cameraState.source_type}:${cameraState.source_id || "0"}`
          : selectedSourceId || "webcam:0";
      const restoreMode = cameraState.mode === "gate" ? "gate" : null;

      setError(null);
      setIsRecoveringFeed(true);
      try {
        if (restoreMode === "gate") {
          setGateStatus({
            match_status: "starting",
            message: "Recovering camera feed...",
          });
        }
        await startStableFeed(activeSourceId, { restoreMode });
      } catch (cameraError) {
        setError(cameraError.message || "Failed to recover camera feed.");
      } finally {
        setIsRecoveringFeed(false);
      }
      return;
    }

    try {
      const data = await getCameraSources();
      setSources(data || []);
      setSelectedSourceId((current) =>
        current || (data?.length ? getSourceId(data[0]) : current),
      );
    } catch (loadError) {
      setError(loadError.message || "Failed to refresh sources.");
    }
  };

  const waitForLiveFrame = (timeoutMs = 3500) =>
    new Promise((resolve, reject) => {
      const startedAt = Date.now();

      const checkReady = () => {
        if (hasLiveFrameRef.current) {
          resolve();
          return;
        }

        if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error("Camera feed started but no live frames were received."));
          return;
        }

        window.setTimeout(checkReady, 120);
      };

      checkReady();
    });

  const startStableFeed = async (sourceId, { restoreMode = null } = {}) => {
    const parsed = parseSourceId(sourceId || "webcam:0");
    let started = false;
    let lastError = null;

    for (let attempt = 0; attempt < 3 && !started; attempt += 1) {
      try {
        setStreamSession((current) => current + 1);
        resetLiveMetrics();

        const state = await startCamera(
          parsed.type,
          parsed.id,
          cameraOwnerRef.current,
        );
        applyCameraState(state);
        if (state?.source_type && state?.source_id != null) {
          setSelectedSourceId(`${state.source_type}:${state.source_id}`);
        }

        await waitForLiveFrame(3600);

        if (restoreMode && restoreMode !== "idle") {
          const restoredState = await setCameraMode(restoreMode, cameraOwnerRef.current);
          applyCameraState(restoredState);
        }

        started = true;
      } catch (cameraError) {
        lastError = cameraError;
        try {
          await stopCamera(cameraOwnerRef.current);
        } catch {
          // Ignore cleanup errors between startup retries.
        }
      }
    }

    if (!started) {
      throw lastError || new Error("Failed to start a stable live feed.");
    }
  };

  const handleStart = async () => {
    const fallbackSourceId = selectedSourceId || "webcam:0";

    setError(null);
    setIsStarting(true);
    try {
      await startStableFeed(fallbackSourceId);
    } catch (cameraError) {
      setError(cameraError.message || "Failed to start gate camera.");
    } finally {
      setIsStarting(false);
    }
  };

  const handleStop = async () => {
    try {
      setError(null);
      const state = await stopCamera(cameraOwnerRef.current);
      applyCameraState(state);
      resetLiveMetrics();
      setGateStatus(null);
      setGateReviews((current) => current.filter((review) => review.status !== "PENDING"));
      setAttendanceRefreshTick((current) => current + 1);
    } catch (cameraError) {
      setError(cameraError.message || "Failed to stop gate camera.");
    }
  };

  const handleToggleGateMode = async () => {
    if (!cameraState?.active) {
      setError("Start the feed before enabling recognition mode.");
      return;
    }

    if (!hasLiveFrame && !gateModeEnabled) {
      setError("Wait for the live feed to stabilize before enabling recognition mode.");
      return;
    }

    const nextMode = gateModeEnabled ? "idle" : "gate";

    try {
      setError(null);
      setIsChangingRecognitionMode(true);
      if (nextMode === "gate") {
        setGateStatus({
          match_status: "starting",
          message: "Recognition mode is starting...",
        });
      }
      const state = await setCameraMode(nextMode, cameraOwnerRef.current);
      applyCameraState(state);
      if (nextMode !== "gate") {
        setGateStatus(null);
        setGateReviews((current) => current.filter((review) => review.status !== "PENDING"));
        setAttendanceRefreshTick((current) => current + 1);
      }
    } catch (cameraError) {
      setError(cameraError.message || "Failed to change gate mode.");
    } finally {
      setIsChangingRecognitionMode(false);
    }
  };

  const handleGateDirectionChange = async (directionMode) => {
    if (directionMode === gateDirectionMode) {
      return;
    }

    // Direction can now be hot-swapped at any time — even while the camera is
    // running. The backend swaps the candidate scope on the next frame and the
    // operator does not need to stop + restart the feed just to check someone
    // out after checking others in.
    try {
      setError(null);
      setIsChangingGateDirection(true);
      const payload = await updateAttendanceGateMode(directionMode);
      setGateDirectionMode(payload.direction_mode);
      setGateStatus((currentStatus) =>
        currentStatus
          ? {
              ...currentStatus,
              direction_mode: payload.direction_mode,
              candidate_scope: payload.candidate_scope,
            }
          : currentStatus,
      );
    } catch (modeError) {
      setError(modeError.message || "Failed to change gate direction mode.");
    } finally {
      setIsChangingGateDirection(false);
    }
  };

  const handleReviewDecision = async (reviewId, decision) => {
    try {
      setError(null);
      setDecisionInFlightId(reviewId);
      setGateReviews((current) =>
        current.map((review) =>
          review.id === reviewId
            ? {
                ...review,
                status: decision,
                decided_by: user?.email || "Authorized operator",
                decided_at: new Date().toISOString(),
              }
            : review,
        ),
      );
      // Attribution is taken from the session server-side; the body only
      // carries the decision.
      const decidedReview = await decideAttendanceReview(reviewId, { decision });
      setGateReviews((current) =>
        current.map((review) => (review.id === reviewId ? decidedReview : review)),
      );
      try {
        const [persons, records, reviews] = await Promise.all([
          getPersons(),
          getAttendance({ limit: 500 }),
          getAttendanceReviews("all", { limit: 500 }),
        ]);
        setPersonsData(persons || []);
        setAttendanceRecords(records || []);
        setGateReviews(reviews || []);
      } catch (refreshError) {
        console.error("[Attendance] Failed to refresh after review decision", refreshError);
      }
      setAttendanceRefreshTick((current) => current + 1);
    } catch (decisionError) {
      setAttendanceRefreshTick((current) => current + 1);
      setError(decisionError.message || "Failed to resolve gate review.");
    } finally {
      setDecisionInFlightId(null);
    }
  };

  const handleChangePpeMode = async (nextMode) => {
    if (nextMode === ppeMode || isChangingPpePolicy || !canEditPpePolicy) return;
    let nextPolicy;
    if (nextMode === "off") {
      nextPolicy = {
        require_helmet: false,
        require_vest: false,
        deny_non_compliant_entry: false,
      };
    } else if (nextMode === "monitor") {
      nextPolicy = {
        require_helmet: true,
        require_vest: true,
        deny_non_compliant_entry: false,
      };
    } else {
      nextPolicy = {
        require_helmet: true,
        require_vest: true,
        deny_non_compliant_entry: true,
      };
    }

    try {
      setError(null);
      setIsChangingPpePolicy(true);
      const updatedPolicy = await updateAttendancePpePolicy(nextPolicy);
      setPpePolicy(updatedPolicy);
      if (
        updatedPolicy?.require_helmet ||
        updatedPolicy?.require_vest ||
        updatedPolicy?.deny_non_compliant_entry
      ) {
        lastEnabledPpePolicyRef.current = {
          require_helmet: Boolean(updatedPolicy.require_helmet),
          require_vest: Boolean(updatedPolicy.require_vest),
          deny_non_compliant_entry: Boolean(updatedPolicy.deny_non_compliant_entry),
        };
      }
    } catch (policyError) {
      setError(policyError.message || "Failed to change PPE mode.");
    } finally {
      setIsChangingPpePolicy(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden p-6 xl:p-8">
      <div className="pointer-events-none absolute inset-0">
        <div
          className="absolute left-[18%] top-[-12%] h-[24rem] w-[24rem] rounded-full blur-3xl"
          style={{
            background:
              "radial-gradient(circle, var(--color-accent-primary-glow), transparent 65%)",
          }}
        />
        <div
          className="absolute bottom-[-8rem] right-[-6rem] h-[18rem] w-[18rem] rounded-full blur-3xl"
          style={{
            background:
              "radial-gradient(circle, var(--color-success-muted), transparent 70%)",
          }}
        />
      </div>

      {/* Real-time alert notifications */}
      <div className="fixed right-4 top-4 z-50 flex flex-col gap-2" style={{ maxWidth: "380px" }}>
        <AnimatePresence>
          {alertNotifications.map((n) => (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, x: 60 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 60 }}
              className="flex items-start gap-3 rounded-2xl border px-4 py-3 shadow-lg"
              style={{
                borderColor: n.type === "danger" ? "var(--color-error)" : "var(--color-warning)",
                backgroundColor: "var(--color-bg-card)",
              }}
            >
              <AlertTriangleIcon
                size={18}
                style={{ color: n.type === "danger" ? "var(--color-error)" : "var(--color-warning)", flexShrink: 0, marginTop: 2 }}
              />
              <p className="text-sm font-semibold text-primary">{n.message}</p>
              <button
                type="button"
                onClick={() => setAlertNotifications((prev) => prev.filter((x) => x.id !== n.id))}
                className="ml-auto text-secondary hover:text-primary"
                aria-label="Dismiss"
              >
                ×
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <div className="relative z-10">
        <motion.header
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between"
        >
          <div className="max-w-3xl">
            <p className="eyebrow mb-3">{t("command_center")}</p>
            <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
              {t("attendance_detection")}
            </h1>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[480px]">
            {SHIFT_BLOCKS.map((shift) => (
              <button
                key={shift.id}
                type="button"
                onClick={() => setSelectedShiftId(shift.id)}
                className={`rounded-2xl border px-4 py-4 text-left transition-all duration-200 ${
                  shift.id === selectedShift.id
                    ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary-muted)] shadow-[var(--glow-accent)]"
                    : "border-default bg-card hover:border-[var(--color-border-emphasis)] hover:bg-[var(--color-bg-card-hover)]"
                }`}
              >
                <p className="text-sm font-semibold text-primary">{shift.label}</p>
                <p className="mt-1 text-sm text-secondary">{shift.window}</p>
              </button>
            ))}
          </div>
        </motion.header>

        <AnimatePresence>
          {displayError && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-8 overflow-hidden rounded-2xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-5 py-4"
            >
              <p
                className="text-sm font-semibold"
                style={{ color: "var(--color-error)" }}
              >
                {displayError}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="space-y-8">
          <div className="grid gap-8 2xl:grid-cols-[1.55fr_1fr]">
            <motion.section
              custom={0}
              variants={cardVariants}
              initial="hidden"
              animate="visible"
              className="panel overflow-hidden"
            >
              <div className="panel__header">
                <div className="flex items-center gap-3">
                  <VideoIcon size={20} className="text-accent" />
                  <div>
                    <h2 className="font-display text-xl font-semibold text-primary">
                      Live Gate Verification
                    </h2>
                    <p className="mt-1 text-sm text-secondary">
                      Selected camera: {selectedSourceLabel}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={
                      gateModeEnabled ? "badge badge-success" : "badge badge-info"
                    }
                  >
                    {liveHealthLabel}
                  </span>
                  {cameraState?.active && (
                    <span className="badge badge-error flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-current pulse" />
                      LIVE
                    </span>
                  )}
                </div>
              </div>

              <div className="grid gap-0 xl:grid-cols-[1.65fr_0.95fr]">
                <div className="relative aspect-[16/9] bg-[var(--color-bg-deepest)] xl:aspect-auto">
                  <img
                    ref={liveImageRef}
                    alt="Gate monitoring feed"
                    className={`h-full w-full object-contain ${
                      hasLiveFrame ? "block" : "hidden"
                    }`}
                  />
                  {!hasLiveFrame ? (
                    <div className="flex h-full items-center justify-center px-8 py-12">
                      <div className="max-w-md text-center">
                        <CameraIcon size={48} className="mx-auto mb-4 text-muted" />
                        <p className="text-lg font-semibold text-primary">
                          Gate camera standing by
                        </p>
                      </div>
                    </div>
                  ) : null}

                  <div className="absolute bottom-4 left-4 right-4 flex flex-wrap gap-3">
                    <div className="rounded-xl border border-default bg-card/90 px-4 py-2.5 backdrop-blur-sm">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-tertiary">
                        Shift Window
                      </p>
                      <p className="mt-1 text-sm font-semibold text-primary">
                        {selectedShift.window}
                      </p>
                    </div>
                    <div className="rounded-xl border border-default bg-card/90 px-4 py-2.5 backdrop-blur-sm">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-tertiary">
                        Live FPS
                      </p>
                      <p className="mt-1 text-sm font-semibold text-primary">
                        {liveFps ? liveFps.toFixed(1) : "0.0"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-default bg-card/90 px-4 py-2.5 backdrop-blur-sm">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-tertiary">
                        WebSocket
                      </p>
                      <p
                        className="mt-1 text-sm font-semibold"
                        style={{
                          color: wsConnected
                            ? "var(--color-success)"
                            : "var(--color-text-secondary)",
                        }}
                      >
                        {wsConnected ? "Connected" : "Retrying"}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="border-t border-default bg-[var(--color-bg-card)] xl:border-l xl:border-t-0">
                  <div className="space-y-6 p-6">
                    <div>
                      <p className="eyebrow mb-3">Gate Control</p>
                      <div className="mb-4 grid gap-3">
                        <div className="grid gap-3 sm:grid-cols-2">
                          <button
                            type="button"
                            onClick={() => handleGateDirectionChange("ENTRY")}
                            disabled={isChangingGateDirection || !canUseCheckIn}
                            className={`rounded-2xl border px-4 py-3 text-left transition-all ${
                              gateDirectionMode === "ENTRY"
                                ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary-muted)]"
                                : "border-default bg-card hover:border-[var(--color-border-emphasis)]"
                            } ${isChangingGateDirection || !canUseCheckIn ? "opacity-60" : ""}`}
                          >
                            <p className="text-sm font-semibold text-primary">Check-In</p>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleGateDirectionChange("EXIT")}
                            disabled={isChangingGateDirection || !canUseCheckOut}
                            className={`rounded-2xl border px-4 py-3 text-left transition-all ${
                              gateDirectionMode === "EXIT"
                                ? "border-[var(--color-warning)] bg-[var(--color-warning-muted)]"
                                : "border-default bg-card hover:border-[var(--color-border-emphasis)]"
                            } ${isChangingGateDirection || !canUseCheckOut ? "opacity-60" : ""}`}
                          >
                            <p className="text-sm font-semibold text-primary">Check-Out</p>
                          </button>
                        </div>
                        {cameraState?.active ? (
                          <p className="text-sm text-secondary">
                            {checkoutModeLocked
                              ? "Check-In is locked because all registered workers are on site."
                              : checkInModeLocked
                                ? "Check-Out is locked because nobody is currently on site."
                              : allRegisteredWorkersOnSite && gateDirectionMode === "ENTRY"
                                ? "All registered workers on site."
                                : "Switch between Check-In and Check-Out without stopping the camera."}
                          </p>
                        ) : null}
                      </div>
                      <select
                        value={selectedSourceId}
                        onChange={(event) => setSelectedSourceId(event.target.value)}
                        disabled={cameraState?.active || isStarting}
                        className="input h-12 disabled:opacity-50"
                      >
                        {sources.length === 0 && <option value="webcam:0">Webcam 0</option>}
                        {sources.map((source) => (
                          <option key={getSourceId(source)} value={getSourceId(source)}>
                            {source.name}
                          </option>
                        ))}
                      </select>

                      <div className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-2">
                        <button
                          type="button"
                          onClick={handleStart}
                          disabled={cameraState?.active || isStarting || isRecoveringFeed}
                          className="btn btn-primary h-12 px-4"
                        >
                          {isStarting ? "Starting..." : "Start Feed"}
                        </button>
                        <button
                          type="button"
                          onClick={handleStop}
                          disabled={!cameraState?.active}
                          className="btn h-12 px-4 text-white disabled:opacity-50"
                          style={{ backgroundColor: "var(--color-error)" }}
                        >
                          Stop Feed
                        </button>
                        <button
                          type="button"
                          onClick={refreshSources}
                          disabled={isStarting || isRecoveringFeed}
                          className="btn btn-secondary h-12 px-4 disabled:opacity-50 xl:col-span-2"
                        >
                          <RefreshIcon size={16} />
                          {cameraState?.active
                            ? isRecoveringFeed
                              ? "Recovering Feed..."
                              : "Recover Feed"
                            : "Refresh Sources"}
                        </button>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-4">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <p className="text-base font-semibold text-primary">
                            Recognition Mode
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          <span
                            className={
                              gateModeEnabled ? "badge badge-success" : "badge badge-info"
                            }
                          >
                            {gateModeEnabled ? "Enabled" : "Disabled"}
                          </span>
                          <ToggleSwitch
                            checked={gateModeEnabled}
                            disabled={!canToggleGateMode}
                            ariaLabel="Toggle recognition mode"
                            onClick={handleToggleGateMode}
                          />
                        </div>
                      </div>
                      {recognitionStatusDetail ? (
                        <p className="mt-1 text-sm text-secondary">
                          {recognitionStatusDetail}
                        </p>
                      ) : null}
                    </div>

                    <div className="grid gap-4">
                      <div className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-4">
                        <StatCard
                          icon={UsersIcon}
                          label="On Site"
                          value={onSiteValue}
                          helper={
                            registeredWorkers.length > 0
                              ? `${checkInCandidateCount} available for check-in`
                              : "No workers enrolled yet"
                          }
                        />
                      </div>

                    </div>
                  </div>
                </div>
              </div>

              <div className="border-t border-default bg-[var(--color-bg-card)] p-6">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <AlertTriangleIcon size={18} className="text-accent" />
                    <div>
                      <h3 className="text-base font-semibold text-primary">
                        Review Queue
                      </h3>
                    </div>
                  </div>
                  <span className="badge badge-warning">{knownWorkerReviews.length} active</span>
                </div>

                <div className="max-h-[320px] space-y-4 overflow-y-auto pr-1">
                  {knownWorkerReviews.length > 0 ? (
                    knownWorkerReviews.map((review) => (
                      <article
                        key={review.id}
                        className="rounded-2xl border border-[var(--color-warning)] bg-[var(--color-warning-muted)] p-4"
                      >
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                          <div className="flex items-start gap-4">
                            {review.snapshot_data_url ? (
                              <img
                                src={review.snapshot_data_url}
                                alt={review.person_name || "Pending review"}
                                className="h-20 w-20 rounded-2xl border border-default object-cover"
                              />
                            ) : (
                              <div className="flex h-20 w-20 items-center justify-center rounded-2xl border border-default bg-card">
                                <UsersIcon size={24} className="text-accent" />
                              </div>
                            )}
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-base font-semibold text-primary">
                                  {review.person_name || "Unknown worker"}
                                </p>
                                <span className="badge badge-warning">
                                  {review.confidence != null
                                    ? `${Math.round(review.confidence * 100)}% match`
                                    : "Review"}
                                </span>
                              </div>
                              <p className="mt-1 text-sm text-secondary">
                                {[review.person_employee_id, review.suggested_direction]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {formatReviewReasons(review).map((reason) => (
                                  <span key={`${review.id}-${reason}`} className="badge badge-warning">
                                    {reason}
                                  </span>
                                ))}
                                {formatPpeStatusLabel(review.ppe_details) ? (
                                  <span className={getPpeBadgeClass(review.ppe_details)}>
                                    {formatPpeStatusLabel(review.ppe_details)}
                                  </span>
                                ) : null}
                              </div>
                              {normalizePpeDetails(review.ppe_details).missing_items.length > 0 ? (
                                <p className="mt-2 text-sm text-secondary">
                                  Missing PPE: {normalizePpeDetails(review.ppe_details).missing_items.join(", ")}
                                </p>
                              ) : null}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              disabled={decisionInFlightId === review.id}
                              onClick={() => handleReviewDecision(review.id, "APPROVED")}
                              className="btn btn-primary h-10 px-4"
                            >
                              Accept
                            </button>
                            <button
                              type="button"
                              disabled={decisionInFlightId === review.id}
                              onClick={() => handleReviewDecision(review.id, "DENIED")}
                              className="btn h-10 px-4 text-white"
                              style={{ backgroundColor: "var(--color-error)" }}
                            >
                              Deny
                            </button>
                          </div>
                        </div>
                      </article>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-dashed border-default px-5 py-10 text-center">
                      <CheckCircleIcon size={30} className="mx-auto mb-3 text-accent" />
                      <p className="text-base font-semibold text-primary">
                        No manual reviews waiting
                      </p>
                      <p className="mt-2 text-sm text-secondary">
                        New manual-review matches will appear here for approval or denial.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </motion.section>

            <div className="space-y-6">
            <motion.section
              custom={1}
              variants={cardVariants}
              initial="hidden"
              animate="visible"
              className="panel"
            >
              <div className="panel__header">
                <div className="flex items-center gap-3">
                  <UsersIcon size={20} className="text-accent" />
                  <div>
                    <h2 className="font-display text-xl font-semibold text-primary">
                      Workforce Roster
                    </h2>
                  </div>
                </div>
                <span className="badge badge-accent">{rosterEntries.length} active</span>
              </div>

              <div className="panel__content">
                {rosterEntries.length > 0 ? (
                  <div
                    className="grid grid-cols-1 max-h-[640px] gap-5 overflow-y-auto pr-2"
                    style={{
                      // Nudge the roster toward card-by-card stepping instead of
                      // loose free scrolling.
                      scrollSnapType: "y mandatory",
                      scrollBehavior: "smooth",
                      scrollPaddingBlock: "0.5rem",
                      overscrollBehaviorY: "contain",
                      scrollbarGutter: "stable",
                    }}
                  >
                    {rosterEntries.map((row) => (
                      <article
                        key={row.id}
                        style={{
                          scrollSnapAlign: "start",
                          scrollSnapStop: "always",
                          scrollMarginBlock: "0.5rem",
                        }}
                        className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-5 shadow-sm"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div className="min-w-0 flex-1">
                            <h3 className="text-lg font-semibold text-primary">
                              {row.personName}
                            </h3>
                            <p className="mt-1 text-sm text-secondary">
                              {[row.employeeId, getShiftLabel(row.shiftId || selectedShift.id)]
                                .filter(Boolean)
                                .join(" · ")}
                            </p>
                          </div>
                        </div>

                        <div className="mt-5 space-y-4">
                          {[
                            {
                              key: "check-in",
                              label: "Check-In",
                              tone: "badge badge-success",
                              event: row.latestCheckIn,
                            },
                            {
                              key: "check-out",
                              label: "Check-Out",
                              tone: "badge badge-warning",
                              event: row.latestCheckOut,
                            },
                          ].map((section) => (
                            <div
                              key={section.key}
                              className="rounded-xl border border-default bg-card px-4 py-3"
                            >
                              <div className="mb-4 flex flex-wrap items-center gap-2">
                                <span className={section.tone}>{section.label}</span>
                                {section.event ? (
                                  <span className="badge badge-info">
                                    {formatLogMethodLabel(section.event.logMethod)}
                                  </span>
                                ) : null}
                              </div>

                              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                                <div>
                                  <p className="eyebrow mb-1.5">Timestamp</p>
                                  <p className="text-sm font-semibold text-primary">
                                    {formatEventTimestamp(section.event?.timestamp)}
                                  </p>
                                </div>
                                <div>
                                  <p className="eyebrow mb-1.5">Camera</p>
                                  <p className="text-sm font-semibold text-primary">
                                    {formatCameraSourceLabel(
                                      section.event?.cameraSourceType,
                                      section.event?.cameraSourceId,
                                    )}
                                  </p>
                                </div>
                                <div>
                                  <p className="eyebrow mb-1.5">Face Match</p>
                                  <p className="text-sm font-semibold text-primary">
                                    {formatFaceMatchLabel(section.event?.confidence)}
                                  </p>
                                </div>
                                <div>
                                  <p className="eyebrow mb-1.5">Log Method</p>
                                  <p className="text-sm font-semibold text-primary">
                                    {formatLogMethodLabel(section.event?.logMethod)}
                                  </p>
                                </div>
                              </div>

                              {(section.event?.snapshotDataUrl ||
                                (section.key === "check-in" &&
                                  getCompactPpeSummary(
                                    section.event?.ppeDetails,
                                    row.registeredViolations || [],
                                  ))) && (
                                <div className="mt-4 grid gap-x-5 gap-y-3 md:grid-cols-[8.5rem_minmax(0,1fr)] md:items-start">
                                  {section.event?.snapshotDataUrl ? (
                                    <div>
                                      <p className="eyebrow mb-2">Snapshot</p>
                                      <img
                                        src={section.event.snapshotDataUrl}
                                        alt={`${section.label} snapshot`}
                                        className="h-24 w-auto rounded-lg border border-default object-contain"
                                      />
                                    </div>
                                  ) : null}

                                  {section.key === "check-in" ? (
                                    <div className="min-w-0">
                                      {(() => {
                                        const ppeSummary = getCompactPpeSummary(
                                          section.event?.ppeDetails,
                                          row.registeredViolations || [],
                                        );
                                        if (!ppeSummary) {
                                          return (
                                            <p className="text-sm text-secondary">
                                              No PPE status recorded.
                                            </p>
                                          );
                                        }
                                        return (
                                          <div className="space-y-2">
                                            <div className="grid gap-3 sm:grid-cols-[7rem_minmax(0,1fr)] sm:items-start">
                                              <div>
                                                <p className="eyebrow mb-1.5">PPE</p>
                                                <p className="text-sm font-semibold text-primary">
                                                  {ppeSummary.label}
                                                </p>
                                                {ppeSummary.missingItems?.length > 0 ? (
                                                  <div className="mt-2 flex flex-col items-start gap-1">
                                                    {ppeSummary.missingItems.slice(0, 2).map((item) => (
                                                      <span
                                                        key={item}
                                                        className="inline-flex whitespace-nowrap rounded-full border border-[var(--color-error)] bg-[var(--color-error-muted)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]"
                                                        style={{ color: "var(--color-error)" }}
                                                      >
                                                        Missing {item}
                                                      </span>
                                                    ))}
                                                  </div>
                                                ) : (
                                                  <p className="mt-1 text-sm text-secondary">
                                                    {ppeSummary.description}
                                                  </p>
                                                )}
                                              </div>
                                              <div />
                                            </div>
                                          </div>
                                        );
                                      })()}
                                    </div>
                                  ) : null}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-default px-5 py-12 text-center">
                    <UsersIcon size={30} className="mx-auto mb-3 text-accent" />
                    <p className="text-base font-semibold text-primary">
                      No active attendance cycles for this shift
                    </p>
                    <p className="mt-2 text-sm text-secondary">
                      Completed check-in and check-out cycles clear from the roster automatically.
                    </p>
                  </div>
                )}
              </div>
            </motion.section>

            {/* PPE Command Center — vertical panel stacked under the Roster */}
            <motion.section
              custom={2}
              variants={cardVariants}
              initial="hidden"
              animate="visible"
              className="panel"
            >
              <div className="panel__header">
                <div className="flex items-center gap-3">
                  <ShieldIcon size={20} className="text-accent" />
                  <div>
                    <h2 className="font-display text-xl font-semibold text-primary">
                      PPE Command Center
                    </h2>
                    <p className="text-sm text-secondary">
                      Mode control and live helmet/vest scan status.
                    </p>
                  </div>
                </div>
                <span
                  className={
                    ppeMode === "enforce"
                      ? "badge badge-error"
                      : ppeMode === "monitor"
                        ? "badge badge-warning"
                        : "badge badge-info"
                  }
                >
                  {ppeMode === "enforce"
                    ? "Enforce"
                    : ppeMode === "monitor"
                      ? "Monitor"
                      : "Off"}
                </span>
              </div>

              <div className="panel__content space-y-5">
                {/* Mode selector */}
                <div>
                  <p className="eyebrow mb-3">Operating Mode</p>
                  {canEditPpePolicy ? null : (
                    <p className="mb-3 text-xs text-secondary">
                      Set by an administrator or general manager. Changes are recorded in the audit log.
                    </p>
                  )}
                  <div className="flex flex-col gap-2">
                    {[
                      {
                        id: "off",
                        title: "Off",
                        desc: "Face match alone grants entry.",
                      },
                      {
                        id: "monitor",
                        title: "Monitor",
                        desc: "Helmet + vest are scanned and logged, but entry is still granted.",
                      },
                      {
                        id: "enforce",
                        title: "Enforce",
                        desc: "Helmet + vest required. Non-compliant workers are blocked and routed to review.",
                      },
                    ].map((option) => {
                      const active = ppeMode === option.id;
                      return (
                        <button
                          key={option.id}
                          type="button"
                          disabled={isChangingPpePolicy || !canEditPpePolicy}
                          aria-disabled={!canEditPpePolicy}
                          onClick={() => handleChangePpeMode(option.id)}
                          className={`rounded-xl border px-4 py-3 text-left transition ${
                            active
                              ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary-muted)]"
                              : "border-default bg-card hover:border-[var(--color-accent-primary)]"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-semibold text-primary">
                              {option.title}
                            </span>
                            {active ? (
                              <span className="badge badge-success">Active</span>
                            ) : null}
                          </div>
                          <p className="mt-1 text-xs text-secondary">{option.desc}</p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Live scan status */}
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <p className="eyebrow">Live Scan Status</p>
                    <span className={gateModeEnabled ? "badge badge-success" : "badge badge-info"}>
                      {gateModeEnabled ? "Live detector active" : "Standby"}
                    </span>
                  </div>

                  {ppeMode === "off" ? (
                    <p className="text-sm text-secondary">
                      PPE scanning is disabled. Switch to Monitor or Enforce to start the detector.
                    </p>
                  ) : (
                    <>
                      {cameraState?.active && gateModeEnabled && gateDirectionMode !== "EXIT" ? (
                        <div className="mb-3 space-y-2">
                          {formatPpeStatusLabel(livePpeDetails) ? (
                            <span className={getPpeBadgeClass(livePpeDetails)}>
                              {formatPpeStatusLabel(livePpeDetails)}
                            </span>
                          ) : (
                            <span className="badge badge-info">Waiting for a matched worker</span>
                          )}
                          <div className="flex flex-wrap gap-2">
                            {(livePpeDetails.required_items || []).length > 0 ? (
                              (livePpeDetails.required_items || []).map((item) => {
                                const detected = (livePpeDetails.detected_items || []).includes(item);
                                return (
                                  <span
                                    key={item}
                                    className={detected ? "badge badge-success" : "badge badge-warning"}
                                  >
                                    {detected ? `${item} detected` : `${item} missing`}
                                  </span>
                                );
                              })
                            ) : (
                              <span className="badge badge-info">No PPE items required</span>
                            )}
                          </div>
                        </div>
                      ) : null}
                      <p className="mb-3 text-xs text-secondary">{livePpeSummary}</p>
                    </>
                  )}
                </div>
              </div>
            </motion.section>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

export default Attendance;
