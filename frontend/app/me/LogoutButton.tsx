"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";

export default function LogoutButton() {
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  async function onLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    startTransition(() => router.replace("/auth"));
  }

  return (
    <button onClick={onLogout} disabled={isPending} style={{ padding: 8 }}>
      {isPending ? "Logging out…" : "Logout"}
    </button>
  );
}

