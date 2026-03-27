import process from "node:process";
import TelegramBot from "node-telegram-bot-api";
import { loadConfig, validateConfig } from "./config.mjs";
import { Logger } from "./logger.mjs";
import { StateStore } from "./state-store.mjs";
import { CodexController } from "./codex-controller.mjs";
import { sendLongMessage, truncateForTelegramStatus } from "./telegram-utils.mjs";
import { listWorkspaceProjects, resolveWorkspaceProject } from "./workspace-projects.mjs";

const config = loadConfig();
const problems = validateConfig(config);

if (problems.length > 0) {
  console.error("Bridge configuration is incomplete:");
  for (const problem of problems) {
    console.error(`- ${problem}`);
  }
  process.exit(1);
}

const logger = new Logger(config.logFile);
await logger.ensureReady();

const stateStore = new StateStore(config.stateFile);
await stateStore.load();

const controller = new CodexController(config, logger, stateStore);
await controller.hydrate();

const bot = new TelegramBot(config.botToken, { polling: true });
const progressMessages = new Map();

function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function formatSessionLine(session, index) {
  const namePart = session.threadName ? ` - ${session.threadName}` : "";
  return `${index + 1}. ${session.threadId}${namePart}\n   cwd: ${session.cwd}\n   updated: ${session.updatedAt}`;
}

function formatProjectLine(project, activeProjectName, index) {
  const marker = project.name === activeProjectName ? " [active]" : "";
  return `${index + 1}. ${project.name}${marker}\n   ${project.path}`;
}

function formatProgress(snapshot) {
  const todoSummary = snapshot.todoItems?.length
    ? `${snapshot.todoItems.filter((item) => item.completed).length}/${snapshot.todoItems.length}`
    : "none";
  const changedSummary = snapshot.changedFiles?.length
    ? snapshot.changedFiles.slice(0, 5).join(", ")
    : "(none yet)";
  const lastReasoning = snapshot.lastReasoning
    ? truncateForTelegramStatus(snapshot.lastReasoning.replace(/\s+/g, " "), 180)
    : "(none yet)";

  return truncateForTelegramStatus(
    [
      "Codex is working...",
      `Thread: ${snapshot.threadId || "(starting)"}`,
      `Workspace: ${snapshot.workingDirectory}`,
      `Active project: ${snapshot.activeProjectName || "(workspace root)"}`,
      `Elapsed: ${formatElapsed(snapshot.elapsedMs || 0)}`,
      `Command: ${snapshot.lastCommand || "(none yet)"}`,
      `Tool: ${snapshot.lastTool || "(none yet)"}`,
      `Todo progress: ${todoSummary}`,
      `Files touched: ${changedSummary}`,
      `Latest reasoning: ${lastReasoning}`,
    ].join("\n"),
  );
}

function formatFinished(result) {
  const changedSummary = result.changedFiles?.length
    ? result.changedFiles.join(", ")
    : "(none)";
  const usageSummary = result.usage
    ? `Usage: in ${result.usage.input_tokens}, out ${result.usage.output_tokens}`
    : "Usage: unavailable";

  return [
    "Codex finished.",
    "",
    `Thread: ${result.threadId}`,
    `Active project: ${result.activeProjectName || "(workspace root)"}`,
    `Duration: ${formatElapsed(result.durationMs || 0)}`,
    usageSummary,
    `Files changed: ${changedSummary}`,
    "",
    result.response || "(empty response)",
  ].join("\n");
}

async function startProgressMessage(chatId, payload) {
  const sent = await bot.sendMessage(
    chatId,
    [
      "Prompt accepted. Codex is working.",
      `Thread: ${payload.threadId || "(starting)"}`,
      `Workspace: ${payload.workingDirectory}`,
      `Active project: ${payload.activeProjectName || "(workspace root)"}`,
      `Prompt: ${payload.prompt}`,
    ].join("\n"),
  );

  progressMessages.set(chatId, {
    messageId: sent.message_id,
    lastRenderedAt: 0,
  });
}

async function updateProgressMessage(chatId, text) {
  const entry = progressMessages.get(chatId);
  if (!entry) {
    return;
  }

  const now = Date.now();
  if (now - entry.lastRenderedAt < 1500) {
    return;
  }

  entry.lastRenderedAt = now;

  try {
    await bot.editMessageText(text, {
      chat_id: chatId,
      message_id: entry.messageId,
    });
  } catch {
    // Ignore edit races and continue.
  }
}

