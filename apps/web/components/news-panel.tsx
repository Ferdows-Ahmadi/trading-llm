import Link from "next/link";
import { fetchNewsFeed, NewsFeedItem } from "../lib/news-api";

function sentimentStyles(sentiment: string | null): string {
  if (sentiment === "positive") {
    return "bg-emerald-100 text-emerald-800";
  }
  if (sentiment === "negative") {
    return "bg-rose-100 text-rose-800";
  }
  return "bg-slate-100 text-slate-700";
}

function formatPublishedAt(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

function NewsCard({ item }: { item: NewsFeedItem }) {
  const hasContradiction = item.contradiction_signals.some((signal) => signal.is_contradiction);
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] ${sentimentStyles(item.sentiment_label)}`}
        >
          {item.sentiment_label ?? "neutral"}
        </span>
        <span className="text-xs text-slate-500">{item.source_name}</span>
        <span className="text-xs text-slate-500">{formatPublishedAt(item.published_at)}</span>
        {item.importance_score !== null ? (
          <span className="ml-auto rounded-full bg-slate-900 px-2 py-1 text-[11px] font-semibold text-white">
            Importance {item.importance_score.toFixed(1)}
          </span>
        ) : null}
      </div>

      <h3 className="text-base font-semibold text-slate-900">{item.title}</h3>
      <p className="mt-2 text-sm text-slate-600">{item.summary || "No summary provided."}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {item.asset_symbols.map((symbol) => (
          <span key={symbol} className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
            {symbol}
          </span>
        ))}
      </div>

      {hasContradiction ? (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          Contradiction detected between sentiment and 24h price action for at least one linked asset.
        </div>
      ) : null}

      {item.url ? (
        <Link
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block text-sm font-semibold text-slateBlue hover:underline"
        >
          Open source
        </Link>
      ) : null}
    </article>
  );
}

export async function NewsPanel(props: {
  title?: string;
  limit?: number;
  hours?: number;
  symbol?: string;
  assetClass?: "crypto" | "forex";
}) {
  const items = await fetchNewsFeed({
    limit: props.limit ?? 8,
    hours: props.hours ?? 72,
    symbol: props.symbol,
    assetClass: props.assetClass
  });

  return (
    <section className="rounded-2xl border border-slate-200 bg-white/70 p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-900">{props.title ?? "News & Context"}</h2>
        <Link href="/news-context" className="text-sm font-semibold text-slateBlue hover:underline">
          View full panel
        </Link>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-slate-600">
          No news available yet. Run `POST /api/v1/news/ingest` to populate the feed.
        </p>
      ) : (
        <div className="grid gap-4">
          {items.map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}
