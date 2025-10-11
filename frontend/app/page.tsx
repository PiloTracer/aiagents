import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default async function Home() {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    redirect("/auth");
  }
  redirect("/menu");
}
