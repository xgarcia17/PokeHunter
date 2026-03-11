import { NextResponse } from "next/server";
import { fetchCollectionTopValuableCardsWithHistory } from "@/lib/cardPricing";

const inFlightJobs = new Map<string, Promise<void>>();

function startRefreshJob(userId: string): "started" | "already_running" {
  if (inFlightJobs.has(userId)) {
    return "already_running";
  }

  const job = (async () => {
    try {
      await fetchCollectionTopValuableCardsWithHistory(userId, null, {
        refreshStalePrices: true,
        includeHistory: false,
      });
    } finally {
      inFlightJobs.delete(userId);
    }
  })();

  inFlightJobs.set(userId, job);
  return "started";
}

export async function POST(req: Request) {
  let userId = "";
  try {
    const body = (await req.json()) as { userId?: string };
    userId = body.userId?.trim() ?? "";
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  const status = startRefreshJob(userId);
  return NextResponse.json({ ok: true, status }, { status: 202 });
}
