"use client";

import { useState } from "react";
import { AdvisorProfile } from "@/lib/types";

// ─────────────────────────────────────────────────────────────────────────────
// SIGNAL FRAMEWORK
//
// Each bullet the wholesaler sees is backed by a named Signal.
// To add a new data source (CRM, email engagement, prior CION allocation):
//   1. Add a new signal type below
//   2. Add a builder function that returns Signal | null
//   3. Call it inside buildSignals()
//
// Signals are intentionally typed — null means "no data", not "negative signal".
// Only non-null signals produce bullets. This keeps the UI honest.
// ─────────────────────────────────────────────────────────────────────────────

type SignalStrength = "confirmed" | "inferred" | "limited";

interface Signal {
  bullet: string;
  strength: SignalStrength;
  source: string;
}

function platformSignal(a: AdvisorProfile): Signal | null {
  if (a.platforms.length === 0) return null;
  const sources = a.platform_sources ?? {};
  const confirmed = a.platforms.filter((p) => sources[p] === "csv");
  const brochure  = a.platforms.filter((p) => sources[p] === "adv_brochure");
  const inferred  = a.platforms.filter((p) => sources[p] === "edgar_inferred" || !sources[p]);

  let bullet: string;
  let strength: SignalStrength;

  if (confirmed.length >= 2) {
    bullet = `Confirmed ${confirmed[0]} and ${confirmed[1]} partner — direct channel overlap`;
    strength = "confirmed";
  } else if (confirmed.length === 1 && a.platforms.length >= 2) {
    const others = a.platforms.filter((p) => p !== confirmed[0]);
    bullet = `Confirmed ${confirmed[0]} partner; also active on ${others.slice(0, 2).join(" and ")}`;
    strength = "confirmed";
  } else if (confirmed.length === 1) {
    bullet = `Confirmed ${confirmed[0]} partner — accesses deals through CION's channel`;
    strength = "confirmed";
  } else if (brochure.length > 0) {
    bullet = `Listed ${brochure.slice(0, 2).join(" and ")} on their ADV brochure`;
    strength = "inferred";
  } else if (inferred.length >= 2) {
    bullet = `Active on ${inferred[0]} and ${inferred[1]} — overlaps CION's distribution channels (EDGAR inferred)`;
    strength = "inferred";
  } else {
    bullet = `Likely ${inferred[0]} partner — EDGAR filing inference`;
    strength = "inferred";
  }
  return {
    bullet,
    strength,
    source: confirmed.length > 0 ? "Platform CSV" : brochure.length > 0 ? "ADV Brochure" : "EDGAR Inferred",
  };
}

function allocationSignal(a: AdvisorProfile): Signal | null {
  if (a.allocation_count_90d === 0) return null;
  const n = a.allocation_count_90d;
  const bullet =
    n >= 3 ? `Allocated to ${n} similar funds in the last 90 days — actively deploying capital`
    : n === 2 ? `Allocated to 2 similar credit funds in the last 90 days`
    : `Made 1 allocation to a similar fund in the last 90 days`;
  return { bullet, strength: "confirmed", source: "ria_fund_allocations (Form D)" };
}

function privateFundAumSignal(a: AdvisorProfile): Signal | null {
  if (!a.private_fund_aum || a.private_fund_aum < 1e7) return null;
  const bullet =
    a.private_fund_aum >= 5e8 ? `${a.private_fund_aum_fmt} already in private funds — high-conviction buyer`
    : a.private_fund_aum >= 1e8 ? `${a.private_fund_aum_fmt} in private fund allocations — established appetite`
    : `${a.private_fund_aum_fmt} in private fund allocations`;
  return { bullet, strength: "confirmed", source: "Form ADV Schedule D" };
}

function aumSignal(a: AdvisorProfile): Signal | null {
  if (!a.aum || a.aum_tier === "unknown") return null;
  const bullet =
    a.aum_tier === "mega" ? `${a.aum_fmt} AUM — institutional scale, meaningful ticket size expected`
    : a.aum_tier === "large" ? `${a.aum_fmt} AUM — significant allocation capacity`
    : a.aum_fmt ? `${a.aum_fmt} AUM`
    : null;
  if (!bullet) return null;
  return { bullet, strength: "confirmed", source: "Form ADV (IAPD)" };
}

