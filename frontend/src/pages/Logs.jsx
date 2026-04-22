/*
 * SafeGuard 360 - Platform Logs Page
 * "Precision Command" Design System
 */

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import {
  clearAttendanceLogs,
  getAttendance,
  getAttendanceReviews,
  getPersons,
} from "../services/api";
import {
  clearPlatformLogModule,
  readPlatformLogs,
} from "../utils/platformLogs";
import { buildAttendanceSessionState } from "../utils/attendanceSessions";
import {
  canAccessAttendance,
  canAccessDrivers,
} from "../utils/accessControl";
import {
  DriversIcon,
  AttendanceIcon,
} from "../components/icons";

const LOG_FILTERS_KEY = "safeguard360-log-filters";

const SHIFT_LABELS = {
  day: "Day Shift",
  swing: "Swing Shift",
  night: "Night Shift",
};

function normalizePpeDetails(details) {
  return {
    status: "not_evaluated",
    required_items: [],
    detected_items: [],
    missing_items: [],
    override_used: false,
    override_reason_type: null,
    detector_message: null,
    ...(details || {}),
  };
}

function formatSessionTime(timestamp) {
  if (!timestamp) {
    return "--";
  }

  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatConfidence(confidence) {
  if (confidence == null) {
    return "Pending";
  }

  return `${Math.round(confidence * 100)}%`;
}

function formatPpeStatus(details, { entry = false } = {}) {
  const ppe = normalizePpeDetails(details);
  if (!entry) {
    return "--";
  }
  if (ppe.status === "compliant") {
    return "Helmet and vest confirmed";
  }
  if (ppe.status === "non_compliant") {
    return `Missing ${ppe.missing_items.join(", ")}`;
  }
  if (ppe.status === "uncertain") {
    return "PPE needs operator review";
  }
  if (ppe.status === "skipped") {
    return "PPE not required for this entry";
  }
  if (ppe.status === "unavailable") {
    return "PPE detector unavailable";
  }
  return "PPE not evaluated";
}

function getManualOverrideDetail(session, direction) {
  return (
    session.manualOverrideDetails?.find((detail) => detail.direction === direction) ||
    null
  );
}

function readLogFilters() {
  if (typeof window === "undefined") {
    return { attendanceClearedAt: 0 };
  }

  try {
    const raw = window.localStorage.getItem(LOG_FILTERS_KEY);
    if (!raw) {
      return { attendanceClearedAt: 0 };
    }

    return {
      attendanceClearedAt: 0,
      ...JSON.parse(raw),
    };
  } catch (error) {
    console.error("[Logs] Failed to read filters", error);
    return { attendanceClearedAt: 0 };
  }
}

function writeLogFilters(filters) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(LOG_FILTERS_KEY, JSON.stringify(filters));
  } catch (error) {
    console.error("[Logs] Failed to write filters", error);
  }
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

