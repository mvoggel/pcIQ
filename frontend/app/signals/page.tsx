"use client";

import { useState, useEffect } from "react";
import TerritoryTabs from "@/components/TerritoryTabs";
import SignalTable from "@/components/SignalTable";
import PlatformPanel from "@/components/PlatformPanel";
import { fetchSignals } from "@/lib/api";
import { SignalsResponse } from "@/lib/types";

const TERRITORIES = ["Northeast", "Southeast", "Midwest", "Southwest", "West Coast"];
const DAY_OPTIONS = [7, 14, 30];

function filteredSignals(data: SignalsResponse, query: string) {
  if (!query.trim()) return data.signals;
  const q = query.toLowerCase();
  return data.signals.filter(
    (s) =>
      s.fund_name.toLowerCase().includes(q) ||
      s.fund_type.toLowerCase().includes(q) ||
      s.platforms.some((p) => p.toLowerCase().includes(q))
  );
}

export default function SignalsPage() {
  const [territory, setTerritory] = useState("Northeast");
  const [days, setDays] = useState(7);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<SignalsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setQuery("");
    fetchSignals(territory, days)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [territory, days]);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-slate-900 text-white px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold tracking-tight">pcIQ</span>
          <span className="text-slate-500 text-sm">|</span>
          <span className="text-slate-400 text-sm">Private Credit Intelligence</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-slate-500 text-xs mr-2">Lookback</span>
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                days === d
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white hover:bg-slate-700"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </header>

      {/* Territory tabs */}
      <TerritoryTabs territories={TERRITORIES} active={territory} onChange={setTerritory} />

      {/* Main content */}
      <main className="px-6 py-6 max-w-screen-xl mx-auto">
        {loading && (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-slate-400 text-sm">Loading signals from Supabase...</p>
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm">
            <strong>Error:</strong> {error}
            <p className="text-red-500 text-xs mt-1">
              Make sure the FastAPI server is running: <code>cd backend && make run</code>
            </p>
          </div>
        )}

        {data && !loading && (
          <div className="flex gap-8">
            {/* Left: platform activity */}
            <aside className="w-52 shrink-0 pt-1">
              <PlatformPanel platformCounts={data.platform_counts} />
            </aside>

            {/* Right: signal feed */}
            <div className="flex-1 min-w-0">
              {/* Toolbar: count + search */}
              <div className="mb-3 flex items-center gap-4">
                <div className="shrink-0">
                  <span className="font-medium text-slate-700">
                    {filteredSignals(data, query).length}
                    {query && <span className="text-slate-400"> of {data.signals.length}</span>}
                    {" "}signal{data.signals.length !== 1 ? "s" : ""} in {data.territory}
                  </span>
                  <span className="text-slate-400 text-sm ml-2">
                    — {data.total_filings_scanned} filings scanned over {data.days}d
                  </span>
                </div>
                <div className="relative flex-1 max-w-xs ml-auto">
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
                  </svg>
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search funds, e.g. Blue Owl, Ares…"
                    className="w-full pl-8 pr-8 py-1.5 text-sm border border-slate-200 rounded-lg bg-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  {query && (
                    <button
                      onClick={() => setQuery("")}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
              <SignalTable signals={filteredSignals(data, query)} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
