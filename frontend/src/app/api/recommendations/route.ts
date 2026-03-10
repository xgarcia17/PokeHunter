import { NextResponse } from "next/server";

const RECOMMENDATIONS_API_URL =
  process.env.RECOMMENDATIONS_API_URL ?? "http://127.0.0.1:8000/recommendations";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const userId = searchParams.get("userId")?.trim() ?? "";
  const forceRefresh = ["1", "true", "yes"].includes(
    searchParams.get("forceRefresh")?.trim().toLowerCase() ?? "",
  );

  if (!userId) {
    return NextResponse.json(
      { error: "userId is required" },
      { status: 400 },
    );
  }

  let backendRes: Response;
  try {
    backendRes = await fetch(RECOMMENDATIONS_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        source: "supabase",
        user_id: userId,
        budget_usd: 1000,
        limit: 15,
        force_refresh: forceRefresh,
      }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      {
        error:
          "Could not reach the Python recommendations service. Make sure backend API is running.",
      },
      { status: 502 },
    );
  }

  let payload: unknown = null;
  try {
    payload = await backendRes.json();
  } catch {
    payload = null;
  }

  if (!backendRes.ok) {
    const message =
      payload && typeof payload === "object"
        ? ((payload as { detail?: string; error?: string }).detail ??
          (payload as { detail?: string; error?: string }).error ??
          "Failed to load recommendations")
        : "Failed to load recommendations";

    return NextResponse.json({ error: message }, { status: backendRes.status });
  }

  return NextResponse.json({ ok: true, ...(payload as Record<string, unknown>) });
}
