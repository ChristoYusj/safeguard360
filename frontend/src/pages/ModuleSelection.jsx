/*
 * SafeGuard 360 - Module Selection Page
 * "Precision Command" Design System
 */

import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useThemePreference } from "../hooks/useThemePreference";
import { useAppLanguage } from "../contexts/AppLanguageContext";
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
  const { t } = useAppLanguage();
  const modules = [
    {
      id: "drivers",
      name: t("drivers_module"),
      description: t("drivers_module_description"),
      route: "/drivers",
      Icon: DriversIcon,
      accent: "var(--color-accent-primary)",
    },
    {
      id: "attendance",
      name: t("attendance_ppe"),
      description: t("attendance_module_description"),
      route: "/attendance",
      Icon: AttendanceIcon,
      accent: "var(--color-accent-secondary)",
    },
    {
      id: "logs",
      name: t("logs"),
      description: t("logs_module_description"),
      route: "/logs",
      Icon: LogsIcon,
      accent: "var(--color-info)",
    },
    {
      id: "chatbot",
      name: t("ai_chatbot"),
      description: t("ai_chatbot_description"),
      route: "/ai-chatbot",
      Icon: ChatbotIcon,
      accent: "var(--color-success)",
    },
    {
      id: "settings",
      name: t("settings"),
      description: t("settings_module_description"),
      route: "/settings",
      Icon: SettingsIcon,
      accent: "var(--color-text-tertiary)",
    },
  ];

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
            <ShieldIcon size={86} />
          </div>

          <h1 className="font-display text-4xl font-bold tracking-tight text-primary md:text-5xl">
            {t("app_name")}
          </h1>
          <p className="mt-3 text-lg font-medium tracking-wide text-tertiary">
            {t("platform_tagline")}
          </p>
        </motion.header>

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
                    <span className="text-sm font-medium">{t("open_module")}</span>
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
            {t("footer_notice")}
          </p>
        </motion.footer>
      </div>
    </div>
  );
}

export default ModuleSelection;
