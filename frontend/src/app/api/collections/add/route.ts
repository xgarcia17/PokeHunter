import { NextResponse } from "next/server";

const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";

type AddCollectionBody = {
  userId?: string;
  cardId?: string;
};

function supabaseHeaders() {
  return {
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
}

export async function POST(req: Request) {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return NextResponse.json(
      { error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY" },
      { status: 500 },
    );
  }

  let body: AddCollectionBody;
  try {
    body = (await req.json()) as AddCollectionBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const userId = (body.userId ?? "").trim();
  const cardId = (body.cardId ?? "").trim();

  if (!userId || !cardId) {
    return NextResponse.json(
      { error: "userId and cardId are required" },
      { status: 400 },
    );
  }

  const selectUrl = `${SUPABASE_URL}/rest/v1/collections?user_id=eq.${encodeURIComponent(
    userId,
  )}&card_id=eq.${encodeURIComponent(cardId)}&select=id,quantity&limit=1`;
  const selectRes = await fetch(selectUrl, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!selectRes.ok) {
    return NextResponse.json(
      { error: "Failed to query collections table" },
      { status: 502 },
    );
  }

  const existing = (await selectRes.json()) as Array<{ id: string; quantity: number }>;

  if (existing.length > 0) {
    const current = existing[0];
    const nextQuantity = Number(current.quantity || 0) + 1;
    const patchUrl = `${SUPABASE_URL}/rest/v1/collections?id=eq.${encodeURIComponent(
      current.id,
    )}`;
    const patchRes = await fetch(patchUrl, {
      method: "PATCH",
      headers: supabaseHeaders(),
      body: JSON.stringify({ quantity: nextQuantity }),
      cache: "no-store",
    });

    if (!patchRes.ok) {
      return NextResponse.json(
        { error: "Failed to update collection quantity" },
        { status: 502 },
      );
    }

    return NextResponse.json({ ok: true, cardId, userId, quantity: nextQuantity });
  }

  const insertUrl = `${SUPABASE_URL}/rest/v1/collections`;
  const insertRes = await fetch(insertUrl, {
    method: "POST",
    headers: { ...supabaseHeaders(), Prefer: "return=representation" },
    body: JSON.stringify([{ user_id: userId, card_id: cardId, quantity: 1 }]),
    cache: "no-store",
  });

  if (!insertRes.ok) {
    return NextResponse.json(
      { error: "Failed to insert into collections table" },
      { status: 502 },
    );
  }

  return NextResponse.json({ ok: true, cardId, userId, quantity: 1 });
}
