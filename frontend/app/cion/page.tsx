"use client";

import { useState, useEffect } from "react";
import AppHeader from "@/components/AppHeader";
import CionFundCard from "@/components/CionFundCard";
import { fetchCionFunds, fetchCompetitorFunds } from "@/lib/api";
import { CionFund } from "@/lib/types";

export default function CionPage() {
  const [funds, setFunds] = useState<CionFund[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [competitors, setCompetitors] = useState<CionFund[]>([]);
  const [competitorsLoading, setCompetitorsLoading] = useState(true);
  const [competitorsError, setCompetitorsError] = useState<string | null>(null);

  useEffect(() => {
    fetchCionFunds()
      .then(setFunds)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

    fetchCompetitorFunds()
      .then(setCompetitors)
      .catch((e) => setCompetitorsError(e.message))
      .finally(() => setCompetitorsLoading(false));
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

        {/* Competitor funds section */}
        <div className="mt-10">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Competitor Funds</h2>
              <p className="text-sm text-slate-500 mt-0.5">
                Registered interval funds and BDCs competing in the same distribution channels
              </p>
            </div>
            <span className="text-xs text-slate-400 hidden sm:inline">
              ARCC · ASIF · BCRED · OBDC
            </span>
          </div>

          {competitorsLoading && (
            <div className="flex items-center justify-center h-32">
              <div className="w-5 h-5 border-2 border-slate-300 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {competitorsError && !competitorsLoading && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm">
              <strong>Error:</strong> {competitorsError}
            </div>
          )}

          {!competitorsLoading && !competitorsError && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {competitors.map((fund) => (
                <div key={fund.ticker} className="relative">
                  <div className="absolute top-3 right-3 z-10">
                    <span className="text-xs bg-orange-100 text-orange-700 border border-orange-200 rounded px-1.5 py-0.5 font-medium">
                      Competitor
                    </span>
                  </div>
                  <CionFundCard fund={fund} footerLabel={fund.name} />
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
