"use client";

import { useEffect, useMemo, useState } from "react";
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
  rarity: string | null;
  price_usd: number | null;
  price_status: "under_budget" | "over_budget" | "unknown";
  image_url: string | null;
  reason: string;
};

type RecommendationPayload = {
  source: string;
  budget_usd: number;
  profile: RecommendationProfile;
  profile_summary: string;
  recommendations: RecommendationCard[];
};

type RecommendationResponse =
  | ({ ok: true } & RecommendationPayload)
  | { error: string };

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

function priceStatusTone(status: RecommendationCard["price_status"]) {
  switch (status) {
    case "under_budget":
      return {
        label: "Under Budget",
        pill: "bg-emerald-100 text-emerald-700 border border-emerald-200",
      };
    case "over_budget":
      return {
        label: "Over Budget",
        pill: "bg-amber-100 text-amber-700 border border-amber-200",
      };
    default:
      return {
        label: "Price Unknown",
        pill: "bg-slate-100 text-slate-700 border border-slate-200",
      };
  }
}

function affinityLabel(label: string, count: number) {
  return `${label} (${count})`;
}

export default function RecommendationsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<RecommendationPayload | null>(null);

  useEffect(() => {
    async function loadRecommendations() {
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

      try {
        const res = await fetch(
          `/api/recommendations?userId=${encodeURIComponent(userId)}`,
          { cache: "no-store" },
        );
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
    }

    void loadRecommendations();
  }, []);

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

  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      <NavBar currentPage={"recommendations"} />
      <div className="flex-1 my-4 overflow-auto max-w-7xl mx-auto w-[80%] px-8 py-6 text-black">
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

        {loading && (
          <div className="mt-6 text-gray-700">Loading recommendations...</div>
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

            {payload.recommendations.map((card, index) => {
              const tone = metricTone(index);
              const statusTone = priceStatusTone(card.price_status);

              return (
                <div
                  key={card.card_id}
                  className={`rounded-[28px] border bg-white p-6 shadow-sm ${tone.border}`}
                >
                  <div className="flex flex-col gap-5">
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div className="flex items-start gap-4">
                        <div
                          className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-lg font-bold text-white ${tone.ring}`}
                        >
                          #{index + 1}
                        </div>
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                            Recommended Next Pickup
                          </div>
                          <h2 className="mt-1 text-2xl font-semibold text-gray-900">
                            {card.name}
                          </h2>
                          <div className="mt-1 text-sm text-gray-600">
                            #{card.card_number} • {card.set_name}
                          </div>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                        <div className={`rounded-2xl px-4 py-3 ${tone.soft}`}>
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                            Price
                          </div>
                          <div className="mt-1 text-lg font-bold text-gray-900">
                            {formatPrice(card.price_usd)}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-gray-50 px-4 py-3">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                            Rarity
                          </div>
                          <div className="mt-1 text-sm font-bold text-gray-900 break-words">
                            {card.rarity ?? "Unknown"}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-gray-900 px-4 py-3 text-white col-span-2 sm:col-span-1">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/70">
                            Budget Fit
                          </div>
                          <div className="mt-2">
                            <span
                              className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${statusTone.pill}`}
                            >
                              {statusTone.label}
                            </span>
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
                          <div className="rounded-2xl bg-white/80 px-4 py-3">
                            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                              Price Status
                            </div>
                            <div className={`mt-1 text-sm font-semibold ${tone.text}`}>
                              {statusTone.label}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
