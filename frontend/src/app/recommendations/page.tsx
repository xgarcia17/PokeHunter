"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import NavBar from "@/components/navbar";
import { supabase } from "@/lib/supabaseClient";

type PokemonAffinity = {
  name: string;
  count: number;
};

type SetAffinity = {
  set_id: string;
  set_name: string;
  count: number;
};

type RarityAffinity = {
  rarity: string;
  count: number;
};

type RecommendationProfile = {
  budget_usd: number;
  collection_size: number;
  top_pokemon: PokemonAffinity[];
  top_sets: SetAffinity[];
  top_rarities: RarityAffinity[];
  finish_affinity_status: string;
};

type RecommendationCard = {
  card_id: string;
  name: string;
  set_id: string;
  set_name: string;
  card_number: string;
  price_usd: number | null;
  image_url: string | null;
  reason: string;
  driver_key: string;
};

type RecommendationGroup = {
  key: string;
  title: string;
  focus: string;
  recommendations: RecommendationCard[];
};

type RecommendationPayload = {
  source: string;
  budget_usd: number;
  profile: RecommendationProfile;
  profile_summary: string;
  recommendations: RecommendationCard[];
  recommendation_groups: RecommendationGroup[];
};

type RecommendationResponse =
  | ({ ok: true } & RecommendationPayload)
  | { error: string };

const LOADING_MESSAGES = [
  "Reading your collection",
  "Finding matching sets and Pokemon",
  "Ranking the best next cards",
  "Writing recommendation notes",
] as const;

function formatPrice(price: number | null | undefined) {
  if (typeof price !== "number") return "N/A";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(price);
}

function metricTone(index: number) {
  return [
    {
      border: "border-rose-200",
      ring: "from-rose-500 to-orange-400",
      soft: "bg-rose-50",
      text: "text-rose-700",
    },
    {
      border: "border-blue-200",
      ring: "from-blue-500 to-cyan-400",
      soft: "bg-blue-50",
      text: "text-blue-700",
    },
    {
      border: "border-emerald-200",
      ring: "from-emerald-500 to-lime-400",
      soft: "bg-emerald-50",
      text: "text-emerald-700",
    },
  ][index % 3];
}

function affinityLabel(label: string, count: number) {
  return `${label} (${count})`;
}

const GROUP_FALLBACKS: RecommendationGroup[] = [
  {
    key: "pokemon_affinity",
    title: "Pokemon Affinity",
    focus: "Cards that match the Pokemon you collect most.",
    recommendations: [],
  },
  {
    key: "set_affinity",
    title: "Set Affinity",
    focus: "Cards that deepen the sets you already favor.",
    recommendations: [],
  },
  {
    key: "rarity_affinity",
    title: "Rarity Affinity",
    focus: "Cards that match the rarities you tend to keep.",
    recommendations: [],
  },
];

