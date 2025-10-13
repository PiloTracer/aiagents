import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import CatalogClient from "./CatalogClient";

export default async function CatalogPage() {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    redirect("/auth");
  }

  return <CatalogClient />;
}

