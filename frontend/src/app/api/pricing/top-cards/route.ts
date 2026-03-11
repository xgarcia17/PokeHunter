import { NextResponse } from "next/server";
import { fetchCollectionTopValuableCardsWithHistory } from "@/lib/cardPricing";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const userId = searchParams.get("userId")?.trim() ?? "";
  const includeHistory = searchParams.get("includeHistory") === "1";
  const refreshStalePrices = searchParams.get("refreshStalePrices") === "1";

  if (!userId) {
    return NextResponse.json(
      { error: "userId is required" },
      { status: 400 },
    );
  }

  try {
    const result = await fetchCollectionTopValuableCardsWithHistory(userId, null, {
      refreshStalePrices,
      includeHistory,
    });
    return NextResponse.json({ ok: true, ...result });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to load pricing data",
      },
      { status: 502 },
    );
  }
}
