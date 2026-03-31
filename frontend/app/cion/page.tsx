"use client";

import { useState, useEffect } from "react";
import AppHeader from "@/components/AppHeader";
import CionFundCard from "@/components/CionFundCard";
import { fetchCionFunds } from "@/lib/api";
import { CionFund } from "@/lib/types";

export default function CionPage() {
  const [funds, setFunds] = useState<CionFund[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCionFunds()
      .then(setFunds)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />

      <main className="px-6 py-8 max-w-screen-lg mx-auto">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-slate-900">CION Investment Management</h1>
          <p className="text-sm text-slate-500 mt-1">
            Live fund intelligence for your registered interval funds — NAV, performance, and 90-day price history.
          </p>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-slate-400 text-sm">Fetching fund data from Yahoo Finance...</p>
            </div>
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

        {!loading && !error && funds.length > 0 && (
          <div className="mt-8 bg-blue-50 border border-blue-100 rounded-lg px-5 py-4">
            <p className="text-sm font-semibold text-blue-800 mb-1">Track competitor registered funds</p>
            <p className="text-sm text-blue-600 leading-relaxed">
              pcIQ can monitor NAV, performance, and 52-week ranges for any registered fund — Blackstone BCRED,
              Blue Owl BCLO, Ares ASIF, and others. Add tickers to expand competitive intelligence beyond
              Form D private placements.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
