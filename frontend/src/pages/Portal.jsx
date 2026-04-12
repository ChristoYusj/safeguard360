/*
 * SafeGuard 360 - Portal (Login) Page
 * "Precision Command" Design System
 */

import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext";
import { useThemePreference } from "../hooks/useThemePreference";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import {
  SunIcon,
  MoonIcon,
  ShieldIcon,
} from "../components/icons";

const LEGACY_OPERATOR_EMAIL_KEY = "safeguard360-operator-email";

// Animation variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.2 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] },
  },
};

const floatVariants = {
  initial: { y: 0 },
  animate: {
    y: [-8, 8, -8],
    transition: { duration: 6, repeat: Infinity, ease: "easeInOut" },
  },
};

function Portal() {
  const location = useLocation();
  const navigate = useNavigate();
  const { login, isAuthenticated, isLoading } = useAuth();
  const { darkMode, toggleDarkMode } = useThemePreference();
  const { t } = useAppLanguage();
  const [operatorEmail, setOperatorEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nextPath = location.state?.from?.pathname || "/modules";

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(LEGACY_OPERATOR_EMAIL_KEY);
  }, []);

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate(nextPath, { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate, nextPath]);

  const handleSignIn = async (event) => {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }

    setAuthError("");
    setIsSubmitting(true);

    try {
      await login({
        email: operatorEmail.trim(),
        password,
      });
      navigate(nextPath, { replace: true });
    } catch (error) {
      setAuthError(error.message || "Unable to sign in with those credentials.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-base">
      {/* Ambient background effects */}
      <div className="pointer-events-none fixed inset-0">
        {/* Top accent glow */}
        <div
          className="absolute -top-[40%] left-1/2 h-[80%] w-[120%] -translate-x-1/2"
          style={{
            background:
              "radial-gradient(ellipse at center, var(--color-accent-primary-glow) 0%, transparent 60%)",
          }}
        />
        {/* Bottom subtle gradient */}
        <div
          className="absolute bottom-0 left-0 right-0 h-[40%]"
          style={{
            background:
              "linear-gradient(to top, var(--color-bg-deepest), transparent)",
          }}
        />
      </div>

      {/* Theme toggle - top right */}
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
      <div className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 pb-24 pt-20">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="w-full max-w-md"
        >
          {/* Logo and title */}
          <motion.div variants={itemVariants} className="mb-12 text-center">
            <motion.div
              variants={floatVariants}
              initial="initial"
              animate="animate"
              className="mb-6 inline-flex"
            >
              <ShieldIcon size={124} />
            </motion.div>

            <h1 className="font-display text-4xl font-bold tracking-tight text-primary md:text-5xl">
              {t("app_name")}
            </h1>
            <p className="mt-3 text-lg font-medium tracking-wide text-tertiary">
              {t("platform_tagline")}
            </p>
          </motion.div>

          {/* Login card with gradient border */}
          <motion.section
            variants={itemVariants}
            className="relative rounded-2xl p-8 shadow-card md:p-10"
            style={{
              background: "var(--color-bg-card)",
            }}
          >
            {/* Gradient border glow */}
            <div
              className="pointer-events-none absolute -inset-[1px] rounded-2xl opacity-60"
              style={{
                background:
                  "linear-gradient(135deg, var(--color-accent-primary) 0%, transparent 50%, var(--color-accent-secondary) 100%)",
                mask: "linear-gradient(#000, #000) content-box, linear-gradient(#000, #000)",
                maskComposite: "exclude",
                WebkitMaskComposite: "xor",
                padding: "1px",
              }}
            />
            {/* Inner ambient glow */}
            <div
              className="pointer-events-none absolute inset-0 rounded-2xl"
              style={{
                background:
                  "radial-gradient(ellipse at 50% 0%, var(--color-accent-primary-glow) 0%, transparent 50%)",
              }}
            />

            {/* Card content */}
            <div className="relative">
              <div className="mb-8">
              <h2 className="font-display text-2xl font-semibold text-primary">
                {t("system_access")}
              </h2>
              <p className="mt-2 text-secondary">
                {t("enter_credentials")}
              </p>
            </div>

            <form
              className="space-y-6"
              autoComplete="off"
              onSubmit={handleSignIn}
            >
              {/* Operator ID field */}
              <div className="space-y-2">
                <label
                  htmlFor="operatorId"
                  className="block text-sm font-semibold text-primary"
                >
                  {t("email")}
                </label>
                <input
                  id="operatorId"
                  type="text"
                  required
                  value={operatorEmail}
                  onChange={(e) => {
                    setOperatorEmail(e.target.value);
                    setAuthError("");
                  }}
                  placeholder={t("enter_account_email")}
                  autoComplete="email"
                  spellCheck="false"
                  className="input h-14 text-base"
                />
              </div>

              {/* Access Key field */}
              <div className="space-y-2">
                <label
                  htmlFor="accessKey"
                  className="block text-sm font-semibold text-primary"
                >
                  Password
                </label>
                <input
                  id="accessKey"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setAuthError("");
                  }}
                  placeholder={t("enter_access_key")}
                  autoComplete="current-password"
                  className="input h-14 text-base"
                />
              </div>

              {authError ? (
                <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                  <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                    {authError}
                  </p>
                </div>
              ) : null}

              {/* Sign in button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="btn btn-primary h-14 w-full text-base font-semibold disabled:opacity-60"
              >
                <span>{t("sign_in")}</span>
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="h-5 w-5"
                >
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </form>

            {/* System status */}
            <div className="mt-8 flex items-center justify-center gap-2 border-t border-default pt-6">
              <span className="status-dot status-dot-online pulse" />
              <span className="text-sm font-medium text-secondary">
                {t("system_status_operational")}
              </span>
            </div>
            </div>
          </motion.section>
        </motion.div>
      </div>

      {/* Footer */}
      <motion.footer
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.8, duration: 0.4 }}
        className="fixed bottom-0 left-0 right-0 border-t border-default bg-base/80 py-4 backdrop-blur-xl"
      >
        <p className="text-center text-sm text-muted">
          {t("footer_notice")}
        </p>
      </motion.footer>
    </div>
  );
}

export default Portal;
