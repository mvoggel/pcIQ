"use client";

import { ThirteenFHolder } from "@/lib/types";

// ─── helpers ────────────────────────────────────────────────────────────────

function fmtUsd(val: number): string {
  if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (val >= 1e6) return `$${Math.round(val / 1e6)}M`;
  return `$${Math.round(val / 1e3)}K`;
}

function cleanName(name: string): string {
  return name
    .replace(/\s*\(CIK\s+\d+\)\s*$/i, "")
    .replace(/\s*\([A-Z]{1,5}\)\s*$/, "")
    .trim();
}

const TICKER_COLORS: Record<string, string> = {
  ARCC: "bg-blue-50 text-blue-700 border-blue-200",
  MAIN: "bg-emerald-50 text-emerald-700 border-emerald-200",
  ORCC: "bg-violet-50 text-violet-700 border-violet-200",
  BXSL: "bg-orange-50 text-orange-700 border-orange-200",
  HTGC: "bg-rose-50 text-rose-700 border-rose-200",
  GBDC: "bg-sky-50 text-sky-700 border-sky-200",
  NMFC: "bg-amber-50 text-amber-700 border-amber-200",
  CSWC: "bg-teal-50 text-teal-700 border-teal-200",
  PFLT: "bg-indigo-50 text-indigo-700 border-indigo-200",
};

function tickerColor(ticker: string): string {
  return TICKER_COLORS[ticker] ?? "bg-slate-50 text-slate-600 border-slate-200";
}

function signalStrength(value: number): { label: string; dotColor: string } {
  if (value >= 5e8) return { label: "Institutional buyer",   dotColor: "bg-emerald-400" };
  if (value >= 1e8) return { label: "Established allocator", dotColor: "bg-blue-400" };
  return              { label: "Active holder",             dotColor: "bg-slate-400" };
}

// ─── row ────────────────────────────────────────────────────────────────────

function HolderRow({ holder, rank }: { holder: ThirteenFHolder; rank: number }) {
  const name = cleanName(holder.filer_name);
  const { label, dotColor } = signalStrength(holder.total_bdc_value_usd);
  const isRiaMatch = !!holder.ria_crd;

  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-3 pl-4 pr-2 text-xs text-slate-400 font-mono w-8">{rank}</td>

      <td className="py-3 pr-4">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-medium text-slate-800 text-sm leading-tight">{name}</span>
          {isRiaMatch && (
            <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border bg-emerald-50 text-emerald-700 border-emerald-200 font-medium">
              ✓ In RIA DB
            </span>
          )}
        </div>
        {holder.period_of_report && (
          <div className="text-xs text-slate-400 mt-0.5">As of {holder.period_of_report}</div>
        )}
      </td>

      <td className="py-3 pr-4">
        <div className="text-sm font-semibold text-slate-800">{fmtUsd(holder.total_bdc_value_usd)}</div>
        <div className="text-xs text-slate-400 mt-0.5">in BDC positions</div>
      </td>

      <td className="py-3 pr-4 hidden md:table-cell">
        <div className="flex flex-wrap gap-1">
          {holder.tickers.slice(0, 4).map((t) => (
            <span key={t} className={`text-xs px-1.5 py-0.5 rounded border font-medium ${tickerColor(t)}`}>
              {t}
            </span>
          ))}
          {holder.tickers.length > 4 && (
            <span className="text-xs text-slate-400">+{holder.tickers.length - 4}</span>
          )}
        </div>
      </td>

      <td className="py-3 pr-4 hidden sm:table-cell">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
          <span className="text-xs text-slate-500">{label}</span>
        </div>
      </td>
    </tr>
  );
}

// ─── modal ───────────────────────────────────────────────────────────────────

interface Props {
  holders: ThirteenFHolder[];
  total: number;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

export default function BdcHoldersModal({ holders, total, loading, error, onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-16"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[80vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-100 flex items-start justify-between gap-3 shrink-0">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Known BDC Buyers</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {loading
                ? "Loading…"
                : total > 0
                ? `${total} filers with confirmed BDC positions · Source: SEC Form 13F`
                : "No 13F holdings data yet"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 transition-colors shrink-0 mt-0.5"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1">
          {loading && (
            <div className="flex items-center justify-center h-40">
              <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {error && !loading && (
            <div className="px-5 py-8 text-center text-sm text-red-500">
              Could not load 13F data: {error}
            </div>
          )}

          {!loading && !error && holders.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-slate-400">
              No 13F holdings data yet — run ingestion to populate.
            </div>
          )}

          {!loading && !error && holders.length > 0 && (
            <table className="w-full">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="py-2.5 pl-4 pr-2 text-left text-xs font-medium text-slate-500 w-8">#</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500">Firm</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500">BDC Position</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden md:table-cell">Holds</th>
                  <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden sm:table-cell">Signal</th>
                </tr>
              </thead>
              <tbody>
                {holders.map((h, i) => (
                  <HolderRow key={h.filer_cik} holder={h} rank={i + 1} />
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-100 bg-slate-50 shrink-0">
          <p className="text-xs text-slate-400">
            Tracks ARCC · MAIN · ORCC · BXSL · HTGC · GBDC and more · Quarterly SEC 13F filings
          </p>
        </div>
      </div>
    </div>
  );
}
