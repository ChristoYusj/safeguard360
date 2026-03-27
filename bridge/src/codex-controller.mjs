import { Codex } from "@openai/codex-sdk";
import path from "node:path";
import { discoverLatestMatchingThread } from "./session-discovery.mjs";

function summarizeError(error) {
  if (!error) {
    return "Unknown error";
  }

  if (error.name === "AbortError") {
    return "Turn aborted";
  }

  return error.message || String(error);
}

export class CodexController {
  constructor(config, logger, stateStore) {
    this.config = config;
    this.logger = logger;
    this.stateStore = stateStore;
    this.codex = new Codex({
      codexPathOverride: path.join(this.config.bridgeRoot, "node_modules", ".bin", "codex.cmd"),
      env: process.env,
      config: {
        approval_policy: this.config.codex.approvalPolicy,
        sandbox_mode: this.config.codex.sandboxMode,
        sandbox_workspace_write: {
          network_access: this.config.codex.networkAccessEnabled,
        },
        windows: {
          sandbox: "elevated",
        },
      },
    });
    this.thread = null;
    this.busy = false;
    this.abortController = null;
    this.queue = [];
    this.onRunFinished = null;
  }

  async hydrate() {
    const state = this.stateStore.get();
    this.queue = Array.isArray(state.queue) ? [...state.queue] : [];

    if (state.attachedThreadId) {
      this.thread = this.codex.resumeThread(state.attachedThreadId, this.threadOptions());
      await this.logger.info("Resumed saved thread", { threadId: state.attachedThreadId });
    }
  }

  threadOptions() {
    return {
      model: this.config.codex.model,
      approvalPolicy: this.config.codex.approvalPolicy,
      sandboxMode: this.config.codex.sandboxMode,
      workingDirectory: this.config.workingDirectory,
      modelReasoningEffort: this.config.codex.modelReasoningEffort,
      networkAccessEnabled: this.config.codex.networkAccessEnabled,
      webSearchMode: this.config.codex.webSearchMode,
      additionalDirectories: this.config.codex.additionalDirectories,
    };
  }

  async attachExplicit(threadId) {
    if (this.busy) {
      throw new Error("Cannot attach a different thread while a Codex turn is active");
    }

    this.thread = this.codex.resumeThread(threadId, this.threadOptions());
    await this.stateStore.patch({
      attachedThreadId: threadId,
      attachedFrom: "explicit",
      attachedSessionFile: null,
      attachedCwd: null,
    });
    await this.logger.info("Attached to explicit thread", { threadId });
    return { threadId, source: "explicit" };
  }

  async attachLatest() {
    if (this.busy) {
      throw new Error("Cannot attach a different thread while a Codex turn is active");
    }

    const latest = await discoverLatestMatchingThread({
      sessionRoot: this.config.sessionDiscoveryRoot,
      projectRoot: this.config.workingDirectory,
      hints: this.config.discoveryHints,
    });

    if (!latest?.threadId) {
      throw new Error("No matching Codex session was found for this project");
    }

    this.thread = this.codex.resumeThread(latest.threadId, this.threadOptions());
    await this.stateStore.patch({
      attachedThreadId: latest.threadId,
      attachedFrom: "latest-session-scan",
      attachedSessionFile: latest.sessionFile,
      attachedCwd: latest.cwd,
    });
    await this.logger.info("Attached to latest matching thread", latest);
    return { threadId: latest.threadId, source: "latest-session-scan", session: latest };
  }

  async ensureThread() {
    if (this.thread) {
      return this.thread;
    }

    try {
      await this.attachLatest();
      return this.thread;
    } catch {
      this.thread = this.codex.startThread(this.threadOptions());
      await this.logger.info("Started a new Codex thread");
      return this.thread;
    }
  }

  async enqueue(prompt, meta = {}) {
    const entry = {
      prompt,
      requestedAt: new Date().toISOString(),
      chatId: meta.chatId ?? null,
    };

    if (this.busy) {
      this.queue.push(entry);
      await this.stateStore.patch({ queue: this.queue });
      await this.logger.info("Queued prompt", { queueLength: this.queue.length });
      return { status: "queued", queueLength: this.queue.length };
    }

    this.queue.push(entry);
    await this.stateStore.patch({ queue: this.queue });
    void this.processQueue();
    return { status: "started", queueLength: this.queue.length };
  }

  async processQueue() {
    if (this.busy) {
      return;
    }

    const next = this.queue.shift();
    await this.stateStore.patch({ queue: this.queue });

    if (!next) {
      return;
    }

    this.busy = true;
    this.abortController = new AbortController();

    try {
      const thread = await this.ensureThread();
      await this.stateStore.patch({
        currentPrompt: next.prompt,
        lastPrompt: next.prompt,
        lastError: null,
        lastStartedAt: new Date().toISOString(),
      });

      await this.logger.info("Starting Codex turn", {
        threadId: this.stateStore.get().attachedThreadId,
        prompt: next.prompt,
      });

      const turn = await thread.run(next.prompt, { signal: this.abortController.signal });
      const threadId = thread.id || this.stateStore.get().attachedThreadId;

      await this.stateStore.patch({
        attachedThreadId: threadId,
        lastResponse: turn.finalResponse,
        lastCompletedAt: new Date().toISOString(),
        currentPrompt: null,
      });

      await this.logger.info("Completed Codex turn", {
        threadId,
        usage: turn.usage,
      });

      if (typeof this.onRunFinished === "function") {
        await this.onRunFinished({
          ok: true,
          threadId,
          response: turn.finalResponse,
          prompt: next.prompt,
          usage: turn.usage,
          chatId: next.chatId,
        });
      }
    } catch (error) {
      const message = summarizeError(error);
      await this.stateStore.patch({
        lastError: message,
        lastCompletedAt: new Date().toISOString(),
        currentPrompt: null,
      });
      await this.logger.error("Codex turn failed", { error: message });

      if (typeof this.onRunFinished === "function") {
        await this.onRunFinished({
          ok: false,
          error: message,
          prompt: next.prompt,
          chatId: next.chatId,
        });
      }
    } finally {
      this.busy = false;
      this.abortController = null;
      if (this.queue.length > 0) {
        void this.processQueue();
      }
    }
  }

  async stopCurrentTurn() {
    const queued = this.queue.length;
    this.queue = [];
    await this.stateStore.patch({ queue: [] });

    if (!this.abortController) {
      return { stopped: false, clearedQueue: queued };
    }

    this.abortController.abort();
    await this.logger.warn("Abort requested for active turn");
    return { stopped: true, clearedQueue: queued };
  }

  getStatus() {
    const state = this.stateStore.get();
    return {
      busy: this.busy,
      threadId: state.attachedThreadId,
      attachedFrom: state.attachedFrom,
      currentPrompt: state.currentPrompt,
      queueLength: this.queue.length,
      lastCompletedAt: state.lastCompletedAt,
      lastError: state.lastError,
      workingDirectory: this.config.workingDirectory,
      sessionFile: state.attachedSessionFile,
      attachedCwd: state.attachedCwd,
    };
  }
}
