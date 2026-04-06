import { CionFund } from "@/lib/types";
import Sparkline from "./Sparkline";

function fmt(n: number | null | undefined, prefix = "$", decimals = 2): string {
  if (n == null) return "—";
  return `${prefix}${n.toFixed(decimals)}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(2)}%`;
}

function fmtPctRaw(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function PctBadge({ value, raw = false }: { value: number | null; raw?: boolean }) {
  if (value == null) return <span className="text-slate-400">—</span>;
  const positive = value >= 0;
  const color = positive ? "text-emerald-600" : "text-red-500";
  const text = raw ? fmtPctRaw(value) : fmtPct(value);
  return <span className={`font-semibold ${color}`}>{text}</span>;
}

function RangeBar({
  low, high, current,
}: {
  low: number | null; high: number | null; current: number | null;
}) {
  if (low == null || high == null || current == null) return null;
  const range = high - low;
  const pct = range > 0 ? ((current - low) / range) * 100 : 50;

  return (
    <div className="mt-1">
      <div className="relative h-1 bg-slate-200 rounded-full">
        <div
          className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-blue-500 border-2 border-white shadow-sm"
          style={{ left: `calc(${Math.max(2, Math.min(98, pct))}% - 5px)` }}
        />
      </div>
      <div className="flex justify-between text-xs text-slate-400 mt-1">
        <span>${low.toFixed(2)}</span>
        <span className="text-slate-500 text-xs">52-week range</span>
        <span>${high.toFixed(2)}</span>
      </div>
    </div>
  );
}

interface Props {
  fund: CionFund;
  footerLabel?: string;
}

export default function CionFundCard({ fund, footerLabel }: Props) {
  if (fund.error) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <p className="font-semibold text-slate-700">{fund.ticker}</p>
        <p className="text-sm text-red-500 mt-1">Data unavailable: {fund.error}</p>
      </div>
    );
  }

  const dayUp = (fund.nav_change ?? 0) >= 0;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-bold tracking-wider text-white bg-slate-700 px-2 py-0.5 rounded">
              {fund.ticker}
            </span>
            <span className="text-xs text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">
              {fund.exchange}
            </span>
            <span className="text-xs text-blue-600 border border-blue-200 bg-blue-50 rounded px-1.5 py-0.5">
              {fund.focus}
            </span>
          </div>
          <h3 className="text-base font-semibold text-slate-900 leading-tight">{fund.name}</h3>
          <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{fund.strategy}</p>
        </div>

        {/* NAV + day change */}
        <div className="text-right shrink-0">
          <p className="text-2xl font-bold text-slate-900">
            {fund.nav != null ? `$${fund.nav.toFixed(2)}` : "—"}
          </p>
          {fund.nav_change != null && (
            <p className={`text-sm font-medium ${dayUp ? "text-emerald-600" : "text-red-500"}`}>
              {dayUp ? "▲" : "▼"} ${Math.abs(fund.nav_change).toFixed(2)} (
              {Math.abs((fund.nav_change_pct ?? 0) * 100).toFixed(2)}%)
            </p>
          )}
          <p className="text-xs text-slate-400 mt-0.5">NAV today</p>
        </div>
      </div>

      {/* Sparkline */}
      {fund.sparkline.length > 1 && (
        <div>
          <p className="text-xs text-slate-400 mb-1">90-day NAV</p>
          <Sparkline data={fund.sparkline} height={60} />
        </div>
      )}

      {/* 52-week range bar */}
      <RangeBar low={fund.fifty_two_week_low} high={fund.fifty_two_week_high} current={fund.nav} />

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-8 gap-y-3 pt-1 border-t border-slate-100">
        <div>
          <p className="text-xs uppercase tracking-wider text-slate-400 mb-0.5">52-Week Return</p>
          <PctBadge value={fund.fifty_two_week_change_pct} raw />
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-slate-400 mb-0.5">Prev. Close</p>
          <span className="text-sm font-medium text-slate-800">
            {fmt(fund.nav_prev_close)}
          </span>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-slate-400 mb-0.5">50-Day Avg</p>
          <span className="text-sm text-slate-700">{fmt(fund.fifty_day_avg)}</span>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-slate-400 mb-0.5">200-Day Avg</p>
          <span className="text-sm text-slate-700">{fmt(fund.two_hundred_day_avg)}</span>
        </div>
      </div>

      {/* Footer */}
      <p className="text-xs text-slate-300 border-t border-slate-100 pt-3">
        Source: Yahoo Finance (delayed) · {footerLabel ?? "CION Investment Management"}
      </p>
    </div>
  );
}
