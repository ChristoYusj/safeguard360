import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  acknowledgeAlert,
  getAlerts,
} from "../services/api";
import {
  AlertTriangleIcon,
  BellIcon,
  CheckCircleIcon,
} from "../components/icons";

function formatAlertTime(value) {
  if (!value) {
    return "--";
  }

  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function getSeverityBadge(severity) {
  if (severity === "ALERT" || severity === "CRITICAL") {
    return "badge badge-warning";
  }
  if (severity === "WARNING") {
    return "badge badge-info";
  }
  return "badge badge-success";
}

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState("");
  const [activeAlertId, setActiveAlertId] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const loadAlerts = async () => {
      try {
        const records = await getAlerts();
        if (!cancelled) {
          setAlerts(records || []);
        }
      } catch (loadError) {
        if (!cancelled) {
          console.error("[Alerts] Failed to load alerts", loadError);
          setError(loadError.message || "Failed to load alerts.");
        }
      }
    };

    loadAlerts();
    const timer = window.setInterval(loadAlerts, 8000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const activeAlerts = useMemo(
    () => alerts.filter((alert) => alert.is_active),
    [alerts],
  );
  const historicalAlerts = useMemo(
    () => alerts.filter((alert) => !alert.is_active),
    [alerts],
  );

  const handleAcknowledge = async (alertId) => {
    try {
      setActiveAlertId(alertId);
      setError("");
      const updated = await acknowledgeAlert(alertId);
      setAlerts((current) =>
        current.map((alert) => (alert.id === alertId ? updated : alert)),
      );
    } catch (ackError) {
      console.error("[Alerts] Failed to acknowledge alert", ackError);
      setError(ackError.message || "Failed to acknowledge alert.");
    } finally {
      setActiveAlertId(null);
    }
  };

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">active incident board</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          Alerts
        </h1>
        <p className="mt-3 max-w-3xl text-sm text-secondary">
          PPE gate incidents and future fleet alerts land here from the backend alert pipeline.
        </p>
      </motion.header>

      <section className="mb-8 grid gap-4 md:grid-cols-3">
        <article className="stat-card">
          <p className="stat-card__label">Active alerts</p>
          <p className="stat-card__value">{activeAlerts.length}</p>
        </article>
        <article className="stat-card">
          <p className="stat-card__label">Historical alerts</p>
          <p className="stat-card__value">{historicalAlerts.length}</p>
        </article>
        <article className="stat-card">
          <p className="stat-card__label">PPE alerts</p>
          <p className="stat-card__value">
            {alerts.filter((alert) => alert.category === "PPE").length}
          </p>
        </article>
      </section>

      {error ? (
        <div className="mb-6 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
          <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
            {error}
          </p>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="panel">
          <div className="panel__header">
            <div className="flex items-center gap-3">
              <AlertTriangleIcon size={20} className="text-accent" />
              <div>
                <h2 className="font-display text-xl font-semibold text-primary">
                  Active Alerts
                </h2>
                <p className="mt-1 text-sm text-secondary">
                  Alerts remain active until an operator acknowledges them.
                </p>
              </div>
            </div>
            <span className="badge badge-warning">{activeAlerts.length} active</span>
          </div>

          <div className="panel__content space-y-4">
            {activeAlerts.length > 0 ? (
              activeAlerts.map((alert) => (
                <article
                  key={alert.id}
                  className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-base font-semibold text-primary">
                          {alert.title}
                        </p>
                        <span className={getSeverityBadge(alert.severity)}>
                          {alert.severity}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-secondary">
                        {[alert.category, alert.event_type, formatAlertTime(alert.created_at)]
                          .filter(Boolean)
                          .join(" • ")}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleAcknowledge(alert.id)}
                      disabled={activeAlertId === alert.id}
                      className="btn btn-secondary h-10 px-4"
                    >
                      {activeAlertId === alert.id ? "Saving..." : "Acknowledge"}
                    </button>
                  </div>
                  <p className="mt-4 text-sm font-medium text-primary">
                    {alert.message || "No alert summary available."}
                  </p>
                </article>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-default px-5 py-12 text-center">
                <CheckCircleIcon size={30} className="mx-auto mb-3 text-accent" />
                <p className="text-base font-semibold text-primary">
                  No active alerts
                </p>
                <p className="mt-2 text-sm text-secondary">
                  Once PPE or fleet incidents are raised, they will surface here immediately.
                </p>
              </div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel__header">
            <div className="flex items-center gap-3">
              <BellIcon size={20} className="text-accent" />
              <div>
                <h2 className="font-display text-xl font-semibold text-primary">
                  Alert History
                </h2>
                <p className="mt-1 text-sm text-secondary">
                  Acknowledged alerts remain available for audit review.
                </p>
              </div>
            </div>
            <span className="badge badge-info">{historicalAlerts.length} logged</span>
          </div>

          <div className="panel__content space-y-4">
            {historicalAlerts.length > 0 ? (
              historicalAlerts.map((alert) => (
                <article
                  key={alert.id}
                  className="rounded-2xl border border-default bg-[var(--color-bg-surface)] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-base font-semibold text-primary">
                          {alert.title}
                        </p>
                        <span className="badge badge-success">Acknowledged</span>
                      </div>
                      <p className="mt-2 text-sm text-secondary">
                        {[alert.category, formatAlertTime(alert.acknowledged_at || alert.created_at)]
                          .filter(Boolean)
                          .join(" • ")}
                      </p>
                    </div>
                    <span className={getSeverityBadge(alert.severity)}>
                      {alert.severity}
                    </span>
                  </div>
                  <p className="mt-4 text-sm font-medium text-primary">
                    {alert.message || "No alert summary available."}
                  </p>
                </article>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-default px-5 py-12 text-center">
                <BellIcon size={30} className="mx-auto mb-3 text-accent" />
                <p className="text-base font-semibold text-primary">
                  No alert history yet
                </p>
                <p className="mt-2 text-sm text-secondary">
                  Acknowledged alerts will remain visible here after the active queue is cleared.
                </p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default Alerts;
