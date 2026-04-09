"use client";

import { useState } from "react";
import { AdvisorProfile } from "@/lib/types";
import {
  buildSignals,
  getPriority,
  getAumBucket,
  SOURCE_TAG_STYLES,
  SOURCE_TAG_LABELS,
  Signal,
} from "@/lib/advisorSignals";
import AdvisorModal from "@/components/AdvisorModal";

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns the single most meaningful signal to preview in the row.
 * Only surfaces behavioral signals (13F holdings, Form D allocations) —
 * pure ADV data (AUM, headcount) is shown via badges and doesn't need a bullet.
 */
function getBehavioralPreview(signals: Signal[]): Signal | null {
  return (
    signals.find((s) => s.sourceTag === "thirteenf") ??
    signals.find((s) => s.sourceTag === "formd") ??
    null
  );
}

// ── Row ───────────────────────────────────────────────────────────────────────

export function AdvisorRow({
  advisor,
  rank,
  onView,
  compact = false,
}: {
  advisor: AdvisorProfile;
  rank: number;
  onView: () => void;
  compact?: boolean;
}) {
  const priority = getPriority(advisor);
  const signals  = buildSignals(advisor);
  const preview  = compact ? null : getBehavioralPreview(signals);

  const location  = [advisor.city, advisor.state].filter(Boolean).join(", ");
  const aumBucket = getAumBucket(advisor.aum);

  return (
    <div
      className={`flex items-start gap-3 px-4 border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors group cursor-pointer ${compact ? "py-3" : "py-3.5"}`}
      onClick={onView}
    >
      {/* Rank — dark navy square, never changes color */}
      <div className="shrink-0 mt-0.5 w-7 h-7 rounded bg-slate-800 flex items-center justify-center text-xs font-bold text-white">
        {rank}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Name + priority badge */}
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-slate-900 leading-tight truncate">
            {advisor.firm_name}
          </p>
          <span
            className={`shrink-0 inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${priority.lightBadge}`}
          >
            {priority.emoji} {priority.label}
          </span>
        </div>

        {/* Location · AUM · precise tier badge */}
        <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5 flex-wrap">
          {location}
          {advisor.aum_fmt && <span>· {advisor.aum_fmt}</span>}
          {aumBucket && (
            <span className={`inline-flex items-center text-xs px-1.5 py-px rounded border font-medium ${aumBucket.color}`}>
              {aumBucket.label}
            </span>
          )}
        </p>

        {/* Behavioral signal bullet — only 13F or Form D */}
        {preview && (
          <p className="mt-1.5 text-xs text-slate-600 leading-relaxed flex items-start gap-1.5">
            <span
              className={`shrink-0 mt-px inline-flex items-center text-xs px-1.5 py-px rounded border font-medium ${SOURCE_TAG_STYLES[preview.sourceTag]}`}
            >
              {SOURCE_TAG_LABELS[preview.sourceTag]}
            </span>
            {preview.bullet}
          </p>
        )}

        {/* Active fund allocations chip */}
        {!compact && advisor.allocation_count_90d > 0 && (
          <p className="mt-1 flex items-center gap-1">
            <span className="inline-flex items-center text-xs px-1.5 py-px rounded border font-medium bg-blue-50 text-blue-700 border-blue-200">
              Active in {advisor.allocation_count_90d} fund{advisor.allocation_count_90d > 1 ? "s" : ""} · 90d
            </span>
          </p>
        )}
      </div>

      {/* View arrow — visible on hover */}
      <div className="shrink-0 mt-1 text-slate-300 group-hover:text-blue-500 transition-colors">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </div>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface Props {
  advisors: AdvisorProfile[];
  territory: string;
}

export default function TopAdvisorsPanel({ advisors, territory }: Props) {
  const top10 = advisors.slice(0, 10);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  if (top10.length === 0) return null;

  const highCount = top10.filter((a) => getPriority(a).score === 3).length;

  return (
    <>
      <section className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Top 10 to Call This Week</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {highCount > 0
                ? `${highCount} high-priority firm${highCount > 1 ? "s" : ""} · click any row for the full call brief`
                : "Click any row for the full call brief — scored across SEC 13F, Form D, and ADV"}
              {territory && territory !== "All" ? ` · ${territory}` : ""}
            </p>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline">SEC 13F · Form D · EDGAR</span>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          {top10.map((a, i) => (
            <AdvisorRow
              key={a.crd_number || i}
              advisor={a}
              rank={i + 1}
              onView={() => setActiveIndex(i)}
            />
          ))}
        </div>
      </section>

      {activeIndex !== null && (
        <AdvisorModal
          advisor={top10[activeIndex]}
          rank={activeIndex + 1}
          onClose={() => setActiveIndex(null)}
        />
      )}
    </>
  );
}
