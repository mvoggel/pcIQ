"use client";

import { useEffect, useRef, useState } from "react";
import { Signal } from "@/lib/types";
import FundModal from "./FundModal";

// ── helpers ──────────────────────────────────────────────────────────────────

function formatSize(m: number | null): string {
  if (m === null) return "—";
  if (m >= 1000) return `$${(m / 1000).toFixed(1)}B`;
  return `$${m}M`;
}

function formatDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ── overflow tooltip: shows remaining items on hover or tap ──────────────────

function OverflowTooltip({ items, label }: { items: string[]; label: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-block">
      <span
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className="text-xs text-blue-500 cursor-pointer underline decoration-dotted select-none"
      >
        +{items.length} {label}
      </span>
      <span className={`pointer-events-none absolute bottom-full left-0 mb-1.5 w-64 bg-slate-800 text-white text-xs rounded-lg px-3 py-2 transition-opacity z-50 shadow-xl whitespace-normal break-words leading-relaxed ${open ? "opacity-100" : "opacity-0"}`}>
        {items.join(", ")}
        <span className="absolute top-full left-4 border-4 border-transparent border-t-slate-800" />
      </span>
    </span>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 8
      ? "bg-emerald-100 text-emerald-800"
      : score >= 5
      ? "bg-amber-100 text-amber-800"
      : "bg-slate-100 text-slate-600";
  return (
    <span className={`inline-flex items-center justify-center w-10 h-6 rounded text-xs font-bold ${color}`}>
      {score.toFixed(1)}
    </span>
  );
}

function StatesCell({ states, fundState }: { states: string[]; fundState: string }) {
  if (states.length === 0) return <span className="text-slate-500 text-xs">{fundState || "—"}</span>;
  const shown = states.slice(0, 3);
  const rest = states.slice(3);
  return (
    <span className="text-slate-500 text-xs">
      {shown.join(", ")}
      {rest.length > 0 && (
        <span className="ml-1">
          <OverflowTooltip items={rest} label="more" />
        </span>
      )}
    </span>
  );
}

function PlatformBadges({ platforms, known }: { platforms: string[]; known: string[] }) {
  const knownSet = new Set(known.map((p) => p.toLowerCase()));
  const shown = platforms.slice(0, 2);
  const rest = platforms.slice(2);
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((p) => {
        const isKnown = knownSet.has(p.toLowerCase());
        return (
          <span
            key={p}
            className={`px-1.5 py-0.5 rounded text-xs truncate max-w-[110px] ${
              isKnown ? "bg-blue-100 text-blue-700 font-medium" : "bg-slate-100 text-slate-600"
            }`}
            title={p}
          >
            {p}
          </span>
        );
      })}
      {rest.length > 0 && <OverflowTooltip items={rest} label="more" />}
    </div>
  );
}

function InfoTooltip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex items-center ml-1.5 align-middle">
      <span
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className="w-3.5 h-3.5 rounded-full border border-slate-400 text-slate-400 text-[9px] flex items-center justify-center cursor-pointer font-bold select-none"
      >
        i
      </span>
      <span className={`pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60 bg-slate-800 text-white text-xs rounded-lg px-3 py-2 leading-relaxed transition-opacity z-50 shadow-xl normal-case tracking-normal font-normal whitespace-normal ${open ? "opacity-100" : "opacity-0"}`}>
        {text}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800" />
      </span>
    </span>
  );
}

// ── main component ────────────────────────────────────────────────────────────

interface Props {
  signals: Signal[];
}

export default function SignalTable({ signals }: Props) {
  const [selected, setSelected] = useState<Signal | null>(null);

  if (signals.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 px-6 py-12 text-center">
        <p className="text-slate-500 text-sm">No signals in this territory for the selected period.</p>
        <p className="text-slate-400 text-xs mt-1">
          Try expanding the date range or run <code>make ingest</code> to fetch fresh data.
        </p>
      </div>
    );
  }

  return (
    <>
      {/* Mobile card list */}
      <div className="sm:hidden space-y-2">
        {signals.map((s, i) => (
          <div
            key={i}
            className="bg-white rounded-lg border border-slate-200 px-4 py-3 cursor-pointer active:bg-blue-50"
            onClick={() => setSelected(s)}
          >
            <div className="flex items-start justify-between gap-3 mb-1.5">
              <p className="font-medium text-slate-800 text-sm leading-snug flex-1">{s.fund_name}</p>
              <ScoreBadge score={s.priority_score} />
            </div>
            <p className="text-xs text-slate-400 mb-2">{s.fund_type}</p>
            <div className="flex items-center gap-3 text-xs text-slate-500 flex-wrap">
              <span className="font-medium text-slate-700">{formatSize(s.offering_size_m)}</span>
              <span>{formatDate(s.date_of_first_sale)}</span>
              <StatesCell states={s.solicitation_states} fundState={s.fund_state} />
            </div>
            {s.platforms.length > 0 && (
              <div className="mt-2">
                <PlatformBadges platforms={s.platforms} known={s.known_platforms} />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Desktop table */}
      {/* No overflow-hidden here — it clips absolutely-positioned tooltips */}
      <div className="hidden sm:block bg-white rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3 text-left w-16">
                Score
                <InfoTooltip text="Priority score (0–10). Weighted by: known platform distributing (+3), territory overlap (+2), offering size (+2), fund type, and recency. Higher = more likely a call opportunity." />
              </th>
              <th className="px-4 py-3 text-left">
                Fund
                <InfoTooltip text="A private fund actively raising capital right now via SEC Form D. Click any row for full details and a direct link to the filing." />
              </th>
              <th className="px-4 py-3 text-right w-24">Size</th>
              <th className="px-4 py-3 text-left w-36">States</th>
              <th className="px-4 py-3 text-left w-20">First Sale</th>
              <th className="px-4 py-3 text-left">
                Platforms
                <InfoTooltip text="Broker-dealers or platforms paid to distribute this fund. Blue = known private markets platform (iCapital, CAIS, etc.). Blank = direct institutional placement, no intermediary commissions disclosed." />
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {signals.map((s, i) => (
              <tr
                key={i}
                className="hover:bg-blue-50 cursor-pointer transition-colors"
                onClick={() => setSelected(s)}
              >
                <td className="px-4 py-3">
                  <ScoreBadge score={s.priority_score} />
                </td>
                <td className="px-4 py-3">
                  <p className="font-medium text-slate-800 truncate max-w-[260px]" title={s.fund_name}>
                    {s.fund_name}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">{s.fund_type}</p>
                </td>
                <td className="px-4 py-3 text-right font-medium text-slate-700">
                  {formatSize(s.offering_size_m)}
                </td>
                <td className="px-4 py-3">
                  <StatesCell states={s.solicitation_states} fundState={s.fund_state} />
                </td>
                <td className="px-4 py-3 text-slate-500 text-xs">
                  {formatDate(s.date_of_first_sale)}
                </td>
                <td className="px-4 py-3">
                  {s.platforms.length > 0 ? (
                    <PlatformBadges platforms={s.platforms} known={s.known_platforms} />
                  ) : (
                    <span className="text-slate-300 text-xs">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && <FundModal signal={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
