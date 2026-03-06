import Link from "next/link";

import { NewsPanel } from "../components/news-panel";

const overviewCards = [
  { title: "Market Overview", value: "Crypto + Forex", hint: "Unified registry enabled" },
  { title: "Top Movers", value: "Phase 2", hint: "Ingestion pipeline pending" },
  { title: "Current Opportunities", value: "Phase 3", hint: "Scoring engine pending" },
  { title: "Risk Widgets", value: "Phase 5", hint: "Position sizing pending" }
];

export default async function HomePage() {
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-8">
      <header className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
          Trading Analyst Platform
        </p>
        <h1 className="mt-2 text-3xl font-bold text-slate-900">
          Decision support for crypto and forex research
        </h1>
        <p className="mt-3 max-w-3xl text-sm text-slate-600">
          This platform surfaces structured market context, opportunities, and risk tooling.
          Outputs are informational and not financial advice.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link href="/news-context" className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white">
            Open News Panel
          </Link>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        {overviewCards.map((card) => (
          <article
            key={card.title}
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <h2 className="text-sm font-semibold text-slate-500">{card.title}</h2>
            <p className="mt-2 text-2xl font-bold text-slate-900">{card.value}</p>
            <p className="mt-1 text-xs text-slate-600">{card.hint}</p>
          </article>
        ))}
      </section>

      <div className="mt-8">
        <NewsPanel title="Latest Relevant News" limit={6} hours={72} />
      </div>
    </main>
  );
}
