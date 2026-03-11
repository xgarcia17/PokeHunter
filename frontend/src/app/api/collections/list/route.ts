import { NextResponse } from "next/server";

const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
const STORAGE_BUCKET = process.env.STORAGE_BUCKET ?? "pokemon-images";

type CollectionRow = {
  card_id: string;
  quantity: number;
  date_added: string | null;
  price_usd: number | null;
  price_last_updated: string | null;
};

type CardRow = {
  id: string;
  name: string;
  set_id: string;
  price_usd: number | null;
  price_last_updated: string | null;
};

type SetRow = {
  id: string;
  name: string;
};

type CardImageRow = {
  card_id: string;
  storage_path: string;
};

function headers() {
  return {
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
  };
}

function toPublicImageUrl(storagePath: string | null | undefined): string | null {
  if (!storagePath || !SUPABASE_URL) return null;
  const cleaned = storagePath.replace(/^\/+/, "");
  return `${SUPABASE_URL}/storage/v1/object/public/${STORAGE_BUCKET}/${cleaned}`;
}

function buildOrFilter(column: string, values: string[]): string {
  return values
    .map((value) => `${column}.eq.${encodeURIComponent(value)}`)
    .join(",");
}

export async function GET(req: Request) {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return NextResponse.json(
      { error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY" },
      { status: 500 },
    );
  }

  const { searchParams } = new URL(req.url);
  const userId = searchParams.get("userId")?.trim();
  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  const collectionsUrl = `${SUPABASE_URL}/rest/v1/collections?user_id=eq.${encodeURIComponent(
    userId,
  )}&select=card_id,quantity,date_added,price_usd,price_last_updated`;
  const collectionsRes = await fetch(collectionsUrl, {
    headers: headers(),
    cache: "no-store",
  });

  if (!collectionsRes.ok) {
    return NextResponse.json(
      { error: "Failed to query collections" },
      { status: 502 },
    );
  }

  const collectionRows = (await collectionsRes.json()) as CollectionRow[];
  if (collectionRows.length === 0) {
    return NextResponse.json({ ok: true, items: [] });
  }

  const cardIds = [...new Set(collectionRows.map((r) => r.card_id))];
  const cardsUrl = `${SUPABASE_URL}/rest/v1/cards?or=(${buildOrFilter(
    "id",
    cardIds,
  )})&select=id,name,set_id,price_usd,price_last_updated`;
  const imagesUrl = `${SUPABASE_URL}/rest/v1/card_images?or=(${buildOrFilter(
    "card_id",
    cardIds,
  )})&select=card_id,storage_path`;

  const [cardsRes, imagesRes] = await Promise.all([
    fetch(cardsUrl, { headers: headers(), cache: "no-store" }),
    fetch(imagesUrl, { headers: headers(), cache: "no-store" }),
  ]);

  if (!cardsRes.ok || !imagesRes.ok) {
    return NextResponse.json(
      { error: "Failed to query cards or card_images" },
      { status: 502 },
    );
  }

  const cards = (await cardsRes.json()) as CardRow[];
  const images = (await imagesRes.json()) as CardImageRow[];
  const setIds = [...new Set(cards.map((c) => c.set_id))];

  const setsUrl = `${SUPABASE_URL}/rest/v1/sets?or=(${buildOrFilter(
    "id",
    setIds,
  )})&select=id,name`;
  const setsRes = await fetch(setsUrl, {
    headers: headers(),
    cache: "no-store",
  });

  if (!setsRes.ok) {
    return NextResponse.json({ error: "Failed to query sets" }, { status: 502 });
  }

  const sets = (await setsRes.json()) as SetRow[];

  const cardsById = new Map(cards.map((c) => [c.id, c]));
  const setsById = new Map(sets.map((s) => [s.id, s]));
  const imageByCardId = new Map<string, string>();
  for (const image of images) {
    if (!imageByCardId.has(image.card_id)) {
      imageByCardId.set(image.card_id, image.storage_path);
    }
  }

  const items = collectionRows.map((row) => {
    const card = cardsById.get(row.card_id);
    const set = card ? setsById.get(card.set_id) : null;
    const storagePath = imageByCardId.get(row.card_id) ?? null;
    return {
      card_id: row.card_id,
      quantity: row.quantity,
      date_added: row.date_added,
      card_name: card?.name ?? "Unknown Card",
      set_name: set?.name ?? "Unknown Set",
      price_usd: row.price_usd ?? card?.price_usd ?? null,
      price_last_updated:
        row.price_last_updated ?? card?.price_last_updated ?? null,
      image_url: toPublicImageUrl(storagePath),
    };
  });

  return NextResponse.json({ ok: true, items });
}
