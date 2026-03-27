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

async function loadThreadIndex(sessionRoot) {
  const indexPath = path.resolve(sessionRoot, "..", "session_index.jsonl");
  const map = new Map();

  try {
    const raw = await fs.readFile(indexPath, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      if (!line.trim()) {
        continue;
      }

      try {
        const parsed = JSON.parse(line);
        if (parsed.id) {
          map.set(parsed.id, parsed);
        }
      } catch {
        // Ignore malformed index lines.
      }
    }
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }

  return map;
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

async function buildSessionRecord(file, indexMap) {
  const threadId = parseThreadId(file.fullPath);
  if (!threadId) {
    return null;
  }

  const cwd = await extractCwd(file.fullPath);
  if (!cwd) {
    return null;
  }

  const indexEntry = indexMap.get(threadId);
  return {
    threadId,
    threadName: indexEntry?.thread_name || null,
    sessionFile: file.fullPath,
    cwd,
    updatedAt: new Date(file.mtimeMs).toISOString(),
  };
}

export async function listMatchingThreads({ sessionRoot, projectRoot, hints = [], limit = 8 }) {
  const targets = [projectRoot, ...hints].filter(Boolean);
  const files = await collectSessionFiles(sessionRoot);
  const indexMap = await loadThreadIndex(sessionRoot);
  const matches = [];

  for (const file of files) {
    const record = await buildSessionRecord(file, indexMap);
    if (!record) {
      continue;
    }

    if (targets.length === 0 || targets.some((target) => pathsOverlap(target, record.cwd))) {
      matches.push(record);
      if (matches.length >= limit) {
        break;
      }
    }
  }

  return matches;
}

export async function discoverLatestMatchingThread({ sessionRoot, projectRoot, hints = [] }) {
  const matches = await listMatchingThreads({ sessionRoot, projectRoot, hints, limit: 1 });
  return matches[0] || null;
}

export async function findThreadById({ sessionRoot, threadId }) {
  const files = await collectSessionFiles(sessionRoot);
  const indexMap = await loadThreadIndex(sessionRoot);

  for (const file of files) {
    if (parseThreadId(file.fullPath) !== threadId) {
      continue;
    }

    return buildSessionRecord(file, indexMap);
  }

  return null;
}
