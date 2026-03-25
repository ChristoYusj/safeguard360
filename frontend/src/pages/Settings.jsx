/*
 * SafeGuard 360 - Settings Page
 * "Precision Command" Design System
 */

import { motion } from "framer-motion";
import { useThemePreference } from "../hooks/useThemePreference";
import { SettingsIcon, ShieldIcon, DriversIcon } from "../components/icons";

const sections = [
  {
    title: "Workspace Controls",
    icon: SettingsIcon,
    items: [
      ["Theme Preference", "Dark command center"],
      ["Alert Delivery", "Operator dashboard + escalation queue"],
      ["Language", "English (US)"],
    ],
  },
  {
    title: "Monitoring Defaults",
    icon: DriversIcon,
    items: [
      ["Fleet Destination", "Beirut"],
      ["Attendance Gate", "North entry checkpoint"],
      ["Retention Window", "30 days live / 180 days archive"],
    ],
  },
  {
    title: "Security",
    icon: ShieldIcon,
    items: [
      ["Operator Session", "Protected"],
      ["Audit Trail", "Immutable event history"],
      ["Access Level", "Regional supervisor"],
    ],
  },
];

const coreServices = [
  { label: "Fleet Monitoring Engine", status: "Online", variant: "success" },
  { label: "Attendance Gate Service", status: "Standby", variant: "warning" },
  { label: "Audit Logger", status: "Healthy", variant: "info" },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

function Settings() {
  const { darkMode, toggleDarkMode } = useThemePreference();

  const variantColors = {
    success: "var(--color-success)",
    warning: "var(--color-warning)",
    info: "var(--color-info)",
  };

  return (
    <div className="min-h-screen p-6 xl:p-8">
      {/* Header */}
      <motion.section
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">Platform Configuration</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          Settings
        </h1>
        <p className="mt-3 max-w-3xl text-base text-secondary">
          Control system-wide defaults, operator preferences, and monitoring
          rules from one secure workspace.
        </p>
      </motion.section>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        {/* Main settings sections */}
        <motion.section
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="space-y-6"
        >
          {sections.map((section) => (
            <motion.article
              key={section.title}
              variants={itemVariants}
              className="panel"
            >
              <div className="panel__header">
                <div className="flex items-center gap-3">
                  <section.icon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                  <h2 className="font-display text-xl font-semibold text-primary">
                    {section.title}
                  </h2>
                </div>
              </div>
              <div className="panel__content space-y-3">
                {section.items.map(([label, value]) => (
                  <div
                    key={label}
                    className="flex items-center justify-between gap-4 rounded-xl border border-default bg-surface px-5 py-4 transition hover:border-[var(--color-accent-primary)]"
                  >
                    <span className="text-secondary">{label}</span>
                    <span className="font-semibold text-primary">{value}</span>
                  </div>
                ))}
              </div>
            </motion.article>
          ))}
        </motion.section>

        {/* Sidebar */}
        <aside className="space-y-6">
          {/* Theme toggle card */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="panel"
          >
            <div className="panel__header">
              <h2 className="font-display text-xl font-semibold text-primary">
                Appearance
              </h2>
            </div>
            <div className="panel__content">
              <div className="flex items-center justify-between gap-4 rounded-xl border border-default bg-surface px-5 py-4">
                <div>
                  <p className="font-semibold text-primary">Dark Mode</p>
                  <p className="mt-0.5 text-sm text-secondary">
                    Toggle interface theme
                  </p>
                </div>
                <button
                  type="button"
                  onClick={toggleDarkMode}
                  className={`relative h-7 w-12 rounded-full transition-colors ${
                    darkMode
                      ? "bg-[var(--color-accent-primary)]"
                      : "bg-[var(--color-border)]"
                  }`}
                >
                  <span
                    className={`absolute left-1 top-1 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
                      darkMode ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            </div>
          </motion.section>

          {/* System Health - with ambient glow */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="panel relative overflow-hidden"
          >
            {/* Ambient glow */}
            <div
              className="pointer-events-none absolute inset-0"
              style={{
                background:
                  "radial-gradient(ellipse at 50% 0%, var(--color-success-muted), transparent 50%)",
              }}
            />
            <div className="panel__header relative">
              <div>
                <p className="eyebrow text-[10px]">System Health</p>
                <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                  Core Services
                </h2>
              </div>
            </div>
            <div className="panel__content relative space-y-3">
              {coreServices.map((service) => (
                <div
                  key={service.label}
                  className="rounded-xl border border-default bg-surface px-5 py-4"
                >
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-secondary">{service.label}</span>
                    <div className="flex items-center gap-2">
                      <span
                        className="status-dot"
                        style={{
                          backgroundColor: variantColors[service.variant],
                        }}
                      />
                      <span
                        className="text-sm font-semibold"
                        style={{ color: variantColors[service.variant] }}
                      >
                        {service.status}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.section>

          {/* Info card */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="panel"
          >
            <div className="panel__header">
              <div>
                <p className="eyebrow text-[10px]">Operator Note</p>
                <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                  Deployment Ready
                </h2>
              </div>
            </div>
            <div className="panel__content">
              <p className="text-sm leading-relaxed text-secondary">
                This settings surface is structured for future live
                configuration wiring, while presenting the final visual system
                for the platform.
              </p>
            </div>
          </motion.section>
        </aside>
      </div>
    </div>
  );
}

export default Settings;
