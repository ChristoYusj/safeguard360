import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_STATE = {
  attachedThreadId: null,
  attachedFrom: null,
  attachedSessionFile: null,
  attachedCwd: null,
  activeProjectName: null,
  activeProjectPath: null,
  lastPrompt: null,
  lastResponse: null,
  lastError: null,
  lastChangedFiles: [],
  lastUsage: null,
  lastDurationMs: null,
  lastCompletedAt: null,
  lastStartedAt: null,
  currentPrompt: null,
  queue: [],
};

export class StateStore {
  constructor(filePath) {
    this.filePath = filePath;
    this.state = { ...DEFAULT_STATE };
  }

  async load() {
    await fs.mkdir(path.dirname(this.filePath), { recursive: true });

    try {
      const raw = await fs.readFile(this.filePath, "utf8");
      this.state = { ...DEFAULT_STATE, ...JSON.parse(raw) };
    } catch (error) {
      if (error.code !== "ENOENT") {
        throw error;
      }
      await this.save();
    }

    return this.state;
  }

  get() {
    return this.state;
  }

  async patch(patch) {
    this.state = { ...this.state, ...patch };
    await this.save();
    return this.state;
  }

  async save() {
    await fs.writeFile(this.filePath, JSON.stringify(this.state, null, 2), "utf8");
  }
}
