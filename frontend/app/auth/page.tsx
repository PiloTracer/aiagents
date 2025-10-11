"use client";

import { FormEvent, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

const styles = {
  page: {
    minHeight: "100vh",
    display: "flex" as const,
    alignItems: "center",
    justifyContent: "center",
    background: "radial-gradient(circle at top, #0f172a, #020617)",
    padding: "40px 16px",
    color: "#e2e8f0",
    fontFamily: "Inter, system-ui, sans-serif",
  },
  card: {
    width: "100%",
    maxWidth: 420,
    padding: "32px 28px",
    background: "rgba(15, 23, 42, 0.85)",
    borderRadius: 18,
    border: "1px solid rgba(148, 163, 184, 0.15)",
    boxShadow: "0 30px 70px rgba(15, 23, 42, 0.5)",
    backdropFilter: "blur(18px)",
  },
  tabs: {
    display: "flex",
    gap: 12,
    marginBottom: 24,
  },
  tabButton: (active: boolean) => ({
    padding: "6px 14px",
    borderRadius: 10,
    border: "1px solid",
    borderColor: active ? "#1d4ed8" : "rgba(148, 163, 184, 0.3)",
    background: active ? "linear-gradient(135deg, #2563eb, #1d4ed8)" : "transparent",
    color: active ? "#f8fafc" : "#94a3b8",
    fontWeight: 600,
    cursor: active ? "default" : "pointer",
    transition: "all 0.2s ease",
  }),
  label: {
    display: "block",
    fontSize: 13,
    fontWeight: 600,
    marginBottom: 6,
    letterSpacing: 0.3,
    textTransform: "uppercase" as const,
    color: "#94a3b8",
  },
  input: {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid rgba(148, 163, 184, 0.2)",
    background: "rgba(15, 23, 42, 0.6)",
    color: "#e2e8f0",
    fontSize: 15,
    outline: "none",
    transition: "border-color 0.2s ease, box-shadow 0.2s ease",
  },
  primaryButton: {
    marginTop: 12,
    padding: "12px",
    borderRadius: 12,
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    border: "none",
    color: "#f8fafc",
    fontWeight: 600,
    fontSize: 16,
    cursor: "pointer",
    transition: "transform 0.15s ease, box-shadow 0.15s ease",
  },
  disabledButton: {
    opacity: 0.6,
    cursor: "not-allowed",
  },
  message: (variant: "error" | "info") => ({
    fontSize: 14,
    fontWeight: 500,
    color: variant === "error" ? "#f87171" : "#34d399",
  }),
};

export default function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  const tabs = useMemo(
    () => [
      { key: "login", label: "Login" },
      { key: "register", label: "Register" },
    ] as const,
    [],
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    const url = mode === "login" ? "/api/auth/login" : "/api/auth/register";
    const payload: Record<string, unknown> = { email, password };
    if (mode === "register") payload.full_name = fullName || null;
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setError((j as { error?: string }).error || "Authentication failed");
        return;
      }
      if (mode === "login") {
        startTransition(() => router.push("/me"));
      } else {
        setInfo("Account created. Please wait for an administrator to activate it.");
        setMode("login");
        setPassword("");
      }
    } catch (err: any) {
      setError(err?.message || "Unexpected error");
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={{ marginBottom: 20, fontWeight: 700 }}>Welcome</h1>
        <div style={styles.tabs}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setMode(tab.key)}
              disabled={mode === tab.key}
              style={styles.tabButton(mode === tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <form onSubmit={onSubmit} style={{ display: "grid", gap: 16 }}>
          {mode === "register" && (
            <div>
              <label style={styles.label} htmlFor="fullName">
                Full name
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Jane Doe"
                style={styles.input}
              />
            </div>
          )}
          <div>
            <label style={styles.label} htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              required
              style={styles.input}
            />
          </div>
          <div>
            <label style={styles.label} htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="********"
              required
              minLength={8}
              style={styles.input}
            />
          </div>
          {error && <div style={styles.message("error")}>{error}</div>}
          {info && !error && <div style={styles.message("info")}>{info}</div>}
          <button
            type="submit"
            disabled={isPending}
            style={{
              ...styles.primaryButton,
              ...(isPending ? styles.disabledButton : {}),
            }}
          >
            {isPending ? "Please wait..." : mode === "login" ? "Login" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
