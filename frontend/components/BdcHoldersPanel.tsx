"use client";

import { useEffect, useState } from "react";
import { fetchThirteenFHolders } from "@/lib/api";
import { ThirteenFHolder } from "@/lib/types";
import BdcHoldersModal from "@/components/BdcHoldersModal";

function fmtUsd(val: number): string {
  if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (val >= 1e6) return `$${Math.round(val / 1e6)}M`;
  return `$${Math.round(val / 1e3)}K`;
}

export default function BdcHoldersPanel() {
  const [holders, setHolders] = useState<ThirteenFHolder[]>([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [open, setOpen]       = useState(false);

  useEffect(() => {
    fetchThirteenFHolders(50, 1_000_000)
      .then((d) => { setHolders(d.holders); setTotal(d.total); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const institutionalCount = holders.filter((h) => h.total_bdc_value_usd >= 1e8).length;
  const totalValue = holders.reduce((sum, h) => sum + h.total_bdc_value_usd, 0);

  const summary = loading
    ? "Loading 13F data…"
    : error
    ? "13F data unavailable"
    : total === 0
    ? "No 13F holdings yet — run ingestion to populate"
    : `${institutionalCount} institutional holders · ${fmtUsd(totalValue)} in BDC positions · SEC Form 13F`;

  return (
    <>
      {/* Compact callout card */}
      <div className="mb-6 flex items-center justify-between gap-4 bg-white rounded-xl border border-slate-200 px-4 py-3">
        <div className="flex items-center gap-3 min-w-0">
          {/* Icon */}
          <div className="shrink-0 w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center">
            <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-700">Known BDC Buyers</p>
            <p className="text-xs text-slate-400 truncate">{summary}</p>
          </div>
        </div>

        <button
          onClick={() => setOpen(true)}
          disabled={loading || total === 0}
          className="shrink-0 inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 disabled:text-slate-300 disabled:cursor-default transition-colors"
        >
          View all 13F holders
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* Modal */}
      {open && (
        <BdcHoldersModal
          holders={holders}
          total={total}
          loading={loading}
          error={error}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
