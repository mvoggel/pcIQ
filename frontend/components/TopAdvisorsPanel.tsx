"use client";

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
  bullet: string;           // plain-English bullet text shown to wholesaler
  strength: SignalStrength; // drives confidence roll-up
  source: string;           // data source label shown on hover / future tooltip
}

// ── Platform signal ───────────────────────────────────────────────────────────
// Source: ria_platforms table (populated from iCapital/CAIS CSV, ADV brochures,
// or EDGAR inference). "csv" = directly confirmed from platform data file.

function platformSignal(a: AdvisorProfile): Signal | null {
  if (a.platforms.length === 0) return null;

  const sources = a.platform_sources ?? {};

  // Rank by confidence: csv > adv_brochure > edgar_inferred
  const confirmed = a.platforms.filter((p) => sources[p] === "csv");
  const brochure  = a.platforms.filter((p) => sources[p] === "adv_brochure");
  const inferred  = a.platforms.filter((p) => sources[p] === "edgar_inferred" || !sources[p]);

  // Build bullet text
  let bullet: string;
  let strength: SignalStrength;

  if (confirmed.length >= 2) {
    bullet = `Confirmed ${confirmed[0]} and ${confirmed[1]} partner — direct channel overlap`;
    strength = "confirmed";
  } else if (confirmed.length === 1 && a.platforms.length >= 2) {
    const others = a.platforms.filter((p) => p !== confirmed[0]);
    bullet = `Confirmed ${confirmed[0]} partner; also active on ${others.slice(0,2).join(" and ")}`;
    strength = "confirmed";
  } else if (confirmed.length === 1) {
    bullet = `Confirmed ${confirmed[0]} partner — accesses deals through CION's channel`;
    strength = "confirmed";
  } else if (brochure.length > 0) {
    const named = brochure.slice(0, 2).join(" and ");
    bullet = `Listed ${named} on their ADV brochure`;
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

// ── Recent allocation signal ──────────────────────────────────────────────────
// Source: ria_fund_allocations table (Form D timestamps, Phase 2+).
// When CRM confirms a prior CION allocation this should be replaced/augmented.

function allocationSignal(a: AdvisorProfile): Signal | null {
  if (a.allocation_count_90d === 0) return null;

  const n = a.allocation_count_90d;
  const bullet =
    n >= 3
      ? `Allocated to ${n} similar funds in the last 90 days — actively deploying capital`
      : n === 2
      ? `Allocated to 2 similar credit funds in the last 90 days`
      : `Made 1 allocation to a similar fund in the last 90 days`;

  return { bullet, strength: "confirmed", source: "ria_fund_allocations (Form D)" };
}

// ── Private fund AUM signal ───────────────────────────────────────────────────
// Source: rias.private_fund_aum (ADV Schedule D — currently sparse; fills in as
// ADV parser is upgraded from Part 1A to Schedule D).

function privateFundAumSignal(a: AdvisorProfile): Signal | null {
  if (!a.private_fund_aum || a.private_fund_aum < 1e7) return null;

  const bullet =
    a.private_fund_aum >= 5e8
      ? `${a.private_fund_aum_fmt} already in private funds — high-conviction alternative buyer`
      : a.private_fund_aum >= 1e8
      ? `${a.private_fund_aum_fmt} in private fund allocations — established appetite`
      : `${a.private_fund_aum_fmt} in private fund allocations`;

  return { bullet, strength: "confirmed", source: "Form ADV Schedule D" };
}

// ── AUM capacity signal ───────────────────────────────────────────────────────
// Source: rias.aum (Form ADV Part 1A Item 5, enriched via IAPD).

function aumSignal(a: AdvisorProfile): Signal | null {
  if (!a.aum || a.aum_tier === "unknown") return null;

  const bullet =
    a.aum_tier === "mega"
      ? `${a.aum_fmt} AUM — institutional scale, meaningful ticket size expected`
      : a.aum_tier === "large"
      ? `${a.aum_fmt} AUM — significant allocation capacity`
      : a.aum_fmt
      ? `${a.aum_fmt} AUM`
      : null;

  if (!bullet) return null;
  return { bullet, strength: "confirmed", source: "Form ADV (IAPD)" };
}

// ── Advisor headcount signal ──────────────────────────────────────────────────
// Source: rias.num_advisors (Form ADV Part 1A Item 5).

function headcountSignal(a: AdvisorProfile): Signal | null {
  if (!a.num_advisors || a.num_advisors < 50) return null;

  const bullet =
    a.num_advisors >= 200
      ? `${a.num_advisors.toLocaleString()} advisors on staff — broad reach across the firm`
      : `${a.num_advisors} advisors on staff`;

  return { bullet, strength: "confirmed", source: "Form ADV (IAPD)" };
}

// ── FUTURE SIGNAL HOOKS ───────────────────────────────────────────────────────
// These return null until the data source is wired. Add the data field to
// AdvisorProfile and fill in the logic when ready.

// function crmEmailSignal(a: AdvisorProfile): Signal | null {
//   TODO: when CRM email engagement data is available
//   if (!a.email_opens_30d) return null;
//   return { bullet: `Opened your last ${a.email_opens_30d} emails`, strength: "confirmed", source: "CRM" };
// }

// function priorCionAllocationSignal(a: AdvisorProfile): Signal | null {
//   TODO: when prior CION allocation history is available (CRM / fund records)
//   if (!a.prior_cion_allocation_amt) return null;
//   return { bullet: `Previously allocated $${fmt(a.prior_cion_allocation_amt)} to a CION fund`, strength: "confirmed", source: "CRM / Fund Records" };
// }

// function mandateSizeSignal(a: AdvisorProfile): Signal | null {
//   TODO: when strategy preference data is available (inferred from allocation history)
//   if (!a.preferred_strategy) return null;
//   return { bullet: `Strategy preference aligns: ${a.preferred_strategy}`, strength: "inferred", source: "Allocation History" };
// }

// ── Assemble all signals ──────────────────────────────────────────────────────

function buildSignals(a: AdvisorProfile): Signal[] {
  return [
    allocationSignal(a),       // highest intent signal — recent deals first
    platformSignal(a),         // channel overlap — confirms access
    privateFundAumSignal(a),   // shows existing appetite
    aumSignal(a),              // capacity
    headcountSignal(a),        // reach
    // crmEmailSignal(a),      // TODO: plug in when CRM data arrives
    // priorCionAllocationSignal(a), // TODO
    // mandateSizeSignal(a),   // TODO
  ]
    .filter((s): s is Signal => s !== null)
    .slice(0, 4); // cap at 4 bullets per card
}

// ── Confidence roll-up ────────────────────────────────────────────────────────

function getConfidence(signals: Signal[]): { label: string; color: string } {
  if (signals.length === 0)
    return { label: "Limited data", color: "text-slate-400" };

  const confirmedCount = signals.filter((s) => s.strength === "confirmed").length;

  if (confirmedCount >= 2)
    return { label: "Strong signal", color: "text-emerald-600" };
  if (confirmedCount >= 1)
    return { label: "Emerging signal", color: "text-amber-600" };
  return { label: "Limited data", color: "text-slate-400" };
}

// ── Priority tier ─────────────────────────────────────────────────────────────

interface PriorityTier {
  label: string;
  emoji: string;
  badgeClass: string;
  borderClass: string;
  rankClass: string;
}

function getPriority(a: AdvisorProfile): PriorityTier {
  const hasDeals   = a.allocation_count_90d > 0;
  const multiPlat  = a.platform_count >= 2;
  const onePlat    = a.platform_count === 1;
  const bigAum     = a.aum_tier === "mega" || a.aum_tier === "large";
  const hasConfirmedPlat = Object.values(a.platform_sources ?? {}).some((s) => s === "csv");

  if (hasDeals && (multiPlat || bigAum) || hasConfirmedPlat && (hasDeals || bigAum)) {
    return {
      label: "High Priority",
      emoji: "🔥",
      badgeClass: "bg-red-50 text-red-700 border-red-200",
      borderClass: "border-red-200",
      rankClass: "bg-red-600 text-white",
    };
  }
  if (hasDeals || multiPlat || (onePlat && bigAum) || hasConfirmedPlat) {
    return {
      label: "Medium",
      emoji: "⚡",
      badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
      borderClass: "border-amber-200",
      rankClass: "bg-amber-500 text-white",
    };
  }
  return {
    label: "Watchlist",
    emoji: "👀",
    badgeClass: "bg-slate-100 text-slate-600 border-slate-200",
    borderClass: "border-slate-200",
    rankClass: "bg-slate-400 text-white",
  };
}

// ── Outcome anchor ────────────────────────────────────────────────────────────

function getOutcomeAnchor(a: AdvisorProfile, signals: Signal[]): string | null {
  const hasDeals  = a.allocation_count_90d > 0;
  const multiPlat = a.platform_count >= 2;

  if (hasDeals && multiPlat)
    return "Active buying behavior + multi-platform presence → strong fit for current raise";
  if (hasDeals && a.platform_count === 1)
    return "Recent allocation activity + confirmed channel access → worth a call this week";
  if (multiPlat && (a.aum_tier === "mega" || a.aum_tier === "large"))
    return "Institutional buyer across multiple channels → positioned to allocate at scale";
  if (a.platform_count > 0 && (a.aum_tier === "mega" || a.aum_tier === "large"))
    return "Large AUM + platform access → capacity and channel confirmed";
  if (signals.length >= 3)
    return "Multiple data points align → high confidence on fit";
  return null;
}

// ── Single card ───────────────────────────────────────────────────────────────

function TopAdvisorCard({ advisor, rank }: { advisor: AdvisorProfile; rank: number }) {
  const priority   = getPriority(advisor);
  const signals    = buildSignals(advisor);
  const confidence = getConfidence(signals);
  const anchor     = getOutcomeAnchor(advisor, signals);

  return (
    <div className={`bg-white rounded-xl border ${priority.borderClass} p-5 flex gap-4`}>
      {/* Rank */}
      <div className="shrink-0 pt-0.5">
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${priority.rankClass}`}
        >
          {rank}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <h3 className="font-semibold text-slate-900 text-sm leading-tight">
              {advisor.firm_name}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              {[advisor.city, advisor.state].filter(Boolean).join(", ")}
              {advisor.aum_fmt ? ` · ${advisor.aum_fmt} AUM` : ""}
            </p>
          </div>
          <span className={`shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full border ${priority.badgeClass}`}>
            {priority.emoji} {priority.label}
          </span>
        </div>

        {/* Signal bullets */}
        {signals.length > 0 ? (
          <ul className="space-y-1 mb-3">
            {signals.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-600">
                <span className="text-slate-300 mt-0.5 shrink-0">•</span>
                <span>{s.bullet}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-400 mb-3 italic">No detailed signals yet — AUM and location available</p>
        )}

        {/* Footer: anchor + confidence */}
        <div className="flex items-center justify-between gap-3 pt-2 border-t border-slate-100">
          {anchor ? (
            <p className="text-xs text-slate-500 italic leading-tight">→ {anchor}</p>
          ) : (
            <span />
          )}
          <span className={`text-xs font-medium shrink-0 ${confidence.color}`}>
            {confidence.label}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface Props {
  advisors: AdvisorProfile[];   // full ranked list — top 10 sliced here
  territory: string;
}

export default function TopAdvisorsPanel({ advisors, territory }: Props) {
  const top10 = advisors.slice(0, 10);
  if (top10.length === 0) return null;

  const highCount = top10.filter((a) => getPriority(a).label === "High Priority").length;

  return (
    <section className="mb-8">
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

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {top10.map((a, i) => (
          <TopAdvisorCard key={a.crd_number || i} advisor={a} rank={i + 1} />
        ))}
      </div>
    </section>
  );
}
