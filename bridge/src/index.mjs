import process from "node:process";
import TelegramBot from "node-telegram-bot-api";
import { loadConfig, validateConfig } from "./config.mjs";
import { Logger } from "./logger.mjs";
import { StateStore } from "./state-store.mjs";
import { CodexController } from "./codex-controller.mjs";
import { sendLongMessage } from "./telegram-utils.mjs";

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

controller.onRunFinished = async (result) => {
  if (!result.chatId) {
    return;
  }

  if (result.ok) {
    await sendLongMessage(
      bot,
      result.chatId,
      `Codex finished.\n\nThread: ${result.threadId}\n\n${result.response}`,
    );
    return;
  }

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
    `Project: ${status.workingDirectory}`,
    `Current prompt: ${status.currentPrompt || "(none)"}`,
    `Queued prompts: ${status.queueLength}`,
    `Last completed: ${status.lastCompletedAt || "(never)"}`,
    `Last error: ${status.lastError || "(none)"}`,
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
        const result = arg ? await controller.attachExplicit(arg) : await controller.attachLatest();
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
            ? `Last response from thread ${state.attachedThreadId || "(unknown)"}:\n\n${state.lastResponse}`
            : "No completed Codex response is stored yet.",
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
            "/attach <thread-id>",
            "/codex <prompt>",
            "/status",
            "/last",
            "/stop",
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
