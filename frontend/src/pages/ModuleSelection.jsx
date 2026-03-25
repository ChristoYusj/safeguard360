/*
 * SafeGuard 360 - Module Selection Page
 * "Precision Command" Design System
 */

import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useThemePreference } from "../hooks/useThemePreference";
import {
  DriversIcon,
  AttendanceIcon,
  LogsIcon,
  ChatbotIcon,
  SettingsIcon,
  SunIcon,
  MoonIcon,
  ShieldIcon,
  ChevronRightIcon,
} from "../components/icons";

const modules = [
  {
    id: "drivers",
    name: "Drivers",
    description: "Real-time fleet monitoring and driver fatigue detection",
    route: "/drivers",
    Icon: DriversIcon,
    accent: "var(--color-accent-primary)",
  },
  {
    id: "attendance",
    name: "Attendance & PPE",
    description: "Track check-ins, PPE verification, and shift management",
    route: "/attendance",
    Icon: AttendanceIcon,
    accent: "var(--color-accent-secondary)",
  },
  {
    id: "logs",
    name: "Logs",
    description: "System audit trail and session history",
    route: "/logs",
    Icon: LogsIcon,
    accent: "var(--color-info)",
  },
  {
    id: "chatbot",
    name: "AI Chatbot",
    description: "Intelligent assistant for operations support",
    route: "/ai-chatbot",
    Icon: ChatbotIcon,
    accent: "var(--color-success)",
  },
  {
    id: "settings",
    name: "Settings",
    description: "System configuration and workspace preferences",
    route: "/settings",
    Icon: SettingsIcon,
    accent: "var(--color-text-tertiary)",
  },
];

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.3 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 24, scale: 0.95 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] },
  },
};

const headerVariants = {
  hidden: { opacity: 0, y: -20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] },
  },
};

function ModuleSelection() {
  const { darkMode, toggleDarkMode } = useThemePreference();

  return (
    <div className="relative min-h-screen overflow-hidden bg-base">
      {/* Ambient background effects */}
      <div className="pointer-events-none fixed inset-0">
        <div
          className="absolute -top-[30%] left-1/2 h-[60%] w-[100%] -translate-x-1/2"
          style={{
            background:
              "radial-gradient(ellipse at center, var(--color-accent-primary-glow) 0%, transparent 50%)",
          }}
        />
      </div>

      {/* Theme toggle */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.4 }}
        className="absolute right-6 top-6 z-20 flex items-center gap-2"
      >
        <SunIcon size={16} className="text-muted" />
        <button
          type="button"
          onClick={toggleDarkMode}
          role="switch"
          aria-checked={darkMode}
          aria-label="Toggle dark mode"
          className={`relative inline-flex h-7 w-12 items-center rounded-full border transition-colors ${
            darkMode
              ? "border-[var(--color-accent-primary)] bg-[var(--color-accent-primary)]"
              : "border-[var(--color-border-emphasis)] bg-[var(--color-bg-surface)]"
          }`}
        >
          <motion.span
            initial={false}
            animate={{ x: darkMode ? 22 : 2 }}
            transition={{ type: "spring", stiffness: 500, damping: 30 }}
            className="inline-block h-5 w-5 rounded-full bg-white shadow-md"
          />
        </button>
        <MoonIcon size={16} className="text-muted" />
      </motion.div>

      {/* Main content */}
      <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col px-6 pb-20 pt-16 md:px-8">
        {/* Header */}
        <motion.header
          variants={headerVariants}
          initial="hidden"
          animate="visible"
          className="mb-16 text-center"
        >
          <div className="mb-6 inline-flex items-center justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--color-accent-primary)] shadow-[var(--glow-accent)]">
              <ShieldIcon
                size={32}
                className="text-[var(--color-text-inverse)]"
              />
            </div>
          </div>

          <h1 className="font-display text-4xl font-bold tracking-tight text-primary md:text-5xl">
            SafeGuard 360
          </h1>
          <p className="mt-3 text-lg font-medium tracking-wide text-tertiary">
            Unified AI Safety & Operations Platform
          </p>
        </motion.header>

        {/* Welcome message */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
          className="mb-12 text-center"
        >
          <h2 className="font-display text-2xl font-semibold text-primary md:text-3xl">
            Welcome, Operator
          </h2>
          <p className="mt-2 text-lg text-secondary">
            Select a module to begin monitoring
          </p>
        </motion.div>

        {/* Module grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="mx-auto grid w-full max-w-6xl gap-5 sm:grid-cols-2 lg:grid-cols-3"
        >
          {modules.map((module) => {
            const { Icon } = module;

            return (
              <motion.div key={module.id} variants={itemVariants}>
                <Link
                  to={module.route}
                  className="group relative flex min-h-[200px] flex-col rounded-2xl border border-default bg-card p-6 shadow-card transition-all duration-300 hover:-translate-y-1 hover:border-[var(--color-border-accent)] hover:shadow-card-hover"
                >
                  {/* Hover glow effect */}
                  <div
                    className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                    style={{
                      background: `radial-gradient(circle at 50% 0%, ${module.accent}15, transparent 60%)`,
                    }}
                  />

                  {/* Icon */}
                  <div
                    className="relative mb-5 flex h-14 w-14 items-center justify-center rounded-xl border border-default bg-surface transition-all duration-300 group-hover:border-[var(--color-border-accent)]"
                    style={{ color: module.accent }}
                  >
                    <Icon size={26} />
                  </div>

                  {/* Content */}
                  <div className="relative flex-1">
                    <h3 className="font-display text-lg font-semibold text-primary">
                      {module.name}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-secondary">
                      {module.description}
                    </p>
                  </div>

                  {/* Arrow indicator */}
                  <div className="relative mt-4 flex items-center text-tertiary transition-colors group-hover:text-accent">
                    <span className="text-sm font-medium">Open module</span>
                    <motion.div
                      className="ml-2"
                      initial={{ x: 0 }}
                      whileHover={{ x: 4 }}
                    >
                      <ChevronRightIcon size={16} />
                    </motion.div>
                  </div>
                </Link>
              </motion.div>
            );
          })}
        </motion.div>

        {/* Footer */}
        <motion.footer
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1, duration: 0.5 }}
          className="mt-auto pt-16 text-center"
        >
          <p className="text-sm text-muted">
            © 2026 SafeGuard 360. All rights reserved. Authorized personnel
            only.
          </p>
        </motion.footer>
      </div>
    </div>
  );
}

export default ModuleSelection;
