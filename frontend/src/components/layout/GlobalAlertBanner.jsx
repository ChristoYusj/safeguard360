/*
 * Site-wide alert overlay — red full-screen flash + toast stack driven
 * by AlertFeedContext. Sits in the Layout so every authenticated page
 * inherits it automatically.
 */
import { AnimatePresence, motion } from "framer-motion";
import { useAlertFeed } from "../../contexts/AlertFeedContext";

const SEVERITY_STYLES = {
  danger: {
    border: "1px solid rgba(239, 68, 68, 0.75)",
    glow: "0 0 32px rgba(239, 68, 68, 0.35)",
    accent: "#ef4444",
    label: "CRITICAL",
  },
  warning: {
    border: "1px solid rgba(245, 158, 11, 0.75)",
    glow: "0 0 28px rgba(245, 158, 11, 0.3)",
    accent: "#f59e0b",
    label: "ALERT",
  },
  info: {
    border: "1px solid rgba(59, 130, 246, 0.75)",
    glow: "0 0 24px rgba(59, 130, 246, 0.25)",
    accent: "#3b82f6",
    label: "INFO",
  },
};

export default function GlobalAlertBanner() {
  const { alerts, flashSeverity, dismissAlert } = useAlertFeed();

  return (
    <>
      {/* Full-viewport red/amber flash — pointer-events none so it doesn't
          steal clicks. Triple-pulse opacity ramp reads as an urgent flash
          without lingering on-screen. */}
      <AnimatePresence>
        {flashSeverity && (
          <motion.div
            key={`flash-${flashSeverity}-${Date.now()}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.4, 0, 0.28, 0] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.9, times: [0, 0.18, 0.4, 0.65, 1] }}
            style={{
              pointerEvents: "none",
              position: "fixed",
              inset: 0,
              zIndex: 450,
              backgroundColor: SEVERITY_STYLES[flashSeverity]?.accent || "#ef4444",
              mixBlendMode: "screen",
            }}
          />
        )}
      </AnimatePresence>

      {/* Toast stack */}
      <div
        style={{
          position: "fixed",
          right: 16,
          top: 16,
          zIndex: 500,
          pointerEvents: "none",
        }}
        className="flex w-[min(380px,calc(100vw-32px))] flex-col gap-2"
      >
        <AnimatePresence initial={false}>
          {alerts.map((alert) => {
            const style = SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.info;
            return (
              <motion.div
                key={alert.id}
                layout
                initial={{ opacity: 0, x: 80, scale: 0.96 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 80, scale: 0.96 }}
                transition={{ type: "spring", stiffness: 420, damping: 36 }}
                className="glass rounded-xl p-3 shadow-xl"
                style={{
                  pointerEvents: "auto",
                  border: style.border,
                  boxShadow: style.glow,
                }}
              >
                <div className="flex items-start gap-3">
                  <div
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: 999,
                      marginTop: 8,
                      backgroundColor: style.accent,
                      boxShadow: `0 0 12px ${style.accent}`,
                      flexShrink: 0,
                    }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className="text-[10px] font-bold uppercase tracking-wider"
                        style={{ color: style.accent }}
                      >
                        {style.label}
                      </span>
                      <span className="text-[10px] text-tertiary">
                        · {new Date(alert.receivedAt).toLocaleTimeString()}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-primary mt-1 truncate">
                      {alert.title}
                    </p>
                    {alert.message && (
                      <p className="text-xs text-secondary mt-1 break-words">
                        {alert.message}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => dismissAlert(alert.id)}
                    aria-label="Dismiss"
                    className="text-tertiary hover:text-primary text-lg leading-none px-1"
                  >
                    ×
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </>
  );
}
