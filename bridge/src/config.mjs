import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";

dotenv.config({ quiet: true });

const bridgeRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const defaultProjectRoot = path.resolve(bridgeRoot, "..");
const defaultCodexHome = path.join(process.env.USERPROFILE ?? process.env.HOME ?? defaultProjectRoot, ".codex");

function normalizeAbsolute(inputPath) {
  return path.resolve(inputPath);
}

function splitPaths(value) {
  if (!value) {
    return [];
  }

  return value
    .split(/[;,]/)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => normalizeAbsolute(entry));
}

export function loadConfig() {
  const discoveryHints = splitPaths(process.env.BRIDGE_DISCOVERY_HINTS || "");
  const workingDirectory = normalizeAbsolute(
    process.env.CODEX_WORKING_DIRECTORY || defaultProjectRoot,
  );
  const codexHome = normalizeAbsolute(process.env.CODEX_HOME || defaultCodexHome);
  const sessionDiscoveryRoot = normalizeAbsolute(
    process.env.CODEX_SESSION_DISCOVERY_ROOT || path.join(codexHome, "sessions"),
  );

  return {
    bridgeRoot,
    workingDirectory,
    botToken: process.env.TELEGRAM_BOT_TOKEN || "",
    allowedUserId: process.env.TELEGRAM_ALLOWED_USER_ID || "",
    codexHome,
    sessionDiscoveryRoot,
    discoveryHints: discoveryHints.length
      ? discoveryHints
      : [path.dirname(workingDirectory), workingDirectory],
    stateFile: normalizeAbsolute(
      process.env.BRIDGE_STATE_FILE || path.join(bridgeRoot, "state", "bridge-state.json"),
    ),
    logFile: normalizeAbsolute(
      process.env.BRIDGE_LOG_FILE || path.join(bridgeRoot, "logs", "bridge.log"),
    ),
    codex: {
      model: process.env.CODEX_MODEL || "gpt-5.4",
      approvalPolicy: process.env.CODEX_APPROVAL_POLICY || "never",
      sandboxMode: process.env.CODEX_SANDBOX_MODE || "workspace-write",
      networkAccessEnabled: String(process.env.CODEX_NETWORK_ACCESS || "false").toLowerCase() === "true",
      webSearchMode: process.env.CODEX_WEB_SEARCH_MODE || "disabled",
      modelReasoningEffort: process.env.CODEX_REASONING_EFFORT || "medium",
      additionalDirectories: splitPaths(process.env.CODEX_ADDITIONAL_DIRECTORIES || ""),
    },
  };
}

export function validateConfig(config) {
  const problems = [];

  if (!config.botToken) {
    problems.push("Missing TELEGRAM_BOT_TOKEN");
  }

  if (!config.allowedUserId) {
    problems.push("Missing TELEGRAM_ALLOWED_USER_ID");
  }

  return problems;
}
