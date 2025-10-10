import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { email, password, full_name } = await req.json();
    const base =
      process.env.BACKEND_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_API_BASE ||
      "http://localhost:18001";
    // Register
    const r = await fetch(`${base}/users/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name }),
    });
    if (!r.ok) {
      const msg = await r.text();
      return NextResponse.json({ error: msg || "Registration failed" }, { status: 400 });
    }
    // Auto-login
    const login = await fetch(`${base}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!login.ok) {
      const msg = await login.text();
      return NextResponse.json({ error: msg || "Auto-login failed" }, { status: 401 });
    }
    const data = (await login.json()) as { access_token: string; token_type: string };
    const res = NextResponse.json({ ok: true });
    const isProd = process.env.NODE_ENV === "production";
    res.cookies.set("access_token", data.access_token, {
      httpOnly: true,
      sameSite: "lax",
      secure: isProd,
      path: "/",
      maxAge: 60 * 60 * 24,
    });
    return res;
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "Unexpected error" }, { status: 500 });
  }
}
