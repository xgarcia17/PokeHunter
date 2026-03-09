import { NextResponse } from "next/server";

const ALLOWED_TYPES = new Set(["image/jpeg", "image/png"]);
const MAX_MB = 8;
const MAX_BYTES = MAX_MB * 1024 * 1024;
const IDENTIFY_API_URL =
  process.env.IDENTIFY_API_URL ?? "http://127.0.0.1:8000/identify";
const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
const STORAGE_BUCKET = process.env.STORAGE_BUCKET ?? "pokemon-images";

type IdentifyResponse = {
  best_set_id: string | null;
  best_card_number: string | null;
  best_db_card_id: string | null;
  score: number;
  top_k?: Array<{
    resolved?: {
      storage_path?: string | null;
      set_id?: string | null;
      card_number?: string | null;
      db_card_id?: string | null;
    };
  }>;
};

type CardRow = {
  id: string;
  set_id: string | null;
  card_number: string | null;
  name?: string | null;
};

type CardImageRow = {
  card_id: string;
  storage_path: string;
};

function toPublicImageUrl(storagePath: string | null | undefined): string | null {
  if (!storagePath || !SUPABASE_URL) return null;
  const path = storagePath.replace(/^\/+/, "");
  return `${SUPABASE_URL}/storage/v1/object/public/${STORAGE_BUCKET}/${path}`;
}

async function fetchSupabaseCard(cardId: string): Promise<CardRow | null> {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) return null;
  const url = `${SUPABASE_URL}/rest/v1/cards?id=eq.${encodeURIComponent(
    cardId,
  )}&select=id,set_id,card_number,name&limit=1`;
  const res = await fetch(url, {
    headers: {
      apikey: SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    },
    cache: "no-store",
  });
  if (!res.ok) return null;
  const rows = (await res.json()) as CardRow[];
  return rows[0] ?? null;
}

function cardNumberCandidates(cardNumber: string): string[] {
  const value = cardNumber.trim();
  if (!value) return [];
  const out = [value];
  if (/^\d+$/.test(value)) {
    const withoutLeadingZeros = String(Number(value));
    if (!out.includes(withoutLeadingZeros)) out.push(withoutLeadingZeros);
  }
  return out;
}

async function fetchSupabaseCardBySetAndNumber(
  setId: string,
  cardNumber: string,
): Promise<CardRow | null> {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) return null;
  const numbers = cardNumberCandidates(cardNumber);
  if (numbers.length === 0) return null;

  const numberFilter =
    numbers.length === 1
      ? `card_number.eq.${encodeURIComponent(numbers[0])}`
      : numbers
          .map((n) => `card_number.eq.${encodeURIComponent(n)}`)
          .join(",");
  const url = `${SUPABASE_URL}/rest/v1/cards?set_id=eq.${encodeURIComponent(
    setId,
  )}&or=(${numberFilter})&select=id,set_id,card_number,name&limit=1`;

  const res = await fetch(url, {
    headers: {
      apikey: SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    },
    cache: "no-store",
  });
  if (!res.ok) return null;
  const rows = (await res.json()) as CardRow[];
  return rows[0] ?? null;
}

async function fetchSupabaseCardImage(cardId: string): Promise<CardImageRow | null> {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) return null;
  const url = `${SUPABASE_URL}/rest/v1/card_images?card_id=eq.${encodeURIComponent(
    cardId,
  )}&select=card_id,storage_path&limit=1`;
  const res = await fetch(url, {
    headers: {
      apikey: SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    },
    cache: "no-store",
  });
  if (!res.ok) return null;
  const rows = (await res.json()) as CardImageRow[];
  return rows[0] ?? null;
}

export async function POST(req: Request) {
  const formData = await req.formData();
  const file = formData.get("file");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file uploaded" }, { status: 400 });
  }

  if (!ALLOWED_TYPES.has(file.type)) {
    return NextResponse.json(
      { error: "Invalid file type. Use JPEG, PNG, or WebP." },
      { status: 415 },
    );
  }

  if (file.size > MAX_BYTES) {
    return NextResponse.json(
      { error: `File too large. Max is ${MAX_MB}MB.` },
      { status: 413 },
    );
  }

  const identifyForm = new FormData();
  identifyForm.append("file", file);

  let identifyData: IdentifyResponse;
  try {
    const identifyRes = await fetch(IDENTIFY_API_URL, {
      method: "POST",
      body: identifyForm,
      cache: "no-store",
    });

    const payload = await identifyRes.json();
    if (!identifyRes.ok) {
      const msg = payload?.detail ?? payload?.error ?? "Identify API failed";
      return NextResponse.json({ error: msg }, { status: identifyRes.status });
    }
    identifyData = payload as IdentifyResponse;
  } catch {
    return NextResponse.json(
      {
        error:
          "Could not reach the Python identify service. Make sure backend API is running.",
      },
      { status: 502 },
    );
  }

  const bestDbCardId = identifyData.best_db_card_id;
  const resolved = identifyData.top_k?.[0]?.resolved;
  const fallbackStoragePath = resolved?.storage_path ?? null;
  const fallbackSetId = identifyData.best_set_id ?? resolved?.set_id ?? null;
  const fallbackCardNumber =
    identifyData.best_card_number ?? resolved?.card_number ?? null;

  let card = bestDbCardId ? await fetchSupabaseCard(bestDbCardId) : null;
  if (!card && fallbackSetId && fallbackCardNumber) {
    card = await fetchSupabaseCardBySetAndNumber(fallbackSetId, fallbackCardNumber);
  }

  const resolvedCardId = card?.id ?? bestDbCardId ?? null;
  const cardImage = resolvedCardId ? await fetchSupabaseCardImage(resolvedCardId) : null;
  const matchedStoragePath = cardImage?.storage_path ?? fallbackStoragePath;

  return NextResponse.json({
    ok: true,
    name: file.name,
    type: file.type,
    size: file.size,
    identify: {
      score: identifyData.score,
      card_id: resolvedCardId,
      set_id: card?.set_id ?? fallbackSetId,
      card_number: card?.card_number ?? fallbackCardNumber,
      card_name: card?.name ?? null,
      matched_storage_path: matchedStoragePath,
      matched_image_url: toPublicImageUrl(matchedStoragePath),
    },
  });
}