function Logs() {
  const { t } = useAppLanguage();
  const { user } = useAuth();
  const [store, setStore] = useState(() => readPlatformLogs());
  const [filters, setFilters] = useState(() => readLogFilters());
  const [persons, setPersons] = useState([]);
  const [attendanceRecords, setAttendanceRecords] = useState([]);
  const [gateReviews, setGateReviews] = useState([]);
  const [attendanceBusy, setAttendanceBusy] = useState(false);
  const [attendanceMessage, setAttendanceMessage] = useState("");
  const [attendanceError, setAttendanceError] = useState("");
  const canViewFleetLogs = canAccessDrivers(user?.role);
  const canViewAttendanceLogs = canAccessAttendance(user?.role);

  const fleetSessions = store.fleet.sessions || [];

  useEffect(() => {
    let cancelled = false;

    const loadLogs = async () => {
      try {
        const [personList, attendanceList, reviewList] = await Promise.all([
          canViewAttendanceLogs ? getPersons() : Promise.resolve([]),
          canViewAttendanceLogs ? getAttendance({ limit: 500 }) : Promise.resolve([]),
          canViewAttendanceLogs
            ? getAttendanceReviews("all", { limit: 500 })
            : Promise.resolve([]),
        ]);

        if (cancelled) {
          return;
        }

        setPersons(personList || []);
        setAttendanceRecords(attendanceList || []);
        setGateReviews(reviewList || []);
      } catch (error) {
        if (!cancelled) {
          console.error("[Logs] Failed to load backend logs", error);
        }
      }
    };

    loadLogs();
    const timer = window.setInterval(loadLogs, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [canViewAttendanceLogs]);

  const completedSessions = useMemo(
    () =>
      buildAttendanceSessionState({
        persons,
        attendanceRecords,
        gateReviews,
      }).completedSessions.filter((session) => {
        const endedAt = new Date(
          session.checkOut?.timestamp || session.checkIn?.timestamp || 0,
        ).getTime();
        return endedAt > (filters.attendanceClearedAt || 0);
      }),
    [persons, attendanceRecords, gateReviews, filters.attendanceClearedAt],
  );
  const visibleLogCategories = [
    canViewFleetLogs
      ? {
          icon: DriversIcon,
          color: "var(--color-info)",
          type: "Fleet Logs",
          description: "Fatigue, route activity, and driver monitoring sessions.",
          countLabel: `${fleetSessions.length} session${fleetSessions.length === 1 ? "" : "s"} tracked`,
        }
      : null,
    canViewAttendanceLogs
      ? {
          icon: AttendanceIcon,
          color: "var(--color-success)",
          type: "Attendance Logs",
          description:
            "Completed worker sessions with check-in, check-out, face match, and operator notes.",
          countLabel: `${completedSessions.length} completed session${completedSessions.length === 1 ? "" : "s"}`,
        }
      : null,
  ].filter(Boolean);

  const handleClearModule = (moduleName) => {
    clearPlatformLogModule(moduleName);
    setStore(readPlatformLogs());
  };

  const handleClearAttendanceLogs = async () => {
    const confirmed = window.confirm(
      "Clear all attendance logs, review queue items, and PPE log history?",
    );
    if (!confirmed || attendanceBusy) {
      return;
    }

    setAttendanceBusy(true);
    setAttendanceError("");
    setAttendanceMessage("");
    try {
      const response = await clearAttendanceLogs();
      setAttendanceRecords([]);
      setGateReviews([]);
      const summary = [
        response.attendance_deleted || 0,
        response.reviews_deleted || 0,
        response.ppe_events_deleted || 0,
      ].reduce((total, count) => total + count, 0);
      setAttendanceMessage(
        `Attendance history cleared. ${summary} attendance, review, and PPE records removed.`,
      );
    } catch (error) {
      setAttendanceError(error.message || "Attendance logs could not be cleared.");
      return;
    } finally {
      setAttendanceBusy(false);
    }

    const nextFilters = {
      ...filters,
      attendanceClearedAt: Date.now(),
    };
    setFilters(nextFilters);
    writeLogFilters(nextFilters);
  };

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.section
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">{t("unified_audit_trail")}</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          {t("platform_logs")}
        </h1>
      </motion.section>

      <motion.section
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className={`mb-8 grid gap-4 ${visibleLogCategories.length > 1 ? "lg:grid-cols-2" : ""}`}
      >
        {visibleLogCategories.map((cat) => (
          <motion.article
            key={cat.type}
            variants={itemVariants}
            className="stat-card group"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="stat-card__label">{cat.countLabel}</p>
                <h2 className="mt-3 font-display text-2xl font-semibold text-primary">
                  {cat.type}
                </h2>
                <p className="mt-2 text-sm text-secondary">{cat.description}</p>
              </div>
              <div
                className="rounded-xl p-3"
                style={{
                  backgroundColor: `color-mix(in srgb, ${cat.color} 15%, transparent)`,
                }}
              >
                <cat.icon className="h-6 w-6" style={{ color: cat.color }} />
              </div>
            </div>
          </motion.article>
        ))}
      </motion.section>

      <div className={`grid gap-6 ${canViewFleetLogs && canViewAttendanceLogs ? "xl:grid-cols-2" : ""}`}>
        {canViewFleetLogs ? (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="space-y-4"
        >
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold text-primary">
              Fleet Sessions
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-secondary">Driver history</span>
              <button
                type="button"
                onClick={() => handleClearModule("fleet")}
                className="btn btn-secondary h-10 px-4"
              >
                Clear
              </button>
            </div>
          </div>
          {fleetSessions.length > 0 ? (
            fleetSessions.map((session, index) => (
              <article key={session.id} className="panel">
                <div className="panel__header border-b-0 pb-0">
                  <div>
                    <p className="eyebrow text-[10px]">
                      Fleet Session {index + 1}
                    </p>
                    <h3 className="mt-1 font-display text-lg font-semibold text-primary">
                      {session.driverName}
                    </h3>
                    <p className="mt-1 text-sm text-secondary">
                      {session.truckId} • {session.sourceLabel || "Camera source"} •
                      Started {formatSessionTime(session.startedAt)}
                    </p>
                  </div>
                  <span className="badge badge-info">
                    {session.events.length} event
                    {session.events.length === 1 ? "" : "s"}
                  </span>
                </div>

                <div className="panel__content space-y-3">
                  {session.events.length > 0 ? (
                    session.events.map((event) => (
                      <div
                        key={event.id}
                        className="rounded-xl border border-default bg-surface px-4 py-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-primary">
                              {event.details}
                            </p>
                            <p className="mt-1 text-sm text-secondary">
                              {event.coordinates}
                            </p>
                          </div>
                          <span className="text-sm text-tertiary">
                            {formatSessionTime(event.timestamp * 1000)}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-default bg-surface px-4 py-4 text-sm text-secondary">
                      No warnings were logged during this session.
                    </div>
                  )}
                </div>
              </article>
            ))
          ) : (
            <div className="relative overflow-hidden rounded-xl border border-dashed border-default bg-card p-8 text-center">
              <div
                className="pointer-events-none absolute inset-0 opacity-30"
                style={{
                  background:
                    "radial-gradient(ellipse at 50% 0%, var(--color-info-muted), transparent 60%)",
                }}
              />
              <div className="relative">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--color-info-muted)]">
                  <DriversIcon className="h-6 w-6 text-[var(--color-info)]" />
                </div>
                <p className="font-medium text-primary">No Fleet Sessions</p>
                <p className="mt-1 text-sm text-secondary">
                  Start a driver session and warnings will be archived here
                  automatically.
                </p>
              </div>
            </div>
          )}
        </motion.section>
        ) : null}

        {canViewAttendanceLogs ? (
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: canViewFleetLogs ? 0.3 : 0.2 }}
          className="space-y-4"
        >
          {attendanceMessage ? (
            <div className="rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
              <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                {attendanceMessage}
              </p>
            </div>
          ) : null}
          {attendanceError ? (
            <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
              <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                {attendanceError}
              </p>
            </div>
          ) : null}
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold text-primary">
              Attendance Sessions
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-secondary">Completed workforce flow</span>
              <button
                type="button"
                onClick={handleClearAttendanceLogs}
                disabled={attendanceBusy}
                className="btn btn-secondary h-10 px-4"
              >
                {attendanceBusy ? "Clearing..." : "Clear"}
              </button>
            </div>
          </div>
          {completedSessions.length > 0 ? (
            completedSessions.map((session, index) => {
              const checkInOverride = getManualOverrideDetail(session, "Check-In");
              const checkOutOverride = getManualOverrideDetail(session, "Check-Out");

              return (
              <article key={session.id} className="panel">
                <div className="panel__header border-b-0 pb-0">
                  <div>
                    <p className="eyebrow text-[10px]">
                      Attendance Session {index + 1}
                    </p>
                    <h3 className="mt-1 font-display text-lg font-semibold text-primary">
                      {session.personName}
                    </h3>
                    <p className="mt-1 text-sm text-secondary">
                      {[session.employeeId, SHIFT_LABELS[session.shiftId] || "Shift pending"]
                        .filter(Boolean)
                        .join(" • ")}
                    </p>
                  </div>
                  <span className="badge badge-success">
                    {session.hasManualOverride ? "Manual override used" : "Auto matched"}
                  </span>
                </div>

                <div className="panel__content space-y-3">
                  <div className="rounded-xl border border-default bg-surface px-4 py-3">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <p className="eyebrow mb-1.5">Check-In</p>
                        <p className="text-sm font-semibold text-primary">
                          {formatSessionTime(session.checkIn?.timestamp)}
                        </p>
                        <p className="mt-1 text-sm text-secondary">
                          Face match: {formatConfidence(session.checkIn?.confidence)}
                        </p>
                        {checkInOverride ? (
                          <p className="mt-1 text-sm text-secondary">
                            {checkInOverride.note}
                          </p>
                        ) : null}
                        <p className="mt-1 text-sm text-secondary">
                          PPE: {formatPpeStatus(session.ppeDetails?.checkIn, { entry: true })}
                        </p>
                      </div>
                      <div>
                        <p className="eyebrow mb-1.5">Check-Out</p>
                        <p className="text-sm font-semibold text-primary">
                          {formatSessionTime(session.checkOut?.timestamp)}
                        </p>
                        <p className="mt-1 text-sm text-secondary">
                          Face match: {formatConfidence(session.checkOut?.confidence)}
                        </p>
                        {checkOutOverride ? (
                          <p className="mt-1 text-sm text-secondary">
                            {checkOutOverride.note}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>
              </article>
            );
            })
          ) : (
            <div className="relative overflow-hidden rounded-xl border border-dashed border-default bg-card p-8 text-center">
              <div
                className="pointer-events-none absolute inset-0 opacity-30"
                style={{
                  background:
                    "radial-gradient(ellipse at 50% 0%, var(--color-success-muted), transparent 60%)",
                }}
              />
              <div className="relative">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--color-success-muted)]">
                  <AttendanceIcon className="h-6 w-6 text-[var(--color-success)]" />
                </div>
                <p className="font-medium text-primary">No Completed Sessions</p>
                <p className="mt-1 text-sm text-secondary">
                  Worker sessions appear here after both check-in and check-out are logged.
                </p>
              </div>
            </div>
          )}
        </motion.section>
        ) : null}

      </div>
    </div>
  );
}

export default Logs;
