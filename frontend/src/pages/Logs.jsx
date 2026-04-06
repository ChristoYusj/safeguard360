/*
 * SafeGuard 360 - Platform Logs Page
 * "Precision Command" Design System
 */

import { useState } from "react";
import { motion } from "framer-motion";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import {
  clearPlatformLogModule,
  readPlatformLogs,
} from "../utils/platformLogs";
import {
  AlertTriangleIcon,
  DriversIcon,
  AttendanceIcon,
} from "../components/icons";

function formatSessionTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
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

const logCategories = [
  {
    icon: DriversIcon,
    color: "var(--color-info)",
    type: "Fleet Logs",
    description: "Fatigue, route activity, and driver monitoring sessions.",
  },
  {
    icon: AttendanceIcon,
    color: "var(--color-success)",
    type: "Attendance Logs",
    description:
      "Worker check-ins, shift approvals, and access activity by session.",
  },
  {
    icon: AlertTriangleIcon,
    color: "var(--color-warning)",
    type: "PPE Logs",
    description:
      "PPE detections, access decisions, and override activity by session.",
  },
];

function Logs() {
  const { t } = useAppLanguage();
  const [store, setStore] = useState(() => readPlatformLogs());
  const fleetSessions = store.fleet.sessions || [];
  const attendanceSessions = store.attendance?.sessions || [];
  const ppeSessions = store.gatePpe?.sessions || [];

  const counts = [
    `${fleetSessions.length} session${fleetSessions.length === 1 ? "" : "s"} tracked`,
    `${attendanceSessions.length} session${attendanceSessions.length === 1 ? "" : "s"} open`,
    `${ppeSessions.length} session${ppeSessions.length === 1 ? "" : "s"} open`,
  ];

  const handleClearModule = (moduleName) => {
    clearPlatformLogModule(moduleName);
    setStore(readPlatformLogs());
  };

  return (
    <div className="min-h-screen p-6 xl:p-8">
      {/* Header */}
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

      {/* Category cards */}
      <motion.section
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="mb-8 grid gap-4 lg:grid-cols-3"
      >
        {logCategories.map((cat, i) => (
          <motion.article
            key={cat.type}
            variants={itemVariants}
            className="stat-card group"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="stat-card__label">{counts[i]}</p>
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

      {/* Sessions grid */}
      <div className="grid gap-6 xl:grid-cols-3">
        {/* Fleet Sessions */}
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
                      {session.truckId} •{" "}
                      {session.sourceLabel || "Camera source"} • Started{" "}
                      {formatSessionTime(session.startedAt)}
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
              {/* Subtle gradient accent */}
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

        {/* Attendance Sessions */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="space-y-4"
        >
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold text-primary">
              Attendance Sessions
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-secondary">Workforce flow</span>
              <button
                type="button"
                onClick={() => handleClearModule("attendance")}
                className="btn btn-secondary h-10 px-4"
              >
                Clear
              </button>
            </div>
          </div>
          {attendanceSessions.length > 0 ? (
            attendanceSessions.map((session, index) => (
              <article key={session.id} className="panel">
                <div className="panel__header border-b-0 pb-0">
                  <div>
                    <p className="eyebrow text-[10px]">
                      Attendance Session {index + 1}
                    </p>
                    <h3 className="mt-1 font-display text-lg font-semibold text-primary">
                      {session.title || session.workerName || "Attendance Session"}
                    </h3>
                    <p className="mt-1 text-sm text-secondary">
                      Started{" "}
                      {session.startedAt
                        ? formatSessionTime(session.startedAt)
                        : "Unknown"}
                    </p>
                  </div>
                  <span className="badge badge-success">
                    {(session.events || []).length} event
                    {(session.events || []).length === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="panel__content space-y-3">
                  {(session.events || []).length > 0 ? (
                    session.events.map((event) => (
                      <div
                        key={event.id}
                        className="rounded-xl border border-default bg-surface px-4 py-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-primary">
                              {event.details || event.title || "Attendance event"}
                            </p>
                            <p className="mt-1 text-sm text-secondary">
                              {event.status || event.sourceLabel || "Attendance"}
                            </p>
                          </div>
                          <span className="text-sm text-tertiary">
                            {event.timestamp
                              ? formatSessionTime(event.timestamp)
                              : "--"}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-default bg-surface px-4 py-4 text-sm text-secondary">
                      No attendance events were logged during this session.
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
                    "radial-gradient(ellipse at 50% 0%, var(--color-success-muted), transparent 60%)",
                }}
              />
              <div className="relative">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--color-success-muted)]">
                  <AttendanceIcon className="h-6 w-6 text-[var(--color-success)]" />
                </div>
                <p className="font-medium text-primary">No Attendance Sessions</p>
                <p className="mt-1 text-sm text-secondary">
                  Attendance history will appear here once real worker check-ins are
                  logged.
                </p>
              </div>
            </div>
          )}
        </motion.section>

        {/* PPE Sessions */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="space-y-4"
        >
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold text-primary">
              PPE Sessions
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-secondary">PPE compliance</span>
              <button
                type="button"
                onClick={() => handleClearModule("gatePpe")}
                className="btn btn-secondary h-10 px-4"
              >
                Clear
              </button>
            </div>
          </div>
          {ppeSessions.length > 0 ? (
            ppeSessions.map((session, index) => (
              <article key={session.id} className="panel">
                <div className="panel__header border-b-0 pb-0">
                  <div>
                    <p className="eyebrow text-[10px]">PPE Session {index + 1}</p>
                    <h3 className="mt-1 font-display text-lg font-semibold text-primary">
                      {session.title || session.cameraSource || "PPE Session"}
                    </h3>
                    <p className="mt-1 text-sm text-secondary">
                      Started{" "}
                      {session.startedAt
                        ? formatSessionTime(session.startedAt)
                        : "Unknown"}
                    </p>
                  </div>
                  <span className="badge badge-warning">
                    {(session.events || []).length} event
                    {(session.events || []).length === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="panel__content space-y-3">
                  {(session.events || []).length > 0 ? (
                    session.events.map((event) => (
                      <div
                        key={event.id}
                        className="rounded-xl border border-default bg-surface px-4 py-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-primary">
                              {event.details || event.title || "PPE event"}
                            </p>
                            <p className="mt-1 text-sm text-secondary">
                              {event.status || event.sourceLabel || "PPE"}
                            </p>
                          </div>
                          <span className="text-sm text-tertiary">
                            {event.timestamp
                              ? formatSessionTime(event.timestamp)
                              : "--"}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-default bg-surface px-4 py-4 text-sm text-secondary">
                      No PPE events were logged during this session.
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
                    "radial-gradient(ellipse at 50% 0%, var(--color-warning-muted), transparent 60%)",
                }}
              />
              <div className="relative">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--color-warning-muted)]">
                  <AlertTriangleIcon className="h-6 w-6 text-[var(--color-warning)]" />
                </div>
                <p className="font-medium text-primary">No PPE Sessions</p>
                <p className="mt-1 text-sm text-secondary">
                  PPE history will appear here once live compliance detections are
                  logged.
                </p>
              </div>
            </div>
          )}
        </motion.section>
      </div>
    </div>
  );
}

export default Logs;
