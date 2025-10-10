"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

export default function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const url = mode === "login" ? "/api/auth/login" : "/api/auth/register";
    const payload: any = { email, password };
    if (mode === "register") payload.full_name = fullName || null;
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setError(j.error || "Request failed");
        return;
      }
      startTransition(() => router.push("/"));
    } catch (e: any) {
      setError(e?.message || "Unexpected error");
    }
  }

  return (
    <div style={{ maxWidth: 420, margin: "40px auto", padding: 16 }}>
      <h1 style={{ marginBottom: 8 }}>Auth</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setMode("login")}
          disabled={mode === "login"}
          style={{ padding: "6px 10px" }}
        >
          Login
        </button>
        <button
          onClick={() => setMode("register")}
          disabled={mode === "register"}
          style={{ padding: "6px 10px" }}
        >
          Register
        </button>
      </div>

      <form onSubmit={onSubmit} style={{ display: "grid", gap: 12 }}>
        {mode === "register" && (
          <div>
            <label htmlFor="fullName">Full name</label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
              style={{ width: "100%", padding: 8 }}
            />
          </div>
        )}
        <div>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
            style={{ width: "100%", padding: 8 }}
          />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="********"
            required
            minLength={8}
            style={{ width: "100%", padding: 8 }}
          />
        </div>
        {error && (
          <div style={{ color: "#c00", fontSize: 14 }}>{error}</div>
        )}
        <button type="submit" disabled={isPending} style={{ padding: 10 }}>
          {isPending ? "Please wait…" : mode === "login" ? "Login" : "Create account"}
        </button>
      </form>
    </div>
  );
}

