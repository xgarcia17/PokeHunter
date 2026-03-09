import { NextResponse } from "next/server";
import { refreshCardPriceIfNeeded, type CardRecord } from "@/lib/cardPricing";

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

async function updateCollectionPricing(
  collectionId: string,
  card: CardRecord,
): Promise<void> {
  const patchUrl = `${SUPABASE_URL}/rest/v1/collections?id=eq.${encodeURIComponent(
    collectionId,
  )}`;
  const patchRes = await fetch(patchUrl, {
    method: "PATCH",
    headers: supabaseHeaders(),
    body: JSON.stringify({
      price_usd: card.price_usd,
      price_last_updated: card.price_last_updated,
    }),
    cache: "no-store",
  });

  if (!patchRes.ok) {
    throw new Error("Failed to sync collection pricing");
  }
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

  let pricedCard: CardRecord;
  try {
    pricedCard = await refreshCardPriceIfNeeded(cardId);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to refresh card price",
      },
      { status: 502 },
    );
  }

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

    try {
      await updateCollectionPricing(current.id, pricedCard);
    } catch (error) {
      return NextResponse.json(
        {
          error:
            error instanceof Error
              ? error.message
              : "Failed to sync collection pricing",
        },
        { status: 502 },
      );
    }

    return NextResponse.json({
      ok: true,
      cardId,
      userId,
      quantity: nextQuantity,
      card: pricedCard,
    });
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

  const insertedRows = (await insertRes.json()) as Array<{ id: string }>;
  const insertedCollection = insertedRows[0];
  if (insertedCollection) {
    try {
      await updateCollectionPricing(insertedCollection.id, pricedCard);
    } catch (error) {
      return NextResponse.json(
        {
          error:
            error instanceof Error
              ? error.message
              : "Failed to sync collection pricing",
        },
        { status: 502 },
      );
    }
  }

  return NextResponse.json({
    ok: true,
    cardId,
    userId,
    quantity: 1,
    card: pricedCard,
  });
}
