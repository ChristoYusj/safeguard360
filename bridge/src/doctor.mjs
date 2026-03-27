import fs from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { loadConfig, validateConfig } from "./config.mjs";
import { discoverLatestMatchingThread, listMatchingThreads } from "./session-discovery.mjs";
import { listWorkspaceProjects } from "./workspace-projects.mjs";

const execFileAsync = promisify(execFile);
const config = loadConfig();

async function exists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  console.log(`Bridge root: ${config.bridgeRoot}`);
  console.log(`Project root: ${config.workingDirectory}`);
  console.log(`Codex home: ${config.codexHome}`);
  console.log(`Session root: ${config.sessionDiscoveryRoot}`);
  console.log(`State file: ${config.stateFile}`);
  console.log(`Log file: ${config.logFile}`);
  console.log(`Telegram token set: ${config.botToken ? "yes" : "no"}`);
  console.log(`Allowed Telegram user set: ${config.allowedUserId ? "yes" : "no"}`);
  console.log(`Working directory exists: ${await exists(config.workingDirectory) ? "yes" : "no"}`);
  console.log(`Project .codex config exists: ${await exists(path.join(config.workingDirectory, ".codex", "config.toml")) ? "yes" : "no"}`);

  try {
    const { stdout } = await execFileAsync(process.execPath, [path.join(config.bridgeRoot, "node_modules", "@openai", "codex", "bin", "codex.js"), "--version"], {
      cwd: config.bridgeRoot,
    });
    console.log(`Bundled Codex CLI: ${stdout.trim()}`);
  } catch (error) {
    console.log(`Bundled Codex CLI: unavailable (${error.message})`);
  }

  const latest = await discoverLatestMatchingThread({
    sessionRoot: config.sessionDiscoveryRoot,
    projectRoot: config.workingDirectory,
    hints: config.discoveryHints,
  });

  if (latest) {
    console.log(`Latest matching thread: ${latest.threadId}`);
    console.log(`Latest session cwd: ${latest.cwd}`);
    console.log(`Latest session file: ${latest.sessionFile}`);
  } else {
    console.log("Latest matching thread: none found");
  }

  const sessions = await listMatchingThreads({
    sessionRoot: config.sessionDiscoveryRoot,
    projectRoot: config.workingDirectory,
    hints: config.discoveryHints,
    limit: 3,
  });
  console.log(`Recent matching sessions: ${sessions.length}`);

  const projects = await listWorkspaceProjects(config.workingDirectory);
  console.log(`Workspace projects found: ${projects.map((project) => project.name).join(", ") || "(none)"}`);

  const problems = validateConfig(config);
  if (problems.length > 0) {
    console.log("Configuration issues:");
    for (const problem of problems) {
      console.log(`- ${problem}`);
    }
    process.exitCode = 1;
  }
}

await main();
