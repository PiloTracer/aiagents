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
  const base = process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:18001";
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
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h1 style={{ margin: 0 }}>Account</h1>
        {me.is_superuser && (
          <span
            title="Administrator"
            style={{
              display: "inline-block",
              padding: "2px 8px",
              fontSize: 12,
              fontWeight: 600,
              borderRadius: 999,
              background: "#fee2e2",
              color: "#b91c1c",
              border: "1px solid #fecaca",
            }}
          >
            Admin
          </span>
        )}
      </div>
      <div style={{ marginTop: 16, display: "grid", gap: 6 }}>
        <div>
          <b>ID:</b> {me.id}
        </div>
        <div>
          <b>Email:</b> {me.email}
        </div>
        <div>
          <b>Full name:</b> {me.full_name ?? "-"}
        </div>
        <div>
          <b>Role:</b> {me.is_superuser ? "Admin" : "User"}
        </div>
      </div>
      <div style={{ marginTop: 20, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <Link
          href="/menu"
          style={{
            display: "inline-block",
            padding: "8px 16px",
            borderRadius: 8,
            background: "#2563eb",
            color: "#fff",
            fontWeight: 600,
          }}
        >
          Open Operations Menu
        </Link>
        <LogoutButton />
      </div>
    </div>
  );
}
