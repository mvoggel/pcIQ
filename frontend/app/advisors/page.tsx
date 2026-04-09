"use client";

import { useState, useEffect } from "react";
import AppHeader from "@/components/AppHeader";
import TopAdvisorsPanel, { AdvisorRow } from "@/components/TopAdvisorsPanel";
import AdvisorModal from "@/components/AdvisorModal";
import { fetchAdvisors } from "@/lib/api";
import { AdvisorProfile, AdvisorsResponse } from "@/lib/types";

const TERRITORIES = ["", "Northeast", "Southeast", "Midwest", "Southwest", "West Coast"];

export default function AdvisorsPage() {
  const [territory, setTerritory] = useState("");
  const [data, setData]           = useState<AdvisorsResponse | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [query, setQuery]         = useState("");

  // Modal state for the "All Advisors" list
  const [activeModal, setActiveModal] = useState<{ advisor: AdvisorProfile; rank: number } | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setQuery("");
    fetchAdvisors(territory)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [territory]);

  const filtered: AdvisorProfile[] = data
    ? query.trim()
      ? data.advisors.filter(
          (a) =>
            a.firm_name.toLowerCase().includes(query.toLowerCase()) ||
            a.state.toLowerCase().includes(query.toLowerCase()) ||
            a.city.toLowerCase().includes(query.toLowerCase())
        )
      : data.advisors
    : [];

  // When searching, show all filtered rows; otherwise skip top 10 (shown in panel above)
  const tableRows  = query ? filtered : filtered.slice(10);
  const rankOffset = query ? 0 : 10;

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />

      {/* Subheader */}
      <div className="bg-slate-800 border-b border-slate-700">
        <div className="px-4 sm:px-6 py-3 max-w-screen-xl mx-auto flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1">
            <h1 className="text-sm font-semibold text-white">Advisor Intelligence</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Alternative credit allocation signals — who to call first
            </p>
          </div>

          {/* Territory filter */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-400 shrink-0">Territory</span>
            <div className="flex flex-wrap gap-1">
              {TERRITORIES.map((t) => (
                <button
                  key={t || "all"}
                  onClick={() => setTerritory(t)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    territory === t
                      ? "bg-blue-600 text-white"
                      : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                  }`}
                >
                  {t || "All"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <main className="px-4 sm:px-6 py-4 max-w-screen-xl mx-auto">
        {loading && (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-slate-400 text-sm">Building advisor profiles…</p>
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm">
            <strong>Error:</strong> {error}
          </div>
        )}

        {data && !loading && (
          <>
            {/* Top 10 — hidden while search is active */}
            {!query && (
              <TopAdvisorsPanel advisors={data.advisors} territory={data.territory} />
            )}

            {/* All Advisors divider + search */}
            <div className="flex items-center gap-3 mb-3">
              <h2 className="text-sm font-semibold text-slate-900 shrink-0">
                {query ? "Search Results" : "All Advisors"}
              </h2>
              <div className="h-px flex-1 bg-slate-200" />
              {!query && data.advisors.length > 10 && (
                <span className="text-xs text-slate-400 shrink-0">
                  #{11}–{data.advisors.length}
                </span>
              )}
            </div>

            {/* Toolbar */}
            <div className="mb-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
              <div className="shrink-0 text-sm font-medium text-slate-700">
                {query ? (
                  <>
                    {filtered.length}
                    <span className="text-slate-400"> of {data.advisors.length}</span> advisor
                    {data.advisors.length !== 1 ? "s" : ""}
                  </>
                ) : (
                  <>
                    {Math.max(0, filtered.length - 10)} advisor
                    {filtered.length - 10 !== 1 ? "s" : ""} below top 10
                  </>
                )}
                {data.territory !== "All" ? ` · ${data.territory}` : ""}
              </div>
              <div className="relative sm:flex-1 sm:max-w-xs sm:ml-auto">
                <svg
                  className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none"
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
                </svg>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search firm or state…"
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

            {/* Card list — same component as Top 10 */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              {tableRows.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-sm">
                  {query ? "No advisors match your search" : "No additional advisors beyond top 10"}
                </div>
              ) : (
                tableRows.map((a, i) => (
                  <AdvisorRow
                    key={a.crd_number || i}
                    advisor={a}
                    rank={rankOffset + i + 1}
                    onView={() => setActiveModal({ advisor: a, rank: rankOffset + i + 1 })}
                    compact
                  />
                ))
              )}
            </div>

            {/* Legend */}
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
              <span>Priority scored across SEC Form 13F · EDGAR Form D · Form ADV</span>
              <span>Click any row to open the full call brief</span>
              <span>Source: Form ADV · EDGAR · SEC 13F</span>
            </div>
          </>
        )}
      </main>

      {/* Modal for All Advisors rows */}
      {activeModal && (
        <AdvisorModal
          advisor={activeModal.advisor}
          rank={activeModal.rank}
          onClose={() => setActiveModal(null)}
        />
      )}
    </div>
  );
}
