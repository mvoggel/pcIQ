"use client";

import { AdvisorProfile } from "@/lib/types";
import {
  buildSignals,
  getPriority,
  getOutcomeAnchor,
  SOURCE_TAG_STYLES,
  SOURCE_TAG_LABELS,
  Signal,
} from "@/lib/advisorSignals";

// ── Helpers ───────────────────────────────────────────────────────────────────

const TIER_LABELS: Record<string, string> = {
  mega:    ">$5B AUM",
  large:   "$1–5B AUM",
  mid:     "$500M–1B AUM",
  small:   "<$500M AUM",
  unknown: "AUM unknown",
};

const TIER_COLORS: Record<string, string> = {
  mega:    "bg-purple-100 text-purple-700 border-purple-200",
  large:   "bg-blue-100 text-blue-700 border-blue-200",
  mid:     "bg-sky-100 text-sky-700 border-sky-200",
  small:   "bg-slate-100 text-slate-600 border-slate-200",
  unknown: "bg-slate-50 text-slate-400 border-slate-100",
};

// Group signals by source tag for cleaner presentation
function groupSignals(signals: Signal[]): { tag: Signal["sourceTag"]; items: Signal[] }[] {
  const order: Signal["sourceTag"][] = ["thirteenf", "formd", "adv", "brochure", "inferred"];
  const groups: Record<string, Signal[]> = {};
  for (const s of signals) {
    if (!groups[s.sourceTag]) groups[s.sourceTag] = [];
    groups[s.sourceTag].push(s);
  }
  return order
    .filter((tag) => groups[tag]?.length)
    .map((tag) => ({ tag, items: groups[tag] }));
}

// ── Modal ─────────────────────────────────────────────────────────────────────

interface Props {
  advisor: AdvisorProfile;
  rank: number;
  onClose: () => void;
}

export default function AdvisorModal({ advisor, rank, onClose }: Props) {
  const priority = getPriority(advisor);
  const signals  = buildSignals(advisor);
  const anchor   = getOutcomeAnchor(advisor, signals);
  const groups   = groupSignals(signals);

  const location = [advisor.city, advisor.state].filter(Boolean).join(", ");
  const tierLabel = advisor.aum_fmt ?? TIER_LABELS[advisor.aum_tier];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto overscroll-contain">

        {/* ── Header ── */}
        <div className="px-5 pt-5 pb-4 border-b border-slate-100">
          <div className="flex items-start justify-between gap-3 mb-3">
            {/* Rank + priority */}
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded bg-slate-800 flex items-center justify-center text-xs font-bold text-white shrink-0">
                {rank}
              </div>
              <span
                className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full border ${priority.lightBadge}`}
              >
                {priority.emoji} {priority.label}
              </span>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 transition-colors shrink-0"
              aria-label="Close"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Firm */}
          <h2 className="text-lg font-bold text-slate-900 leading-tight">{advisor.firm_name}</h2>
          <div className="flex flex-wrap items-center gap-2 mt-1.5">
            {location && <span className="text-sm text-slate-500">{location}</span>}
            {tierLabel && advisor.aum_tier !== "unknown" && (
              <span
                className={`inline-flex items-center text-xs px-2 py-0.5 rounded border font-medium ${TIER_COLORS[advisor.aum_tier]}`}
              >
                {tierLabel}
              </span>
            )}
            {advisor.num_advisors && (
              <span className="text-xs text-slate-400">
                {advisor.num_advisors.toLocaleString()} advisors
              </span>
            )}
          </div>
        </div>

        {/* ── Body ── */}
        <div className="px-5 py-5 space-y-5">

          {/* Outcome anchor */}
          {anchor && (
            <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3">
              <p className="text-sm text-blue-800 font-medium leading-relaxed">→ {anchor}</p>
            </div>
          )}

          {/* Signals — grouped by source */}
          {groups.length > 0 ? (
            <div className="space-y-4">
              {groups.map(({ tag, items }) => (
                <div key={tag}>
                  {/* Source header */}
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className={`inline-flex items-center text-xs px-2 py-0.5 rounded border font-semibold ${SOURCE_TAG_STYLES[tag]}`}
                    >
                      {SOURCE_TAG_LABELS[tag]}
                    </span>
                    <div className="h-px flex-1 bg-slate-100" />
                  </div>
                  {/* Bullets under this source */}
                  <ul className="space-y-1.5 pl-1">
                    {items.map((s, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-700 leading-relaxed">
                        <span className="shrink-0 text-slate-300 mt-0.5">•</span>
                        {s.bullet}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400 italic">
              No detailed signals yet — AUM and location available; additional enrichment pending.
            </p>
          )}

          {/* What "priority" means — demystify for non-technical users */}
          <div className="bg-slate-50 rounded-lg px-4 py-3 border border-slate-100">
            <p className="text-xs font-semibold text-slate-500 mb-1.5">How priority is calculated</p>
            <p className="text-xs text-slate-400 leading-relaxed">
              <strong className="text-slate-600">High Priority</strong> = behavioral signals confirmed (13F BDC holdings or recent fund allocations) plus large AUM.{" "}
              <strong className="text-slate-600">Medium</strong> = one strong signal or large AUM alone.{" "}
              <strong className="text-slate-600">Watchlist</strong> = in territory with limited signal data yet.
              All signals are drawn from public SEC filings — no third-party data vendors.
            </p>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="px-5 py-4 border-t border-slate-100 flex items-center justify-between gap-3">
          <p className="text-xs text-slate-400">
            {[...new Set(signals.map((s) => s.source))].join(" · ") || "Form ADV · EDGAR"}
          </p>
          <button className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
            </svg>
            Contact
          </button>
        </div>
      </div>
    </div>
  );
}
