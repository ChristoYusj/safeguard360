import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext";
import { useThemePreference } from "../hooks/useThemePreference";
import { MoonIcon, ShieldIcon, SunIcon } from "../components/icons";

function TwoFactorChallenge() {
  const location = useLocation();
  const navigate = useNavigate();
  const { verifyTwoFactor, isAuthenticated, isLoading } = useAuth();
  const { darkMode, toggleDarkMode } = useThemePreference();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nextPath = location.state?.from?.pathname || "/modules";
  const challengeEmail = location.state?.email || "your account";

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate(nextPath, { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate, nextPath]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (isSubmitting) return;

    setError("");
    setIsSubmitting(true);
    try {
      await verifyTwoFactor({ code: code.trim() });
      navigate(nextPath, { replace: true });
    } catch (submitError) {
      setError(submitError.message || "Two-factor verification failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-base">
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

      <div className="relative z-10 flex min-h-screen items-center justify-center px-6">
        <section className="relative w-full max-w-md rounded-2xl bg-[var(--color-bg-card)] p-8 shadow-card md:p-10">
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
              <div className="mb-5 inline-flex">
                <ShieldIcon size={88} />
              </div>
              <h1 className="font-display text-3xl font-semibold text-primary">
                Two-factor verification
              </h1>
              <p className="mt-2 text-secondary">
                Enter the 6-digit authenticator code or one of your backup codes for {challengeEmail}.
              </p>
            </div>

            <form className="space-y-5" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <label htmlFor="twoFactorCode" className="block text-sm font-semibold text-primary">
                  Authentication code
                </label>
                <input
                  id="twoFactorCode"
                  type="text"
                  required
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value);
                    setError("");
                  }}
                  placeholder="123456 or ABCD-EFGH"
                  className="input h-14 text-base"
                />
              </div>

              {error ? (
                <div className="rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                  <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                    {error}
                  </p>
                </div>
              ) : null}

              <button
                type="submit"
                disabled={isSubmitting}
                className="btn btn-primary h-14 w-full text-base font-semibold disabled:opacity-60"
              >
                Verify and continue
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}

export default TwoFactorChallenge;
