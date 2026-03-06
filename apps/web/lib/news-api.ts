export interface ContradictionSignal {
  asset_symbol: string;
  price_change_pct_24h: number;
  is_contradiction: boolean;
}

export interface NewsFeedItem {
  id: string;
  title: string;
  summary: string;
  url: string;
  source_name: string;
  published_at: string;
  sentiment_label: string | null;
  importance_score: number | null;
  asset_symbols: string[];
  contradiction_signals: ContradictionSignal[];
}

export interface NewsFeedResponse {
  items: NewsFeedItem[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function fetchNewsFeed(params?: {
  limit?: number;
  hours?: number;
  symbol?: string;
  assetClass?: "crypto" | "forex";
}): Promise<NewsFeedItem[]> {
  const query = new URLSearchParams();
  query.set("limit", String(params?.limit ?? 20));
  query.set("hours", String(params?.hours ?? 72));
  if (params?.symbol) {
    query.set("symbol", params.symbol);
  }
  if (params?.assetClass) {
    query.set("asset_class", params.assetClass);
  }

  const response = await fetch(`${API_BASE}/api/v1/news/feed?${query.toString()}`, {
    method: "GET",
    next: { revalidate: 120 }
  });
  if (!response.ok) {
    return [];
  }

  const payload = (await response.json()) as NewsFeedResponse;
  return payload.items ?? [];
}
