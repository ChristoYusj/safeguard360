/*
 * SafeGuard 360 - Attendance Page
 * "Precision Command" Design System
 */

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import {
  decideAttendanceReview,
  getAttendance,
  getAttendanceGateMode,
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
} from "../services/api";
import {
  AlertTriangleIcon,
  BellIcon,
  CameraIcon,
  CheckCircleIcon,
  RefreshIcon,
  UsersIcon,
  VideoIcon,
} from "../components/icons";

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

function getAttendanceTone(worker) {
  if (worker.attendanceState === "verified") return "badge badge-success";
  if (worker.attendanceState === "checkedOut") return "badge badge-info";
  if (worker.attendanceState === "held") {
    return "badge badge-warning";
  }
  return "badge badge-info";
}

function getAttendanceLabel(worker) {
  if (worker.attendanceState === "verified") return "Checked In";
  if (worker.attendanceState === "checkedOut") return "Checked Out";
  if (worker.attendanceState === "held") return "Review Needed";
  return "Ready";
}

function getGateReviewClass(status) {
  if (status === "matched") return "badge badge-success";
  if (status === "review") return "badge badge-warning";
  return "badge badge-info";
}

function getGateReviewLabel(status) {
  if (status === "matched") return "Auto Match";
  if (status === "review") return "Manual Review";
  return "Awaiting Match";
}

