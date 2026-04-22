import { PASSWORD_RULES } from "../../utils/passwordValidation";

function PasswordStrength({ password }) {
  const passedRules = PASSWORD_RULES.filter((rule) => rule.test(password || "")).length;
  const isStrong = passedRules === PASSWORD_RULES.length;

  return (
    <div className="rounded-xl border border-default bg-[var(--color-bg-surface)] px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-primary">Password strength</p>
        <span className={isStrong ? "badge badge-success" : "badge badge-warning"}>
          {isStrong ? "Strong" : `${passedRules}/${PASSWORD_RULES.length} rules`}
        </span>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {PASSWORD_RULES.map((rule) => {
          const passed = rule.test(password || "");
          return (
            <div
              key={rule.key}
              className="rounded-lg border px-3 py-2 text-sm"
              style={{
                borderColor: passed
                  ? "color-mix(in srgb, var(--color-success) 55%, transparent)"
                  : "var(--color-border-default)",
                backgroundColor: passed
                  ? "color-mix(in srgb, var(--color-success-muted) 88%, transparent)"
                  : "var(--color-bg-card)",
                color: passed ? "var(--color-success)" : "var(--color-text-secondary)",
              }}
            >
              {rule.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default PasswordStrength;
