import { CionFund } from "@/lib/types";

interface Props {
  fund: CionFund;
}

export default function CompetitorTicker({ fund }: Props) {
  const up = (fund.nav_change ?? 0) >= 0;

  if (fund.error) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 flex flex-col gap-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold font-mono tracking-wider bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
            {fund.ticker}
          </span>
        </div>
        <p className="text-xs text-slate-400 truncate">Data unavailable</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 flex flex-col gap-1.5 min-w-0 hover:border-slate-300 transition-colors">
      {/* Line 1: ticker + short name */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="shrink-0 text-xs font-bold font-mono tracking-wider bg-slate-800 text-white px-1.5 py-0.5 rounded">
          {fund.ticker}
        </span>
        <span className="text-xs text-slate-500 truncate">{fund.name || fund.ticker}</span>
      </div>

      {/* Line 2: NAV + change */}
      <div className="flex items-baseline gap-2">
        <span className="text-base font-bold text-slate-900 tabular-nums">
          {fund.nav != null ? `$${fund.nav.toFixed(2)}` : "—"}
        </span>
        {fund.nav_change != null && (
          <span className={`text-xs font-semibold tabular-nums ${up ? "text-emerald-600" : "text-red-500"}`}>
            {up ? "▲" : "▼"} {Math.abs((fund.nav_change_pct ?? 0) * 100).toFixed(2)}%
          </span>
        )}
      </div>
    </div>
  );
}
