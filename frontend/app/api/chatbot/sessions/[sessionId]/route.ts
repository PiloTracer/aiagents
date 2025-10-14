import { cookies } from "next/headers";
import { NextResponse } from "next/server";

function backendBase(): string {
  return (
    process.env.BACKEND_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:18001"
  );
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ sessionId: string }> },
) {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const { sessionId } = await context.params;

  const response = await fetch(`${backendBase()}/chatbot/sessions/${sessionId}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  const text = await response.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!response.ok) {
    return NextResponse.json(
      { detail: data ?? response.statusText },
      { status: response.status },
    );
  }

  return NextResponse.json(data, { status: response.status });
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ sessionId: string }> },
) {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const { sessionId } = await context.params;

  const response = await fetch(`${backendBase()}/chatbot/sessions/${sessionId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  const text = await response.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!response.ok) {
    return NextResponse.json(
      { detail: data ?? response.statusText },
      { status: response.status },
    );
  }

  return NextResponse.json(data, { status: response.status });
}
