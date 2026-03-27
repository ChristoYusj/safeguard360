import fs from "node:fs/promises";
import path from "node:path";

function timestamp() {
  return new Date().toISOString();
}

export class Logger {
  constructor(logFile) {
    this.logFile = logFile;
  }

  async ensureReady() {
    await fs.mkdir(path.dirname(this.logFile), { recursive: true });
  }

  async write(level, message, extra = null) {
    const line = `[${timestamp()}] [${level}] ${message}${extra ? ` ${JSON.stringify(extra)}` : ""}`;
    console.log(line);
    await fs.appendFile(this.logFile, `${line}\n`, "utf8");
  }

  info(message, extra = null) {
    return this.write("INFO", message, extra);
  }

  warn(message, extra = null) {
    return this.write("WARN", message, extra);
  }

  error(message, extra = null) {
    return this.write("ERROR", message, extra);
  }
}
