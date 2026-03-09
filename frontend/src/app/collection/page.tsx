"use client";

import { useEffect, useState } from "react";
import NavBar from "@/components/navbar";
import { supabase } from "@/lib/supabaseClient";

type CollectionItem = {
  card_id: string;
  quantity: number;
  card_name: string;
  set_name: string;
  image_url: string | null;
};

export default function CollectionPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<CollectionItem[]>([]);

  useEffect(() => {
    async function loadCollection() {
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

      try {
        const res = await fetch(
          `/api/collections/list?userId=${encodeURIComponent(userId)}`,
          { cache: "no-store" },
        );
        const payload = await res.json();
        if (!res.ok) {
          throw new Error(payload?.error ?? "Failed to load collection");
        }
        setItems((payload?.items ?? []) as CollectionItem[]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load collection");
      } finally {
        setLoading(false);
      }
    }

    void loadCollection();
  }, []);

  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      <NavBar currentPage={"collection"} />
      <div className="flex-1 my-4 overflow-auto max-w-7xl mx-auto w-[80%] px-8 py-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-5">
          My Collection
        </h1>

        {loading && <div className="text-gray-700">Loading collection...</div>}
        {error && <div className="text-red-600">{error}</div>}

        {!loading && !error && items.length === 0 && (
          <div className="text-gray-700">No cards in your collection yet.</div>
        )}

        {!loading && !error && items.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {items.map((item) => (
              <div
                key={item.card_id}
                className="bg-white rounded-xl border border-gray-200 shadow-sm p-3 text-black"
              >
                {item.image_url ? (
                  <img
                    src={item.image_url}
                    alt={item.card_name}
                    className="w-full h-64 object-contain rounded-md bg-gray-50 border"
                  />
                ) : (
                  <div className="w-full h-64 flex items-center justify-center rounded-md bg-gray-100 text-gray-500 border">
                    No image
                  </div>
                )}

                <div className="mt-3">
                  <div className="font-semibold text-sm md:text-base">
                    {item.card_name}
                  </div>
                  <div className="text-xs md:text-sm text-gray-600 mt-1">
                    {item.set_name}
                  </div>
                  <div className="text-xs md:text-sm text-gray-700 mt-1">
                    Qty: {item.quantity}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
