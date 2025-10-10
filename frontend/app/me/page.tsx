import Link from "next/link";
import LogoutButton from "./LogoutButton";
import { cookies } from "next/headers";

type Me = {
  id: string;
  email: string;
  full_name: string | null;
  is_superuser: boolean;
};

async function getMe(): Promise<Me | null> {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) return null;
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:18000";
  try {
    const r = await fetch(`${base}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!r.ok) return null;
    return (await r.json()) as Me;
  } catch {
    return null;
  }
}

export default async function MePage() {
  const me = await getMe();

  if (!me) {
    return (
      <div style={{ maxWidth: 640, margin: "40px auto", padding: 16 }}>
        <h1>Account</h1>
        <p style={{ marginTop: 8 }}>You are not signed in.</p>
        <p>
          <Link href="/auth">Go to sign in</Link>
        </p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 640, margin: "40px auto", padding: 16 }}>
      <h1>Account</h1>
      <div style={{ marginTop: 16, display: "grid", gap: 6 }}>
        <div>
          <b>ID:</b> {me.id}
        </div>
        <div>
          <b>Email:</b> {me.email}
        </div>
        <div>
          <b>Full name:</b> {me.full_name ?? "—"}
        </div>
        <div>
          <b>Role:</b> {me.is_superuser ? "Admin" : "User"}
        </div>
      </div>
      <div style={{ marginTop: 20 }}>
        <LogoutButton />
      </div>
    </div>
  );
}

