const SUPABASE_URL = process.env.SUPABASE_URL?.replace(/\/+$/, "") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
const JUST_TCG_API_KEY = process.env.JUST_TCG_API_KEY ?? "";
const JUST_TCG_BASE_URL = "https://api.justtcg.com/v1";
const PRICE_REFRESH_WINDOW_MS = 24 * 60 * 60 * 1000;
const STORAGE_BUCKET = process.env.STORAGE_BUCKET ?? "pokemon-images";

export type CardRecord = {
  id: string;
  name: string;
  set_id: string;
  number: string;
  price_usd: number | null;
  price_last_updated: string | null;
};

type SetRecord = {
  id: string;
  name: string;
};

type CollectionRow = {
  card_id: string;
  quantity: number;
  price_usd: number | null;
  price_last_updated: string | null;
};

type CardImageRow = {
  card_id: string;
  storage_path: string;
};

type JustTcgListResponse<T> = {
  data?: T[];
  error?: {
    message?: string;
  };
};

type JustTcgSet = {
  id: string;
  name: string;
  game_id?: string;
  game?: string;
};

type JustTcgVariant = {
  price?: number | null;
  condition?: string | null;
  printing?: string | null;
  language?: string | null;
  price_history?: unknown;
  priceHistory?: unknown;
};

type JustTcgCard = {
  id: string;
  name: string;
  set: string;
  set_name?: string;
  number: string;
  variants?: JustTcgVariant[];
};

export type PriceHistoryPoint = {
  timestamp: string;
  price: number;
};

export type TopPricedCard = {
  id: string;
  name: string;
  number: string;
  setId: string;
  setName: string;
  priceUsd: number;
  quantity: number;
  totalValueUsd: number;
  priceLastUpdated: string | null;
  imageUrl: string | null;
  history: PriceHistoryPoint[];
  historyStatus: "available" | "unavailable";
  historyMessage: string | null;
};

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

function toPublicImageUrl(storagePath: string | null | undefined): string | null {
  if (!storagePath || !SUPABASE_URL) return null;
  const cleaned = storagePath.replace(/^\/+/, "");
  return `${SUPABASE_URL}/storage/v1/object/public/${STORAGE_BUCKET}/${cleaned}`;
}

function requireServerConfig() {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
  }

  if (!JUST_TCG_API_KEY) {
    throw new Error("Missing JUST_TCG_API_KEY");
  }
}

function shouldRefreshPrice(priceLastUpdated: string | null) {
  if (!priceLastUpdated) return true;

  const lastUpdatedMs = new Date(priceLastUpdated).getTime();
  if (Number.isNaN(lastUpdatedMs)) return true;

  return Date.now() - lastUpdatedMs > PRICE_REFRESH_WINDOW_MS;
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function normalizeCompact(value: string | null | undefined): string {
  return normalizeText(value).replace(/\s+/g, "");
}

function numberCandidates(value: string): string[] {
  const raw = value.trim();
  if (!raw) return [];

  const out = new Set<string>([raw]);
  const compact = raw.replace(/\s+/g, "");
  out.add(compact);

  const slashSplit = compact.split("/");
  if (slashSplit[0]) out.add(slashSplit[0]);

  const strippedLeadingZeros = slashSplit[0]?.replace(/^0+(\d)/, "$1");
  if (strippedLeadingZeros) out.add(strippedLeadingZeros);

  const alnumOnly = compact.replace(/[^a-zA-Z0-9]/g, "");
  if (alnumOnly) out.add(alnumOnly);

  return [...out].filter(Boolean);
}

function tokenSet(value: string): Set<string> {
  const normalized = normalizeText(value);
  return new Set(normalized ? normalized.split(/\s+/) : []);
}

function overlapScore(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;

  let matches = 0;
  for (const token of a) {
    if (b.has(token)) matches += 1;
  }

  return matches / Math.max(a.size, b.size);
}

async function fetchSupabaseCard(cardId: string): Promise<CardRecord | null> {
  const url = `${SUPABASE_URL}/rest/v1/cards?id=eq.${encodeURIComponent(
    cardId,
  )}&select=id,name,set_id,number:card_number,price_usd,price_last_updated&limit=1`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to load card details");
  }

  const rows = (await res.json()) as CardRecord[];
  return rows[0] ?? null;
}

