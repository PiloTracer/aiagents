import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import MenuClient from "./MenuClient";

export default async function MenuPage() {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    redirect("/auth");
  }

  return <MenuClient />;
}
