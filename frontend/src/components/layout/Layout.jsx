/*
 * SafeGuard 360 - Main Layout Component
 * "Precision Command" Design System
 */

import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "../../contexts/AuthContext";
import { useThemePreference } from "../../hooks/useThemePreference";
import { useAppLanguage } from "../../contexts/AppLanguageContext";
import {
  SteeringWheelIcon,
  AttendanceIcon,
  UsersIcon,
  LogsIcon,
  ChatbotIcon,
  SettingsIcon,
  SunIcon,
  MoonIcon,
  ChevronLeftIcon,
  ShieldIcon,
} from "../icons";

const SIDEBAR_STATE_KEY = "safeguard360-sidebar-open";

function getInitialSidebarState() {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(SIDEBAR_STATE_KEY) !== "false";
}

function formatHeaderTime(locale) {
  return new Date().toLocaleString(locale, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const { darkMode, toggleDarkMode } = useThemePreference();
  const { locale, t } = useAppLanguage();
  const navItems = [
    { path: "/drivers", label: t("fleet_monitoring"), icon: SteeringWheelIcon },
    { path: "/attendance", label: t("attendance_ppe"), icon: AttendanceIcon },
    { path: "/enrollment", label: "Enrollment", icon: UsersIcon },
    { path: "/logs", label: t("logs"), icon: LogsIcon },
    { path: "/ai-chatbot", label: t("ai_chatbot"), icon: ChatbotIcon },
    { path: "/settings", label: t("settings"), icon: SettingsIcon },
  ];
  const [sidebarOpen, setSidebarOpen] = useState(getInitialSidebarState);
  const [currentTime, setCurrentTime] = useState(() => formatHeaderTime(locale));

  // Update time every minute
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(formatHeaderTime(locale));
    }, 60000);
    return () => clearInterval(interval);
  }, [locale]);

  useEffect(() => {
    setCurrentTime(formatHeaderTime(locale));
  }, [locale]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      SIDEBAR_STATE_KEY,
      sidebarOpen ? "true" : "false",
    );
  }, [sidebarOpen]);

  const handleLogout = async () => {
    await logout();
    navigate("/", { replace: true });
  };

  return (
    <div className="flex min-h-screen bg-base">
      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{ width: sidebarOpen ? 280 : 80 }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
        className="fixed left-0 top-0 z-[300] flex h-screen flex-col border-r border-default bg-elevated"
      >
        {/* Logo area */}
        <div className="flex h-20 items-center border-b border-default px-4">
          <Link
            to="/"
            className="flex items-center gap-3 rounded-xl p-2 transition hover:bg-[var(--color-active-bg)]"
          >
            <div className="flex h-10 w-10 items-center justify-center">
              <ShieldIcon size={30} />
            </div>
            <AnimatePresence mode="wait">
              {sidebarOpen && (
                <motion.div
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <p className="eyebrow text-[10px]">{t("app_name")}</p>
                  <h1 className="font-display text-sm font-semibold text-primary">
                    {t("command_center")}
                  </h1>
                </motion.div>
              )}
            </AnimatePresence>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto p-3">
          <ul className="space-y-1">
            {navItems.map((item, index) => {
              const isActive =
                location.pathname === item.path ||
                location.pathname.startsWith(`${item.path}/`);
              const IconComponent = item.icon;

              return (
                <motion.li
                  key={item.path}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 + 0.1, duration: 0.3 }}
                >
                  <Link
                    to={item.path}
                    title={sidebarOpen ? undefined : item.label}
                    className={`group flex items-center gap-3 rounded-xl px-3 py-3 transition-all duration-200 ${
                      isActive
                        ? "text-[var(--color-text-inverse)]"
                        : "text-secondary hover:bg-[var(--color-active-bg)] hover:text-primary"
                    }`}
                    style={
                      isActive
                        ? {
                            backgroundColor: "var(--color-info)",
                            boxShadow: "0 0 22px rgba(96, 165, 250, 0.32)",
                          }
                        : undefined
                    }
                  >
                    <div
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition ${
                        isActive
                          ? "bg-white/20"
                          : "bg-[var(--color-bg-surface)] group-hover:bg-[var(--color-bg-card)]"
                      }`}
                    >
                      <IconComponent size={18} />
                    </div>
                    <AnimatePresence mode="wait">
                      {sidebarOpen && (
                        <motion.span
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: -8 }}
                          transition={{ duration: 0.15 }}
                          className="text-sm font-medium whitespace-nowrap"
                        >
                          {item.label}
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </Link>
                </motion.li>
              );
            })}
          </ul>
        </nav>

        {/* Sidebar toggle */}
        <div className="border-t border-default p-3">
          <button
            type="button"
            onClick={() => setSidebarOpen((prev) => !prev)}
            aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-[var(--color-bg-surface)] text-tertiary transition hover:bg-[var(--color-bg-card)] hover:text-primary"
          >
            <motion.div
              animate={{ rotate: sidebarOpen ? 0 : 180 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronLeftIcon size={18} />
            </motion.div>
            <AnimatePresence mode="wait">
              {sidebarOpen && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="text-sm font-medium"
                >
                  {t("collapse")}
                </motion.span>
              )}
            </AnimatePresence>
          </button>
        </div>
      </motion.aside>

      {/* Main content area */}
      <motion.div
        initial={false}
        animate={{ marginLeft: sidebarOpen ? 280 : 80 }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
        className="min-w-0 flex-1"
      >
        {/* Header */}
        <header className="sticky top-0 z-[200] border-b border-default glass">
          <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4 xl:px-8">
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
            >
              <p className="font-display text-lg font-semibold text-primary mt-0.5">
                Signed in as operator
              </p>
              <p className="mt-1 text-sm text-secondary">
                {user?.email || "No operator signed in"}
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="flex flex-wrap items-center gap-4"
            >
              {/* Theme toggle */}
              <div className="flex items-center gap-2">
                <SunIcon size={16} className="text-muted" />
                <button
                  type="button"
                  onClick={toggleDarkMode}
                  role="switch"
                  aria-checked={darkMode}
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
              </div>

              {/* System status */}
              <div className="flex items-center gap-2 rounded-full border border-default bg-card px-4 py-2">
                <span className="status-dot status-dot-online pulse" />
                <span className="text-sm font-medium text-primary">
                  {t("system_online")}
                </span>
              </div>

              {/* Time */}
              <div className="rounded-full border border-default bg-card px-4 py-2">
                <span className="text-sm font-medium text-secondary">
                  {currentTime}
                </span>
              </div>

              <button
                type="button"
                onClick={handleLogout}
                className="btn btn-secondary h-10 px-4"
              >
                Sign out
              </button>
            </motion.div>
          </div>
        </header>

        {/* Page content with route transitions */}
        <main className="min-h-[calc(100vh-73px)]">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </motion.div>
    </div>
  );
}

export default Layout;
