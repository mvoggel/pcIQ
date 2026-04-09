"use client";

import { useState } from "react";
import { AdvisorProfile } from "@/lib/types";
import { buildSignals, getPriority, getConfidence } from "@/lib/advisorSignals";
import AdvisorModal from "@/components/AdvisorModal";

// ── Tier badge ────────────────────────────────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  mega:    "bg-purple-100 text-purple-700 border-purple-200",
  large:   "bg-blue-100 text-blue-700 border-blue-200",
  mid:     "bg-sky-100 text-sky-700 border-sky-200",
  small:   "bg-slate-100 text-slate-600 border-slate-200",
  unknown: "",
};

// ── Row ───────────────────────────────────────────────────────────────────────

function AdvisorRow({
  advisor, rank, onView,
}: {
  advisor: AdvisorProfile;
  rank: number;
  onView: () => void;
}) {
  const priority   = getPriority(advisor);
  const signals    = buildSignals(advisor);
  const confidence = getConfidence(signals, advisor);

  const location = [advisor.city, advisor.state].filter(Boolean).join(", ");

  // Preview: up to 2 signal bullets shown inline
  const preview = signals.slice(0, 2);

  return (
    <div className="flex items-start gap-3 px-4 py-3.5 border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors group">

      {/* Rank circle — color = priority */}
      <div className={`shrink-0 mt-0.5 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white ${priority.rankBg}`}>
        {rank}
      </div>

      {/* Main content */}
      <div className="flex-1 min-w-0">
        {/* Firm name + priority badge */}
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-slate-900 leading-tight truncate">{advisor.firm_name}</p>
          <span className={`shrink-0 inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${priority.lightBadge}`}>
            {priority.emoji} {priority.label}
          </span>
        </div>

        {/* Location + AUM */}
        <p className="text-xs text-slate-400 mt-0.5">
          {location}
          {advisor.aum_fmt ? ` · ${advisor.aum_fmt}` : ""}
          {advisor.aum_tier !== "unknown" && TIER_COLORS[advisor.aum_tier] ? (
            <span className={`ml-1.5 inline-flex items-center text-xs px-1.5 py-px rounded border font-medium ${TIER_COLORS[advisor.aum_tier]}`}>
              {advisor.aum_tier === "mega" ? ">$5B" : advisor.aum_tier === "large" ? "$1–5B" : advisor.aum_tier === "mid" ? "$500M–1B" : "<$500M"}
            </span>
          ) : null}
        </p>

        {/* Signal preview bullets */}
        {preview.length > 0 && (
          <ul className="mt-1.5 space-y-0.5">
            {preview.map((s, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-slate-500">
                <span className="shrink-0 mt-0.5 text-slate-300">•</span>
                <span className="leading-relaxed">{s.bullet}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Confidence dot */}
        <div className="flex items-center gap-1.5 mt-2">
          <div className={`w-1.5 h-1.5 rounded-full ${confidence.dotColor}`} />
          <span className="text-xs text-slate-400">{confidence.label}</span>
        </div>
      </div>

      {/* View button */}
      <button
        onClick={onView}
        className="shrink-0 mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 rounded hover:bg-blue-50"
      >
        View
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
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
        {/* Section header */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Top 10 to Call This Week</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {highCount > 0
                ? `${highCount} high-priority firm${highCount > 1 ? "s" : ""} — click any row for full call brief`
                : "Click any row for the full call brief — ranked by combined 13F, Form D, and ADV signals"}
              {territory && territory !== "All" ? ` · ${territory}` : ""}
            </p>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline">SEC Form 13F · Form D · EDGAR</span>
        </div>

        {/* List */}
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

        <p className="text-xs text-slate-400 mt-2 text-right">
          Hover any row to open · Contact placeholder for CRM / Salesforce integration
        </p>
      </section>

      {/* Modal */}
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
