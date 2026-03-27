import TelegramBot from "node-telegram-bot-api";
import { loadConfig } from "./config.mjs";

const config = loadConfig();

if (!config.botToken) {
  console.error("Missing TELEGRAM_BOT_TOKEN");
  process.exit(1);
}

const bot = new TelegramBot(config.botToken, { polling: false });
const updates = await bot.getUpdates({ limit: 10, timeout: 0 });

if (updates.length === 0) {
  console.log("No recent bot updates were found.");
  process.exit(0);
}

for (const update of updates) {
  const message = update.message;
  if (!message) {
    continue;
  }

  console.log(JSON.stringify({
    updateId: update.update_id,
    fromId: message.from?.id ?? null,
    username: message.from?.username ?? null,
    chatId: message.chat?.id ?? null,
    text: message.text ?? null,
  }, null, 2));
}
