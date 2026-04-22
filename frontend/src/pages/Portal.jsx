/*
 * SafeGuard 360 - Portal (Login) Page
 * "Precision Command" Design System
 */

import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext";
import { useThemePreference } from "../hooks/useThemePreference";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import PasswordStrength from "../components/auth/PasswordStrength";
import { registerOperator, requestPasswordReset } from "../services/api";
import { REGISTRATION_ROLE_OPTIONS } from "../utils/accessControl";
import { isStrongPassword } from "../utils/passwordValidation";
import {
  SunIcon,
  MoonIcon,
  ShieldIcon,
} from "../components/icons";

const LEGACY_OPERATOR_EMAIL_KEY = "safeguard360-operator-email";

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
  const [mode, setMode] = useState("login");
  const [loginForm, setLoginForm] = useState({
    email: "",
    password: "",
  });
  const [resetForm, setResetForm] = useState({
    email: "",
  });
  const [registerForm, setRegisterForm] = useState({
    full_name: "",
    email: "",
    role: REGISTRATION_ROLE_OPTIONS[0].value,
    password: "",
    confirm_password: "",
  });
  const [authError, setAuthError] = useState("");
  const [authWarning, setAuthWarning] = useState(null);
  const [registerError, setRegisterError] = useState("");
  const [registerSuccess, setRegisterSuccess] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetSuccess, setResetSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nextPath = location.state?.from?.pathname || "/modules";

  const passwordsMatch =
    registerForm.password.length > 0 &&
    registerForm.password === registerForm.confirm_password;
  const passwordIsStrong = useMemo(() => isStrongPassword(registerForm.password), [registerForm.password]);

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
    if (isSubmitting) return;

    setAuthError("");
    setAuthWarning(null);
    setRegisterSuccess("");
    setResetSuccess("");
    setIsSubmitting(true);

    try {
      const response = await login({
        email: loginForm.email.trim(),
        password: loginForm.password,
      });
      if (response?.requires_two_factor) {
        navigate("/auth/2fa", {
          replace: true,
          state: {
            from: location.state?.from,
            email: loginForm.email.trim(),
          },
        });
        return;
      }
      navigate(nextPath, { replace: true });
    } catch (error) {
      if (error.is_locked) {
        setAuthError("");
        setAuthWarning({
          tone: "error",
          message:
            error.message ||
            `Too many failed sign-in attempts. Try again in ${error.retry_after_minutes || 5} minutes.`,
        });
      } else if (error.warning_message && Number.isInteger(error.remaining_attempts)) {
        setAuthError(error.message || "Unable to sign in with those credentials.");
        setAuthWarning({
          tone: error.remaining_attempts === 1 ? "orange" : "warning",
          message: error.warning_message,
        });
      } else {
        setAuthError(error.message || "Unable to sign in with those credentials.");
        setAuthWarning(null);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetRequest = async (event) => {
    event.preventDefault();
    if (isSubmitting) return;

    setResetError("");
    setResetSuccess("");
    setIsSubmitting(true);

    try {
      const response = await requestPasswordReset({
        email: resetForm.email.trim(),
      });
      setResetSuccess(
        response.message || "If the account exists, a password reset link has been sent.",
      );
      setResetForm({ email: "" });
    } catch (error) {
      setResetError(error.message || "Unable to send a password reset link.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegister = async (event) => {
    event.preventDefault();
    if (isSubmitting) return;

    setRegisterError("");
    setRegisterSuccess("");

    if (!passwordIsStrong) {
      setRegisterError(
        "Password must be at least 8 characters and include an uppercase letter, number, and special character.",
      );
      return;
    }

    if (!passwordsMatch) {
      setRegisterError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await registerOperator(registerForm);
      setRegisterSuccess(
        response.message || "Your account request was submitted and is pending approval.",
      );
      setRegisterForm({
        full_name: "",
        email: "",
        role: REGISTRATION_ROLE_OPTIONS[0].value,
        password: "",
        confirm_password: "",
      });
      setMode("login");
    } catch (error) {
      setRegisterError(error.message || "Registration request failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const isLoginMode = mode === "login";
  const isResetMode = mode === "forgot";

  return (
    <div className="relative min-h-screen overflow-hidden bg-base">
      <div className="pointer-events-none fixed inset-0">
        <div
          className="absolute -top-[40%] left-1/2 h-[80%] w-[120%] -translate-x-1/2"
          style={{
            background:
              "radial-gradient(ellipse at center, var(--color-accent-primary-glow) 0%, transparent 60%)",
          }}
        />
        <div
          className="absolute bottom-0 left-0 right-0 h-[40%]"
          style={{
            background:
              "linear-gradient(to top, var(--color-bg-deepest), transparent)",
          }}
        />
      </div>

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

      <div className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 pb-24 pt-20">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="w-full max-w-[36rem]"
        >
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

          <motion.section
            variants={itemVariants}
            className="relative rounded-2xl p-8 shadow-card md:p-10"
            style={{ background: "var(--color-bg-card)" }}
          >
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
            <div
              className="pointer-events-none absolute inset-0 rounded-2xl"
              style={{
                background:
                  "radial-gradient(ellipse at 50% 0%, var(--color-accent-primary-glow) 0%, transparent 50%)",
              }}
            />

            <div className="relative">
              <div className="mb-8">
                <div className="inline-flex rounded-full border border-default bg-[var(--color-bg-surface)] p-1">
                  <button
                    type="button"
                    onClick={() => {
                      setMode("login");
                      setAuthError("");
                      setAuthWarning(null);
                      setRegisterError("");
                      setResetError("");
                    }}
                    className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                      isLoginMode
                        ? "bg-[var(--color-accent-primary)] text-white"
                        : "text-secondary"
                    }`}
                  >
                    Sign in
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMode("register");
                      setAuthError("");
                      setAuthWarning(null);
                      setRegisterError("");
                      setResetError("");
                    }}
                    className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                      !isLoginMode
                        ? "bg-[var(--color-accent-primary)] text-white"
                        : "text-secondary"
                    }`}
                  >
                    Request access
                  </button>
                </div>
                <h2 className="mt-5 font-display text-2xl font-semibold text-primary">
                  {isLoginMode
                    ? t("system_access")
                    : isResetMode
                      ? "Reset password"
                      : "Operator registration"}
                </h2>
                <p className="mt-2 text-secondary">
                  {isLoginMode
                    ? t("enter_credentials")
                    : isResetMode
                      ? "Enter your operator email and we will send a reset link if the account exists."
                      : "Register an operator account for manual admin approval."}
                </p>
              </div>

              {registerSuccess ? (
                <div className="mb-6 rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
                  <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                    {registerSuccess}
                  </p>
                </div>
              ) : null}

              {isLoginMode ? (
                <form className="space-y-6" autoComplete="off" onSubmit={handleSignIn}>
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
                      value={loginForm.email}
                      onChange={(event) => {
                      setLoginForm((current) => ({
                          ...current,
                          email: event.target.value,
                        }));
                        setAuthError("");
                        setAuthWarning(null);
                      }}
                      placeholder={t("enter_account_email")}
                      autoComplete="email"
                      spellCheck="false"
                      className="input h-14 text-base"
                    />
                  </div>

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
                      value={loginForm.password}
                      onChange={(event) => {
                        setLoginForm((current) => ({
                          ...current,
                          password: event.target.value,
                        }));
                        setAuthError("");
                        setAuthWarning(null);
                      }}
                      placeholder={t("enter_access_key")}
                      autoComplete="current-password"
                      className="input h-14 text-base"
                    />
                  </div>

                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        setMode("forgot");
                        setAuthError("");
                        setAuthWarning(null);
                        setResetError("");
                        setResetSuccess("");
                        setResetForm({ email: loginForm.email.trim() });
                      }}
                      className="text-sm font-semibold text-[var(--color-accent-primary)] transition hover:opacity-80"
                    >
                      Forgot password?
                    </button>
                  </div>

                  {authError ? (
                    <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                        {authError}
                      </p>
                    </div>
                  ) : null}

                  {authWarning ? (
                    <div
                      className="rounded-xl border px-4 py-3"
                      style={{
                        borderColor:
                          authWarning.tone === "orange"
                            ? "color-mix(in srgb, var(--color-warning) 70%, transparent)"
                            : authWarning.tone === "warning"
                              ? "color-mix(in srgb, #facc15 70%, transparent)"
                              : "color-mix(in srgb, var(--color-error) 70%, transparent)",
                        backgroundColor:
                          authWarning.tone === "orange"
                            ? "color-mix(in srgb, var(--color-warning) 16%, var(--color-bg-card))"
                            : authWarning.tone === "warning"
                              ? "color-mix(in srgb, #facc15 14%, var(--color-bg-card))"
                              : "var(--color-error-muted)",
                      }}
                    >
                      <p
                        className="text-sm font-semibold"
                        style={{
                          color:
                            authWarning.tone === "orange"
                              ? "var(--color-warning)"
                              : authWarning.tone === "warning"
                                ? "#ca8a04"
                                : "var(--color-error)",
                        }}
                      >
                        {authWarning.message}
                      </p>
                    </div>
                  ) : null}

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
              ) : isResetMode ? (
                <form className="space-y-6" autoComplete="off" onSubmit={handleResetRequest}>
                  <div className="space-y-2">
                    <label
                      htmlFor="resetEmail"
                      className="block text-sm font-semibold text-primary"
                    >
                      {t("email")}
                    </label>
                    <input
                      id="resetEmail"
                      type="email"
                      required
                      value={resetForm.email}
                      onChange={(event) => {
                        setResetForm({ email: event.target.value });
                        setResetError("");
                      }}
                      placeholder={t("enter_account_email")}
                      autoComplete="email"
                      className="input h-14 text-base"
                    />
                  </div>

                  {resetSuccess ? (
                    <div className="rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                        {resetSuccess}
                      </p>
                    </div>
                  ) : null}

                  {resetError ? (
                    <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                        {resetError}
                      </p>
                    </div>
                  ) : null}

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="btn btn-primary h-14 w-full text-base font-semibold disabled:opacity-60"
                  >
                    Send reset link
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setMode("login");
                      setAuthWarning(null);
                      setResetError("");
                      setResetSuccess("");
                    }}
                    className="btn btn-secondary h-14 w-full text-base font-semibold"
                  >
                    Back to sign in
                  </button>
                </form>
              ) : (
                <form className="space-y-5" autoComplete="off" onSubmit={handleRegister}>
                  <div className="grid gap-5 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <label
                        htmlFor="registerFullName"
                        className="block text-sm font-semibold text-primary"
                      >
                        Full name
                      </label>
                      <input
                        id="registerFullName"
                        type="text"
                        required
                        value={registerForm.full_name}
                        onChange={(event) => {
                          setRegisterForm((current) => ({
                            ...current,
                            full_name: event.target.value,
                          }));
                          setRegisterError("");
                        }}
                        placeholder="Enter your full name"
                        className="input h-14 text-base"
                      />
                    </div>

                    <div className="space-y-2">
                      <label
                        htmlFor="registerEmail"
                        className="block text-sm font-semibold text-primary"
                      >
                        Email
                      </label>
                      <input
                        id="registerEmail"
                        type="email"
                        required
                        value={registerForm.email}
                        onChange={(event) => {
                          setRegisterForm((current) => ({
                            ...current,
                            email: event.target.value,
                          }));
                          setRegisterError("");
                        }}
                        placeholder="Enter your work email"
                        autoComplete="email"
                        className="input h-14 text-base"
                      />
                    </div>

                    <div className="space-y-2">
                      <label
                        htmlFor="registerRole"
                        className="block text-sm font-semibold text-primary"
                      >
                        Operator role
                      </label>
                      <select
                        id="registerRole"
                        required
                        value={registerForm.role}
                        onChange={(event) => {
                          setRegisterForm((current) => ({
                            ...current,
                            role: event.target.value,
                          }));
                          setRegisterError("");
                        }}
                        className="input h-14 text-base"
                      >
                        {REGISTRATION_ROLE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="space-y-2">
                      <label
                        htmlFor="registerPassword"
                        className="block text-sm font-semibold text-primary"
                      >
                        Password
                      </label>
                      <input
                        id="registerPassword"
                        type="password"
                        required
                        value={registerForm.password}
                        onChange={(event) => {
                          setRegisterForm((current) => ({
                            ...current,
                            password: event.target.value,
                          }));
                          setRegisterError("");
                        }}
                        placeholder="Create a password"
                        autoComplete="new-password"
                        className="input h-14 text-base"
                      />
                    </div>

                    <div className="space-y-2">
                      <label
                        htmlFor="registerConfirmPassword"
                        className="block text-sm font-semibold text-primary"
                      >
                        Confirm password
                      </label>
                      <input
                        id="registerConfirmPassword"
                        type="password"
                        required
                        value={registerForm.confirm_password}
                        onChange={(event) => {
                          setRegisterForm((current) => ({
                            ...current,
                            confirm_password: event.target.value,
                          }));
                          setRegisterError("");
                        }}
                        placeholder="Repeat your password"
                        autoComplete="new-password"
                        className="input h-14 text-base"
                      />
                    </div>
                  </div>

                  <PasswordStrength password={registerForm.password} />

                  {registerForm.confirm_password ? (
                    <div
                      className="rounded-xl border px-4 py-3"
                      style={{
                        borderColor: passwordsMatch
                          ? "color-mix(in srgb, var(--color-success) 55%, transparent)"
                          : "color-mix(in srgb, var(--color-error) 55%, transparent)",
                        backgroundColor: passwordsMatch
                          ? "color-mix(in srgb, var(--color-success-muted) 88%, transparent)"
                          : "color-mix(in srgb, var(--color-error-muted) 88%, transparent)",
                      }}
                    >
                      <p
                        className="text-sm font-semibold"
                        style={{
                          color: passwordsMatch
                            ? "var(--color-success)"
                            : "var(--color-error)",
                        }}
                      >
                        {passwordsMatch ? "Passwords match." : "Passwords do not match."}
                      </p>
                    </div>
                  ) : null}

                  {registerError ? (
                    <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                        {registerError}
                      </p>
                    </div>
                  ) : null}

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="btn btn-primary h-14 w-full text-base font-semibold disabled:opacity-60"
                  >
                    Submit approval request
                  </button>
                </form>
              )}

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
