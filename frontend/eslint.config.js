import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

// Flat config (ESLint 9+). Correctness-focused: recommended JS rules plus the
// React hooks rules, which catch the effect/dependency bugs the audit found.
// No formatting rules — Prettier-style opinions are out of scope here.
export default [
  { ignores: ["dist/**", "node_modules/**", "scripts/**"] },
  js.configs.recommended,
  reactHooks.configs.flat.recommended,
  reactRefresh.configs.vite,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // Component names are capitalised and often unused inside their own file
      // when exported for the router; keep the rule but skip that pattern.
      "no-unused-vars": ["warn", { varsIgnorePattern: "^[A-Z_]", argsIgnorePattern: "^_" }],
      "react-refresh/only-export-components": "warn",
    },
  },
  {
    files: ["**/*.test.{js,jsx}", "**/*.config.js"],
    languageOptions: { globals: { ...globals.node } },
  },
];