function headcountSignal(a: AdvisorProfile): Signal | null {
  if (!a.num_advisors || a.num_advisors < 50) return null;
  const bullet =
    a.num_advisors >= 200
      ? `${a.num_advisors.toLocaleString()} advisors on staff — broad reach across the firm`
      : `${a.num_advisors} advisors on staff`;
  return { bullet, strength: "confirmed", source: "Form ADV (IAPD)" };
}

// Future hooks — uncomment and fill in when data source is wired:
// function crmEmailSignal(a: AdvisorProfile): Signal | null { ... }
// function priorCionAllocationSignal(a: AdvisorProfile): Signal | null { ... }
// function mandateSizeSignal(a: AdvisorProfile): Signal | null { ... }

function buildSignals(a: AdvisorProfile): Signal[] {
  return [
    allocationSignal(a),
    platformSignal(a),
    privateFundAumSignal(a),
    aumSignal(a),
    headcountSignal(a),
  ].filter((s): s is Signal => s !== null).slice(0, 4);
}

function getConfidence(signals: Signal[]): { label: string; dotColor: string } {
  if (signals.length === 0) return { label: "Limited data", dotColor: "bg-slate-400" };
  const confirmed = signals.filter((s) => s.strength === "confirmed").length;
  if (confirmed >= 2) return { label: "Strong signal",    dotColor: "bg-emerald-400" };
  if (confirmed >= 1) return { label: "Emerging signal",  dotColor: "bg-blue-400" };
  return                      { label: "Limited data",    dotColor: "bg-slate-400" };
}

// ── Priority — on dark header backgrounds ─────────────────────────────────────

interface Priority {
  label: string;
  emoji: string;
  // badge on dark (accordion header)
  darkBadge: string;
  // rank circle color
  rankBg: string;
}

function getPriority(a: AdvisorProfile): Priority {
  const hasDeals        = a.allocation_count_90d > 0;
  const multiPlat       = a.platform_count >= 2;
  const onePlat         = a.platform_count === 1;
  const bigAum          = a.aum_tier === "mega" || a.aum_tier === "large";
  const hasConfirmedPlat = Object.values(a.platform_sources ?? {}).some((s) => s === "csv");

  if ((hasDeals && (multiPlat || bigAum)) || (hasConfirmedPlat && (hasDeals || bigAum))) {
    return { label: "High Priority", emoji: "🔥", darkBadge: "bg-red-500/20 text-red-300 border-red-500/40",  rankBg: "bg-red-500" };
  }
  if (hasDeals || multiPlat || (onePlat && bigAum) || hasConfirmedPlat) {
    return { label: "Medium",        emoji: "⚡", darkBadge: "bg-blue-500/20 text-blue-300 border-blue-500/40", rankBg: "bg-blue-600" };
  }
  return   { label: "Watchlist",     emoji: "👀", darkBadge: "bg-slate-600 text-slate-300 border-slate-500",   rankBg: "bg-slate-500" };
}

function getOutcomeAnchor(a: AdvisorProfile, signals: Signal[]): string | null {
  const hasDeals  = a.allocation_count_90d > 0;
  const multiPlat = a.platform_count >= 2;
  if (hasDeals && multiPlat)    return "Active buying behavior + multi-platform presence → strong fit for current raise";
  if (hasDeals)                 return "Recent allocation activity + confirmed channel access → worth a call this week";
  if (multiPlat && (a.aum_tier === "mega" || a.aum_tier === "large"))
                                return "Institutional buyer across multiple channels → positioned to allocate at scale";
  if (a.platform_count > 0 && (a.aum_tier === "mega" || a.aum_tier === "large"))
                                return "Large AUM + platform access → capacity and channel confirmed";
  if (signals.length >= 3)      return "Multiple data points align → high confidence on fit";
  return null;
}