async function finalizeProgressMessage(chatId, text) {
  const entry = progressMessages.get(chatId);
  if (!entry) {
    return;
  }

  try {
    await bot.editMessageText(text, {
      chat_id: chatId,
      message_id: entry.messageId,
    });
  } catch {
    // Ignore edit races and continue.
  }
}

function clearProgressMessage(chatId) {
  progressMessages.delete(chatId);
}

controller.onRunStarted = async (payload) => {
  if (payload.chatId) {
    await startProgressMessage(payload.chatId, payload);
  }
};

controller.onRunEvent = async (snapshot) => {
  if (!snapshot.chatId) {
    return;
  }
  await updateProgressMessage(snapshot.chatId, formatProgress(snapshot));
};

controller.onRunFinished = async (result) => {
  if (!result.chatId) {
    return;
  }

  if (result.ok) {
    await finalizeProgressMessage(
      result.chatId,
      `Codex finished.\nThread: ${result.threadId}\nDuration: ${formatElapsed(result.durationMs || 0)}`,
    );
    clearProgressMessage(result.chatId);
    await sendLongMessage(bot, result.chatId, formatFinished(result));
    return;
  }

  await finalizeProgressMessage(
    result.chatId,
    `Codex failed.\nPrompt: ${result.prompt}\nError: ${result.error}`,
  );
  clearProgressMessage(result.chatId);
  await sendLongMessage(
    bot,
    result.chatId,
    `Codex failed.\n\nPrompt: ${result.prompt}\n\nError: ${result.error}`,
  );
};

function isAuthorized(message) {
  return `${message.from?.id || ""}` === `${config.allowedUserId}`;
}

async function handleUnauthorized(message) {
  await logger.warn("Rejected unauthorized Telegram user", {
    userId: message.from?.id ?? null,
    username: message.from?.username ?? null,
    chatId: message.chat?.id ?? null,
  });
  await bot.sendMessage(message.chat.id, "Unauthorized.");
}

function parseCommand(messageText) {
  const text = (messageText || "").trim();
  const firstSpace = text.indexOf(" ");
  if (firstSpace < 0) {
    return { command: text, arg: "" };
  }
  return {
    command: text.slice(0, firstSpace),
    arg: text.slice(firstSpace + 1).trim(),
  };
}

function formatStatus(status) {
  return [
    `Bridge: ${status.busy ? "busy" : "idle"}`,
    `Thread: ${status.threadId || "(none attached)"}`,
    `Attached via: ${status.attachedFrom || "(none)"}`,
    `Active project: ${status.activeProjectName || "(workspace root)"}`,
    `Active project path: ${status.activeProjectPath || "(none pinned)"}`,
    `Project: ${status.workingDirectory}`,
    `Current prompt: ${status.currentPrompt || "(none)"}`,
    `Queued prompts: ${status.queueLength}`,
    `Last completed: ${status.lastCompletedAt || "(never)"}`,
    `Last error: ${status.lastError || "(none)"}`,
    `Last changed files: ${status.lastChangedFiles?.length ? status.lastChangedFiles.join(", ") : "(none)"}`,
    `Attached session cwd: ${status.attachedCwd || "(unknown)"}`,
  ].join("\n");
}

await logger.info("Telegram Codex bridge started", {
  workingDirectory: config.workingDirectory,
  stateFile: config.stateFile,
});

