import { cookies } from "next/headers";
import { NextResponse } from "next/server";

function backendBase(): string {
  return (
    process.env.BACKEND_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:18001"
  );
}

export async function POST(
  request: Request,
  { params }: { params: { userId: string } },
) {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const payload = await request.json();
  const response = await fetch(
    `${backendBase()}/catalog/users/${params.userId}/roles`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    const text = await response.text();
    let data: unknown;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    return NextResponse.json(
      { detail: data ?? response.statusText },
      { status: response.status },
    );
  }

  return new NextResponse(null, { status: response.status });
}