// ── Accordion item ────────────────────────────────────────────────────────────

function AccordionItem({
  advisor, rank, open, onToggle,
}: {
  advisor: AdvisorProfile;
  rank: number;
  open: boolean;
  onToggle: () => void;
}) {
  const priority   = getPriority(advisor);
  const signals    = buildSignals(advisor);
  const confidence = getConfidence(signals);
  const anchor     = getOutcomeAnchor(advisor, signals);

  return (
    <div className="overflow-hidden">
      {/* ── Collapsed header (always visible) ── */}
      <button
        onClick={onToggle}
        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors
          ${open ? "bg-slate-700" : "bg-slate-800 hover:bg-slate-750"}`}
        style={!open ? { } : {}}
      >
        {/* Rank */}
        <div className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white ${priority.rankBg}`}>
          {rank}
        </div>

        {/* Name + location */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white leading-tight truncate">{advisor.firm_name}</p>
          <p className="text-xs text-slate-400 mt-0.5 truncate">
            {[advisor.city, advisor.state].filter(Boolean).join(", ")}
            {advisor.aum_fmt ? ` · ${advisor.aum_fmt}` : ""}
          </p>
        </div>

        {/* Priority badge */}
        <span className={`shrink-0 hidden sm:inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full border ${priority.darkBadge}`}>
          {priority.emoji} {priority.label}
        </span>

        {/* Chevron */}
        <svg
          className={`shrink-0 w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* ── Expanded body ── */}
      {open && (
        <div className="bg-white border-t border-slate-200 px-4 py-4">
          {/* Mobile priority badge */}
          <div className="sm:hidden mb-3">
            <span className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full border bg-slate-100 text-slate-700 border-slate-200">
              {priority.emoji} {priority.label}
            </span>
          </div>

          {/* Signal bullets */}
          {signals.length > 0 ? (
            <ul className="space-y-1.5 mb-4">
              {signals.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <span className="text-slate-300 mt-0.5 shrink-0">•</span>
                  <span className="text-slate-800 font-medium leading-relaxed">{s.bullet}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-400 italic mb-4">No detailed signals yet — AUM and location available</p>
          )}

          {/* Anchor */}
          {anchor && (
            <p className="text-xs text-slate-500 italic mb-4">→ {anchor}</p>
          )}

          {/* Footer: confidence + Contact button */}
          <div className="flex items-center justify-between pt-3 border-t border-slate-100">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${confidence.dotColor}`} />
              <span className="text-xs text-slate-500">{confidence.label}</span>
            </div>
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-colors">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
              </svg>
              Contact
            </button>
          </div>
        </div>
      )}
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
  const [openSet, setOpenSet] = useState<Set<number>>(new Set());

  if (top10.length === 0) return null;

  const highCount = top10.filter((a) => getPriority(a).label === "High Priority").length;

  function toggle(i: number) {
    setOpenSet((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  return (
    <section className="mb-8">
      {/* Section header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Top 10 to Call This Week</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {highCount > 0
              ? `${highCount} high-priority firm${highCount > 1 ? "s" : ""} showing active buying signals`
              : "Ranked by platform presence, AUM, and recent allocation activity"}
            {territory && territory !== "All" ? ` · ${territory}` : ""}
          </p>
        </div>
        <span className="text-xs text-slate-400 hidden sm:inline">Public SEC + EDGAR data</span>
      </div>

      {/* Accordion list */}
      <div className="rounded-xl overflow-hidden border border-slate-700 divide-y divide-slate-700 shadow-sm">
        {top10.map((a, i) => (
          <AccordionItem
            key={a.crd_number || i}
            advisor={a}
            rank={i + 1}
            open={openSet.has(i)}
            onToggle={() => toggle(i)}
          />
        ))}
      </div>

      <p className="text-xs text-slate-400 mt-2 text-right">
        Expand any row to see signal detail · Contact placeholder for CRM / Salesforce
      </p>
    </section>
  );
}
