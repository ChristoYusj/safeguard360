import { Codex } from "@openai/codex-sdk";
import { discoverLatestMatchingThread, findThreadById, listMatchingThreads } from "./session-discovery.mjs";

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
    this.onRunStarted = null;
    this.onRunEvent = null;
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
    const state = this.stateStore.get();
    const workingDirectory = state.activeProjectPath || this.config.workingDirectory;

    return {
      model: this.config.codex.model,
      approvalPolicy: this.config.codex.approvalPolicy,
      sandboxMode: this.config.codex.sandboxMode,
      workingDirectory,
      modelReasoningEffort: this.config.codex.modelReasoningEffort,
      networkAccessEnabled: this.config.codex.networkAccessEnabled,
      webSearchMode: this.config.codex.webSearchMode,
      additionalDirectories: this.config.codex.additionalDirectories,
    };
  }

  buildThreadOptions(workingDirectoryOverride = null) {
    const base = this.threadOptions();
    if (workingDirectoryOverride) {
      return {
        ...base,
        workingDirectory: workingDirectoryOverride,
      };
    }
    return base;
  }

  async attachExplicit(threadId) {
    if (this.busy) {
      throw new Error("Cannot attach a different thread while a Codex turn is active");
    }

    const metadata = await findThreadById({
      sessionRoot: this.config.sessionDiscoveryRoot,
      threadId,
    });

    this.thread = this.codex.resumeThread(
      threadId,
      this.buildThreadOptions(metadata?.cwd || null),
    );
    await this.stateStore.patch({
      attachedThreadId: threadId,
      attachedFrom: "explicit",
      attachedSessionFile: metadata?.sessionFile || null,
      attachedCwd: metadata?.cwd || null,
    });
    await this.logger.info("Attached to explicit thread", { threadId });
    return { threadId, source: "explicit", session: metadata };
  }

  async attachLatest() {
    if (this.busy) {
      throw new Error("Cannot attach a different thread while a Codex turn is active");
    }

    const state = this.stateStore.get();
    const projectRoot = state.activeProjectPath || this.config.workingDirectory;
    const hints = state.activeProjectPath ? [] : this.config.discoveryHints;
    const latest = await discoverLatestMatchingThread({
      sessionRoot: this.config.sessionDiscoveryRoot,
      projectRoot,
      hints,
    });

    if (!latest?.threadId) {
      throw new Error("No matching Codex session was found for this project");
    }

    this.thread = this.codex.resumeThread(
      latest.threadId,
      this.buildThreadOptions(latest.cwd),
    );
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

  async listSessions(limit = 8) {
    const state = this.stateStore.get();
    const projectRoot = state.activeProjectPath || this.config.workingDirectory;
    const hints = state.activeProjectPath ? [] : this.config.discoveryHints;
    return listMatchingThreads({
      sessionRoot: this.config.sessionDiscoveryRoot,
      projectRoot,
      hints,
      limit,
    });
  }

  async attachReference(reference) {
    const trimmed = `${reference || ""}`.trim();
    if (!trimmed) {
      return this.attachLatest();
    }

    if (/^\d+$/.test(trimmed)) {
      const sessions = await this.listSessions(8);
      const index = Number.parseInt(trimmed, 10) - 1;
      if (index < 0 || index >= sessions.length) {
        throw new Error(`No session found at index ${trimmed}`);
      }
      return this.attachExplicit(sessions[index].threadId);
    }

    return this.attachExplicit(trimmed);
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
      const startedAt = Date.now();
      const progress = {
        status: "starting",
        lastCommand: null,
        commandStatus: null,
        changedFiles: [],
        todoItems: [],
        lastReasoning: null,
        lastTool: null,
      };

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

      if (typeof this.onRunStarted === "function") {
        await this.onRunStarted({
          chatId: next.chatId,
          prompt: next.prompt,
          threadId: thread.id || this.stateStore.get().attachedThreadId,
          activeProjectName: this.stateStore.get().activeProjectName,
          workingDirectory: this.stateStore.get().activeProjectPath || this.config.workingDirectory,
        });
      }

      const { events } = await thread.runStreamed(next.prompt, { signal: this.abortController.signal });
      const items = [];
      let finalResponse = "";
      let usage = null;
      let turnFailure = null;

      for await (const event of events) {
        if (event.type === "item.started" || event.type === "item.updated" || event.type === "item.completed") {
          const item = event.item;

          if (item.type === "command_execution") {
            progress.lastCommand = item.command;
            progress.commandStatus = item.status;
          } else if (item.type === "file_change") {
            progress.changedFiles = item.changes.map((change) => change.path);
          } else if (item.type === "todo_list") {
            progress.todoItems = item.items;
          } else if (item.type === "reasoning") {
            progress.lastReasoning = item.text;
          } else if (item.type === "mcp_tool_call") {
            progress.lastTool = `${item.server}:${item.tool}`;
          }
        }

        if (event.type === "item.completed") {
          if (event.item.type === "agent_message") {
            finalResponse = event.item.text;
          }
          items.push(event.item);
        } else if (event.type === "turn.completed") {
          usage = event.usage;
        } else if (event.type === "turn.failed") {
          turnFailure = event.error;
          break;
        }

        if ((event.type === "item.started" || event.type === "item.updated" || event.type === "item.completed") && typeof this.onRunEvent === "function") {
          await this.onRunEvent({
            chatId: next.chatId,
            threadId: thread.id || this.stateStore.get().attachedThreadId,
            prompt: next.prompt,
            status: progress.commandStatus || progress.status,
            workingDirectory: this.stateStore.get().activeProjectPath || this.config.workingDirectory,
            activeProjectName: this.stateStore.get().activeProjectName,
            lastCommand: progress.lastCommand,
            changedFiles: progress.changedFiles,
            todoItems: progress.todoItems,
            lastReasoning: progress.lastReasoning,
            lastTool: progress.lastTool,
            elapsedMs: Date.now() - startedAt,
          });
        }
      }

      if (turnFailure) {
        throw new Error(turnFailure.message);
      }

      const threadId = thread.id || this.stateStore.get().attachedThreadId;

      await this.stateStore.patch({
        attachedThreadId: threadId,
        lastResponse: finalResponse,
        lastChangedFiles: progress.changedFiles,
        lastUsage: usage,
        lastDurationMs: Date.now() - startedAt,
        lastCompletedAt: new Date().toISOString(),
        currentPrompt: null,
      });

      await this.logger.info("Completed Codex turn", {
        threadId,
        usage,
      });

      if (typeof this.onRunFinished === "function") {
        await this.onRunFinished({
          ok: true,
          threadId,
          response: finalResponse,
          prompt: next.prompt,
          usage,
          changedFiles: progress.changedFiles,
          durationMs: Date.now() - startedAt,
          activeProjectName: this.stateStore.get().activeProjectName,
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
      activeProjectName: state.activeProjectName,
      activeProjectPath: state.activeProjectPath,
      currentPrompt: state.currentPrompt,
      queueLength: this.queue.length,
      lastCompletedAt: state.lastCompletedAt,
      lastError: state.lastError,
      lastChangedFiles: state.lastChangedFiles,
      workingDirectory: this.config.workingDirectory,
      sessionFile: state.attachedSessionFile,
      attachedCwd: state.attachedCwd,
    };
  }
}
