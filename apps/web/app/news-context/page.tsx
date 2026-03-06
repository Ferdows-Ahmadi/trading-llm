import Link from "next/link";

import { NewsPanel } from "../../components/news-panel";

export default async function NewsContextPage() {
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-8">
      <header className="mb-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">News & Context Engine</p>
        <h1 className="mt-2 text-3xl font-bold text-slate-900">Market headlines, relevance, and contradiction checks</h1>
        <p className="mt-3 max-w-3xl text-sm text-slate-600">
          This panel uses deterministic ingestion and scoring. Contradiction flags appear when sentiment and recent
          price action diverge for linked assets.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link href="/" className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white">
            Back to dashboard
          </Link>
          <code className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-700">
            POST /api/v1/news/ingest
          </code>
        </div>
      </header>

      <NewsPanel title="Latest News Feed" limit={25} hours={120} />
    </main>
  );
}
