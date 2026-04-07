"use client";

import { useState, useEffect } from "react";
import AppHeader from "@/components/AppHeader";
import CionFundCard from "@/components/CionFundCard";
import CompetitorTicker from "@/components/CompetitorTicker";
import { fetchCionFunds, fetchCompetitorFunds, fetchAdvisors } from "@/lib/api";
import { CionFund, AdvisorProfile } from "@/lib/types";

// ── Platform chip ────────────────────────────────────────────────────────────

const PLATFORM_COLORS: Record<string, string> = {
  iCapital: "bg-emerald-50 text-emerald-700 border-emerald-200",
  CAIS: "bg-amber-50 text-amber-700 border-amber-200",
  Orion: "bg-violet-50 text-violet-700 border-violet-200",
  default: "bg-slate-50 text-slate-600 border-slate-200",
};

function PlatformChip({ name }: { name: string }) {
  const cls = PLATFORM_COLORS[name] ?? PLATFORM_COLORS.default;
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${cls}`}>{name}</span>
  );
}

// ── Likely RIA row ───────────────────────────────────────────────────────────

function LikelyRiaRow({ ria, rank }: { ria: AdvisorProfile; rank: number }) {
  const isConfirmed = Object.values(ria.platform_sources ?? {}).some((s) => s === "csv");

  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2.5 pl-4 pr-2 text-xs text-slate-400 font-mono w-8">{rank}</td>

      <td className="py-2.5 pr-4">
        <div className="font-medium text-slate-800 text-sm leading-tight">{ria.firm_name}</div>
        <div className="text-xs text-slate-400 mt-0.5">
          {[ria.city, ria.state].filter(Boolean).join(", ")}
        </div>
      </td>

      <td className="py-2.5 pr-4 hidden sm:table-cell">
        <span className="text-sm font-semibold text-slate-800">{ria.aum_fmt ?? "—"}</span>
      </td>

      <td className="py-2.5 pr-4 hidden md:table-cell">
        <div className="flex flex-wrap gap-1">
          {ria.platforms.slice(0, 3).map((p) => (
            <PlatformChip key={p} name={p} />
          ))}
          {ria.platforms.length > 3 && (
            <span className="text-xs text-slate-400">+{ria.platforms.length - 3}</span>
          )}
        </div>
      </td>

      <td className="py-2.5 pr-4">
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full border ${
            isConfirmed
              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
              : "bg-slate-100 text-slate-500 border-slate-200"
          }`}
        >
          {isConfirmed ? "Confirmed" : "Inferred"}
        </span>
      </td>
    </tr>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function CionPage() {
  const [funds, setFunds] = useState<CionFund[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [competitors, setCompetitors] = useState<CionFund[]>([]);
  const [competitorsLoading, setCompetitorsLoading] = useState(true);

  const [likelyRias, setLikelyRias] = useState<AdvisorProfile[]>([]);
  const [riasLoading, setRiasLoading] = useState(true);
  const [riasError, setRiasError] = useState<string | null>(null);

  useEffect(() => {
    fetchCionFunds()
      .then(setFunds)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

    fetchCompetitorFunds()
      .then(setCompetitors)
      .catch(() => {/* silent — tickers show unavailable state */})
      .finally(() => setCompetitorsLoading(false));

    // Top 30 by activity — represents the RIAs most visible to competitors
    fetchAdvisors("", 30)
      .then((r) => setLikelyRias(r.advisors))
      .catch((e) => setRiasError(e.message))
      .finally(() => setRiasLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />

      {/* ── Platform stats callout ──────────────────────────────────── */}
      <div className="bg-slate-800 border-b border-slate-700">
        <div className="px-6 py-4 max-w-screen-lg mx-auto grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { value: "2,543", label: "RIAs tracked" },
            { value: "$5.6T",  label: "AUM represented" },
            { value: "44",     label: "states covered" },
            { value: "138",    label: "feeder funds indexed" },
          ].map(({ value, label }) => (
            <div key={label} className="text-center">
              <p className="text-xl font-bold text-blue-400">{value}</p>
              <p className="text-xs text-slate-400 mt-0.5">{label}</p>
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-slate-500 pb-3">Built entirely from public SEC data</p>
      </div>

      <main className="px-6 py-8 max-w-screen-lg mx-auto">

        {/* ── CION own funds ──────────────────────────────────────────── */}
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-slate-900">CION Investment Management</h1>
          <p className="text-sm text-slate-500 mt-1">
            Live fund intelligence — NAV, performance, and 90-day price history.
          </p>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-48">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm">
            <strong>Error:</strong> {error}
          </div>
        )}
        {!loading && !error && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {funds.map((fund) => (
              <CionFundCard key={fund.ticker} fund={fund} />
            ))}
          </div>
        )}

        {/* ── Competitor tickers ──────────────────────────────────────── */}
        <div className="mt-10">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Competitor Watch</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Registered interval funds and BDCs in the same distribution channels
              </p>
            </div>
            <span className="text-xs text-slate-400 hidden sm:inline">Yahoo Finance · delayed</span>
          </div>

          {competitorsLoading ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[0,1,2,3].map((i) => (
                <div key={i} className="bg-white border border-slate-200 rounded-lg px-4 py-3 animate-pulse h-16" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {competitors.map((fund) => (
                <CompetitorTicker key={fund.ticker} fund={fund} />
              ))}
            </div>
          )}
        </div>

        {/* ── Likely distribution partners (reverse signal) ───────────── */}
        <div className="mt-10">
          <div className="mb-3">
            <h2 className="text-base font-semibold text-slate-900">
              Likely Distribution Partners
            </h2>
            <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
              RIAs most likely already in CION's network — ranked by platform overlap and AUM.
              This is what a competitor using pcIQ would see when targeting your accounts.
            </p>
          </div>

          {riasLoading && (
            <div className="flex items-center justify-center h-32">
              <div className="w-5 h-5 border-2 border-slate-300 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {riasError && !riasLoading && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm">
              <strong>Error:</strong> {riasError}
            </div>
          )}

          {!riasLoading && !riasError && likelyRias.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="py-2.5 pl-4 pr-2 text-left text-xs font-medium text-slate-500 w-8">#</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500">Firm</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden sm:table-cell">AUM</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden md:table-cell">Platforms</th>
                    <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500">Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {likelyRias.map((ria, i) => (
                    <LikelyRiaRow key={ria.crd_number || i} ria={ria} rank={i + 1} />
                  ))}
                </tbody>
              </table>
              <div className="px-4 py-3 border-t border-slate-100 bg-slate-50">
                <p className="text-xs text-slate-400">
                  Source: Form ADV · EDGAR · iCapital/CAIS platform inference ·{" "}
                  <span className="font-medium text-slate-500">
                    Confirmed = CSV-verified platform partner · Inferred = EDGAR filing inference
                  </span>
                </p>
              </div>
            </div>
          )}
        </div>

      </main>
    </div>
  );
}
