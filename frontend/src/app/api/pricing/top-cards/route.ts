import { NextResponse } from "next/server";
import { fetchCollectionTopValuableCardsWithHistory } from "@/lib/cardPricing";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const userId = searchParams.get("userId")?.trim() ?? "";

  if (!userId) {
    return NextResponse.json(
      { error: "userId is required" },
      { status: 400 },
    );
  }

  try {
    const result = await fetchCollectionTopValuableCardsWithHistory(userId, 3);
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
