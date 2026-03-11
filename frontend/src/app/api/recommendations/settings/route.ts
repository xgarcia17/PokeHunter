import { NextResponse } from "next/server";

const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";

const ALLOWED_BUDGET_POLICIES = new Set(["soft_cap", "strict_cap", "market_flex"]);

function supabaseHeaders() {
  return {
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
}

function normalizeBudgetPolicy(value: string | null | undefined) {
  const normalized = (value ?? "").trim().toLowerCase();
  if (ALLOWED_BUDGET_POLICIES.has(normalized)) return normalized;
  return "soft_cap";
}

function normalizeBudget(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return 1000;
  return Number(value.toFixed(2));
}

function normalizeNum(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return 10;
  const intValue = Math.trunc(value);
  if (intValue < 1) return 1;
  if (intValue > 15) return 15;
  return intValue;
}

export async function GET(req: Request) {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return NextResponse.json(
      { error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY" },
      { status: 500 },
    );
  }

  const { searchParams } = new URL(req.url);
  const userId = searchParams.get("userId")?.trim() ?? "";
  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  const url = `${SUPABASE_URL}/rest/v1/recommendation_preferences?user_id=eq.${encodeURIComponent(
    userId,
  )}&select=user_id,budget_policy,budget_usd,num&limit=1`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    return NextResponse.json({ error: "Failed to load recommendation settings" }, { status: 502 });
  }

  const rows = (await res.json()) as Array<{
    user_id: string;
    budget_policy: string;
    budget_usd: number;
    num: number;
  }>;
  const row = rows[0];
  if (!row) {
    return NextResponse.json({
      ok: true,
      settings: {
        userId,
        budgetPolicy: "soft_cap",
        budgetUsd: 1000,
        num: 10,
      },
    });
  }

  return NextResponse.json({
    ok: true,
    settings: {
      userId,
      budgetPolicy: normalizeBudgetPolicy(row.budget_policy),
      budgetUsd: normalizeBudget(row.budget_usd),
      num: normalizeNum(row.num),
    },
  });
}

export async function PUT(req: Request) {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return NextResponse.json(
      { error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY" },
      { status: 500 },
    );
  }

  let body: {
    userId?: string;
    budgetPolicy?: string;
    budgetUsd?: number;
    num?: number;
  };
  try {
    body = (await req.json()) as {
      userId?: string;
      budgetPolicy?: string;
      budgetUsd?: number;
      num?: number;
    };
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const userId = body.userId?.trim() ?? "";
  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  const budgetPolicy = normalizeBudgetPolicy(body.budgetPolicy);
  const budgetUsd = normalizeBudget(body.budgetUsd);
  const num = normalizeNum(body.num);

  const upsertUrl = `${SUPABASE_URL}/rest/v1/recommendation_preferences?on_conflict=user_id`;
  const upsertRes = await fetch(upsertUrl, {
    method: "POST",
    headers: {
      ...supabaseHeaders(),
      Prefer: "resolution=merge-duplicates,return=representation",
    },
    body: JSON.stringify([
      {
        user_id: userId,
        budget_policy: budgetPolicy,
        budget_usd: budgetUsd,
        num,
      },
    ]),
    cache: "no-store",
  });

  if (!upsertRes.ok) {
    return NextResponse.json({ error: "Failed to save recommendation settings" }, { status: 502 });
  }

  return NextResponse.json({
    ok: true,
    settings: {
      userId,
      budgetPolicy,
      budgetUsd,
      num,
    },
  });
}
