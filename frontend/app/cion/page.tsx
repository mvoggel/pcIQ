"use client";

import { useState, useEffect } from "react";
import AppHeader from "@/components/AppHeader";
import CionFundCard from "@/components/CionFundCard";
import { fetchCionFunds, fetchAdvisors, fetchPlatformStats } from "@/lib/api";
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

// ── Confirmed partner row ────────────────────────────────────────────────────

function ConfirmedPartnerRow({ ria, rank }: { ria: AdvisorProfile; rank: number }) {
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
    </tr>
  );
}

// ── Financial metric card ────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}) {
  const valueColor =
    positive === undefined
      ? "text-slate-900"
      : positive
      ? "text-emerald-600"
      : "text-red-500";
  return (
    <div className="bg-white rounded-lg border border-slate-200 px-4 py-3.5">
      <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">{label}</p>
      <p className={`text-lg font-bold ${valueColor}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Fund financial summary ───────────────────────────────────────────────────

function FundPerformanceSummary({ fund }: { fund: CionFund }) {
  const fmtPct = (n: number | null | undefined) => {
    if (n == null) return "—";
    const v = Math.abs(n) > 1 ? n : n * 100;
    const sign = v >= 0 ? "+" : "";
    return `${sign}${v.toFixed(2)}%`;
  };

  const fmtAUM = (n: number | null | undefined) => {
    if (n == null) return "—";
    if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
    if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    return `$${n.toLocaleString()}`;
  };

  const vsMA200 =
    fund.nav != null && fund.two_hundred_day_avg != null
      ? ((fund.nav - fund.two_hundred_day_avg) / fund.two_hundred_day_avg) * 100
      : null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs font-bold tracking-wider text-white bg-slate-700 px-2 py-0.5 rounded font-mono">
          {fund.ticker}
        </span>
        <span className="text-sm font-semibold text-slate-800">{fund.name}</span>
        <span className="text-xs text-blue-600 border border-blue-200 bg-blue-50 rounded px-1.5 py-0.5 ml-auto">
          {fund.focus}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label="Total Net Assets"
          value={fmtAUM(fund.total_assets)}
          sub="fund size"
        />
        <MetricCard
          label="Distribution Yield"
          value={fund.distribution_yield != null ? `${(fund.distribution_yield * 100).toFixed(2)}%` : "—"}
          sub="trailing 12-mo"
          positive={fund.distribution_yield != null ? fund.distribution_yield > 0 : undefined}
        />
        <MetricCard
          label="YTD Return"
          value={fmtPct(fund.ytd_return)}
          sub="year to date"
          positive={fund.ytd_return != null ? fund.ytd_return >= 0 : undefined}
        />
        <MetricCard
          label="vs 200-Day Avg"
          value={vsMA200 != null ? `${vsMA200 >= 0 ? "+" : ""}${vsMA200.toFixed(2)}%` : "—"}
          sub={
            vsMA200 != null
              ? vsMA200 >= 0
                ? "trading above trend"
                : "trading below trend"
              : undefined
          }
          positive={vsMA200 != null ? vsMA200 >= 0 : undefined}
        />
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function CionPage() {
  const [funds, setFunds] = useState<CionFund[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [allAdvisors, setAllAdvisors] = useState<AdvisorProfile[]>([]);
  const [advisorsLoading, setAdvisorsLoading] = useState(true);

  const [platformStats, setPlatformStats] = useState<{
    rias_tracked: number;
    aum_represented: string;
    states_covered: number;
    feeder_funds: number;
  } | null>(null);

  useEffect(() => {
    fetchCionFunds()
      .then(setFunds)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

    fetchAdvisors("", 50)
      .then((r) => setAllAdvisors(r.advisors))
      .catch(() => {})
      .finally(() => setAdvisorsLoading(false));

    fetchPlatformStats()
      .then(setPlatformStats)
      .catch(() => {});
  }, []);

  // Only show RIAs with at least one CSV-confirmed platform relationship
  const confirmedPartners = allAdvisors
    .filter((ria) =>
      Object.values(ria.platform_sources ?? {}).some((s) => s === "csv")
    )
    .slice(0, 10);

  // Nav ticker data — pass live CION fund prices into the header
  const navTickers = funds
    .filter((f) => !f.error)
    .map((f) => ({ ticker: f.ticker, nav: f.nav, nav_change: f.nav_change }));

  const stats = [
    {
      value: platformStats ? platformStats.rias_tracked.toLocaleString() : "2,543",
      label: "RIAs tracked",
      desc: "active registered advisors",
    },
    {
      value: platformStats ? platformStats.aum_represented : "$5.6T",
      label: "AUM represented",
      desc: "across tracked firms",
    },
    {
      value: platformStats ? String(platformStats.states_covered) : "44",
      label: "states covered",
      desc: "geographic reach",
    },
    {
      value: platformStats ? String(platformStats.feeder_funds) : "138",
      label: "feeder funds indexed",
      desc: "from SEC EDGAR",
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader navTickers={navTickers} />

      {/* ── Platform stats cards ────────────────────────────────────── */}
      <div className="bg-slate-800 border-b border-slate-700">
        <div className="px-6 py-5 max-w-screen-lg mx-auto">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
            What pcIQ gives you
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {stats.map(({ value, label, desc }) => (
              <div
                key={label}
                className="bg-slate-700/40 border border-slate-600/60 rounded-xl px-4 py-3.5"
              >
                <p className="text-2xl font-bold text-blue-400 leading-none">{value}</p>
                <p className="text-xs font-medium text-slate-300 mt-1">{label}</p>
                <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
              </div>
            ))}
          </div>
        </div>
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

        {/* ── Financial Performance Data ──────────────────────────────── */}
        <div className="mt-10">
          <div className="mb-4">
            <h2 className="text-base font-semibold text-slate-900">Financial Performance Data</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Fund-level performance indicators and confirmed distribution relationships.
            </p>
          </div>

          {/* Performance by fund */}
          {!loading && !error && funds.length > 0 && (
            <div className="flex flex-col gap-4 mb-8">
              {funds.map((fund) =>
                fund.error ? null : <FundPerformanceSummary key={fund.ticker} fund={fund} />
              )}
            </div>
          )}

          {/* Confirmed distribution partners */}
          <div>
            <div className="mb-3">
              <h3 className="text-sm font-semibold text-slate-800">Confirmed Distribution Partners</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                RIAs with verified platform relationships — confirmed via CSV data from iCapital, CAIS, or similar distribution networks.
              </p>
            </div>

            {advisorsLoading && (
              <div className="flex items-center justify-center h-24">
                <div className="w-5 h-5 border-2 border-slate-300 border-t-transparent rounded-full animate-spin" />
              </div>
            )}

            {!advisorsLoading && confirmedPartners.length > 0 && (
              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50">
                      <th className="py-2.5 pl-4 pr-2 text-left text-xs font-medium text-slate-500 w-8">#</th>
                      <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500">Firm</th>
                      <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden sm:table-cell">AUM</th>
                      <th className="py-2.5 pr-4 text-left text-xs font-medium text-slate-500 hidden md:table-cell">Platforms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {confirmedPartners.map((ria, i) => (
                      <ConfirmedPartnerRow key={ria.crd_number || i} ria={ria} rank={i + 1} />
                    ))}
                  </tbody>
                </table>
                <div className="px-4 py-3 border-t border-slate-100 bg-slate-50">
                  <p className="text-xs text-slate-400">
                    Source: Form ADV · iCapital/CAIS platform data ·{" "}
                    <span className="font-medium text-slate-500">
                      Confirmed = CSV-verified direct platform relationship
                    </span>
                  </p>
                </div>
              </div>
            )}

            {!advisorsLoading && confirmedPartners.length === 0 && (
              <div className="bg-white rounded-xl border border-slate-200 px-6 py-8 text-center">
                <p className="text-sm text-slate-400">No confirmed partners found in current data.</p>
              </div>
            )}
          </div>
        </div>

      </main>
    </div>
  );
}
