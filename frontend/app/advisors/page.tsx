"use client";

import { useState, useEffect } from "react";
import AppHeader from "@/components/AppHeader";
import { AdvisorRow } from "@/components/TopAdvisorsPanel";
import AdvisorModal from "@/components/AdvisorModal";
import { fetchAdvisors } from "@/lib/api";
import { AdvisorProfile, AdvisorsResponse } from "@/lib/types";
import { getPriority } from "@/lib/advisorSignals";

const TERRITORIES = ["", "Northeast", "Southeast", "Midwest", "Southwest", "West Coast"];
const PAGE_SIZE   = 20;

// ── Info panel ────────────────────────────────────────────────────────────────

function InfoPanel() {
  return (
    <div className="mb-4 bg-blue-50 border border-blue-100 rounded-xl px-4 py-3.5">
      <p className="text-xs font-semibold text-blue-700 mb-1.5">What this list shows</p>
      <p className="text-xs text-blue-800 leading-relaxed">
        Every RIA in our database, ranked by their likelihood to allocate to CION's BDC.
        Scored across three public SEC data sources:{" "}
        <strong>SEC Form 13F</strong> (do they already hold BDC positions like ARCC or MAIN?),{" "}
        <strong>EDGAR Form D</strong> (recent allocations to similar private credit funds?), and{" "}
        <strong>Form ADV</strong> (AUM size and advisor headcount).{" "}
        <span className="text-blue-700 font-medium">🔥 High Priority</span> firms have confirmed
        buying behavior — they already allocate to this asset class. No third-party vendors;
        all signals are derived from public SEC filings.
      </p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdvisorsPage() {
  const [territory, setTerritory]     = useState("");
  const [data, setData]               = useState<AdvisorsResponse | null>(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [query, setQuery]             = useState("");
  const [visibleCount, setVisible]    = useState(PAGE_SIZE);
  const [showInfo, setShowInfo]       = useState(false);
  const [filterOpen, setFilterOpen]   = useState(false);
  const [activeModal, setActiveModal] = useState<{ advisor: AdvisorProfile; rank: number } | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setQuery("");
    setVisible(PAGE_SIZE);
    setShowInfo(false);
    fetchAdvisors(territory)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [territory]);

  useEffect(() => { setVisible(PAGE_SIZE); }, [query]);

  const allAdvisors: AdvisorProfile[] = data?.advisors ?? [];

  const filtered = query.trim()
    ? allAdvisors.filter(
        (a) =>
          a.firm_name.toLowerCase().includes(query.toLowerCase()) ||
          a.state.toLowerCase().includes(query.toLowerCase()) ||
          a.city.toLowerCase().includes(query.toLowerCase())
      )
    : allAdvisors;

  const visibleRows = filtered.slice(0, visibleCount);
  const remaining   = filtered.length - visibleCount;
  const highCount   = allAdvisors.slice(0, 20).filter((a) => getPriority(a).score === 3).length;

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />

      {/* Subheader */}
      <div className="bg-slate-800 border-b border-slate-700">
        <div className="px-4 sm:px-6 py-3 max-w-screen-xl mx-auto">
          {/* Title row — on mobile acts as toggle trigger */}
          <div className="flex items-center justify-between sm:hidden">
            <div>
              <h1 className="text-sm font-semibold text-white">Advisor Intelligence</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Alternative credit allocation signals — who to call first
              </p>
            </div>
            <button
              onClick={() => setFilterOpen((v) => !v)}
              aria-label="Toggle territory filter"
              className="flex items-center gap-1.5 ml-3 shrink-0 px-2.5 py-1.5 rounded bg-slate-700 text-slate-300 text-xs font-medium"
            >
              <span>{territory || "All"}</span>
              <svg
                className={`w-3.5 h-3.5 transition-transform duration-200 ${filterOpen ? "rotate-180" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          </div>

          {/* Desktop: original side-by-side layout */}
          <div className="hidden sm:flex sm:items-center sm:gap-3">
            <div className="flex-1">
              <h1 className="text-sm font-semibold text-white">Advisor Intelligence</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Alternative credit allocation signals — who to call first
              </p>
            </div>
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

          {/* Mobile: expandable territory filter */}
          {filterOpen && (
            <div className="sm:hidden mt-3 pt-3 border-t border-slate-700 flex flex-wrap gap-1.5">
              {TERRITORIES.map((t) => (
                <button
                  key={t || "all"}
                  onClick={() => { setTerritory(t); setFilterOpen(false); }}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    territory === t
                      ? "bg-blue-600 text-white"
                      : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                  }`}
                >
                  {t || "All"}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <main className="px-4 sm:px-6 py-4 max-w-screen-xl mx-auto">

        {/* ── Search — always at top ── */}
        {data && !loading && (
          <div className="relative mb-5">
            <svg
              className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
            </svg>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search all ${allAdvisors.length} advisors by firm or state…`}
              className="w-full pl-10 pr-10 py-2.5 text-sm border border-slate-200 rounded-xl bg-white shadow-sm placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        )}

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
            {/* ── Section heading ── */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-slate-900">
                  {query
                    ? `${filtered.length} result${filtered.length !== 1 ? "s" : ""} for "${query}"`
                    : "Top Advisors to Call This Week"}
                </h2>

                {/* Info circle — click/tap to toggle */}
                {!query && (
                  <button
                    onClick={() => setShowInfo((v) => !v)}
                    aria-label="What is this list?"
                    className={`shrink-0 w-5 h-5 rounded-full border flex items-center justify-center text-xs font-bold transition-colors ${
                      showInfo
                        ? "bg-blue-600 border-blue-600 text-white"
                        : "border-slate-300 text-slate-400 hover:border-blue-400 hover:text-blue-500"
                    }`}
                  >
                    i
                  </button>
                )}
              </div>

              {/* Right-side context */}
              {!query && (
                <span className="text-xs text-slate-400 hidden sm:inline">
                  {highCount > 0
                    ? `${highCount} high-priority firm${highCount > 1 ? "s" : ""} · `
                    : ""}
                  SEC 13F · Form D · EDGAR
                </span>
              )}
            </div>

            {/* Info panel — expands below heading */}
            {showInfo && !query && <InfoPanel />}

            {/* ── Unified advisor list ── */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              {visibleRows.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-sm">
                  No advisors match your search — try a different firm name or state
                </div>
              ) : (
                visibleRows.map((a, i) => (
                  <AdvisorRow
                    key={a.crd_number || i}
                    advisor={a}
                    rank={i + 1}
                    onView={() => setActiveModal({ advisor: a, rank: i + 1 })}
                  />
                ))
              )}
            </div>

            {/* Load more */}
            {remaining > 0 && (
              <div className="mt-4 flex justify-center">
                <button
                  onClick={() => setVisible((v) => v + PAGE_SIZE)}
                  className="inline-flex items-center gap-2 px-5 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 hover:border-slate-300 shadow-sm transition-colors"
                >
                  Load {Math.min(remaining, PAGE_SIZE)} more
                  <span className="text-xs text-slate-400">({remaining} remaining)</span>
                </button>
              </div>
            )}

            {/* Legend */}
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
              <span>Priority scored across SEC Form 13F · EDGAR Form D · Form ADV</span>
              <span>Click any row to open the full call brief</span>
            </div>
          </>
        )}
      </main>

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