function formatEventTime(value) {
  if (!value) {
    return "--";
  }

  return new Date(value).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
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

function getShiftIdForTimestamp(timestamp) {
  if (!timestamp) {
    return null;
  }

  const date = new Date(timestamp);
  const hour = date.getHours();
  if (hour >= 6 && hour < 14) return "day";
  if (hour >= 14 && hour < 22) return "swing";
  return "night";
}

function isRecordInShiftWindow(record, shiftWindow) {
  if (!record?.timestamp) {
    return false;
  }

  const recordTime = new Date(record.timestamp);
  return isDateInShiftWindow(recordTime, shiftWindow);
}

function buildWorkerNote(
  person,
  attendanceState,
  latestRecord,
  lastEntryRecord,
  shiftWindow,
  pendingReview,
) {
  const shiftLabel = getShiftLabel(shiftWindow.shiftId);

  if (!person.has_embedding) {
    return person.embedding_message || "Enrollment still needs usable face samples.";
  }

  if (pendingReview) {
    return `Low-confidence match at ${Math.round((pendingReview.confidence || 0) * 100)}%. Waiting for operator approval.`;
  }

  if (attendanceState === "held") {
    return "Latest gate event needs manual review before attendance can be cleared.";
  }

  if (attendanceState === "verified") {
    return `Checked in for ${shiftLabel} at ${formatEventTime(lastEntryRecord?.timestamp)}.`;
  }

  if (attendanceState === "checkedOut") {
    return `Checked out from ${shiftLabel} at ${formatEventTime(latestRecord?.timestamp)}.`;
  }

  if (!shiftWindow.hasStarted) {
    return `Expected once ${shiftLabel} opens at ${formatEventTime(shiftWindow.start)}.`;
  }

  return `Ready for gate scan during ${shiftLabel}.`;
}

function buildWorkerRecords(
  persons,
  attendanceRecords,
  gateReviews,
  selectedSourceLabel,
  selectedShiftWindow,
  liveGateStatus,
  gateModeEnabled,
) {
  const recordsByPersonId = new Map();
  const pendingReviewsByPersonId = new Map();
  const now = new Date();

  attendanceRecords.forEach((record) => {
    if (!record.person_id || !isRecordInShiftWindow(record, selectedShiftWindow)) {
      return;
    }

    const currentRecords = recordsByPersonId.get(record.person_id) || [];
    currentRecords.push(record);
    recordsByPersonId.set(record.person_id, currentRecords);
  });

  gateReviews.forEach((review) => {
    if (
      review.status !== "PENDING" ||
      !review.person_id ||
      !isRecordInShiftWindow(review, selectedShiftWindow)
    ) {
      return;
    }

    const currentReview = pendingReviewsByPersonId.get(review.person_id);
    if (!currentReview || new Date(review.timestamp) > new Date(currentReview.timestamp)) {
      pendingReviewsByPersonId.set(review.person_id, review);
    }
  });

  return persons.map((person) => {
    const personRecords = recordsByPersonId.get(person.id) || [];
    const pendingReview = pendingReviewsByPersonId.get(person.id) || null;
    const liveGateApplies =
      Boolean(gateModeEnabled) &&
      liveGateStatus?.person_id === person.id &&
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
    const latestRecord = personRecords[0];
    const lastEntryRecord =
      personRecords.find(
        (record) => record.direction === "ENTRY" && record.access_granted,
      ) || null;
    const isHeld =
      Boolean(effectivePendingReview) ||
      (liveGateApplies &&
        ["review_required", "possible_match", "not_checked_in"].includes(
          liveGateStatus?.match_status,
        )) ||
      (Boolean(latestRecord) &&
        (!latestRecord.access_granted || !latestRecord.ppe_compliant));
    const isVerified =
      Boolean(latestRecord) &&
      latestRecord.direction === "ENTRY" &&
      latestRecord.access_granted;
    const isCheckedOut =
      Boolean(latestRecord) &&
      latestRecord.direction === "EXIT" &&
      latestRecord.access_granted;
    const attendanceState = isHeld
      ? "held"
      : isVerified
        ? "verified"
        : isCheckedOut
          ? "checkedOut"
          : "expected";

    return {
      id: person.id,
      shiftId: person.shift_id || null,
      name: person.name,
      role: person.employee_id || "Enrolled worker",
      company: person.shift_id
        ? `${getShiftLabel(person.shift_id)} assigned`
        : "No shift assigned",
      attendanceState,
      matchState:
        liveGateApplies && liveGateStatus?.match_status === "confirmed_match"
          ? "matched"
          : effectivePendingReview
        ? "review"
        : latestRecord?.access_granted
          ? "matched"
          : "pending",
      cameraSource: selectedSourceLabel,
      lastCheckIn: lastEntryRecord?.timestamp
        ? formatEventTime(lastEntryRecord.timestamp)
        : null,
      confidence:
        liveConfidence != null
          ? liveConfidence
          : effectivePendingReview?.confidence != null
            ? Math.round(effectivePendingReview.confidence * 100)
            : latestRecord?.confidence != null
              ? Math.round(latestRecord.confidence * 100)
              : null,
      pendingReview: effectivePendingReview,
      riskLabel:
        liveGateApplies && liveGateStatus?.message
          ? liveGateStatus.message
          : buildWorkerNote(
        person,
        attendanceState,
        latestRecord,
        lastEntryRecord,
        selectedShiftWindow,
        effectivePendingReview,
      ),
    };
  });
}

function buildManualOverrideEntries(gateReviews) {
  return gateReviews
    .filter((review) => review.status === "APPROVED" || review.status === "DENIED")
    .map((review) => ({
      id: review.id,
      shiftId: getShiftIdForTimestamp(review.timestamp),
      workerName: review.person_name || "Unknown worker",
      cameraSource: "Gate review",
      triggeredBy: review.decided_by || "Authorized operator",
      time: formatEventTime(review.decided_at || review.timestamp),
      reason: review.decision_note || "Low-confidence recognition required operator review.",
      decision: review.status === "APPROVED" ? "Accepted" : "Denied",
      confidence: review.confidence != null ? Math.round(review.confidence * 100) : null,
    }));
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
  const { t } = useAppLanguage();
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
  const [isChangingRecognitionMode, setIsChangingRecognitionMode] = useState(false);
  const [isChangingGateDirection, setIsChangingGateDirection] = useState(false);
  const [liveFps, setLiveFps] = useState(0);
  const [decisionInFlightId, setDecisionInFlightId] = useState(null);

  const liveWsRef = useRef(null);
  const eventsWsRef = useRef(null);
  const cameraOwnerRef = useRef(getCameraOwner("attendance"));
  const latestCameraStateVersionRef = useRef(-1);
  const liveReconnectRef = useRef(null);
  const eventsReconnectRef = useRef(null);
  const liveImageRef = useRef(null);
  const hasLiveFrameRef = useRef(false);
  const pendingFrameSrcRef = useRef("");
  const frameFlushRef = useRef(null);
  const lastFrameTsRef = useRef(null);
  const smoothedFpsRef = useRef(0);
  const lastFpsUiUpdateRef = useRef(0);

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

      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        if (!disposed) {
          liveReconnectRef.current = setTimeout(connectLive, 2000);
        }
      };
      ws.onerror = () => setWsConnected(false);
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type !== "frame" || !payload.data) return;

          pendingFrameSrcRef.current = `data:image/jpeg;base64,${payload.data}`;
          if (frameFlushRef.current === null) {
            frameFlushRef.current = window.requestAnimationFrame(() => {
              frameFlushRef.current = null;
              if (liveImageRef.current && pendingFrameSrcRef.current) {
                liveImageRef.current.src = pendingFrameSrcRef.current;
              }
              if (!hasLiveFrameRef.current) {
                hasLiveFrameRef.current = true;
                setHasLiveFrame(true);
              }
            });
          }

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
      if (frameFlushRef.current !== null) {
        window.cancelAnimationFrame(frameFlushRef.current);
      }
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
  const personnel = buildWorkerRecords(
    personsData,
    attendanceRecords,
    gateReviews,
    selectedSourceLabel,
    selectedShiftWindow,
    gateStatus,
    gateModeEnabled,
  );
  const pendingReviews = gateModeEnabled
    ? gateReviews
        .filter(
          (review) =>
            review.status === "PENDING" &&
            (!getShiftIdForTimestamp(review.timestamp) ||
              getShiftIdForTimestamp(review.timestamp) === selectedShift.id),
        )
        .filter(
          (review) =>
            !(
              gateStatus?.person_id &&
              gateStatus.person_id === review.person_id &&
              gateStatus.match_status === "confirmed_match"
            ),
        )
        .map((review) => {
          if (
            gateStatus?.person_id &&
            gateStatus.person_id === review.person_id &&
            gateStatus.confidence != null
          ) {
            return {
              ...review,
              confidence: Math.max(review.confidence || 0, gateStatus.confidence),
            };
          }
          return review;
        })
    : [];
  const shiftWorkers = personnel.filter(
    (worker) => !worker.shiftId || worker.shiftId === selectedShift.id,
  );
  const onSiteCount = shiftWorkers.filter(
    (worker) => worker.attendanceState === "verified",
  ).length;
  const checkedOutCount = shiftWorkers.filter(
    (worker) => worker.attendanceState === "checkedOut",
  ).length;
  const flaggedWorkers = shiftWorkers.filter(
    (worker) =>
      worker.pendingReview,
  );
  const overrideEntries = buildManualOverrideEntries(gateReviews).filter(
    (entry) => !entry.shiftId || entry.shiftId === selectedShift.id,
  );
  const gateDirectionLabel =
    gateDirectionMode === "EXIT" ? "Check-Out Lane" : "Check-In Lane";
  const gateDirectionHelper =
    gateDirectionMode === "EXIT"
      ? "Exit lane only considers workers who are still on site and not yet checked out."
      : "Entry lane accepts enrolled workers and logs arrivals.";
  const intakeStatus =
    flaggedWorkers.length > 0
      ? "Review Needed"
      : onSiteCount > 0
        ? "Active"
        : "Awaiting arrivals";
  const intakeStatusBadgeClass =
    flaggedWorkers.length > 0
      ? "badge badge-warning"
      : onSiteCount > 0
        ? "badge badge-success"
        : "badge badge-info";
  const onSiteValue =
    shiftWorkers.length > 0 ? `${onSiteCount}/${shiftWorkers.length}` : "No records";
  const checkedOutValue = shiftWorkers.length > 0 ? `${checkedOutCount}` : "No exits";
  const canToggleGateMode = Boolean(cameraState?.active) && !isChangingRecognitionMode;
  const recognitionStatusDetail = !cameraState?.active
    ? "Start the feed first, then enable recognition."
    : !gateModeEnabled
      ? "Recognition is paused while the live camera stays available."
      : gateStatus?.message ||
        (gateDirectionMode === "EXIT"
          ? "Recognition is scanning checked-in workers for checkout."
          : "Recognition is scanning enrolled workers for check-in.");
  const liveHealthLabel = cameraState?.active
    ? gateModeEnabled
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
          getAttendance(),
          getAttendanceReviews(),
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
  }, [cameraState?.active, hasLiveFrame]);

  const refreshSources = async () => {
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

  const handleStart = async () => {
    const fallbackSourceId = selectedSourceId || "webcam:0";
    const parsed = parseSourceId(fallbackSourceId);

    setError(null);
    setIsStarting(true);
    try {
      setStreamSession((current) => current + 1);
      setHasLiveFrame(false);
      hasLiveFrameRef.current = false;
      pendingFrameSrcRef.current = "";
      lastFrameTsRef.current = null;
      smoothedFpsRef.current = 0;
      lastFpsUiUpdateRef.current = 0;
      if (liveImageRef.current) {
        liveImageRef.current.removeAttribute("src");
      }
      const state = await startCamera(
        parsed.type,
        parsed.id,
        cameraOwnerRef.current,
      );
      applyCameraState(state);
      if (state?.source_type && state?.source_id != null) {
        setSelectedSourceId(`${state.source_type}:${state.source_id}`);
      }
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
      setHasLiveFrame(false);
      setLiveFps(0);
      setGateStatus(null);
      hasLiveFrameRef.current = false;
      pendingFrameSrcRef.current = "";
      lastFrameTsRef.current = null;
      smoothedFpsRef.current = 0;
      lastFpsUiUpdateRef.current = 0;
      if (frameFlushRef.current !== null) {
        window.cancelAnimationFrame(frameFlushRef.current);
        frameFlushRef.current = null;
      }
      if (liveImageRef.current) {
        liveImageRef.current.removeAttribute("src");
      }
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
      await decideAttendanceReview(reviewId, {
        decision,
        decided_by: "Authorized operator",
      });
      setAttendanceRefreshTick((current) => current + 1);
    } catch (decisionError) {
      setError(decisionError.message || "Failed to resolve gate review.");
    } finally {
      setDecisionInFlightId(null);
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

        <motion.section
          initial="hidden"
          animate="visible"
          className="mb-8 grid gap-5 md:grid-cols-2 2xl:grid-cols-4"
        >
          <motion.div custom={0} variants={cardVariants}>
            <StatCard
              icon={UsersIcon}
              label="On Site"
              value={onSiteValue}
            />
          </motion.div>
          <motion.div custom={1} variants={cardVariants}>
            <StatCard
              icon={CheckCircleIcon}
              label="Checked Out"
              value={checkedOutValue}
              tone="success"
            />
          </motion.div>
          <motion.div custom={2} variants={cardVariants}>
            <StatCard
              icon={AlertTriangleIcon}
              label="Flagged"
              value={`${flaggedWorkers.length}`}
              tone="warning"
            />
          </motion.div>
          <motion.div custom={3} variants={cardVariants}>
            <StatCard
              icon={BellIcon}
              label="Manual Override"
              value={`${overrideEntries.length}`}
              tone="info"
            />
          </motion.div>
        </motion.section>

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
                        <p className="mt-2 text-sm leading-relaxed text-secondary">
                          Start the intake feed to verify worker attendance on the
                          selected camera.
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
                            disabled={isChangingGateDirection}
                            className={`rounded-2xl border px-4 py-3 text-left transition-all ${
                              gateDirectionMode === "ENTRY"
                                ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary-muted)]"
                                : "border-default bg-card hover:border-[var(--color-border-emphasis)]"
                            } ${isChangingGateDirection ? "opacity-60" : ""}`}
                          >
                            <p className="text-sm font-semibold text-primary">Check-In</p>
                            <p className="mt-1 text-xs text-secondary">
                              Recognize any enrolled worker entering the site.
                            </p>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleGateDirectionChange("EXIT")}
                            disabled={isChangingGateDirection}
                            className={`rounded-2xl border px-4 py-3 text-left transition-all ${
                              gateDirectionMode === "EXIT"
                                ? "border-[var(--color-warning)] bg-[var(--color-warning-muted)]"
                                : "border-default bg-card hover:border-[var(--color-border-emphasis)]"
                            } ${isChangingGateDirection ? "opacity-60" : ""}`}
                          >
                            <p className="text-sm font-semibold text-primary">Check-Out</p>
                            <p className="mt-1 text-xs text-secondary">
                              Only workers currently on site are considered for exit.
                            </p>
                          </button>
                        </div>
                        <div className="rounded-xl border border-default bg-[var(--color-bg-surface)] px-4 py-3">
                          <p className="text-sm font-semibold text-primary">
                            {gateDirectionLabel}
                          </p>
                          <p className="mt-1 text-sm text-secondary">
                            {gateDirectionHelper}
                          </p>
                        </div>
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
                          disabled={cameraState?.active || isStarting}
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
                          className="btn btn-secondary h-12 px-4 xl:col-span-2"
                        >
                          <RefreshIcon size={16} />
                          Refresh Sources
                        </button>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-4">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <p className="text-base font-semibold text-primary">
                            Recognition Mode
                          </p>
                          <p className="mt-1 text-sm text-secondary">
                            {recognitionStatusDetail}
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
                          <button
                            type="button"
                            role="switch"
                            aria-label="Toggle recognition mode"
                            aria-checked={gateModeEnabled}
                            aria-disabled={!canToggleGateMode}
                            onClick={handleToggleGateMode}
                            className={`relative inline-flex h-8 w-14 shrink-0 items-center rounded-full border p-1 transition-colors ${
                              gateModeEnabled
                                ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary)]"
                                : "border-[var(--color-border-emphasis)] bg-[var(--color-bg-card)]"
                            } ${canToggleGateMode ? "" : "cursor-not-allowed opacity-60"}`}
                            disabled={!canToggleGateMode}
                          >
                            <motion.span
                              initial={false}
                              animate={{ x: gateModeEnabled ? 24 : 0 }}
                              transition={{
                                type: "spring",
                                stiffness: 500,
                                damping: 30,
                              }}
                              className="inline-block h-6 w-6 rounded-full bg-white shadow-md"
                            />
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="grid gap-4">
                      <div className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="eyebrow mb-2">Intake Status</p>
                            <p className="text-base font-semibold text-primary">
                              {intakeStatus}
                            </p>
                            <p className="mt-1 text-sm text-secondary">
                              {flaggedWorkers.length > 0
                                ? "One or more workers need attendance review for this shift."
                                : "Recognition is ready to confirm arrivals and departures."}
                            </p>
                          </div>
                          <span className={intakeStatusBadgeClass}>
                            {flaggedWorkers.length > 0
                              ? `${flaggedWorkers.length} flagged`
                              : onSiteCount > 0
                                ? `${onSiteCount} on site`
                                : "Waiting"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.section>

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
                <span className="badge badge-accent">{shiftWorkers.length} records</span>
              </div>

              <div className="panel__content">
                {shiftWorkers.length > 0 ? (
                  <div className="grid gap-4">
                    {shiftWorkers.map((worker) => (
                      <article
                        key={worker.id}
                        className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-5"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <h3 className="text-lg font-semibold text-primary">
                              {worker.name}
                            </h3>
                            <p className="mt-1 text-sm text-secondary">
                              {[worker.role, worker.company].filter(Boolean).join(" · ")}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <span className={getAttendanceTone(worker)}>
                              {getAttendanceLabel(worker)}
                            </span>
                            <span className={getGateReviewClass(worker.matchState)}>
                              {getGateReviewLabel(worker.matchState)}
                            </span>
                          </div>
                        </div>

                        <div className="mt-5 grid gap-4 sm:grid-cols-3">
                          <div>
                            <p className="eyebrow mb-1.5">Camera</p>
                            <p className="text-sm font-semibold text-primary">
                              {worker.cameraSource || selectedSourceLabel}
                            </p>
                          </div>
                          <div>
                            <p className="eyebrow mb-1.5">Check-In</p>
                            <p className="text-sm font-semibold text-primary">
                              {worker.lastCheckIn || "--"}
                            </p>
                          </div>
                          <div>
                            <p className="eyebrow mb-1.5">Face Match</p>
                            <p className="text-sm font-semibold text-primary">
                              {worker.confidence ? `${worker.confidence}%` : "Pending"}
                            </p>
                          </div>
                        </div>

                        <div className="mt-5 rounded-xl border border-default bg-card px-4 py-3">
                          <p className="eyebrow mb-1.5">Access Note</p>
                          <p className="text-sm font-medium text-primary">
                            {worker.riskLabel || "No notes yet."}
                          </p>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-default px-5 py-12 text-center">
                    <UsersIcon size={30} className="mx-auto mb-3 text-accent" />
                    <p className="text-base font-semibold text-primary">
                      No workers mapped to this shift yet
                    </p>
                    <p className="mt-2 text-sm text-secondary">
                      Enroll workers into this shift, or leave them unassigned to show
                      them in every shift roster.
                    </p>
                  </div>
                )}
              </div>
            </motion.section>
          </div>

          <div className="grid gap-8 2xl:grid-cols-[1.2fr_0.8fr]">
            <motion.section
              custom={2}
              variants={cardVariants}
              initial="hidden"
              animate="visible"
              className="panel"
            >
              <div className="panel__header">
                <div className="flex items-center gap-3">
                  <AlertTriangleIcon size={20} className="text-accent" />
                  <div>
                    <h2 className="font-display text-xl font-semibold text-primary">
                      Review Queue
                    </h2>
                    <p className="mt-1 text-sm text-secondary">
                      Low-confidence matches waiting for operator attention stay here.
                    </p>
                  </div>
                </div>
                <span className="badge badge-warning">{pendingReviews.length} active</span>
              </div>

              <div className="panel__content space-y-4">
                {pendingReviews.length > 0 ? (
                  pendingReviews.map((review) => (
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
                            <p className="mt-3 text-sm font-medium text-primary">
                              This worker is between the manual-review threshold and the
                              auto-pass threshold. Approve to log attendance, or deny to
                              keep them outside.
                            </p>
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
            </motion.section>

            <motion.section
              custom={3}
              variants={cardVariants}
              initial="hidden"
              animate="visible"
              className="panel"
            >
              <div className="panel__header">
                <div className="flex items-center gap-3">
                  <BellIcon size={20} className="text-accent" />
                  <div>
                    <h2 className="font-display text-xl font-semibold text-primary">
                      Manual Override
                    </h2>
                    <p className="mt-1 text-sm text-secondary">
                      Accepted or denied low-confidence matches are logged here.
                    </p>
                  </div>
                </div>
                <span className="badge badge-info">{overrideEntries.length} logged</span>
              </div>

              <div className="panel__content space-y-4">
                {overrideEntries.length > 0 ? (
                  overrideEntries.map((entry) => (
                    <article
                      key={entry.id}
                      className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-base font-semibold text-primary">
                            {entry.workerName}
                          </p>
                          <p className="mt-1 text-sm text-secondary">
                            {[entry.cameraSource, `Override by ${entry.triggeredBy}`]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                        </div>
                        <span className="badge badge-warning">{entry.time}</span>
                      </div>
                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <div>
                          <p className="eyebrow mb-1.5">Reason</p>
                          <p className="text-sm font-medium text-primary">
                            {entry.reason}
                          </p>
                        </div>
                        <div>
                          <p className="eyebrow mb-1.5">Decision</p>
                          <p className="text-sm font-medium text-primary">
                            {entry.decision}
                          </p>
                        </div>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="rounded-2xl border border-dashed border-default px-5 py-10 text-center">
                    <BellIcon size={30} className="mx-auto mb-3 text-accent" />
                    <p className="text-base font-semibold text-primary">
                      No manual overrides recorded
                    </p>
                    <p className="mt-2 text-sm text-secondary">
                      When you accept or deny a manual review, the decision will appear here.
                    </p>
                  </div>
                )}
              </div>
            </motion.section>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Attendance;
