import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  clearAuditLogs,
  deleteAdminUser,
  getAdminUsers,
  getAuditLogs,
  getCurrentOperator,
  unlockAdminUser,
  updateAdminUser,
} from "../services/api";
import { ROLE_LABELS, ROLES, getRoleLabel } from "../utils/accessControl";
import { LogsIcon, UsersIcon } from "../components/icons";

const ROLE_OPTIONS = [
  { value: ROLES.ADMIN, label: ROLE_LABELS[ROLES.ADMIN] },
  { value: ROLES.FLEET_OPERATOR, label: ROLE_LABELS[ROLES.FLEET_OPERATOR] },
  { value: ROLES.SAFETY_OPERATOR, label: ROLE_LABELS[ROLES.SAFETY_OPERATOR] },
  { value: ROLES.GENERAL_MANAGER, label: ROLE_LABELS[ROLES.GENERAL_MANAGER] },
];

const TABS = {
  OPERATORS: "operators",
  AUDIT: "audit",
};

function formatStatusLabel(status) {
  if (!status) {
    return "Unknown";
  }
  if (status === "restricted") {
    return "Inactive";
  }
  return status.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function getStatusBadge(status) {
  if (status === "active") return "badge badge-success";
  if (status === "pending") return "badge badge-warning";
  if (status === "restricted") return "badge badge-info";
  return "badge badge-warning";
}

function formatEventType(eventType) {
  return (eventType || "unknown")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function ToggleSwitch({ checked, onChange, ariaLabel, disabled = false }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      aria-disabled={disabled}
      onClick={onChange}
      className={`relative h-7 w-12 rounded-full transition-colors ${
        checked
          ? "bg-[var(--color-accent-primary)]"
          : "bg-[var(--color-border-emphasis)]"
      } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
    >
      <span
        className={`absolute left-1 top-1 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function UserManagement() {
  const [activeTab, setActiveTab] = useState(TABS.OPERATORS);

  const [users, setUsers] = useState([]);
  const [currentOperatorId, setCurrentOperatorId] = useState("");
  const [operatorsError, setOperatorsError] = useState("");
  const [operatorsMessage, setOperatorsMessage] = useState("");
  const [operatorsLoading, setOperatorsLoading] = useState(true);
  const [busyKey, setBusyKey] = useState("");

  const [auditLogs, setAuditLogs] = useState([]);
  const [auditEventTypes, setAuditEventTypes] = useState([]);
  const [auditFilters, setAuditFilters] = useState({
    event_type: "",
    date_from: "",
    date_to: "",
  });
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditError, setAuditError] = useState("");
  const [auditMessage, setAuditMessage] = useState("");
  const [auditBusy, setAuditBusy] = useState(false);

  const loadUsers = async () => {
    setOperatorsLoading(true);
    setOperatorsError("");
    try {
      const [response, currentOperator] = await Promise.all([
        getAdminUsers(),
        getCurrentOperator().catch(() => null),
      ]);
      setUsers(response.users || []);
      setCurrentOperatorId(currentOperator?.user?.id || "");
    } catch (loadError) {
      setOperatorsError(loadError.message || "User accounts could not be loaded.");
    } finally {
      setOperatorsLoading(false);
    }
  };

  const loadAuditLogs = async (nextFilters = auditFilters) => {
    setAuditLoading(true);
    setAuditError("");
    try {
      const response = await getAuditLogs({
        ...nextFilters,
        limit: 250,
      });
      setAuditLogs(response.logs || []);
      setAuditEventTypes(response.event_types || []);
    } catch (loadError) {
      setAuditError(loadError.message || "Audit log could not be loaded.");
    } finally {
      setAuditLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
    loadAuditLogs();
  }, []);

  const counts = useMemo(
    () => ({
      total: users.length,
      pending: users.filter((user) => user.status === "pending").length,
      active: users.filter((user) => user.status === "active").length,
    }),
    [users],
  );

  const auditSummary = useMemo(
    () => ({
      total: auditLogs.length,
      uniqueOperators: new Set(auditLogs.map((entry) => entry.operator_email)).size,
      latestTimestamp: auditLogs[0]?.timestamp || null,
    }),
    [auditLogs],
  );

  const handleRoleChange = async (userId, role) => {
    setBusyKey(`${userId}:role`);
    setOperatorsError("");
    setOperatorsMessage("");
    try {
      const response = await updateAdminUser(userId, { role });
      setUsers((current) =>
        current.map((user) => (user.id === userId ? response.user : user)),
      );
      setOperatorsMessage("Operator role updated.");
      await loadAuditLogs(auditFilters);
    } catch (updateError) {
      setOperatorsError(updateError.message || "Role update failed.");
    } finally {
      setBusyKey("");
    }
  };

  const handleStatusChange = async (userId, status) => {
    setBusyKey(`${userId}:status:${status}`);
    setOperatorsError("");
    setOperatorsMessage("");
    try {
      const response = await updateAdminUser(userId, { status });
      setUsers((current) =>
        current.map((user) => (user.id === userId ? response.user : user)),
      );
      setOperatorsMessage(`Account marked ${formatStatusLabel(status).toLowerCase()}.`);
      await loadAuditLogs(auditFilters);
    } catch (updateError) {
      setOperatorsError(updateError.message || "Account update failed.");
    } finally {
      setBusyKey("");
    }
  };

  const handleDelete = async (userId) => {
    setBusyKey(`${userId}:delete`);
    setOperatorsError("");
    setOperatorsMessage("");
    try {
      await deleteAdminUser(userId);
      setUsers((current) => current.filter((user) => user.id !== userId));
      setOperatorsMessage("Operator account deleted.");
      await loadAuditLogs(auditFilters);
    } catch (deleteError) {
      setOperatorsError(deleteError.message || "Account deletion failed.");
    } finally {
      setBusyKey("");
    }
  };

  const handleUnlock = async (userId) => {
    setBusyKey(`${userId}:unlock`);
    setOperatorsError("");
    setOperatorsMessage("");
    try {
      const response = await unlockAdminUser(userId);
      setUsers((current) =>
        current.map((user) => (user.id === userId ? response.user : user)),
      );
      setOperatorsMessage(response.message || "Account lockout cleared.");
    } catch (unlockError) {
      setOperatorsError(unlockError.message || "Account unlock failed.");
    } finally {
      setBusyKey("");
    }
  };

  const handleApplyAuditFilters = async (event) => {
    event.preventDefault();
    await loadAuditLogs(auditFilters);
  };

  const handleResetAuditFilters = async () => {
    const emptyFilters = {
      event_type: "",
      date_from: "",
      date_to: "",
    };
    setAuditFilters(emptyFilters);
    await loadAuditLogs(emptyFilters);
  };

  const handleClearAuditLog = async () => {
    const confirmed = window.confirm("Are you sure? This cannot be undone.");
    if (!confirmed) {
      return;
    }

    setAuditBusy(true);
    setAuditError("");
    setAuditMessage("");
    try {
      const response = await clearAuditLogs();
      setAuditLogs([]);
      setAuditMessage(`Audit log cleared. ${response.deleted_count || 0} entries deleted.`);
    } catch (clearError) {
      setAuditError(clearError.message || "Audit log could not be cleared.");
    } finally {
      setAuditBusy(false);
    }
  };

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.section
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">Admin Console</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          User Management
        </h1>
      </motion.section>

      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="stat-card">
          <p className="stat-card__label">Accounts</p>
          <p className="stat-card__value">{counts.total}</p>
        </div>
        <div className="stat-card">
          <p className="stat-card__label">Pending</p>
          <p className="stat-card__value">{counts.pending}</p>
        </div>
        <div className="stat-card">
          <p className="stat-card__label">Audit Entries</p>
          <p className="stat-card__value">{auditSummary.total}</p>
        </div>
      </div>

      <div className="mb-6 inline-flex rounded-full border border-default bg-[var(--color-bg-surface)] p-1">
        <button
          type="button"
          onClick={() => setActiveTab(TABS.OPERATORS)}
          className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
            activeTab === TABS.OPERATORS
              ? "bg-[var(--color-accent-primary)] text-white"
              : "text-secondary"
          }`}
        >
          Operators
        </button>
        <button
          type="button"
          onClick={() => setActiveTab(TABS.AUDIT)}
          className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
            activeTab === TABS.AUDIT
              ? "bg-[var(--color-accent-primary)] text-white"
              : "text-secondary"
          }`}
        >
          Audit Log
        </button>
      </div>

      {activeTab === TABS.OPERATORS ? (
        <>
          {operatorsMessage ? (
            <div className="mb-4 rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
              <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                {operatorsMessage}
              </p>
            </div>
          ) : null}

          {operatorsError ? (
            <div className="mb-4 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
              <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                {operatorsError}
              </p>
            </div>
          ) : null}

          <section className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <UsersIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <p className="eyebrow text-[10px]">Operators</p>
                  <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                    Accounts
                  </h2>
                </div>
              </div>
              <button type="button" onClick={loadUsers} className="btn btn-secondary h-10 px-4">
                Refresh
              </button>
            </div>
            <div className="panel__content space-y-4">
              {operatorsLoading ? (
                <div className="rounded-xl border border-dashed border-default px-5 py-10 text-center">
                  <p className="text-base font-semibold text-primary">Loading operator accounts</p>
                </div>
              ) : users.length > 0 ? (
                users.map((user) => {
                  const isCurrentAdmin =
                    user.id === currentOperatorId && user.role === ROLES.ADMIN;
                  return (
                  <article
                    key={user.id}
                    className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-5"
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-semibold text-primary">{user.full_name}</h3>
                          <span className={getStatusBadge(user.status)}>{formatStatusLabel(user.status)}</span>
                          {user.is_locked ? <span className="badge badge-warning">Locked</span> : null}
                        </div>
                        <p className="mt-1 text-sm text-secondary">{user.email}</p>
                        <p className="mt-2 text-sm text-secondary">
                          Created {user.created_at ? new Date(user.created_at).toLocaleString() : "--"}
                        </p>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-[220px_auto]">
                        <select
                          value={user.role || ""}
                          onChange={(event) => handleRoleChange(user.id, event.target.value)}
                          disabled={busyKey.startsWith(`${user.id}:`)}
                          className="input h-11"
                        >
                          {ROLE_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>

                        <div className="flex flex-wrap items-center gap-3">
                          {user.status === "pending" ? (
                            <>
                              <button
                                type="button"
                                onClick={() => handleStatusChange(user.id, "active")}
                                disabled={busyKey !== "" && busyKey.startsWith(`${user.id}:`)}
                                className="btn btn-primary h-10 px-4"
                              >
                                Approve
                              </button>
                              <button
                                type="button"
                                onClick={() => handleStatusChange(user.id, "rejected")}
                                disabled={busyKey !== "" && busyKey.startsWith(`${user.id}:`)}
                                className="btn h-10 px-4 text-white"
                                style={{ backgroundColor: "var(--color-error)" }}
                              >
                                Reject
                              </button>
                            </>
                          ) : isCurrentAdmin ? (
                            <div className="rounded-xl border border-default bg-card px-3 py-2">
                              <p className="text-xs font-semibold uppercase tracking-wide text-secondary">
                                Access
                              </p>
                              <p className="mt-0.5 text-sm font-semibold text-primary">
                                Protected admin account
                              </p>
                            </div>
                          ) : (
                            <div className="flex items-center gap-3 rounded-xl border border-default bg-card px-3 py-2">
                              <div className="min-w-[72px]">
                                <p className="text-xs font-semibold uppercase tracking-wide text-secondary">
                                  Access
                                </p>
                                <p className="mt-0.5 text-sm font-semibold text-primary">
                                  {user.status === "active" ? "Active" : "Inactive"}
                                </p>
                              </div>
                              <ToggleSwitch
                                checked={user.status === "active"}
                                onChange={() =>
                                  handleStatusChange(
                                    user.id,
                                    user.status === "active" ? "restricted" : "active",
                                  )
                                }
                                disabled={busyKey !== "" && busyKey.startsWith(`${user.id}:`)}
                                ariaLabel={`Toggle account access for ${user.full_name}`}
                              />
                            </div>
                          )}

                          <button
                            type="button"
                            onClick={() => handleDelete(user.id)}
                            disabled={busyKey !== "" && busyKey.startsWith(`${user.id}:`)}
                            className="btn h-10 px-4 text-white"
                            style={{ backgroundColor: "var(--color-error)" }}
                          >
                            Delete
                          </button>

                          {user.is_locked ? (
                            <button
                              type="button"
                              onClick={() => handleUnlock(user.id)}
                              disabled={busyKey !== "" && busyKey.startsWith(`${user.id}:`)}
                              className="btn btn-primary h-10 px-4"
                            >
                              Unlock
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      <span className="badge badge-info">{getRoleLabel(user.role)}</span>
                      {isCurrentAdmin ? (
                        <span className="badge badge-info">Current admin session</span>
                      ) : null}
                      {user.lockout_until ? (
                        <span className="badge badge-info">
                          Lockout until {new Date(user.lockout_until).toLocaleString()}
                        </span>
                      ) : null}
                      <span className="badge badge-info">
                        Updated {user.updated_at ? new Date(user.updated_at).toLocaleString() : "--"}
                      </span>
                    </div>
                  </article>
                  );
                })
              ) : (
                <div className="rounded-xl border border-dashed border-default px-5 py-10 text-center">
                  <p className="text-base font-semibold text-primary">No operator accounts found</p>
                </div>
              )}
            </div>
          </section>
        </>
      ) : (
        <>
          {auditMessage ? (
            <div className="mb-4 rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
              <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                {auditMessage}
              </p>
            </div>
          ) : null}

          {auditError ? (
            <div className="mb-4 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
              <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                {auditError}
              </p>
            </div>
          ) : null}

          <section className="panel mb-6">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <LogsIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <p className="eyebrow text-[10px]">Filters</p>
                  <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                    Security Events
                  </h2>
                </div>
              </div>
            </div>
            <div className="panel__content">
              <form className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_auto_auto]" onSubmit={handleApplyAuditFilters}>
                <select
                  value={auditFilters.event_type}
                  onChange={(event) => setAuditFilters((current) => ({ ...current, event_type: event.target.value }))}
                  className="input h-11"
                >
                  <option value="">All event types</option>
                  {auditEventTypes.map((eventType) => (
                    <option key={eventType} value={eventType}>
                      {formatEventType(eventType)}
                    </option>
                  ))}
                </select>
                <input
                  type="date"
                  value={auditFilters.date_from}
                  onChange={(event) => setAuditFilters((current) => ({ ...current, date_from: event.target.value }))}
                  className="input h-11"
                />
                <input
                  type="date"
                  value={auditFilters.date_to}
                  onChange={(event) => setAuditFilters((current) => ({ ...current, date_to: event.target.value }))}
                  className="input h-11"
                />
                <button type="submit" className="btn btn-primary h-11 px-4" disabled={auditBusy}>
                  Apply
                </button>
                <button type="button" onClick={handleResetAuditFilters} className="btn btn-secondary h-11 px-4" disabled={auditBusy}>
                  Clear
                </button>
              </form>
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <LogsIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <p className="eyebrow text-[10px]">Timeline</p>
                  <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                    Audit Log
                  </h2>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => loadAuditLogs(auditFilters)}
                  className="btn btn-secondary h-10 px-4"
                  disabled={auditBusy}
                >
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={handleClearAuditLog}
                  className="btn h-10 px-4 text-white"
                  style={{ backgroundColor: "var(--color-error)" }}
                  disabled={auditBusy}
                >
                  Clear Log
                </button>
              </div>
            </div>
            <div className="panel__content space-y-4">
              {auditLoading ? (
                <div className="rounded-xl border border-dashed border-default px-5 py-10 text-center">
                  <p className="text-base font-semibold text-primary">Loading audit log</p>
                </div>
              ) : auditLogs.length > 0 ? (
                auditLogs.map((entry) => (
                  <article
                    key={entry.id}
                    className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-5"
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-semibold text-primary">
                            {formatEventType(entry.event_type)}
                          </h3>
                          <span className="badge badge-info">{entry.operator_email}</span>
                        </div>
                        <p className="mt-1 text-sm text-secondary">
                          {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "--"}
                        </p>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <span className="badge badge-info">IP {entry.ip_address || "--"}</span>
                      </div>
                    </div>

                    <div className="mt-4 rounded-xl border border-default bg-[var(--color-bg-card)] px-4 py-3">
                      <p className="text-sm text-primary">{entry.detail || "No additional detail recorded."}</p>
                    </div>
                  </article>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-default px-5 py-10 text-center">
                  <p className="text-base font-semibold text-primary">No audit events match the current filters</p>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export default UserManagement;
