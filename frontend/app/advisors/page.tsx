"use client";

import { useState, useEffect } from "react";
import AppHeader from "@/components/AppHeader";
import { fetchAdvisors } from "@/lib/api";
import { AdvisorProfile, AdvisorsResponse } from "@/lib/types";

const TERRITORIES = ["", "Northeast", "Southeast", "Midwest", "Southwest", "West Coast"];

const TIER_COLORS: Record<string, string> = {
  mega: "bg-purple-100 text-purple-700 border-purple-200",
  large: "bg-blue-100 text-blue-700 border-blue-200",
  mid: "bg-sky-100 text-sky-700 border-sky-200",
  small: "bg-slate-100 text-slate-600 border-slate-200",
  unknown: "bg-slate-100 text-slate-400 border-slate-200",
};

const TIER_LABELS: Record<string, string> = {
  mega: ">$5B",
  large: "$1–5B",
  mid: "$500M–1B",
  small: "<$500M",
  unknown: "—",
};

const PLATFORM_COLORS: Record<string, string> = {
  iCapital: "bg-emerald-50 text-emerald-700 border-emerald-200",
  CAIS: "bg-amber-50 text-amber-700 border-amber-200",
  Orion: "bg-violet-50 text-violet-700 border-violet-200",
  Houlihan: "bg-rose-50 text-rose-700 border-rose-200",
  "Houlihan Lokey": "bg-rose-50 text-rose-700 border-rose-200",
  default: "bg-slate-50 text-slate-600 border-slate-200",
};

function platformColor(name: string): string {
  return PLATFORM_COLORS[name] ?? PLATFORM_COLORS.default;
}

function ActivityDots({ score }: { score: number }) {
  // 0–4 dots based on score buckets: 0, <4, <8, <12, 12+
  const filled = score >= 12 ? 4 : score >= 8 ? 3 : score >= 4 ? 2 : score >= 1 ? 1 : 0;
  return (
    <div className="flex gap-0.5 items-center">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className={`w-2 h-2 rounded-full ${
            i < filled ? "bg-blue-500" : "bg-slate-200"
          }`}
        />
      ))}
    </div>
  );
}

function AdvisorRow({ advisor, rank }: { advisor: AdvisorProfile; rank: number }) {
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
      {/* Rank */}
      <td className="py-3 pl-4 pr-2 text-xs text-slate-400 font-mono w-8">{rank}</td>

      {/* Firm */}
      <td className="py-3 pr-4">
        <div className="font-medium text-slate-800 text-sm leading-tight">
          {advisor.firm_name}
        </div>
        <div className="text-xs text-slate-400 mt-0.5">
          {[advisor.city, advisor.state].filter(Boolean).join(", ")}
          {advisor.num_advisors ? ` · ${advisor.num_advisors} advisors` : ""}
        </div>
      </td>

      {/* AUM tier */}
      <td className="py-3 pr-4 hidden sm:table-cell">
        <span
          className={`inline-flex items-center text-xs px-2 py-0.5 rounded border font-medium ${
            TIER_COLORS[advisor.aum_tier]
          }`}
        >
          {advisor.aum_fmt ?? TIER_LABELS[advisor.aum_tier]}
        </span>
        {advisor.private_fund_aum_fmt && (
          <div className="text-xs text-slate-400 mt-0.5">
            {advisor.private_fund_aum_fmt} private
          </div>
        )}
      </td>

      {/* Platforms */}
      <td className="py-3 pr-4 hidden md:table-cell">
        {advisor.platforms.length === 0 ? (
          <span className="text-xs text-slate-300">—</span>
        ) : (
          <div className="flex flex-wrap gap-1">
            {advisor.platforms.slice(0, 3).map((p) => (
              <span
                key={p}
                className={`text-xs px-1.5 py-0.5 rounded border ${platformColor(p)}`}
              >
                {p}
              </span>
            ))}
            {advisor.platforms.length > 3 && (
              <span className="text-xs text-slate-400">+{advisor.platforms.length - 3}</span>
            )}
          </div>
        )}
      </td>

      {/* Activity */}
      <td className="py-3 pr-4">
        <ActivityDots score={advisor.activity_score} />
        {advisor.allocation_count_90d > 0 && (
          <div className="text-xs text-blue-600 mt-0.5 font-medium">
            {advisor.allocation_count_90d} deal{advisor.allocation_count_90d !== 1 ? "s" : ""} / 90d
          </div>
        )}
      </td>
    </tr>
  );
}

export default function AdvisorsPage() {
  const [territory, setTerritory] = useState("");
  const [data, setData] = useState<AdvisorsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

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
            a.city.toLowerCase().includes(query.toLowerCase()) ||
            a.platforms.some((p) => p.toLowerCase().includes(query.toLowerCase()))
        )
      : data.advisors
    : [];

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />

      {/* Subheader */}
      <div className="bg-white border-b border-slate-200">
        <div className="px-4 sm:px-6 py-3 max-w-screen-xl mx-auto flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1">
            <h1 className="text-sm font-semibold text-slate-900">
              Advisor Intelligence
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">
              RIAs ranked by platform presence and allocation activity — who to call first
            </p>
          </div>

          {/* Territory filter */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-500 shrink-0">Territory</span>
            <div className="flex flex-wrap gap-1">
              {TERRITORIES.map((t) => (
                <button
                  key={t || "all"}
                  onClick={() => setTerritory(t)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    territory === t
                      ? "bg-blue-600 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
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
              <p className="text-slate-400 text-sm">Building advisor profiles...</p>
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
            {/* Toolbar */}
            <div className="mb-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
              <div className="shrink-0 text-sm font-medium text-slate-700">
                {filtered.length}
                {query && <span className="text-slate-400"> of {data.advisors.length}</span>}
                {" "}advisor{data.advisors.length !== 1 ? "s" : ""}
                {data.territory !== "All" ? ` in ${data.territory}` : ""}
              </div>
              <div className="relative sm:flex-1 sm:max-w-xs sm:ml-auto">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
                </svg>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search firm, state, platform…"
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

            {/* Table */}
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="py-2.5 pl-4 pr-2 text-left text-xs font-medium text-slate-500 w-8">#</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500">Firm</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden sm:table-cell">AUM</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden md:table-cell">Platforms</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500">Activity</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-slate-400 text-sm">
                        No advisors found
                      </td>
                    </tr>
                  ) : (
                    filtered.map((a, i) => (
                      <AdvisorRow key={a.crd_number || i} advisor={a} rank={i + 1} />
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Legend */}
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
              <span>Activity dots: platform count + AUM tier + recent deals</span>
              <span>Ranked highest-activity first</span>
              <span>Source: Form ADV · EDGAR · iCapital/CAIS inferred</span>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
