import fs from "node:fs/promises";
import path from "node:path";

function normalize(value) {
  return path.resolve(value).toLowerCase();
}

function pathsOverlap(left, right) {
  const a = normalize(left);
  const b = normalize(right);

  return a === b || a.startsWith(`${b}${path.sep}`) || b.startsWith(`${a}${path.sep}`);
}

async function collectSessionFiles(root) {
  const files = [];

  async function walk(current) {
    let entries;
    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch (error) {
      if (error.code === "ENOENT") {
        return;
      }
      throw error;
    }

    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
        continue;
      }

      if (entry.isFile() && entry.name.endsWith(".jsonl")) {
        const stats = await fs.stat(fullPath);
        files.push({ fullPath, mtimeMs: stats.mtimeMs });
      }
    }
  }

  await walk(root);
  files.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return files;
}

function parseThreadId(sessionFile) {
  const match = path.basename(sessionFile).match(/-([0-9a-f-]{36})\.jsonl$/i);
  return match ? match[1] : null;
}

async function extractCwd(sessionFile) {
  const raw = await fs.readFile(sessionFile, "utf8");
  const lines = raw.split(/\r?\n/);

  for (const line of lines) {
    if (!line.trim()) {
      continue;
    }

    try {
      const parsed = JSON.parse(line);
      if (parsed.type === "turn_context" && parsed.payload?.cwd) {
        return parsed.payload.cwd;
      }
    } catch {
      // Ignore malformed lines and keep scanning.
    }
  }

  return null;
}

export async function discoverLatestMatchingThread({ sessionRoot, projectRoot, hints = [] }) {
  const targets = [projectRoot, ...hints].filter(Boolean);
  const files = await collectSessionFiles(sessionRoot);

  for (const file of files) {
    const cwd = await extractCwd(file.fullPath);
    if (!cwd) {
      continue;
    }

    if (targets.some((target) => pathsOverlap(target, cwd))) {
      return {
        threadId: parseThreadId(file.fullPath),
        sessionFile: file.fullPath,
        cwd,
        updatedAt: new Date(file.mtimeMs).toISOString(),
      };
    }
  }

  return null;
}
