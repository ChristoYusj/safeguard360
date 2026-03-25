/*
 * SafeGuard 360 - Dashboard (Drivers) Page
 * "Precision Command" Design System
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useThemePreference } from "../hooks/useThemePreference";
import {
  getCameraSources,
  getCameraState,
  setCameraMode,
  startCamera,
  stopCamera,
} from "../services/api";
import {
  appendFleetEvent,
  beginFleetSession,
  endFleetSession,
} from "../utils/platformLogs";
import {
  VideoIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  InfoIcon,
  TruckIcon,
  ClockIcon,
  MapPinIcon,
  NavigationIcon,
  RefreshIcon,
} from "../components/icons";

// ══════════════════════════════════════════════════════════════
// CONSTANTS
// ══════════════════════════════════════════════════════════════

const DESTINATIONS = {
  beirut: {
    latitude: 33.8938,
    longitude: 35.5018,
    label: "Beirut, Lebanon",
    shortLabel: "Beirut",
  },
  tripoli: {
    latitude: 34.4367,
    longitude: 35.8497,
    label: "Tripoli, Lebanon",
    shortLabel: "Tripoli",
  },
  achrafieh: {
    latitude: 33.8889,
    longitude: 35.5311,
    label: "Achrafieh, Beirut",
    shortLabel: "Achrafieh",
  },
};

const DRIVERS = [
  {
    id: "drv-christopher",
    fullName: "Christopher Yazigi",
    stateId: "LB-3914-7726",
    role: "Senior Transport Operator",
    licenseClass: "C1E",
    assignedRoute: "BRT-12 - Beirut North",
    shift: "Day Shift (06:00 - 14:00)",
    portrait:
      "https://media.formula1.com/content/dam/fom-website/drivers/2024Drivers/verstappen.png.img.512.medium.png",
    truckId: "TRK-4712",
    destination: DESTINATIONS.beirut,
  },
  {
    id: "drv-rami",
    fullName: "Rami Nassar",
    stateId: "LB-5521-1840",
    role: "Regional Fleet Operator",
    licenseClass: "C1E",
    assignedRoute: "NTH-04 - Tripoli Cargo Link",
    shift: "Mid Shift (10:00 - 18:00)",
    portrait:
      "https://media.formula1.com/content/dam/fom-website/drivers/2024Drivers/leclerc.png.img.512.medium.png",
    truckId: "TRK-5824",
    destination: DESTINATIONS.tripoli,
  },
  {
    id: "drv-karim",
    fullName: "Karim Haddad",
    stateId: "LB-8802-4419",
    role: "Urban Safety Driver",
    licenseClass: "C1E",
    assignedRoute: "ACH-09 - Ashrafieh Core",
    shift: "Late Shift (14:00 - 22:00)",
    portrait:
      "https://media.formula1.com/content/dam/fom-website/drivers/2025Drivers/hamilton.png.img.512.medium.png",
    truckId: "TRK-6031",
    destination: DESTINATIONS.achrafieh,
  },
];

// ══════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ══════════════════════════════════════════════════════════════

function haversineDistanceKm(lat1, lon1, lat2, lon2) {
  const toRad = (value) => (value * Math.PI) / 180;
  const earthRadiusKm = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) *
      Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return 2 * earthRadiusKm * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatClockTime(date) {
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatEventTime(timestampSeconds) {
  return new Date(timestampSeconds * 1000).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

function estimateArrivalText(distanceToBeirut) {
  if (distanceToBeirut === null) return "09:15 AM";
  const estimatedHoursRemaining = distanceToBeirut / 58;
  const eta = new Date(Date.now() + estimatedHoursRemaining * 60 * 60 * 1000);
  return formatClockTime(eta);
}

function getAlertVisuals(event) {
  const details = (event.details || "").toLowerCase();
  if (event.event_type === "FATIGUE" && details.includes("eye")) {
    return { variant: "error", tone: "eye" };
  }
  if (event.event_type === "FATIGUE" && details.includes("yawn")) {
    return { variant: "warning", tone: "yawn" };
  }
  if (event.event_type === "INFO") {
    return { variant: "info", tone: "info" };
  }
  return { variant: "success", tone: "safe" };
}

// ══════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ══════════════════════════════════════════════════════════════

function DriverPortrait() {
  return (
    <svg
      viewBox="0 0 108 108"
      className="h-full w-full"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="portrait-bg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1a2640" />
          <stop offset="100%" stopColor="#3a4e74" />
        </linearGradient>
        <linearGradient
          id="portrait-jacket"
          x1="0%"
          y1="0%"
          x2="100%"
          y2="100%"
        >
          <stop offset="0%" stopColor="#203a65" />
          <stop offset="100%" stopColor="#111d35" />
        </linearGradient>
      </defs>
      <rect width="108" height="108" rx="18" fill="url(#portrait-bg)" />
      <circle cx="54" cy="42" r="19" fill="#d8b59c" />
      <path
        d="M35 94c3-15 10-25 19-29 10-4 24 2 30 29"
        fill="url(#portrait-jacket)"
      />
      <path
        d="M40 31c2-10 8-18 15-20 11-4 23 2 28 16-6-4-12-6-19-6-10 0-18 4-24 10Z"
        fill="#16181f"
      />
      <path
        d="M43 44c3 2 7 4 11 4 5 0 9-2 11-4"
        stroke="#8d5d48"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="47" cy="39" r="2" fill="#16181f" />
      <circle cx="61" cy="39" r="2" fill="#16181f" />
      <path
        d="M54 45v7"
        stroke="#8d5d48"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M49 57c2 2 4 3 6 3 3 0 5-1 7-3"
        stroke="#8d5d48"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <rect
        x="11"
        y="82"
        width="30"
        height="11"
        rx="5.5"
        fill="var(--color-accent-primary)"
        opacity="0.95"
      />
      <text
        x="26"
        y="89.5"
        textAnchor="middle"
        fontSize="7.5"
        fontWeight="700"
        fill="#ffffff"
      >
        AI DEMO
      </text>
    </svg>
  );
}

function DriverProfileImage({ driver }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <DriverPortrait />;
  return (
    <img
      src={driver.portrait}
      alt={driver.fullName}
      className="h-full w-full object-cover"
      onError={() => setFailed(true)}
    />
  );
}

function AlertCard({ event, locationState, selectedDriver }) {
  const visuals = getAlertVisuals(event);
  const Icon =
    visuals.tone === "info"
      ? InfoIcon
      : visuals.tone === "safe"
        ? CheckCircleIcon
        : AlertTriangleIcon;

  const variantStyles = {
    error: "border-[var(--color-error)] bg-[var(--color-error-muted)]",
    warning: "border-[var(--color-warning)] bg-[var(--color-warning-muted)]",
    info: "border-[var(--color-info)] bg-[var(--color-info-muted)]",
    success: "border-[var(--color-success)] bg-[var(--color-success-muted)]",
  };

  const iconColors = {
    error: "var(--color-error)",
    warning: "var(--color-warning)",
    info: "var(--color-info)",
    success: "var(--color-success)",
  };

  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={`rounded-xl border p-5 ${variantStyles[visuals.variant]}`}
    >
      <div className="flex items-start gap-4">
        <div className="mt-0.5" style={{ color: iconColors[visuals.variant] }}>
          <Icon size={22} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="text-base font-medium text-primary">
              {event.details}
            </p>
            <span className="text-sm font-medium text-secondary">
              {formatEventTime(event.timestamp)}
            </span>
          </div>
          <p className="mt-2 text-sm text-tertiary">
            {locationState.status === "ready"
              ? `${locationState.latitude.toFixed(4)}, ${locationState.longitude.toFixed(4)}`
              : `${selectedDriver.truckId} • Cabin monitoring`}
          </p>
        </div>
      </div>
    </motion.article>
  );
}

// ══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ══════════════════════════════════════════════════════════════

function Dashboard() {
  const { darkMode } = useThemePreference();
  const [cameraState, setCameraState] = useState(null);
  const [selectedDriverId, setSelectedDriverId] = useState(DRIVERS[0].id);
  const [driverEventsById, setDriverEventsById] = useState(() =>
    Object.fromEntries(DRIVERS.map((driver) => [driver.id, []])),
  );
  const [departureTimesById, setDepartureTimesById] = useState(() =>
    Object.fromEntries(DRIVERS.map((driver) => [driver.id, null])),
  );
  const [sessionIdsById, setSessionIdsById] = useState(() =>
    Object.fromEntries(DRIVERS.map((driver) => [driver.id, null])),
  );
  const [locationState, setLocationState] = useState({
    status: "idle",
    latitude: null,
    longitude: null,
    error: null,
  });
  const [sources, setSources] = useState([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [frameData, setFrameData] = useState(null);
  const [error, setError] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [liveFps, setLiveFps] = useState(0);

  const liveWsRef = useRef(null);
  const eventsWsRef = useRef(null);
  const liveReconnectRef = useRef(null);
  const eventsReconnectRef = useRef(null);
  const lastEventKeyRef = useRef(null);
  const lastFrameTsRef = useRef(null);
  const smoothedFpsRef = useRef(0);
  const selectedDriverIdRef = useRef(selectedDriverId);
  const sessionIdsByIdRef = useRef(sessionIdsById);
  const locationStateRef = useRef(locationState);

  const makeSourceId = (source) => `${source.source_type}:${source.source_id}`;
  const parseSourceId = (sourceId) => {
    const idx = sourceId.indexOf(":");
    if (idx === -1) return { type: sourceId, id: "0" };
    return {
      type: sourceId.substring(0, idx),
      id: sourceId.substring(idx + 1),
    };
  };

  useEffect(() => {
    selectedDriverIdRef.current = selectedDriverId;
  }, [selectedDriverId]);
  useEffect(() => {
    sessionIdsByIdRef.current = sessionIdsById;
  }, [sessionIdsById]);
  useEffect(() => {
    locationStateRef.current = locationState;
  }, [locationState]);

  useEffect(() => {
    let isDisposed = false;
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsBase = `${wsProtocol}//${window.location.host}`;

    const connectLive = () => {
      if (isDisposed) return;
      const ws = new WebSocket(`${wsBase}/ws/live`);
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        if (!isDisposed)
          liveReconnectRef.current = setTimeout(connectLive, 2000);
      };
      ws.onerror = (e) => console.error("[Dashboard] Live WS error:", e);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "frame" && msg.data) {
            const now = performance.now();
            if (lastFrameTsRef.current !== null) {
              const deltaMs = now - lastFrameTsRef.current;
              if (deltaMs > 0) {
                const instantFps = 1000 / deltaMs;
                smoothedFpsRef.current =
                  smoothedFpsRef.current === 0
                    ? instantFps
                    : smoothedFpsRef.current * 0.75 + instantFps * 0.25;
                setLiveFps(smoothedFpsRef.current);
              }
            }
            lastFrameTsRef.current = now;
            setFrameData(msg.data);
          }
        } catch (e) {
          console.error("[Dashboard] Live parse error", e);
        }
      };
      liveWsRef.current = ws;
    };

    const connectEvents = () => {
      if (isDisposed) return;
      const ws = new WebSocket(`${wsBase}/ws/events`);
      ws.onclose = () => {
        if (!isDisposed)
          eventsReconnectRef.current = setTimeout(connectEvents, 2000);
      };
      ws.onerror = (e) => console.error("[Dashboard] Events WS error:", e);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "status" && msg.camera) setCameraState(msg.camera);
          else if (msg.type === "driver_event") {
            const eventKey = `${msg.event_type}-${msg.timestamp}-${msg.details}`;
            if (lastEventKeyRef.current === eventKey) return;
            lastEventKeyRef.current = eventKey;
            const activeDriverId = selectedDriverIdRef.current;
            const eventRecord = {
              id: eventKey,
              event_type: msg.event_type,
              details: msg.details,
              timestamp: msg.timestamp,
              confidence: msg.confidence,
            };
            setDriverEventsById((prev) => ({
              ...prev,
              [activeDriverId]: [eventRecord, ...(prev[activeDriverId] || [])]
                .sort((a, b) => b.timestamp - a.timestamp)
                .slice(0, 25),
            }));
            appendFleetEvent(sessionIdsByIdRef.current[activeDriverId], {
              id: eventKey,
              type: msg.event_type,
              details: msg.details,
              timestamp: msg.timestamp,
              coordinates:
                locationStateRef.current.status === "ready"
                  ? `${locationStateRef.current.latitude.toFixed(4)}, ${locationStateRef.current.longitude.toFixed(4)}`
                  : "Cabin monitoring",
            });
          }
        } catch (e) {
          console.error("[Dashboard] Events parse error", e);
        }
      };
      eventsWsRef.current = ws;
    };

    connectLive();
    connectEvents();
    return () => {
      isDisposed = true;
      if (liveReconnectRef.current) clearTimeout(liveReconnectRef.current);
      if (eventsReconnectRef.current) clearTimeout(eventsReconnectRef.current);
      if (liveWsRef.current) liveWsRef.current.close();
      if (eventsWsRef.current) eventsWsRef.current.close();
    };
  }, []);

  useEffect(() => {
    getCameraState()
      .then((state) => {
        setCameraState(state);
        if (state?.source_type && state?.source_type !== "none")
          setSelectedSourceId(`${state.source_type}:${state.source_id}`);
      })
      .catch((e) =>
        console.error("[Dashboard] Failed to load camera state:", e),
      );
  }, []);

  useEffect(() => {
    getCameraSources()
      .then((data) => {
        setSources(data || []);
        if (data && data.length > 0 && !selectedSourceId)
          setSelectedSourceId(makeSourceId(data[0]));
      })
      .catch((e) => console.error("[Dashboard] Failed to load sources:", e));
  }, [selectedSourceId]);

  useEffect(() => {
    if (!cameraState?.active) {
      setLocationState({
        status: "idle",
        latitude: null,
        longitude: null,
        error: null,
      });
      return;
    }
    if (!navigator.geolocation) {
      setLocationState({
        status: "error",
        latitude: null,
        longitude: null,
        error: "Geolocation not supported.",
      });
      return;
    }
    setLocationState((prev) => ({ ...prev, status: "loading", error: null }));
    const watchId = navigator.geolocation.watchPosition(
      (pos) =>
        setLocationState({
          status: "ready",
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          error: null,
        }),
      (err) =>
        setLocationState({
          status: "error",
          latitude: null,
          longitude: null,
          error: err.message || "Location error.",
        }),
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 10000 },
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, [cameraState?.active]);

  const selectedDriver =
    DRIVERS.find((d) => d.id === selectedDriverId) || DRIVERS[0];

  const handleStart = async () => {
    const parsed = parseSourceId(selectedSourceId);
    setError(null);
    setIsStarting(true);
    try {
      const result = await startCamera(parsed.type, parsed.id);
      setCameraState(result);
      if (result.error) setError(result.error);
      else {
        const startedAt = new Date();
        const startedSessionId = beginFleetSession({
          driverName: selectedDriver.fullName,
          truckId: selectedDriver.truckId,
          sourceLabel:
            sources.find((s) => makeSourceId(s) === selectedSourceId)?.name ||
            selectedSourceId,
          destination: selectedDriver.destination.shortLabel,
        });
        setDepartureTimesById((prev) => ({
          ...prev,
          [selectedDriver.id]: startedAt,
        }));
        setSessionIdsById((prev) => ({
          ...prev,
          [selectedDriver.id]: startedSessionId,
        }));
      }
    } catch (e) {
      setError("Failed to start camera: " + (e.message || "Unknown"));
    } finally {
      setIsStarting(false);
    }
  };

  const handleStop = async () => {
    try {
      setError(null);
      const result = await stopCamera();
      setFrameData(null);
      setLiveFps(0);
      lastFrameTsRef.current = null;
      smoothedFpsRef.current = 0;
      endFleetSession(sessionIdsById[selectedDriver.id]);
      setDepartureTimesById((prev) => ({ ...prev, [selectedDriver.id]: null }));
      setSessionIdsById((prev) => ({ ...prev, [selectedDriver.id]: null }));
      setCameraState(result);
    } catch (e) {
      console.error("[Dashboard] Failed to stop camera:", e);
      setError("Failed to stop camera");
      setDepartureTimesById((prev) => ({ ...prev, [selectedDriver.id]: null }));
      setCameraState({
        active: false,
        source_type: "none",
        source_id: "",
        fps: 0,
        frames_captured: 0,
        mode: "idle",
        error: "",
      });
    }
  };

  const handleReset = () => {
    setIsStarting(false);
    setError(null);
    setCameraState(null);
    setFrameData(null);
    setDriverEventsById((prev) => ({ ...prev, [selectedDriver.id]: [] }));
    setDepartureTimesById((prev) => ({ ...prev, [selectedDriver.id]: null }));
    setLiveFps(0);
    lastFrameTsRef.current = null;
    smoothedFpsRef.current = 0;
    setSessionIdsById((prev) => ({ ...prev, [selectedDriver.id]: null }));
  };

  const handleMediaPipeToggle = async () => {
    const nextMode = cameraState?.mode === "driver" ? "idle" : "driver";
    try {
      const result = await setCameraMode(nextMode);
      setCameraState(result);
    } catch (e) {
      console.error("[Dashboard] Failed to toggle MediaPipe:", e);
      setError("Failed to change MediaPipe state");
    }
  };

  const selectedDriverEvents = driverEventsById[selectedDriver.id] || [];
  const departureTime = departureTimesById[selectedDriver.id] || null;
  const distanceToDestination =
    cameraState?.active && locationState.status === "ready"
      ? haversineDistanceKm(
          locationState.latitude,
          locationState.longitude,
          selectedDriver.destination.latitude,
          selectedDriver.destination.longitude,
        )
      : null;
  const routeMapUrl =
    cameraState?.active && locationState.status === "ready"
      ? `https://maps.google.com/maps?saddr=${locationState.latitude},${locationState.longitude}&daddr=${encodeURIComponent(selectedDriver.destination.label)}&dirflg=d&output=embed`
      : null;
  const mediaPipeEnabled = cameraState?.mode === "driver";
  const departureLabel = departureTime
    ? formatClockTime(departureTime)
    : "--:--";
  const distanceLabel =
    distanceToDestination !== null
      ? `${distanceToDestination.toFixed(1)} km`
      : "--";
  const etaLabel =
    departureTime && distanceToDestination !== null
      ? estimateArrivalText(distanceToDestination)
      : "--:--";

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">Command Center</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          Fleet Monitoring
        </h1>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mb-8"
      >
        <p className="eyebrow mb-3">Drivers on Duty:</p>
        <div className="flex flex-wrap gap-3">
        {DRIVERS.map((driver) => (
          <button
            key={driver.id}
            type="button"
            onClick={() => setSelectedDriverId(driver.id)}
            className={`min-w-[200px] rounded-xl border px-5 py-4 text-left transition-all duration-200 ${driver.id === selectedDriver.id ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary)] text-[var(--color-text-inverse)] shadow-[var(--glow-accent)]" : "border-default bg-card text-primary hover:border-[var(--color-border-emphasis)] hover:bg-[var(--color-bg-card-hover)]"}`}
          >
            <div className="text-base font-semibold">{driver.fullName}</div>
            <div
              className={`mt-1 text-sm ${driver.id === selectedDriver.id ? "text-white/80" : "text-secondary"}`}
            >
              {driver.truckId} • {driver.destination.shortLabel}
            </div>
          </button>
        ))}
        </div>
      </motion.div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-6 overflow-hidden rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-5 py-4"
          >
            <p
              className="text-sm font-medium"
              style={{ color: "var(--color-error)" }}
            >
              {error}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid gap-8 xl:grid-cols-[2fr_1fr]">
        <div className="space-y-8">
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="panel overflow-hidden"
          >
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <VideoIcon size={20} className="text-accent" />
                <span className="font-display text-lg font-semibold text-primary">
                  Live Camera Feed
                </span>
                {cameraState?.active && (
                  <span className="badge badge-error flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-current pulse" />
                    LIVE
                  </span>
                )}
              </div>
              <span className="text-sm font-medium text-secondary">
                Cabin View
              </span>
            </div>
            <div className="relative aspect-video bg-[var(--color-bg-deepest)]">
              {frameData ? (
                <img
                  src={`data:image/jpeg;base64,${frameData}`}
                  alt="Live feed"
                  className="h-full w-full object-contain"
                />
              ) : (
                <div className="flex h-full items-center justify-center">
                  <div className="text-center">
                    <VideoIcon size={48} className="mx-auto mb-4 text-muted" />
                    <p className="text-lg font-semibold text-primary">
                      Camera offline
                    </p>
                    <p className="mt-2 text-sm text-secondary">
                      Start the selected source to begin monitoring.
                    </p>
                  </div>
                </div>
              )}
              {cameraState?.active && (
                <div className="absolute bottom-4 left-4 flex items-center gap-2 rounded-lg border border-default bg-card/90 px-4 py-2.5 backdrop-blur-sm">
                  <span className="status-dot status-dot-error pulse" />
                  <span className="text-sm font-semibold text-primary">
                    Recording
                  </span>
                </div>
              )}
            </div>
            <div className="panel__content">
              <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
                <div className="flex flex-wrap gap-3">
                  <select
                    value={selectedSourceId}
                    onChange={(e) => setSelectedSourceId(e.target.value)}
                    disabled={cameraState?.active}
                    className="input h-12 min-w-[200px] flex-1 disabled:opacity-50"
                  >
                    {sources.length === 0 && (
                      <option value="webcam:0">Webcam 0</option>
                    )}
                    {sources.map((s) => (
                      <option key={makeSourceId(s)} value={makeSourceId(s)}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handleStart}
                    disabled={cameraState?.active || isStarting}
                    className="btn btn-primary h-12 px-6"
                  >
                    {isStarting ? "Starting..." : "Start"}
                  </button>
                  <button
                    onClick={handleStop}
                    disabled={!cameraState?.active && !isStarting}
                    className="btn h-12 px-6"
                    style={{
                      backgroundColor: "var(--color-error)",
                      color: "white",
                    }}
                  >
                    Stop
                  </button>
                  <button
                    onClick={handleReset}
                    className="btn btn-secondary h-12 px-4"
                  >
                    <RefreshIcon size={18} />
                  </button>
                </div>
                <div className="flex gap-3">
                  <div className="rounded-xl border border-default bg-surface px-4 py-2.5 text-center">
                    <div className="text-[10px] font-semibold uppercase tracking-widest text-tertiary">
                      FPS
                    </div>
                    <div className="mt-0.5 text-lg font-bold text-primary">
                      {liveFps ? liveFps.toFixed(1) : "0.0"}
                    </div>
                  </div>
                  <div className="rounded-xl border border-default bg-surface px-4 py-2.5 text-center">
                    <div className="text-[10px] font-semibold uppercase tracking-widest text-tertiary">
                      WebSocket
                    </div>
                    <div
                      className="mt-0.5 text-sm font-semibold"
                      style={{
                        color: wsConnected
                          ? "var(--color-success)"
                          : "var(--color-text-secondary)",
                      }}
                    >
                      {wsConnected ? "Connected" : "Disconnected"}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="panel"
          >
            <div className="panel__header">
              <h2 className="font-display text-xl font-semibold text-primary">
                Recent Driver Alerts
              </h2>
              <span className="badge badge-accent">
                {selectedDriverEvents.length} events
              </span>
            </div>
            <div className="panel__content">
              <div className="space-y-4">
                <AnimatePresence mode="popLayout">
                  {selectedDriverEvents.length > 0 ? (
                    selectedDriverEvents.map((event) => (
                      <AlertCard
                        key={event.id}
                        event={event}
                        locationState={locationState}
                        selectedDriver={selectedDriver}
                      />
                    ))
                  ) : (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="rounded-xl border border-dashed border-default py-12 text-center"
                    >
                      <InfoIcon size={32} className="mx-auto mb-3 text-muted" />
                      <p className="text-base font-semibold text-primary">
                        No driver alerts yet
                      </p>
                      <p className="mt-1 text-sm text-secondary">
                        Events will appear here during testing.
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.section>
        </div>

        <div className="space-y-8">
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="panel"
          >
            <div className="panel__header">
              <h2 className="font-display text-xl font-semibold text-primary">
                Driver Identity
              </h2>
            </div>
            <div className="panel__content">
              <div className="mb-6 flex gap-5">
                <div className="h-24 w-24 flex-shrink-0 overflow-hidden rounded-xl border-2 border-[var(--color-accent-primary)] shadow-lg">
                  <DriverProfileImage driver={selectedDriver} />
                </div>
                <div>
                  <p className="text-lg font-semibold text-primary">
                    {selectedDriver.fullName}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-accent">
                    {selectedDriver.stateId}
                  </p>
                  <span className="mt-3 inline-flex rounded-full bg-[var(--color-success-muted)] px-3 py-1 text-xs font-semibold text-[var(--color-success)]">
                    {selectedDriver.licenseClass}
                  </span>
                </div>
              </div>
              <div className="space-y-5">
                <div>
                  <p className="eyebrow mb-1.5">Role</p>
                  <p className="text-base font-semibold text-primary">
                    {selectedDriver.role}
                  </p>
                </div>
                <div>
                  <p className="eyebrow mb-1.5">Assigned Route</p>
                  <p className="text-base font-semibold text-primary">
                    {selectedDriver.assignedRoute}
                  </p>
                </div>
                <div>
                  <p className="eyebrow mb-1.5">Shift</p>
                  <p className="text-base font-semibold text-primary">
                    {selectedDriver.shift}
                  </p>
                </div>
              </div>
              <div className="mt-6 border-t border-default pt-6">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-base font-semibold text-primary">
                        MediaPipe Detection
                      </span>
                      {mediaPipeEnabled && (
                        <span className="h-2 w-2 rounded-full bg-[var(--color-accent-primary)]" />
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={mediaPipeEnabled}
                    onClick={handleMediaPipeToggle}
                    className={`relative inline-flex h-8 w-14 items-center rounded-full border transition-colors ${mediaPipeEnabled ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary)]" : "border-[var(--color-border-emphasis)] bg-[var(--color-bg-surface)]"}`}
                  >
                    <motion.span
                      initial={false}
                      animate={{ x: mediaPipeEnabled ? 28 : 2 }}
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
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="panel"
          >
            <div className="panel__header">
              <h2 className="font-display text-xl font-semibold text-primary">
                Active Route
              </h2>
              <span className="badge badge-info">In Transit</span>
            </div>
            <div className="panel__content">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="eyebrow mb-2">Truck ID</p>
                  <div className="flex items-center gap-2 text-accent">
                    <TruckIcon size={16} />
                    <span className="text-base font-semibold">
                      {selectedDriver.truckId}
                    </span>
                  </div>
                </div>
                <div>
                  <p className="eyebrow mb-2">Departure</p>
                  <div className="flex items-center gap-2 text-secondary">
                    <ClockIcon size={16} />
                    <span className="text-base font-semibold text-primary">
                      {departureLabel}
                    </span>
                  </div>
                </div>
                <div>
                  <p className="eyebrow mb-2">Destination</p>
                  <div
                    className="flex items-center gap-2"
                    style={{ color: "var(--color-error)" }}
                  >
                    <MapPinIcon size={16} />
                    <span className="text-base font-semibold text-primary">
                      {selectedDriver.destination.shortLabel}
                    </span>
                  </div>
                </div>
                <div>
                  <p className="eyebrow mb-2">Distance Left</p>
                  <div
                    className="flex items-center gap-2"
                    style={{ color: "var(--color-success)" }}
                  >
                    <NavigationIcon size={16} />
                    <span className="text-base font-semibold text-primary">
                      {distanceLabel}
                    </span>
                  </div>
                </div>
              </div>
              <div className="mt-6 border-t border-default pt-6">
                <p className="eyebrow mb-3">Route Map</p>
                <div className="overflow-hidden rounded-xl border border-default">
                  <div className="aspect-[1.5/1]">
                    {routeMapUrl ? (
                      <iframe
                        title={`Route to ${selectedDriver.destination.shortLabel}`}
                        src={routeMapUrl}
                        className="h-full w-full border-0"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center bg-surface px-6 text-center">
                        <div>
                          <MapPinIcon
                            size={32}
                            className="mx-auto mb-3 text-muted"
                          />
                          <p className="text-base font-semibold text-primary">
                            Route unavailable
                          </p>
                          <p className="mt-1 text-sm text-secondary">
                            Start camera and allow location access.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className="text-sm font-medium text-secondary">
                  Est. Arrival
                </span>
                <span
                  className="text-lg font-bold"
                  style={{ color: "var(--color-success)" }}
                >
                  {etaLabel}
                </span>
              </div>
            </div>
          </motion.section>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
