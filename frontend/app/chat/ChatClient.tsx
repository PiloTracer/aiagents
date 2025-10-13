"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type SessionSummary = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  is_archived: boolean;
  message_count: number;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  metadata?: Record<string, unknown> | null;
};

type RetrievedSource = {
  chunk_id: string;
  area_slug: string;
  score: number;
  text: string;
  chunk_index?: number | null;
  artifact_id?: string | null;
  source_path?: string | null;
};

type ChatResponsePayload = {
  session_id: string;
  message: ChatMessage;
  sources: RetrievedSource[];
  total_messages: number;
};

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `temp-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

export default function ChatClient() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sourcesByMessage, setSourcesByMessage] = useState<Record<string, RetrievedSource[]>>({});
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight;
    }
  }, []);

  const formatTimestamp = useCallback((iso: string) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }, []);

  const loadSession = useCallback(
    async (sessionId: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/chatbot/sessions/${sessionId}`, { cache: "no-store" });
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(detail || res.statusText);
        }
        const data = await res.json();
        const sessionMessages = (data.messages ?? []) as ChatMessage[];
        const normalized = sessionMessages.map((message) => ({
          ...message,
          role: message.role as "user" | "assistant",
        }));
        setMessages(normalized);
        const sourceMap: Record<string, RetrievedSource[]> = {};
        normalized.forEach((message) => {
          if (message.role === "assistant" && message.metadata && "sources" in message.metadata) {
            sourceMap[message.id] = (message.metadata.sources as RetrievedSource[]) ?? [];
          }
        });
        setSourcesByMessage(sourceMap);
        setActiveSessionId(sessionId);
        setTimeout(scrollToBottom, 0);
      } catch (err) {
        setError((err as Error).message || "Failed to load session");
      } finally {
        setLoading(false);
      }
    },
    [scrollToBottom],
  );

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/chatbot/sessions", { cache: "no-store" });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || res.statusText);
      }
      const data = (await res.json()) as SessionSummary[];
      setSessions(data);
      if (data.length && !activeSessionId) {
        void loadSession(data[0].id);
      }
    } catch (err) {
      setError((err as Error).message || "Failed to load sessions");
    } finally {
      setIsInitializing(false);
    }
  }, [activeSessionId, loadSession]);

  useEffect(() => {
    void fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleCreateSession = () => {
    setActiveSessionId(null);
    setMessages([]);
    setSourcesByMessage({});
    setError(null);
  };

  const handleDeleteSession = async (sessionId: string) => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`/api/chatbot/sessions/${sessionId}`, { method: "DELETE" });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || res.statusText);
      }
      setSessions((prev) => prev.filter((session) => session.id !== sessionId));
      if (activeSessionId === sessionId) {
        handleCreateSession();
      }
    } catch (err) {
      setError((err as Error).message || "Failed to delete session");
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim()) {
      return;
    }
    setError(null);
    setLoading(true);

    const optimisticId = uuid();
    const now = new Date().toISOString();
    const optimisticMessage: ChatMessage = {
      id: optimisticId,
      role: "user",
      content: input,
      created_at: now,
    };

    setMessages((prev) => [...prev, optimisticMessage]);
    const payload = {
      message: input.trim(),
      session_id: activeSessionId,
    };
    setInput("");

    try {
      const res = await fetch("/api/chatbot/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || res.statusText);
      }
      const data = (await res.json()) as ChatResponsePayload;
      const assistantMessage: ChatMessage = {
        ...data.message,
        role: "assistant",
      };
      setActiveSessionId(data.session_id);
      setMessages((prev) => {
        const filtered = prev.filter((message) => message.id !== optimisticId);
        return [...filtered, optimisticMessage, assistantMessage];
      });
      setSourcesByMessage((prev) => ({
        ...prev,
        [assistantMessage.id]: data.sources ?? [],
      }));
      void fetchSessions();
    } catch (err) {
      setMessages((prev) => prev.filter((message) => message.id !== optimisticId));
      setError((err as Error).message || "Failed to send message");
    } finally {
      setLoading(false);
      setTimeout(scrollToBottom, 0);
    }
  };

  const currentSessionTitle = useMemo(() => {
    if (!activeSessionId) {
      return "New conversation";
    }
    const session = sessions.find((item) => item.id === activeSessionId);
    return session?.title ?? "Conversation";
  }, [activeSessionId, sessions]);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-7xl gap-6 px-6 py-8">
        <aside className="w-full max-w-xs rounded-2xl border border-white/10 bg-white/5 p-4">
          <div className="flex items-center justify-between pb-3">
            <h2 className="text-lg font-semibold text-blue-200">Conversations</h2>
            <button
              className="rounded-lg bg-blue-500 px-3 py-1 text-sm font-semibold text-white hover:bg-blue-400 disabled:bg-blue-900"
              onClick={handleCreateSession}
              disabled={loading}
            >
              New
            </button>
          </div>
          <div className="space-y-2 overflow-y-auto pr-2" style={{ maxHeight: "calc(100vh - 12rem)" }}>
            {sessions.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <div
                  key={session.id}
                  className={`rounded-xl border px-3 py-2 text-sm transition ${
                    isActive
                      ? "border-blue-400 bg-blue-500/20 text-blue-100"
                      : "border-white/10 bg-slate-900/60 text-slate-200 hover:border-blue-200/40"
                  }`}
                >
                  <button
                    className="w-full text-left font-semibold"
                    onClick={() => void loadSession(session.id)}
                    disabled={loading}
                  >
                    {session.title ?? "Untitled conversation"}
                  </button>
                  <div className="mt-1 text-xs text-slate-400">
                    Updated {formatTimestamp(session.updated_at)}
                  </div>
                  <div className="mt-2 flex justify-between text-xs text-slate-400">
                    <span>{session.message_count} messages</span>
                    <button
                      className="text-rose-300 hover:text-rose-200"
                      onClick={() => void handleDeleteSession(session.id)}
                      title="Delete conversation"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              );
            })}
            {!sessions.length && !isInitializing && (
              <div className="rounded-xl border border-dashed border-white/10 bg-transparent p-3 text-sm text-slate-400">
                No saved conversations yet. Start a new one!
              </div>
            )}
          </div>
        </aside>

        <section className="flex flex-1 flex-col rounded-2xl border border-white/10 bg-white/5">
          <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
            <div>
              <h1 className="text-xl font-semibold text-blue-200">{currentSessionTitle}</h1>
              <p className="text-sm text-slate-400">
                Ask about ingested knowledge. Responses cite retrieved sources automatically.
              </p>
            </div>
            {loading && (
              <span className="rounded-lg bg-slate-800 px-3 py-1 text-xs text-slate-200">
                Thinking...
              </span>
            )}
          </header>

          <div ref={messagesEndRef} className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
            {!messages.length && (
              <div className="rounded-xl border border-dashed border-white/10 bg-slate-900/60 p-6 text-sm text-slate-300">
                Start the conversation by asking about any document, jurisprudence topic, or ingestion job.
              </div>
            )}
            {messages.map((message) => {
              const isUser = message.role === "user";
              const sources = sourcesByMessage[message.id] ?? [];
              return (
                <div key={message.id} className="flex flex-col gap-2">
                  <div
                    className={`max-w-3xl rounded-2xl px-4 py-3 text-sm shadow-sm ${
                      isUser
                        ? "self-end bg-blue-500 text-white"
                        : "self-start border border-white/10 bg-slate-900/80 text-slate-100"
                    }`}
                  >
                    <div className="whitespace-pre-wrap leading-relaxed">{message.content}</div>
                    <div className="mt-2 text-xs text-slate-300 opacity-80">
                      {formatTimestamp(message.created_at)}
                    </div>
                  </div>
                  {!isUser && sources.length > 0 && (
                    <div className="grid gap-2 rounded-xl border border-white/10 bg-slate-900/70 p-3 text-xs text-slate-300 sm:grid-cols-2">
                      {sources.map((source, idx) => (
                        <div key={`${message.id}-${idx}`} className="rounded-lg border border-white/5 bg-slate-900/70 p-3">
                          <div className="flex items-center justify-between text-[11px] text-slate-400">
                            <span>Snippet #{idx + 1}</span>
                            <span>{source.area_slug}</span>
                          </div>
                          <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-slate-200">
                            {source.text}
                          </p>
                          <div className="mt-2 text-[11px] text-slate-400">
                            Score {source.score.toFixed(3)}
                            {source.source_path ? ` • ${source.source_path}` : ""}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {error && (
              <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {error}
              </div>
            )}
          </div>

          <footer className="border-t border-white/10 px-6 py-4">
            <form
              className="flex flex-col gap-3 md:flex-row"
              onSubmit={(event) => {
                event.preventDefault();
                void handleSendMessage();
              }}
            >
              <textarea
                className="h-28 flex-1 resize-none rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-sm text-slate-100 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
                placeholder="Ask a question about your knowledge base..."
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void handleSendMessage();
                  }
                }}
                disabled={loading}
              />
              <button
                type="submit"
                className="rounded-2xl bg-blue-500 px-6 py-3 text-sm font-semibold text-white hover:bg-blue-400 disabled:bg-blue-900"
                disabled={loading || !input.trim()}
              >
                Send
              </button>
            </form>
          </footer>
        </section>
      </div>
    </main>
  );
}
