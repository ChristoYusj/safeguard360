import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import PasswordStrength from "../components/auth/PasswordStrength";
import { useThemePreference } from "../hooks/useThemePreference";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import { confirmPasswordReset } from "../services/api";
import { isStrongPassword } from "../utils/passwordValidation";
import { MoonIcon, ShieldIcon, SunIcon } from "../components/icons";

function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { darkMode, toggleDarkMode } = useThemePreference();
  const { t } = useAppLanguage();
  const [form, setForm] = useState({
    password: "",
    confirm_password: "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const token = searchParams.get("token") || "";
  const passwordsMatch = form.password.length > 0 && form.password === form.confirm_password;
  const passwordIsStrong = useMemo(() => isStrongPassword(form.password), [form.password]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (isSubmitting) return;

    if (!token) {
      setError("This password reset link is invalid or expired.");
      return;
    }

    if (!passwordIsStrong) {
      setError(
        "Password must be at least 8 characters and include an uppercase letter, number, and special character.",
      );
      return;
    }

    if (!passwordsMatch) {
      setError("Passwords do not match.");
      return;
    }

    setError("");
    setSuccess("");
    setIsSubmitting(true);
    try {
      const response = await confirmPasswordReset({
        token,
        password: form.password,
        confirm_password: form.confirm_password,
      });
      setSuccess(response.message || "Your password has been reset. You can now sign in.");
      setForm({
        password: "",
        confirm_password: "",
      });
      window.setTimeout(() => {
        navigate("/", { replace: true });
      }, 1200);
    } catch (submitError) {
      setError(submitError.message || "Unable to reset your password.");
    } finally {
      setIsSubmitting(false);
    }
  };

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
        transition={{ delay: 0.2, duration: 0.4 }}
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
        <section
          className="relative w-full max-w-[36rem] rounded-2xl p-8 shadow-card md:p-10"
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
          <div className="relative">
            <div className="mb-8 text-center">
              <div className="mb-6 inline-flex">
                <ShieldIcon size={108} />
              </div>
              <h1 className="font-display text-3xl font-bold tracking-tight text-primary md:text-4xl">
                Reset password
              </h1>
              <p className="mt-3 text-secondary">
                Choose a new password for your SafeGuard 360 operator account.
              </p>
            </div>

            <form className="space-y-5" autoComplete="off" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <label htmlFor="resetPassword" className="block text-sm font-semibold text-primary">
                  New password
                </label>
                <input
                  id="resetPassword"
                  type="password"
                  required
                  value={form.password}
                  onChange={(event) => {
                    setForm((current) => ({ ...current, password: event.target.value }));
                    setError("");
                  }}
                  autoComplete="new-password"
                  placeholder="Create a new password"
                  className="input h-14 text-base"
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="resetConfirmPassword" className="block text-sm font-semibold text-primary">
                  Confirm new password
                </label>
                <input
                  id="resetConfirmPassword"
                  type="password"
                  required
                  value={form.confirm_password}
                  onChange={(event) => {
                    setForm((current) => ({ ...current, confirm_password: event.target.value }));
                    setError("");
                  }}
                  autoComplete="new-password"
                  placeholder="Repeat the new password"
                  className="input h-14 text-base"
                />
              </div>

              <PasswordStrength password={form.password} />

              {form.confirm_password ? (
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
                      color: passwordsMatch ? "var(--color-success)" : "var(--color-error)",
                    }}
                  >
                    {passwordsMatch ? "Passwords match." : "Passwords do not match."}
                  </p>
                </div>
              ) : null}

              {error ? (
                <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                  <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                    {error}
                  </p>
                </div>
              ) : null}

              {success ? (
                <div className="rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
                  <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                    {success}
                  </p>
                </div>
              ) : null}

              <button
                type="submit"
                disabled={isSubmitting}
                className="btn btn-primary h-14 w-full text-base font-semibold disabled:opacity-60"
              >
                Save new password
              </button>

              <Link to="/" className="btn btn-secondary h-14 w-full text-base font-semibold">
                Back to sign in
              </Link>
            </form>

            <div className="mt-8 flex items-center justify-center gap-2 border-t border-default pt-6">
              <span className="status-dot status-dot-online pulse" />
              <span className="text-sm font-medium text-secondary">
                {t("system_status_operational")}
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default ResetPassword;
