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
    score: number;
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

type UploadIdentifyCandidate = {
  score: number;
  card_id: string | null;
  set_id: string | null;
  card_number: string | null;
  card_name: string | null;
  matched_storage_path: string | null;
  matched_image_url: string | null;
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

async function resolveCandidate(
  score: number,
  dbCardId: string | null,
  setId: string | null,
  cardNumber: string | null,
  storagePath: string | null,
): Promise<UploadIdentifyCandidate> {
  let card = dbCardId ? await fetchSupabaseCard(dbCardId) : null;
  if (!card && setId && cardNumber) {
    card = await fetchSupabaseCardBySetAndNumber(setId, cardNumber);
  }

  const resolvedCardId = card?.id ?? dbCardId ?? null;
  const cardImage = resolvedCardId ? await fetchSupabaseCardImage(resolvedCardId) : null;
  const matchedStoragePath = cardImage?.storage_path ?? storagePath;

  return {
    score,
    card_id: resolvedCardId,
    set_id: card?.set_id ?? setId,
    card_number: card?.card_number ?? cardNumber,
    card_name: card?.name ?? null,
    matched_storage_path: matchedStoragePath,
    matched_image_url: toPublicImageUrl(matchedStoragePath),
  };
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

  const topCandidatesPayload = (identifyData.top_k ?? []).slice(0, 2);
  const rawCandidates =
    topCandidatesPayload.length > 0
      ? topCandidatesPayload.map((candidate) => ({
          score: candidate.score,
          dbCardId: candidate.resolved?.db_card_id ?? null,
          setId: candidate.resolved?.set_id ?? null,
          cardNumber: candidate.resolved?.card_number ?? null,
          storagePath: candidate.resolved?.storage_path ?? null,
        }))
      : [
          {
            score: identifyData.score,
            dbCardId: identifyData.best_db_card_id,
            setId: identifyData.best_set_id,
            cardNumber: identifyData.best_card_number,
            storagePath: null,
          },
        ];

  const resolvedCandidates = await Promise.all(
    rawCandidates.map((candidate) =>
      resolveCandidate(
        candidate.score,
        candidate.dbCardId,
        candidate.setId,
        candidate.cardNumber,
        candidate.storagePath,
      ),
    ),
  );

  const uniqueCandidates: UploadIdentifyCandidate[] = [];
  const seen = new Set<string>();
  for (const candidate of resolvedCandidates) {
    const dedupeKey =
      candidate.card_id ??
      `${candidate.set_id ?? "unknown-set"}:${candidate.card_number ?? "unknown-number"}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    uniqueCandidates.push(candidate);
  }

  const primaryCandidate =
    uniqueCandidates[0] ??
    ({
      score: identifyData.score,
      card_id: identifyData.best_db_card_id,
      set_id: identifyData.best_set_id,
      card_number: identifyData.best_card_number,
      card_name: null,
      matched_storage_path: null,
      matched_image_url: null,
    } satisfies UploadIdentifyCandidate);

  return NextResponse.json({
    ok: true,
    name: file.name,
    type: file.type,
    size: file.size,
    identify: {
      score: primaryCandidate.score,
      card_id: primaryCandidate.card_id,
      set_id: primaryCandidate.set_id,
      card_number: primaryCandidate.card_number,
      card_name: primaryCandidate.card_name,
      matched_storage_path: primaryCandidate.matched_storage_path,
      matched_image_url: primaryCandidate.matched_image_url,
      candidates: uniqueCandidates,
    },
  });
}
