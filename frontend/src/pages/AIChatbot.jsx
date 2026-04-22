/*
 * SafeGuard 360 - AI Safety Chatbot
 * "Precision Command" Design System
 *
 * Operator-facing chat interface backed by /api/chatbot/*. The assistant
 * is fed a live site snapshot every turn, so it can answer "who's on
 * site right now?", "any violations today?", etc.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";

import {
  getChatbotContext,
  getChatbotStatus,
  sendChatbotMessage,
} from "../services/api";
import {
  AlertTriangleIcon,
  ChatbotIcon,
  RefreshIcon,
  ShieldIcon,
} from "../components/icons";

const SUGGESTED_PROMPTS = [
  "Who's on site right now?",
  "Any PPE violations today?",
  "Show the last 5 driver events.",
  "Walk me through the gate review workflow.",
];

const WELCOME_MESSAGE = {
  role: "assistant",
  content:
    "Hi — I'm the SafeGuard 360 Safety Assistant. Ask me who's on site, recent violations, driver events, or any industrial safety question.",
};

const SNAPSHOT_REFRESH_MS = 10000;

function formatTimestamp(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function MessageBubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className="max-w-[85%] rounded-2xl px-4 py-3 shadow-sm"
        style={
          isUser
            ? {
                // Use the existing theme's primary accent (cyan) and force
                // white text via inline style — the previous
                // `bg-[var(--color-accent)]` referenced an undefined CSS
                // variable, so user messages were rendering on a transparent
                // background with invisible white text.
                backgroundColor: "var(--color-accent-primary, #0891b2)",
                color: "#ffffff",
                border: "1px solid var(--color-accent-primary, #0891b2)",
              }
            : undefined
        }
      >
        <p
          className={`whitespace-pre-wrap text-[15px] leading-7 ${
            isUser ? "font-medium" : "text-primary"
          }`}
          style={isUser ? { color: "#ffffff" } : undefined}
        >
          {content}
        </p>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="inline-flex items-center gap-2 rounded-2xl border border-default bg-[var(--color-bg-surface)] px-4 py-3 shadow-sm">
        <span
          className="h-2 w-2 animate-bounce rounded-full"
          style={{ animationDelay: "0ms", backgroundColor: "var(--color-accent-primary)" }}
        />
        <span
          className="h-2 w-2 animate-bounce rounded-full"
          style={{ animationDelay: "150ms", backgroundColor: "var(--color-accent-primary)" }}
        />
        <span
          className="h-2 w-2 animate-bounce rounded-full"
          style={{ animationDelay: "300ms", backgroundColor: "var(--color-accent-primary)" }}
        />
      </div>
    </div>
  );
}

function AIChatbot() {
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState(null);
  const [context, setContext] = useState(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Poll /status on mount so the UI knows if Groq is configured.
  useEffect(() => {
    let cancelled = false;
    getChatbotStatus()
      .then((payload) => {
        if (!cancelled) setStatus(payload);
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("[Chatbot] status failed", err);
          setStatus({ configured: false, missing_key_hint: err.message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Pull live site context for the sidebar preview card.
  const refreshContext = useCallback(() => {
    getChatbotContext()
      .then(setContext)
      .catch((err) => console.error("[Chatbot] context failed", err));
  }, []);

  useEffect(() => {
    refreshContext();
    const timer = window.setInterval(refreshContext, SNAPSHOT_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refreshContext]);

  // Auto-scroll to latest message.
  useEffect(() => {
    const node = scrollRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages, isSending]);

  const isReady = status?.configured;

  const handleSend = useCallback(
    async (textOverride) => {
      const text = (textOverride ?? input).trim();
      if (!text || isSending) return;
      if (!isReady) {
        setError(
          status?.missing_key_hint ||
            "Groq is not configured in backend/.env.",
        );
        return;
      }

      setError("");
      const userMessage = { role: "user", content: text };
      const nextMessages = [...messages, userMessage];
      setMessages(nextMessages);
      setInput("");
      setIsSending(true);

      try {
        // Exclude the welcome message from the payload — it's UI-only.
        const payload = nextMessages.filter(
          (m, idx) => !(idx === 0 && m === WELCOME_MESSAGE),
        );
        const result = await sendChatbotMessage(payload);
        setMessages((current) => [
          ...current,
          { role: "assistant", content: result.reply },
        ]);
      } catch (err) {
        console.error("[Chatbot] send failed", err);
        setError(err.message || "Could not reach the assistant.");
      } finally {
        setIsSending(false);
        refreshContext();
        // Re-focus the input for rapid follow-up.
        window.setTimeout(() => inputRef.current?.focus(), 50);
      }
    },
    [input, isSending, isReady, messages, refreshContext, status?.missing_key_hint],
  );

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleReset = () => {
    setMessages([WELCOME_MESSAGE]);
    setError("");
    setInput("");
    inputRef.current?.focus();
  };

  const contextStats = useMemo(() => {
    if (!context) return [];
    return [
      { label: "On site", value: context.on_site_count ?? 0 },
      { label: "Check-ins today", value: context.check_ins_today ?? 0 },
      { label: "PPE violations", value: context.ppe_violations_today ?? 0 },
      { label: "Driver events", value: context.driver_events_today ?? 0 },
    ];
  }, [context]);

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">live site assistant</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          AI Safety Assistant
        </h1>
        <p className="mt-3 max-w-3xl text-sm text-secondary">
          Ask about current site state, recent incidents, or general
          industrial safety guidance. The assistant is scoped to SafeGuard 360
          data and reads a fresh site snapshot on every turn.
        </p>
      </motion.header>

      {status && !status.configured ? (
        <div
          className="mb-6 flex items-start gap-3 rounded-xl border px-4 py-3"
          style={{
            borderColor: "var(--color-warning)",
            background: "var(--color-warning-muted, rgba(245, 158, 11, 0.08))",
          }}
        >
          <AlertTriangleIcon
            size={20}
            style={{ color: "var(--color-warning)" }}
          />
          <div>
            <p
              className="text-sm font-semibold"
              style={{ color: "var(--color-warning)" }}
            >
              Assistant not configured
            </p>
            <p className="mt-1 text-sm text-secondary">
              {status.missing_key_hint ||
                "Set GROQ_API_KEY in backend/.env to enable chat."}
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
        <section className="panel flex flex-col" style={{ minHeight: "70vh" }}>
          <div className="panel__header">
            <div className="flex items-center gap-3">
              <ChatbotIcon size={20} className="text-accent" />
              <div>
                <h2 className="font-display text-xl font-semibold text-primary">
                  Conversation
                </h2>
                <p className="mt-1 text-sm text-secondary">
                  {isReady
                    ? `Powered by ${status?.model || "Groq"} · live site context injected each turn`
                    : "Waiting for Groq credentials"}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleReset}
              className="btn btn-secondary h-9 px-3 text-xs"
              disabled={isSending}
              title="Clear conversation"
            >
              <RefreshIcon size={14} />
              <span className="ml-2">Reset</span>
            </button>
          </div>

          <div
            ref={scrollRef}
            className="panel__content flex-1 space-y-3 overflow-y-auto"
            style={{ maxHeight: "55vh" }}
          >
            {messages.map((m, idx) => (
              <MessageBubble key={`${idx}-${m.role}`} {...m} />
            ))}
            {isSending ? <TypingIndicator /> : null}
          </div>

          {error ? (
            <div
              className="mx-4 mb-3 rounded-lg border px-3 py-2 text-xs"
              style={{
                borderColor: "var(--color-error)",
                background: "var(--color-error-muted)",
                color: "var(--color-error)",
              }}
            >
              {error}
            </div>
          ) : null}

          {messages.length <= 1 && isReady ? (
            <div className="flex flex-wrap gap-2 px-4 pb-3">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleSend(prompt)}
                  disabled={isSending}
                  className="rounded-full border border-default bg-[var(--color-bg-surface)] px-3 py-1.5 text-xs text-secondary transition hover:border-[var(--color-accent-primary)] hover:text-primary"
                >
                  {prompt}
                </button>
              ))}
            </div>
          ) : null}

          <div className="border-t border-default px-4 pb-4 pt-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isReady
                    ? "Ask about the site, recent events, or safety procedures…"
                    : "Configure GROQ_API_KEY to enable chat"
                }
                disabled={!isReady || isSending}
                rows={2}
                className="min-h-[88px] flex-1 resize-none rounded-xl border border-default bg-[var(--color-bg-surface)] px-4 py-3 text-[15px] font-medium leading-6 text-primary outline-none transition focus:border-[var(--color-accent-primary)] focus:ring-1 focus:ring-[var(--color-accent-primary)]"
                style={{ maxHeight: "140px" }}
              />
              <button
                type="button"
                onClick={() => handleSend()}
                disabled={!isReady || isSending || !input.trim()}
                className="btn btn-primary h-11 w-full px-5 sm:w-auto"
              >
                {isSending ? "Sending…" : "Send"}
              </button>
            </div>
            <p className="mt-2 text-xs text-secondary">
              Press Enter to send · Shift+Enter for a new line
            </p>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <ShieldIcon size={20} className="text-accent" />
                <div>
                  <h3 className="font-display text-lg font-semibold text-primary">
                    Live site snapshot
                  </h3>
                  <p className="mt-1 text-xs text-secondary">
                    Data the assistant sees. Synced from current logs every 10s.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={refreshContext}
                className="btn btn-secondary h-8 px-3 text-xs"
                title="Refresh snapshot"
              >
                <RefreshIcon size={14} />
              </button>
            </div>
            <div className="panel__content space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {contextStats.map((stat) => (
                  <div
                    key={stat.label}
                    className="rounded-xl border border-default bg-[var(--color-bg-surface)] px-3 py-3"
                  >
                    <p className="text-xs text-secondary">{stat.label}</p>
                    <p className="mt-1 font-display text-2xl font-semibold text-primary">
                      {stat.value}
                    </p>
                  </div>
                ))}
              </div>
              {context?.on_site?.length ? (
                <div>
                  <p className="eyebrow mb-2">On site now</p>
                  <ul className="space-y-1.5">
                    {context.on_site.slice(0, 6).map((p) => (
                      <li
                        key={p.person_id || p.name}
                        className="flex items-center justify-between text-xs"
                      >
                        <span className="font-medium text-primary">
                          {p.name || "Unknown"}
                        </span>
                        <span className="text-secondary">
                          {p.shift_id ? `${p.shift_id} shift` : "—"}
                        </span>
                      </li>
                    ))}
                    {context.on_site.length > 6 ? (
                      <li className="text-xs text-secondary">
                        … and {context.on_site.length - 6} more
                      </li>
                    ) : null}
                  </ul>
                </div>
              ) : null}
              {context?.generated_at ? (
                <p className="text-[10px] uppercase tracking-wide text-secondary">
                  Snapshot {formatTimestamp(context.generated_at)}
                </p>
              ) : null}
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="font-display text-base font-semibold text-primary">
                Tips
              </h3>
            </div>
            <div className="panel__content space-y-2 text-xs text-secondary">
              <p>
                The assistant answers from the <strong>live site snapshot</strong>.
                It will tell you if an answer isn't available in current data.
              </p>
              <p>
                For procedural questions (PPE, evacuation, incident reporting),
                ask as you would a safety officer.
              </p>
              <p>
                Conversations stay in this browser tab only — they are not
                persisted to the database.
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

export default AIChatbot;
