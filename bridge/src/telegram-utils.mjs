const TELEGRAM_LIMIT = 3500;

export function splitTelegramMessage(input) {
  const text = `${input || ""}`.trim();
  if (!text) {
    return ["(empty response)"];
  }

  const chunks = [];
  let remaining = text;

  while (remaining.length > TELEGRAM_LIMIT) {
    let sliceIndex = remaining.lastIndexOf("\n", TELEGRAM_LIMIT);
    if (sliceIndex < 0 || sliceIndex < TELEGRAM_LIMIT / 2) {
      sliceIndex = TELEGRAM_LIMIT;
    }

    chunks.push(remaining.slice(0, sliceIndex).trim());
    remaining = remaining.slice(sliceIndex).trim();
  }

  if (remaining) {
    chunks.push(remaining);
  }

  return chunks;
}

export async function sendLongMessage(bot, chatId, text) {
  const chunks = splitTelegramMessage(text);
  for (const chunk of chunks) {
    await bot.sendMessage(chatId, chunk);
  }
}

export function truncateForTelegramStatus(input, limit = 3500) {
  const text = `${input || ""}`.trim();
  if (text.length <= limit) {
    return text;
  }

  return `${text.slice(0, limit - 3).trimEnd()}...`;
}