async function fetchSupabaseSet(setId: string): Promise<SetRecord | null> {
  const url = `${SUPABASE_URL}/rest/v1/sets?id=eq.${encodeURIComponent(
    setId,
  )}&select=id,name&limit=1`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to load set details");
  }

  const rows = (await res.json()) as SetRecord[];
  return rows[0] ?? null;
}

async function fetchCollectionRows(userId: string): Promise<CollectionRow[]> {
  const url = `${SUPABASE_URL}/rest/v1/collections?user_id=eq.${encodeURIComponent(
    userId,
  )}&select=card_id,quantity,price_usd,price_last_updated`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to load collection");
  }

  return (await res.json()) as CollectionRow[];
}

async function fetchSupabaseCards(cardIds: string[]): Promise<CardRecord[]> {
  if (cardIds.length === 0) return [];

  const url = `${SUPABASE_URL}/rest/v1/cards?or=(${buildOrFilter(
    "id",
    cardIds,
  )})&select=id,name,set_id,number:card_number,price_usd,price_last_updated`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to load cards for collection");
  }

  return (await res.json()) as CardRecord[];
}

async function fetchSupabaseSets(setIds: string[]): Promise<SetRecord[]> {
  if (setIds.length === 0) return [];

  const url = `${SUPABASE_URL}/rest/v1/sets?or=(${buildOrFilter(
    "id",
    setIds,
  )})&select=id,name`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to load sets for collection");
  }

  return (await res.json()) as SetRecord[];
}