export default function RecommendationsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<RecommendationPayload | null>(null);
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);

  useEffect(() => {
    if (!loading) {
      setLoadingMessageIndex(0);
      return;
    }

    const intervalId = window.setInterval(() => {
      setLoadingMessageIndex(
        (current) => (current + 1) % LOADING_MESSAGES.length,
      );
    }, 1200);

    return () => window.clearInterval(intervalId);
  }, [loading]);

  const loadRecommendations = useCallback(async (forceRefresh = false) => {
    if (!supabase) {
      setError(
        "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY.",
      );
      setLoading(false);
      return;
    }

    const { data } = await supabase.auth.getSession();
    const userId = data.session?.user.id;
    if (!userId) {
      setError("Please sign in on the Scan page first.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setLoadingMessageIndex(0);

    try {
      const params = new URLSearchParams({
        userId,
      });
      if (forceRefresh) {
        params.set("forceRefresh", "1");
      }

      const res = await fetch(`/api/recommendations?${params.toString()}`, {
        cache: "no-store",
      });
      const nextPayload = (await res.json()) as RecommendationResponse;
      if (!res.ok || !("ok" in nextPayload && nextPayload.ok)) {
        throw new Error(
          "error" in nextPayload
            ? nextPayload.error
            : "Failed to load recommendations",
        );
      }
      setPayload(nextPayload);
    } catch (fetchError) {
      setPayload(null);
      setError(
        fetchError instanceof Error
          ? fetchError.message
          : "Failed to load recommendations",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecommendations();
  }, [loadRecommendations]);

  const summary = useMemo(() => {
    const profile = payload?.profile;
    return {
      budget: payload?.budget_usd ?? 1000,
      recommendationCount: payload?.recommendations.length ?? 0,
      favoritePokemon: profile?.top_pokemon[0]?.name ?? "N/A",
      favoriteSet: profile?.top_sets[0]?.set_name ?? "N/A",
      favoriteRarity: profile?.top_rarities[0]?.rarity ?? "N/A",
    };
  }, [payload]);

  const profile = payload?.profile;
  const recommendationGroups = useMemo(() => {
    if (payload?.recommendation_groups?.length) {
      return payload.recommendation_groups;
    }

    const flatRecommendations = payload?.recommendations ?? [];
    return GROUP_FALLBACKS.map((group, index) => {
      const driverMatches = flatRecommendations.filter(
        (card) => card.driver_key === group.key,
      );
      return {
        ...group,
        recommendations:
          driverMatches.length > 0
            ? driverMatches
            : flatRecommendations.slice(index * 5, index * 5 + 5),
      };
    });
  }, [payload]);

  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      <NavBar currentPage={"recommendations"} />
      <div className="flex-1 my-4 overflow-auto max-w-7xl mx-auto w-[80%] px-8 py-6 text-black">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-4xl">
            <h1 className="text-2xl md:text-3xl font-bold text-gray-900">
              What You Should Collect Next
            </h1>
            <p className="mt-2 text-sm md:text-base text-gray-600">
              We infer the themes in your collection, build a shortlist from your
              catalog, and rank the next cards that best fit your current taste and
              budget.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadRecommendations(true)}
            disabled={loading}
            className="inline-flex h-11 items-center justify-center rounded-2xl border border-gray-200 bg-white px-4 text-sm font-semibold text-gray-800 shadow-sm transition hover:border-gray-300 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Refreshing..." : "Refresh Recommendations"}
          </button>
        </div>

        {loading && (
          <div className="mt-6 max-w-2xl rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 text-white shadow-sm">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Building your recommendations
                </div>
                <div className="mt-2 text-xl font-semibold text-gray-900">
                  {LOADING_MESSAGES[loadingMessageIndex]}
                </div>
                <p className="mt-2 text-sm leading-6 text-gray-600">
                  This can take a moment while we read your collection, compare
                  likely candidates, and prepare the final recommendation notes.
                </p>
              </div>
            </div>
          </div>
        )}
        {error && <div className="mt-6 text-red-600">{error}</div>}
        {!loading && !error && payload && payload.recommendations.length === 0 && (
          <div className="mt-6 rounded-2xl border border-gray-200 bg-white p-6 text-gray-700 shadow-sm">
            Not enough collection signal is available yet. Add more cards to your
            collection, then refresh recommendations.
          </div>
        )}

        {!loading && !error && payload && payload.recommendations.length > 0 && (
          <div className="mt-8 space-y-6">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Budget
                </div>
                <div className="mt-2 text-3xl font-bold">
                  {formatPrice(summary.budget)}
                </div>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Picks Ready
                </div>
                <div className="mt-2 text-3xl font-bold">
                  {summary.recommendationCount}
                </div>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Favorite Pokemon
                </div>
                <div className="mt-2 text-3xl font-bold break-words">
                  {summary.favoritePokemon}
                </div>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Favorite Set
                </div>
                <div className="mt-2 text-3xl font-bold break-words">
                  {summary.favoriteSet}
                </div>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.15fr_1.85fr]">
              <div className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Collector Profile
                </div>
                <div className="mt-4 space-y-5">
                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      Pokemon Affinity
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(profile?.top_pokemon ?? []).map((item) => (
                        <span
                          key={item.name}
                          className="rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700"
                        >
                          {affinityLabel(item.name, item.count)}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      Set Affinity
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(profile?.top_sets ?? []).map((item) => (
                        <span
                          key={item.set_id}
                          className="rounded-full bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700"
                        >
                          {affinityLabel(item.set_name, item.count)}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      Rarity Affinity
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(profile?.top_rarities ?? []).map((item) => (
                        <span
                          key={item.rarity}
                          className="rounded-full bg-rose-50 px-3 py-1 text-sm font-medium text-rose-700"
                        >
                          {affinityLabel(item.rarity, item.count)}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600">
                    Finish affinity is intentionally omitted in v1 because owned
                    finish and printing data are not stored in the collection
                    schema yet.
                  </div>
                </div>
              </div>

              <div className="rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Recommendation Outlook
                </div>
                <p className="mt-4 text-lg leading-8 text-gray-800">
                  {payload.profile_summary}
                </p>
                <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  <div className="rounded-2xl bg-gray-50 px-4 py-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                      Collection Size
                    </div>
                    <div className="mt-1 text-lg font-bold text-gray-900">
                      {profile?.collection_size ?? 0}
                    </div>
                  </div>
                  <div className="rounded-2xl bg-gray-50 px-4 py-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                      Top Rarity
                    </div>
                    <div className="mt-1 text-lg font-bold text-gray-900 break-words">
                      {summary.favoriteRarity}
                    </div>
                  </div>
                  <div className="rounded-2xl bg-gray-900 px-4 py-3 text-white">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/70">
                      Budget Policy
                    </div>
                    <div className="mt-1 text-sm font-semibold">
                      Soft cap with unknown prices still allowed
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {recommendationGroups.map((group, groupIndex) => {
              const tone = metricTone(groupIndex);

              return (
                <section key={group.key} className="space-y-4">
                  <div
                    className={`rounded-[28px] border bg-white px-6 py-5 shadow-sm ${tone.border}`}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                          Recommendation Section
                        </div>
                        <h2 className="mt-1 text-2xl font-semibold text-gray-900">
                          {group.title}
                        </h2>
                        <p className="mt-2 text-sm leading-6 text-gray-600">
                          {group.focus}
                        </p>
                      </div>
                      <div
                        className={`inline-flex rounded-full px-4 py-2 text-sm font-semibold ${tone.soft} ${tone.text}`}
                      >
                        {group.recommendations.length} picks
                      </div>
                    </div>
                  </div>

                  {group.recommendations.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-6 py-5 text-sm text-gray-600 shadow-sm">
                      Not enough unique cards matched this affinity bucket yet.
                    </div>
                  )}

                  {group.recommendations.map((card, cardIndex) => {
                    return (
                      <div
                        key={`${group.key}-${card.card_id}`}
                        className={`rounded-[28px] border bg-white p-6 shadow-sm ${tone.border}`}
                      >
                        <div className="flex flex-col gap-5">
                          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                            <div className="flex items-start gap-4">
                              <div
                                className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-lg font-bold text-white ${tone.ring}`}
                              >
                                #{cardIndex + 1}
                              </div>
                              <div>
                                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                                  {group.title} Pick
                                </div>
                                <h3 className="mt-1 text-2xl font-semibold text-gray-900">
                                  {card.name}
                                </h3>
                                <div className="mt-1 text-sm text-gray-600">
                                  #{card.card_number} • {card.set_name}
                                </div>
                              </div>
                            </div>

                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-1">
                              <div className={`rounded-2xl px-4 py-3 ${tone.soft}`}>
                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                                  Price
                                </div>
                                <div className="mt-1 text-lg font-bold text-gray-900">
                                  {formatPrice(card.price_usd)}
                                </div>
                              </div>
                            </div>
                          </div>

                          <div className="grid gap-4 lg:grid-cols-[0.95fr_1.45fr]">
                            <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5">
                              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                                Card Image
                              </div>
                              <div className="mt-4 overflow-hidden rounded-2xl border border-gray-200 bg-white">
                                {card.image_url ? (
                                  <img
                                    src={card.image_url}
                                    alt={card.name}
                                    className="h-80 w-full object-contain bg-white"
                                  />
                                ) : (
                                  <div className="flex h-80 items-center justify-center text-sm text-gray-500">
                                    No image available.
                                  </div>
                                )}
                              </div>
                            </div>

                            <div
                              className={`rounded-3xl border border-dashed p-5 ${tone.border} ${tone.soft}`}
                            >
                              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                                Why This Card Next
                              </div>
                              <p className="mt-4 text-base leading-7 text-gray-800 break-words">
                                {card.reason}
                              </p>
                              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                                <div className="rounded-2xl bg-white/80 px-4 py-3">
                                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                                    Card ID
                                  </div>
                                  <div className="mt-1 break-all text-sm font-medium text-gray-900">
                                    {card.card_id}
                                  </div>
                                </div>
                                <div className="rounded-2xl bg-white/80 px-4 py-3">
                                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                                    Set ID
                                  </div>
                                  <div className="mt-1 text-sm font-medium text-gray-900">
                                    {card.set_id}
                                  </div>
                                </div>
                                <div className="rounded-2xl bg-white/80 px-4 py-3">
                                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                                    Card Number
                                  </div>
                                  <div className="mt-1 text-sm font-medium text-gray-900">
                                    {card.card_number}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