bot.on("message", async (message) => {
  if (!message.text?.startsWith("/")) {
    return;
  }

  if (!isAuthorized(message)) {
    await handleUnauthorized(message);
    return;
  }

  const { command, arg } = parseCommand(message.text);

  try {
    switch (command) {
      case "/attach": {
        const result = arg ? await controller.attachReference(arg) : await controller.attachLatest();
        await bot.sendMessage(
          message.chat.id,
          `Attached to thread ${result.threadId} via ${result.source}.`,
        );
        break;
      }
      case "/codex": {
        if (!arg) {
          await bot.sendMessage(message.chat.id, "Usage: /codex <prompt>");
          break;
        }

        const result = await controller.enqueue(arg, { chatId: message.chat.id });
        if (result.status === "queued") {
          await bot.sendMessage(
            message.chat.id,
            `Prompt queued. ${result.queueLength} prompt(s) waiting.`,
          );
        } else {
          await bot.sendMessage(message.chat.id, "Prompt accepted. Codex is working.");
        }
        break;
      }
      case "/status": {
        await sendLongMessage(bot, message.chat.id, formatStatus(controller.getStatus()));
        break;
      }
      case "/last": {
        const state = stateStore.get();
        await sendLongMessage(
          bot,
          message.chat.id,
          state.lastResponse
            ? [
                `Last response from thread ${state.attachedThreadId || "(unknown)"}:`,
                `Active project: ${state.activeProjectName || "(workspace root)"}`,
                `Files changed: ${state.lastChangedFiles?.length ? state.lastChangedFiles.join(", ") : "(none)"}`,
                "",
                state.lastResponse,
              ].join("\n")
            : "No completed Codex response is stored yet.",
        );
        break;
      }
      case "/sessions": {
        const sessions = await controller.listSessions(8);
        await sendLongMessage(
          bot,
          message.chat.id,
          sessions.length
            ? ["Recent sessions:", ...sessions.map((session, index) => formatSessionLine(session, index))].join("\n\n")
            : "No matching sessions were found for the current workspace/project scope.",
        );
        break;
      }
      case "/projects": {
        const projects = await listWorkspaceProjects(config.workingDirectory);
        const state = stateStore.get();
        await sendLongMessage(
          bot,
          message.chat.id,
          projects.length
            ? ["Workspace projects:", ...projects.map((project, index) => formatProjectLine(project, state.activeProjectName, index))].join("\n\n")
            : "No workspace projects were found.",
        );
        break;
      }
      case "/project": {
        if (controller.getStatus().busy) {
          await bot.sendMessage(message.chat.id, "Cannot change the active project while Codex is running. Use /stop first if needed.");
          break;
        }

        if (!arg) {
          const state = stateStore.get();
          await bot.sendMessage(
            message.chat.id,
            `Active project: ${state.activeProjectName || "(workspace root)"}`,
          );
          break;
        }

        if (["off", "clear", "workspace", "root"].includes(arg.toLowerCase())) {
          await stateStore.patch({
            activeProjectName: null,
            activeProjectPath: null,
          });
          await bot.sendMessage(message.chat.id, "Active project cleared. The bridge is back to workspace-root mode.");
          break;
        }

        const project = await resolveWorkspaceProject(config.workingDirectory, arg);
        if (!project) {
          await bot.sendMessage(message.chat.id, `Project not found: ${arg}`);
          break;
        }

        await stateStore.patch({
          activeProjectName: project.name,
          activeProjectPath: project.path,
          attachedThreadId: null,
          attachedFrom: null,
          attachedSessionFile: null,
          attachedCwd: null,
        });
        controller.thread = null;
        await bot.sendMessage(
          message.chat.id,
          `Active project set to ${project.name}. Use /attach to attach the latest matching session for it.`,
        );
        break;
      }
      case "/stop": {
        const result = await controller.stopCurrentTurn();
        await bot.sendMessage(
          message.chat.id,
          result.stopped
            ? `Active turn aborted. Cleared ${result.clearedQueue} queued prompt(s).`
            : `No active turn. Cleared ${result.clearedQueue} queued prompt(s).`,
        );
        break;
      }
      case "/help":
      case "/start": {
        await sendLongMessage(
          bot,
          message.chat.id,
          [
            "Available commands:",
            "/attach",
            "/attach <thread-id|session-number>",
            "/codex <prompt>",
            "/status",
            "/last",
            "/stop",
            "/sessions",
            "/projects",
            "/project <name>",
            "/project off",
          ].join("\n"),
        );
        break;
      }
      default: {
        await bot.sendMessage(message.chat.id, "Unknown command. Use /help.");
      }
    }
  } catch (error) {
    const messageText = error.message || String(error);
    await logger.error("Telegram command failed", { command, error: messageText });
    await bot.sendMessage(message.chat.id, `Command failed: ${messageText}`);
  }
});

process.on("SIGINT", async () => {
  await logger.warn("Received SIGINT, shutting down bridge");
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await logger.warn("Received SIGTERM, shutting down bridge");
  process.exit(0);
});