async function fetchCardImages(cardIds: string[]): Promise<CardImageRow[]> {
  if (cardIds.length === 0) return [];

  const url = `${SUPABASE_URL}/rest/v1/card_images?or=(${buildOrFilter(
    "card_id",
    cardIds,
  )})&select=card_id,storage_path`;
  const res = await fetch(url, {
    headers: supabaseHeaders(),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to load card images");
  }

  return (await res.json()) as CardImageRow[];
}

async function fetchJustTcg<T>(
  path: string,
  searchParams: Record<string, string | number | boolean | undefined>,
): Promise<T[]> {
  const url = new URL(`${JUST_TCG_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(searchParams)) {
    if (value === undefined) continue;
    url.searchParams.set(key, String(value));
  }

  const res = await fetch(url.toString(), {
    headers: {
      "x-api-key": JUST_TCG_API_KEY,
    },
    cache: "no-store",
  });

  const payload = (await res.json()) as JustTcgListResponse<T>;
  if (!res.ok) {
    throw new Error(payload.error?.message ?? `JustTCG request failed for ${path}`);
  }

  return payload.data ?? [];
}

function rankSetCandidate(candidate: JustTcgSet, input: { setId: string; setName: string }) {
  const localNameTokens = tokenSet(input.setName);
  const candidateNameTokens = tokenSet(candidate.name);
  const localSetIdCompact = normalizeCompact(input.setId);
  const candidateIdCompact = normalizeCompact(candidate.id);
  const candidateNameCompact = normalizeCompact(candidate.name);

  let score = 0;
  if (candidateIdCompact === localSetIdCompact) score += 10;
  if (candidateNameCompact === normalizeCompact(input.setName)) score += 8;
  if (candidateIdCompact.includes(localSetIdCompact) && localSetIdCompact) score += 4;
  if (localSetIdCompact.includes(candidateIdCompact) && candidateIdCompact) score += 3;

  score += overlapScore(localNameTokens, candidateNameTokens) * 5;

  return score;
}

async function resolveJustTcgSetId(input: {
  setId: string;
  setName: string;
}): Promise<string> {
  const queries = [
    input.setName,
    input.setId,
    `${input.setName} pokemon`,
  ].filter((value, index, arr) => value && arr.indexOf(value) === index);

  const candidates = new Map<string, JustTcgSet>();
  for (const query of queries) {
    const results = await fetchJustTcg<JustTcgSet>("/sets", {
      game: "pokemon",
      q: query,
    });

    for (const result of results) {
      candidates.set(result.id, result);
    }
  }

  if (candidates.size === 0) {
    throw new Error(
      `JustTCG set lookup failed for local set "${input.setName}" (${input.setId})`,
    );
  }

  const ranked = [...candidates.values()].sort(
    (left, right) =>
      rankSetCandidate(right, input) - rankSetCandidate(left, input),
  );

  return ranked[0].id;
}

async function resolveJustTcgSet(input: {
  setId: string;
  setName: string;
}): Promise<JustTcgSet> {
  const queries = [
    input.setName,
    input.setId,
    `${input.setName} pokemon`,
  ].filter((value, index, arr) => value && arr.indexOf(value) === index);

  const candidates = new Map<string, JustTcgSet>();
  for (const query of queries) {
    const results = await fetchJustTcg<JustTcgSet>("/sets", {
      game: "pokemon",
      q: query,
    });

    for (const result of results) {
      candidates.set(result.id, result);
    }
  }

  if (candidates.size === 0) {
    throw new Error(
      `JustTCG set lookup failed for local set "${input.setName}" (${input.setId})`,
    );
  }

  const ranked = [...candidates.values()].sort(
    (left, right) =>
      rankSetCandidate(right, input) - rankSetCandidate(left, input),
  );

  return ranked[0];
}

async function tryResolveJustTcgSet(input: {
  setId: string;
  setName: string;
}): Promise<JustTcgSet | null> {
  try {
    return await resolveJustTcgSet(input);
  } catch {
    return null;
  }
}

function rankCardCandidate(candidate: JustTcgCard, input: {
  cardName: string;
  cardNumber: string;
  setName: string;
}) {
  const localNameCompact = normalizeCompact(input.cardName);
  const candidateNameCompact = normalizeCompact(candidate.name);
  const localNumberCandidates = new Set(numberCandidates(input.cardNumber).map(normalizeCompact));
  const candidateNumberCompact = normalizeCompact(candidate.number);

  let score = 0;
  if (candidateNameCompact === localNameCompact) score += 10;
  if (candidateNumberCompact && localNumberCandidates.has(candidateNumberCompact)) score += 8;
  if (normalizeCompact(candidate.set_name) === normalizeCompact(input.setName)) score += 4;
  score += overlapScore(tokenSet(input.cardName), tokenSet(candidate.name)) * 5;

  for (const numberCandidate of localNumberCandidates) {
    if (!numberCandidate) continue;
    if (candidateNumberCompact.includes(numberCandidate)) score += 2;
    if (numberCandidate.includes(candidateNumberCompact) && candidateNumberCompact) score += 1;
  }

  return score;
}

async function searchCardsByNumber(
  justTcgSetId: string,
  cardNumber: string,
): Promise<JustTcgCard[]> {
  const aggregated = new Map<string, JustTcgCard>();

  for (const candidate of numberCandidates(cardNumber)) {
    const results = await fetchJustTcg<JustTcgCard>("/cards", {
      game: "pokemon",
      set: justTcgSetId,
      number: candidate,
      limit: 20,
    });

    for (const result of results) {
      aggregated.set(result.id, result);
    }
  }

  return [...aggregated.values()];
}

async function searchCardsByName(
  justTcgSetId: string,
  cardName: string,
): Promise<JustTcgCard[]> {
  return fetchJustTcg<JustTcgCard>("/cards", {
    game: "pokemon",
    set: justTcgSetId,
    q: cardName,
    limit: 20,
  });
}

async function fetchCardsForSet(justTcgSetId: string): Promise<JustTcgCard[]> {
  return fetchJustTcg<JustTcgCard>("/cards", {
    game: "pokemon",
    set: justTcgSetId,
    orderBy: "price",
    order: "desc",
    limit: 250,
    include_price_history: true,
  });
}

async function resolveJustTcgCard(
  justTcgSetId: string,
  input: {
    cardName: string;
    cardNumber: string;
    setName: string;
  },
): Promise<JustTcgCard> {
  const setCards = await fetchCardsForSet(justTcgSetId);
  const candidates = new Map<string, JustTcgCard>();

  for (const match of setCards) {
    candidates.set(match.id, match);
  }

  if (candidates.size === 0) {
    throw new Error(
      `JustTCG card lookup failed for "${input.cardName}" (#${input.cardNumber})`,
    );
  }

  const ranked = [...candidates.values()].sort(
    (left, right) => rankCardCandidate(right, input) - rankCardCandidate(left, input),
  );

  return ranked[0];
}

function conditionRank(condition: string | null | undefined): number {
  const normalized = normalizeText(condition);
  switch (normalized) {
    case "near mint":
    case "nm":
      return 6;
    case "lightly played":
    case "lp":
      return 5;
    case "moderately played":
    case "mp":
      return 4;
    case "heavily played":
    case "hp":
      return 3;
    case "damaged":
    case "dmg":
      return 2;
    case "sealed":
    case "s":
      return 1;
    default:
      return 0;
  }
}

function printingRank(printing: string | null | undefined): number {
  const normalized = normalizeText(printing);
  if (normalized === "normal") return 3;
  if (normalized.includes("holo")) return 2;
  if (normalized) return 1;
  return 0;
}

function languageRank(language: string | null | undefined): number {
  const normalized = normalizeText(language);
  if (normalized === "english") return 2;
  if (normalized) return 1;
  return 0;
}

function pickRepresentativeVariantPrice(card: JustTcgCard): number {
  const pricedVariants = (card.variants ?? []).filter(
    (variant): variant is JustTcgVariant & { price: number } =>
      typeof variant.price === "number" && Number.isFinite(variant.price),
  );

  if (pricedVariants.length === 0) {
    throw new Error(`JustTCG returned no priced variants for "${card.name}"`);
  }

  pricedVariants.sort((left, right) => {
    const scoreLeft =
      languageRank(left.language) * 100 +
      conditionRank(left.condition) * 10 +
      printingRank(left.printing);
    const scoreRight =
      languageRank(right.language) * 100 +
      conditionRank(right.condition) * 10 +
      printingRank(right.printing);

    if (scoreRight !== scoreLeft) return scoreRight - scoreLeft;
    return left.price - right.price;
  });

  return Number(pricedVariants[0].price.toFixed(2));
}

function pickHighestPricedVariant(card: JustTcgCard): (JustTcgVariant & { price: number }) | null {
  const pricedVariants = (card.variants ?? []).filter(
    (variant): variant is JustTcgVariant & { price: number } =>
      typeof variant.price === "number" && Number.isFinite(variant.price),
  );

  if (pricedVariants.length === 0) return null;

  return pricedVariants.reduce((best, current) =>
    current.price > best.price ? current : best,
  );
}

function normalizeHistoryEntries(history: unknown): PriceHistoryPoint[] {
  if (!Array.isArray(history)) return [];

  const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const points = history
    .map((entry) => {
      if (!entry || typeof entry !== "object") return null;

      const record = entry as Record<string, unknown>;
      const rawPrice = record.price ?? record.value ?? record.close ?? record.y;
      const rawTimestamp =
        record.timestamp ??
        record.time ??
        record.date ??
        record.datetime ??
        record.x;

      const price =
        typeof rawPrice === "number"
          ? rawPrice
          : typeof rawPrice === "string"
            ? Number(rawPrice)
            : Number.NaN;

      let timestamp: string | null = null;
      if (typeof rawTimestamp === "number") {
        const millis = rawTimestamp > 1_000_000_000_000 ? rawTimestamp : rawTimestamp * 1000;
        timestamp = new Date(millis).toISOString();
      } else if (typeof rawTimestamp === "string") {
        const parsed = new Date(rawTimestamp);
        if (!Number.isNaN(parsed.getTime())) {
          timestamp = parsed.toISOString();
        }
      }

      if (!timestamp || !Number.isFinite(price)) return null;

      return {
        timestamp,
        price: Number(price.toFixed(2)),
      };
    })
    .filter((entry): entry is PriceHistoryPoint => Boolean(entry))
    .filter((entry) => new Date(entry.timestamp).getTime() >= sevenDaysAgo)
    .sort(
      (left, right) =>
        new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
    );

  return points;
}

async function updateCardPrice(cardId: string, priceUsd: number): Promise<void> {
  const now = new Date().toISOString();
  const url = `${SUPABASE_URL}/rest/v1/cards?id=eq.${encodeURIComponent(cardId)}`;
  const res = await fetch(url, {
    method: "PATCH",
    headers: supabaseHeaders(),
    body: JSON.stringify({
      price_usd: priceUsd,
      price_last_updated: now,
    }),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to update card price");
  }
}

export async function refreshCardPriceIfNeeded(cardId: string): Promise<CardRecord> {
  requireServerConfig();

  const card = await fetchSupabaseCard(cardId);
  if (!card) {
    throw new Error(`Card ${cardId} was not found`);
  }

  if (!shouldRefreshPrice(card.price_last_updated)) {
    return card;
  }

  const set = await fetchSupabaseSet(card.set_id);
  if (!set) {
    throw new Error(`Set ${card.set_id} was not found`);
  }

  const justTcgSetId = await resolveJustTcgSetId({
    setId: set.id,
    setName: set.name,
  });
  const justTcgCard = await resolveJustTcgCard(justTcgSetId, {
    cardName: card.name,
    cardNumber: card.number,
    setName: set.name,
  });
  const nextPrice = pickRepresentativeVariantPrice(justTcgCard);

  await updateCardPrice(cardId, nextPrice);

  const updatedCard = await fetchSupabaseCard(cardId);
  if (!updatedCard) {
    throw new Error(`Card ${cardId} was not found after price update`);
  }

  return updatedCard;
}

export async function fetchTopValuableCardsWithHistory(
  setQuery: string,
  limit = 3,
): Promise<{
  setId: string;
  setName: string;
  cards: TopPricedCard[];
}> {
  requireServerConfig();

  const resolvedSet = await resolveJustTcgSet({
    setId: setQuery,
    setName: setQuery,
  });

  const cards = await fetchJustTcg<JustTcgCard>("/cards", {
    game: "pokemon",
    set: resolvedSet.id,
    orderBy: "price",
    order: "desc",
    limit,
    include_price_history: true,
  });

  const topCards = cards
    .map<TopPricedCard | null>((card) => {
      const highestPricedVariant = pickHighestPricedVariant(card);
      if (!highestPricedVariant) return null;

      const history = normalizeHistoryEntries(
        highestPricedVariant.price_history ?? highestPricedVariant.priceHistory,
      );

      return {
        id: card.id,
        name: card.name,
        number: card.number,
        setId: resolvedSet.id,
        setName: resolvedSet.name,
        priceUsd: Number(highestPricedVariant.price.toFixed(2)),
        quantity: 1,
        totalValueUsd: Number(highestPricedVariant.price.toFixed(2)),
        priceLastUpdated: null,
        imageUrl: null,
        history,
        historyStatus: history.length > 0 ? "available" : "unavailable",
        historyMessage:
          history.length > 0 ? null : "JustTCG returned no 7-day history.",
      };
    })
    .filter((card): card is TopPricedCard => card !== null)
    .slice(0, limit);

  return {
    setId: resolvedSet.id,
    setName: resolvedSet.name,
    cards: topCards,
  };
}

export async function fetchCollectionTopValuableCardsWithHistory(
  userId: string,
  limit = 3,
): Promise<{
  cards: TopPricedCard[];
}> {
  requireServerConfig();

  const collectionRows = await fetchCollectionRows(userId);
  if (collectionRows.length === 0) {
    return { cards: [] };
  }

  const uniqueCardIds = [...new Set(collectionRows.map((row) => row.card_id))];
  const initialCards = await fetchSupabaseCards(uniqueCardIds);
  const staleCardIds = initialCards
    .filter((card) => shouldRefreshPrice(card.price_last_updated))
    .map((card) => card.id);

  for (const staleCardId of staleCardIds) {
    try {
      await refreshCardPriceIfNeeded(staleCardId);
    } catch {
      // Keep the dashboard usable even if an external refresh fails.
    }
  }

  const cards = await fetchSupabaseCards(uniqueCardIds);
  const sets = await fetchSupabaseSets([...new Set(cards.map((card) => card.set_id))]);
  const images = await fetchCardImages(uniqueCardIds);
  const cardsById = new Map(cards.map((card) => [card.id, card]));
  const setsById = new Map(sets.map((set) => [set.id, set]));
  const imageByCardId = new Map<string, string>();
  for (const image of images) {
    if (!imageByCardId.has(image.card_id)) {
      imageByCardId.set(image.card_id, image.storage_path);
    }
  }

  const rankedCollectionCards = collectionRows
    .map((row) => {
      const card = cardsById.get(row.card_id);
      if (!card) return null;

      return {
        card,
        quantity: row.quantity,
        priceUsd: card.price_usd ?? row.price_usd ?? null,
        priceLastUpdated: card.price_last_updated ?? row.price_last_updated ?? null,
        setName: setsById.get(card.set_id)?.name ?? card.set_id,
      };
    })
    .filter(
      (
        entry,
      ): entry is {
        card: CardRecord;
        quantity: number;
        priceUsd: number | null;
        priceLastUpdated: string | null;
        setName: string;
      } => Boolean(entry),
    )
    .sort((left, right) => (right.priceUsd ?? -1) - (left.priceUsd ?? -1))
    .slice(0, limit);

  const cardsWithHistory = await Promise.all(
    rankedCollectionCards.map(async (entry) => {
      let history: PriceHistoryPoint[] = [];
      let historyStatus: TopPricedCard["historyStatus"] = "unavailable";
      let historyMessage: string | null = "No external history available.";

      try {
        const justTcgSet = await tryResolveJustTcgSet({
          setId: entry.card.set_id,
          setName: entry.setName,
        });

        if (!justTcgSet) {
          throw new Error("Could not resolve this set in JustTCG.");
        }

        const justTcgCard = await resolveJustTcgCard(justTcgSet.id, {
          cardName: entry.card.name,
          cardNumber: entry.card.number,
          setName: entry.setName,
        });

        const highestPricedVariant = justTcgCard
          ? pickHighestPricedVariant(justTcgCard)
          : null;

        history = highestPricedVariant
          ? normalizeHistoryEntries(
              highestPricedVariant.price_history ?? highestPricedVariant.priceHistory,
            )
          : [];
        historyStatus = history.length > 0 ? "available" : "unavailable";
        historyMessage =
          history.length > 0
            ? null
            : "JustTCG returned no 7-day history for the matched card.";
      } catch (error) {
        historyStatus = "unavailable";
        historyMessage = "External 7-day history is unavailable for this card.";
      }

      return {
        id: entry.card.id,
        name: entry.card.name,
        number: entry.card.number,
        setId: entry.card.set_id,
        setName: entry.setName,
        priceUsd: entry.priceUsd ?? 0,
        quantity: entry.quantity,
        totalValueUsd: Number(((entry.priceUsd ?? 0) * entry.quantity).toFixed(2)),
        priceLastUpdated: entry.priceLastUpdated,
        imageUrl: toPublicImageUrl(imageByCardId.get(entry.card.id) ?? null),
        history,
        historyStatus,
        historyMessage,
      } satisfies TopPricedCard;
    }),
  );

  return {
    cards: cardsWithHistory,
  };
}
