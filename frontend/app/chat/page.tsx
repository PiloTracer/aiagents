import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ChatClient from "./ChatClient";

export default async function ChatPage() {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    redirect("/auth");
  }

  return <ChatClient />;
}

