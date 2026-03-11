"use client";

import { useEffect, useMemo, useState } from "react";
import NavBar from "@/components/navbar";
import { supabase } from "@/lib/supabaseClient";

type PriceHistoryPoint = {
  timestamp: string;
  price: number;
};

type TopPricedCard = {
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
  tcgdexPricing: {
    updated: string | null;
    eurToUsdRate: number;
    avgUsd: number | null;
    lowUsd: number | null;
    trendUsd: number | null;
  } | null;
};

type PricingResponse =
  | {
      ok: true;
      cards: TopPricedCard[];
    }
  | {
      error: string;
    };

function formatPrice(price: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(price);
}

function formatNullablePrice(price: number | null) {
  return price === null ? "N/A" : formatPrice(price);
}

function formatTimestamp(value: string | null) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
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

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function PriceHistoryChart({
  points,
  color,
}: {
  points: PriceHistoryPoint[];
  color: string;
}) {
  const width = 560;
  const height = 220;
  const padding = 20;

  const chartData = useMemo(() => {
    if (points.length === 0) return null;

    const timestamps = points.map((point) => new Date(point.timestamp).getTime());
    const prices = points.map((point) => point.price);
    const minX = Math.min(...timestamps);
    const maxX = Math.max(...timestamps);
    const minY = Math.min(...prices);
    const maxY = Math.max(...prices);
    const xRange = maxX - minX || 1;
    const yRange = maxY - minY || 1;

    const polyline = points
      .map((point) => {
        const x =
          padding +
          ((new Date(point.timestamp).getTime() - minX) / xRange) *
            (width - padding * 2);
        const y =
          height -
          padding -
          ((point.price - minY) / yRange) * (height - padding * 2);
        return `${x},${y}`;
      })
      .join(" ");

    return { minY, maxY, polyline, minX, maxX };
  }, [points]);

  if (!chartData) {
    return (
      <div className="h-[220px] flex items-center justify-center rounded-xl border border-dashed border-gray-300 text-gray-500">
        No 7-day price history available.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto overflow-visible"
        role="img"
        aria-label="Price history chart"
      >
        <line
          x1={padding}
          y1={height - padding}
          x2={width - padding}
          y2={height - padding}
          stroke="#cbd5e1"
          strokeWidth="1"
        />
        <line
          x1={padding}
          y1={padding}
          x2={padding}
          y2={height - padding}
          stroke="#cbd5e1"
          strokeWidth="1"
        />
        <polyline
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinejoin="round"
          strokeLinecap="round"
          points={chartData.polyline}
        />
        {points.map((point) => {
          const x =
            padding +
            ((new Date(point.timestamp).getTime() - chartData.minX) /
              (chartData.maxX - chartData.minX || 1)) *
              (width - padding * 2);
          const y =
            height -
            padding -
            ((point.price - chartData.minY) / (chartData.maxY - chartData.minY || 1)) *
              (height - padding * 2);

          return <circle key={point.timestamp} cx={x} cy={y} r="4" fill={color} />;
        })}
      </svg>

      <div className="mt-3 flex items-center justify-between text-xs text-gray-600">
        <span>{formatPrice(chartData.minY)}</span>
        <span>{formatShortDate(points[0].timestamp)}</span>
        <span>{formatShortDate(points[points.length - 1].timestamp)}</span>
        <span>{formatPrice(chartData.maxY)}</span>
      </div>
    </div>
  );
}

export default function PricingPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cards, setCards] = useState<TopPricedCard[]>([]);

  useEffect(() => {
    async function loadPricing() {
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

      void fetch("/api/pricing/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId }),
        keepalive: true,
      }).catch(() => {
        // Do not block page render if background refresh cannot be triggered.
      });

      setLoading(true);
      setError(null);

      try {
        const res = await fetch(
          `/api/pricing/top-cards?userId=${encodeURIComponent(userId)}`,
          { cache: "no-store" },
        );
        const payload = (await res.json()) as PricingResponse & {
          ok?: boolean;
          cards?: TopPricedCard[];
        };
        if (!res.ok) {
          throw new Error(payload?.error ?? "Failed to load pricing");
        }
        setCards((payload?.cards ?? []) as TopPricedCard[]);
      } catch (fetchError) {
        setCards([]);
        setError(
          fetchError instanceof Error ? fetchError.message : "Failed to load pricing",
        );
      } finally {
        setLoading(false);
      }
    }

    void loadPricing();
  }, []);

  const colors = ["#ef4444", "#2563eb", "#16a34a"];
  const dashboardTotals = useMemo(() => {
    const totalTrackedValue = cards.reduce((sum, card) => sum + card.totalValueUsd, 0);
    return { totalTrackedValue };
  }, [cards]);

  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      <NavBar currentPage={"pricing"} />
      <div className="flex-1 my-4 overflow-auto max-w-7xl mx-auto w-[80%] px-8 py-6 text-black">
        <div className="max-w-4xl">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">
            Most Valuable Cards In Your Collection
          </h1>
          <p className="mt-2 text-sm md:text-base text-gray-600">
            All cards in your collection, ranked by saved value with live TCGdex
            pricing in USD.
          </p>
        </div>

        {loading && <div className="mt-6 text-gray-700">Loading pricing data...</div>}
        {error && <div className="mt-6 text-red-600">{error}</div>}
        {!loading && !error && cards.length === 0 && (
          <div className="mt-6 text-gray-700">No priced cards in your collection yet.</div>
        )}

        {!loading && !error && cards.length > 0 && (
          <div className="mt-8 space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Cards Ranked
                </div>
                <div className="mt-2 text-3xl font-bold">{cards.length}</div>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                  Tracked Value
                </div>
                <div className="mt-2 text-3xl font-bold">
                  {formatPrice(dashboardTotals.totalTrackedValue)}
                </div>
              </div>
            </div>

            {cards.map((card, index) => (
              <div
                key={card.id}
                className={`rounded-[28px] border bg-white p-6 shadow-sm ${metricTone(index).border}`}
              >
                <div className="flex flex-col gap-5">
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div className="flex items-start gap-4">
                      <div
                        className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-lg font-bold text-white ${metricTone(index).ring}`}
                      >
                        #{index + 1}
                      </div>
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                          Collection Leaderboard
                        </div>
                        <h2 className="mt-1 text-2xl font-semibold">{card.name}</h2>
                        <div className="mt-1 text-sm text-gray-600">
                          #{card.number} • {card.setName}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
                    <div className={`rounded-3xl border border-dashed p-5 ${metricTone(index).border} ${metricTone(index).soft}`}>
                      <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                        Snapshot
                      </div>
                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        <div className="rounded-2xl bg-white/80 px-4 py-3">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                            Card ID
                          </div>
                          <div className="mt-1 break-all text-sm font-medium text-gray-900">
                            {card.id}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-white/80 px-4 py-3">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                            Set ID
                          </div>
                          <div className="mt-1 text-sm font-medium text-gray-900">
                            {card.setId}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-white/80 px-4 py-3 sm:col-span-2">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">
                            TCGdex Retrieved At
                          </div>
                          <div className="mt-1 text-sm font-medium text-gray-900">
                            {formatTimestamp(card.tcgdexPricing?.updated ?? null)}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-white px-4 py-4 border border-emerald-200">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
                            TCGdex Avg (USD)
                          </div>
                          <div className="mt-1 text-3xl font-extrabold text-gray-900 leading-none">
                            {formatNullablePrice(card.tcgdexPricing?.avgUsd ?? null)}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-white px-4 py-4 border border-blue-200">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-700">
                            TCGdex Low (USD)
                          </div>
                          <div className="mt-1 text-3xl font-extrabold text-gray-900 leading-none">
                            {formatNullablePrice(card.tcgdexPricing?.lowUsd ?? null)}
                          </div>
                        </div>
                        <div className="rounded-2xl bg-white px-4 py-4 border border-amber-200 sm:col-span-2">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700">
                            TCGdex Trend (USD)
                          </div>
                          <div className="mt-1 text-4xl font-extrabold text-gray-900 leading-none">
                            {formatNullablePrice(card.tcgdexPricing?.trendUsd ?? null)}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-3xl border border-gray-200 bg-gray-50 p-5">
                      <div className="text-xs font-semibold uppercase tracking-[0.2em] text-gray-500">
                        Card Image
                      </div>
                      <div className="mt-4 overflow-hidden rounded-2xl border border-gray-200 bg-white">
                        {card.imageUrl ? (
                          <img
                            src={card.imageUrl}
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
                  </div>

                  {card.historyStatus === "available" && card.history.length > 0 && (
                    <div className="mt-1">
                      <PriceHistoryChart
                        points={card.history}
                        color={colors[index % colors.length]}
                      />
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
