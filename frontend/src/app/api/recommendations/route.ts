import { NextResponse } from "next/server";
import { refreshCardsFromTcgdex } from "@/lib/cardPricing";

const RECOMMENDATIONS_API_URL =
  process.env.RECOMMENDATIONS_API_URL ?? "http://127.0.0.1:8000/recommendations";
const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
const ALLOWED_BUDGET_POLICIES = new Set(["soft_cap", "strict_cap", "market_flex"]);

function collectRecommendedCardIds(payload: unknown): string[] {
  if (!payload || typeof payload !== "object") return [];

  const ids = new Set<string>();
  const record = payload as Record<string, unknown>;
  const recommendations = Array.isArray(record.recommendations)
    ? record.recommendations
    : [];
  for (const item of recommendations) {
    if (!item || typeof item !== "object") continue;
    const cardId = (item as { card_id?: unknown }).card_id;
    if (typeof cardId === "string" && cardId.trim()) {
      ids.add(cardId.trim());
    }
  }

  const recommendationGroups = Array.isArray(record.recommendation_groups)
    ? record.recommendation_groups
    : [];
  for (const group of recommendationGroups) {
    if (!group || typeof group !== "object") continue;
    const cards = (group as { recommendations?: unknown }).recommendations;
    if (!Array.isArray(cards)) continue;

    for (const card of cards) {
      if (!card || typeof card !== "object") continue;
      const cardId = (card as { card_id?: unknown }).card_id;
      if (typeof cardId === "string" && cardId.trim()) {
        ids.add(cardId.trim());
      }
    }
  }

  return [...ids];
}

function supabaseHeaders() {
  return {
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
}

function buildOrFilter(column: string, values: string[]): string {
  return values
    .map((value) => `${column}.eq.${encodeURIComponent(value)}`)
    .join(",");
}

async function fetchSupabasePrices(cardIds: string[]): Promise<Map<string, number | null>> {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY || cardIds.length === 0) {
    return new Map();
  }

  const url = `${SUPABASE_URL}/rest/v1/cards?or=(${buildOrFilter(
    "id",
    cardIds,
  )})&select=id,price_usd`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });
  if (!res.ok) return new Map();

  const rows = (await res.json()) as Array<{ id: string; price_usd: number | null }>;
  return new Map(rows.map((row) => [row.id, row.price_usd]));
}

function applyPricesToRecommendationsPayload(
  payload: unknown,
  pricesByCardId: Map<string, number | null>,
): Record<string, unknown> {
  if (!payload || typeof payload !== "object") return {};

  const base = payload as Record<string, unknown>;
  const clone: Record<string, unknown> = { ...base };

  if (Array.isArray(base.recommendations)) {
    clone.recommendations = base.recommendations.map((item) => {
      if (!item || typeof item !== "object") return item;
      const record = item as Record<string, unknown>;
      const cardId = typeof record.card_id === "string" ? record.card_id : "";
      if (!cardId || !pricesByCardId.has(cardId)) return record;
      return {
        ...record,
        price_usd: pricesByCardId.get(cardId) ?? null,
      };
    });
  }

  if (Array.isArray(base.recommendation_groups)) {
    clone.recommendation_groups = base.recommendation_groups.map((group) => {
      if (!group || typeof group !== "object") return group;
      const groupRecord = group as Record<string, unknown>;
      const recommendations = Array.isArray(groupRecord.recommendations)
        ? groupRecord.recommendations
        : [];

      return {
        ...groupRecord,
        recommendations: recommendations.map((item) => {
          if (!item || typeof item !== "object") return item;
          const record = item as Record<string, unknown>;
          const cardId = typeof record.card_id === "string" ? record.card_id : "";
          if (!cardId || !pricesByCardId.has(cardId)) return record;
          return {
            ...record,
            price_usd: pricesByCardId.get(cardId) ?? null,
          };
        }),
      };
    });
  }

  return clone;
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const userId = searchParams.get("userId")?.trim() ?? "";
  const budgetUsdRaw = Number(searchParams.get("budgetUsd") ?? "1000");
  const numRaw = Number(searchParams.get("num") ?? "10");
  const budgetPolicyRaw = (searchParams.get("budgetPolicy") ?? "soft_cap").trim().toLowerCase();
  const forceRefresh = ["1", "true", "yes"].includes(
    searchParams.get("forceRefresh")?.trim().toLowerCase() ?? "",
  );
  const budgetUsd =
    Number.isFinite(budgetUsdRaw) && budgetUsdRaw >= 0
      ? Number(budgetUsdRaw.toFixed(2))
      : 1000;
  const num =
    Number.isFinite(numRaw) && numRaw >= 1
      ? Math.min(15, Math.trunc(numRaw))
      : 10;
  const budgetPolicy = ALLOWED_BUDGET_POLICIES.has(budgetPolicyRaw)
    ? budgetPolicyRaw
    : "soft_cap";

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
        budget_usd: budgetUsd,
        budget_policy: budgetPolicy,
        limit: num,
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

  const cardIds = collectRecommendedCardIds(payload);
  try {
    await refreshCardsFromTcgdex(cardIds);
  } catch {
    // Do not fail recommendations response if pricing sync fails.
  }

  const latestPrices = await fetchSupabasePrices(cardIds);
  const hydratedPayload = applyPricesToRecommendationsPayload(payload, latestPrices);

  return NextResponse.json({ ok: true, ...hydratedPayload });
}
