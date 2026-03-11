import { NextResponse } from "next/server";

const PRICING_INSIGHT_API_URL =
  process.env.PRICING_INSIGHT_API_URL ?? "http://127.0.0.1:8000/pricing-insight";

type PricingInsightCardInput = {
  name?: string;
  set_name?: string;
  price_usd?: number | null;
  quantity?: number;
  date_added?: string | null;
};

type PricingInsightRequestBody = {
  cards?: PricingInsightCardInput[];
  budgetUsd?: number;
};

export async function POST(req: Request) {
  let body: PricingInsightRequestBody;
  try {
    body = (await req.json()) as PricingInsightRequestBody;
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const cards = Array.isArray(body.cards) ? body.cards : [];
  const budgetUsd =
    typeof body.budgetUsd === "number" && Number.isFinite(body.budgetUsd)
      ? body.budgetUsd
      : 1000;

  let backendRes: Response;
  try {
    backendRes = await fetch(PRICING_INSIGHT_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        cards,
        budget_usd: budgetUsd,
      }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      {
        error:
          "Could not reach the Python pricing insight service. Make sure backend API is running.",
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
          "Failed to load pricing insight")
        : "Failed to load pricing insight";

    return NextResponse.json({ error: message }, { status: backendRes.status });
  }

  return NextResponse.json({ ok: true, ...(payload as Record<string, unknown>) });
}
