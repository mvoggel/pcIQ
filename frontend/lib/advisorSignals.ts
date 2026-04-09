/**
 * Advisor signal framework — single source of truth for scoring, priority,
 * and call-brief copy across all advisor UI surfaces (list rows, modal, etc.)
 *
 * Data sources that feed into a unified score:
 *   - SEC Form 13F  → BDC holdings (direct proxy for CION buyer universe)
 *   - EDGAR Form D  → allocation frequency in similar funds
 *   - Form ADV/IAPD → AUM, headcount, platform presence
 *
 * To add a new data source:
 *   1. Add a Signal builder function below
 *   2. Call it inside buildSignals()
 *   null = no data available (not a negative signal — keeps the UI honest)
 */

import { AdvisorProfile } from "@/lib/types";

// ── Types ─────────────────────────────────────────────────────────────────────

export type SignalStrength = "confirmed" | "inferred" | "limited";

export interface Signal {
  bullet: string;        // plain-language sentence for a CION wholesaler
  strength: SignalStrength;
  source: string;        // display label: "SEC Form 13F" | "Form ADV" | etc.
  sourceTag: "thirteenf" | "formd" | "adv" | "brochure" | "inferred";
}

export interface Priority {
  label: string;
  emoji: string;
  score: 1 | 2 | 3;     // 3=High, 2=Medium, 1=Watchlist
  // badges for light backgrounds (rows, modal header)
  lightBadge: string;
  // rank circle color
  rankBg: string;
}

export interface Confidence {
  label: string;
  dotColor: string;
}

// ── Signal builders ───────────────────────────────────────────────────────────

function thirteenFSignal(a: AdvisorProfile): Signal | null {
  if (!a.thirteenf_bdc_value_usd || a.thirteenf_bdc_value_usd <= 0) return null;
  const val    = a.thirteenf_bdc_value_usd;
  const period = a.thirteenf_period ? ` as of ${a.thirteenf_period.slice(0, 7)}` : "";
  const fmt    = val >= 1e9 ? `$${(val / 1e9).toFixed(1)}B` : `$${Math.round(val / 1e6)}M`;
  const bullet =
    val >= 5e8
      ? `${fmt} in BDC positions${period} — institutional-scale buyer of this asset class`
      : val >= 1e8
      ? `${fmt} in BDC holdings${period} — established alternative credit allocator`
      : `${fmt} in BDC positions per SEC 13F filing${period}`;
  return { bullet, strength: "confirmed", source: "SEC Form 13F", sourceTag: "thirteenf" };
}

function allocationSignal(a: AdvisorProfile): Signal | null {
  if (a.allocation_count_90d === 0) return null;
  const n = a.allocation_count_90d;
  const bullet =
    n >= 3 ? `Allocated to ${n} similar private credit funds in the last 90 days — actively deploying capital`
    : n === 2 ? `Allocated to 2 similar credit funds in the last 90 days`
    : `Made 1 allocation to a comparable fund in the last 90 days`;
  return { bullet, strength: "confirmed", source: "EDGAR Form D", sourceTag: "formd" };
}

function privateFundAumSignal(a: AdvisorProfile): Signal | null {
  if (!a.private_fund_aum || a.private_fund_aum < 1e7) return null;
  const bullet =
    a.private_fund_aum >= 5e8
      ? `${a.private_fund_aum_fmt} already allocated to private funds — high-conviction buyer`
      : a.private_fund_aum >= 1e8
      ? `${a.private_fund_aum_fmt} in private fund allocations — established appetite`
      : `${a.private_fund_aum_fmt} in private fund allocations`;
  return { bullet, strength: "confirmed", source: "Form ADV Schedule D", sourceTag: "adv" };
}

function aumSignal(a: AdvisorProfile): Signal | null {
  if (!a.aum || a.aum_tier === "unknown") return null;
  const bullet =
    a.aum_tier === "mega" ? `${a.aum_fmt} AUM — institutional scale, meaningful ticket size expected`
    : a.aum_tier === "large" ? `${a.aum_fmt} AUM — significant allocation capacity`
    : a.aum_fmt ? `${a.aum_fmt} AUM`
    : null;
  if (!bullet) return null;
  return { bullet, strength: "confirmed", source: "Form ADV (IAPD)", sourceTag: "adv" };
}

function headcountSignal(a: AdvisorProfile): Signal | null {
  if (!a.num_advisors || a.num_advisors < 50) return null;
  const bullet =
    a.num_advisors >= 200
      ? `${a.num_advisors.toLocaleString()} advisors on staff — broad distribution reach across the firm`
      : `${a.num_advisors} advisors on staff`;
  return { bullet, strength: "confirmed", source: "Form ADV (IAPD)", sourceTag: "adv" };
}

function platformSignal(a: AdvisorProfile): Signal | null {
  if (a.platforms.length === 0) return null;
  const sources  = a.platform_sources ?? {};
  const brochure = a.platforms.filter((p) => sources[p] === "adv_brochure");
  const inferred = a.platforms.filter((p) => sources[p] === "edgar_inferred" || !sources[p]);

  let bullet: string;
  if (brochure.length >= 2) {
    bullet = `Lists ${brochure[0]} and ${brochure[1]} on their ADV brochure`;
  } else if (brochure.length === 1 && a.platforms.length >= 2) {
    const others = a.platforms.filter((p) => p !== brochure[0]);
    bullet = `Lists ${brochure[0]} on ADV brochure; active on ${others.slice(0, 2).join(" and ")}`;
  } else if (brochure.length === 1) {
    bullet = `Lists ${brochure[0]} on their ADV brochure — alternative credit channel presence`;
  } else if (inferred.length >= 2) {
    bullet = `Active on ${inferred[0]} and ${inferred[1]} — inferred from EDGAR filings`;
  } else if (inferred.length === 1) {
    bullet = `Likely ${inferred[0]} participant — inferred from EDGAR filings`;
  } else {
    return null;
  }
  const tag: Signal["sourceTag"] = brochure.length > 0 ? "brochure" : "inferred";
  return {
    bullet,
    strength: brochure.length > 0 ? "inferred" : "limited",
    source: brochure.length > 0 ? "ADV Brochure" : "EDGAR Inferred",
    sourceTag: tag,
  };
}

// ── Combined builder ──────────────────────────────────────────────────────────

/** Returns up to 5 signals, highest-confidence first. */
export function buildSignals(a: AdvisorProfile): Signal[] {
  return [
    thirteenFSignal(a),
    allocationSignal(a),
    privateFundAumSignal(a),
    aumSignal(a),
    headcountSignal(a),
    platformSignal(a),
  ].filter((s): s is Signal => s !== null).slice(0, 5);
}

// ── Priority ──────────────────────────────────────────────────────────────────

export function getPriority(a: AdvisorProfile): Priority {
  // Use the backend-calculated score as single source of truth.
  // Score 3 = High: Form D + 13F + AUM ≥ $1B
  // Score 2 = Medium: any two of those three pillars
  // Score 1 = Watchlist: one signal or AUM ≥ $500M
  const score = a.priority_score ?? 1;

  if (score === 3) {
    return {
      label: "High Priority", emoji: "", score: 3,
      lightBadge: "bg-red-50 text-red-700 border-red-200",
      rankBg: "bg-red-500",
    };
  }
  if (score === 2) {
    return {
      label: "Medium", emoji: "", score: 2,
      lightBadge: "bg-blue-50 text-blue-700 border-blue-200",
      rankBg: "bg-blue-500",
    };
  }
  return {
    label: "Watchlist", emoji: "", score: 1,
    lightBadge: "bg-slate-100 text-slate-500 border-slate-200",
    rankBg: "bg-slate-400",
  };
}

// ── Confidence ────────────────────────────────────────────────────────────────

export function getConfidence(signals: Signal[], a: AdvisorProfile): Confidence {
  const bigAum    = a.aum_tier === "mega" || a.aum_tier === "large";
  const multiPlat = a.platform_count >= 2;
  const has13F    = (a.thirteenf_bdc_value_usd ?? 0) >= 1e8;
  const confirmed = signals.filter((s) => s.strength === "confirmed").length;

  if (confirmed >= 2 || (bigAum && (multiPlat || has13F)))
    return { label: "Strong signal",   dotColor: "bg-emerald-400" };
  if (confirmed >= 1 || bigAum || multiPlat || has13F)
    return { label: "Emerging signal", dotColor: "bg-blue-400" };
  return   { label: "Limited data",    dotColor: "bg-slate-300" };
}

// ── Outcome anchor ────────────────────────────────────────────────────────────

/** One-line reason to call — shown prominently in the call brief. */
export function getOutcomeAnchor(a: AdvisorProfile, signals: Signal[]): string | null {
  const hasDeals     = a.allocation_count_90d > 0;
  const multiPlat    = a.platform_count >= 2;
  const bigAum       = a.aum_tier === "mega" || a.aum_tier === "large";
  const bigThirteenF = (a.thirteenf_bdc_value_usd ?? 0) >= 1e8;

  if (hasDeals && multiPlat)    return "Active buying across multiple channels — strong fit for CION's current raise";
  if (hasDeals && bigThirteenF) return "Recent fund allocations + confirmed BDC position holder — call this week";
  if (hasDeals)                 return "Recent allocation activity — high probability of receptivity right now";
  if (bigThirteenF && bigAum)   return "Institutional BDC holder at scale — already buys this asset class, positioned to add CION";
  if (bigThirteenF)             return "Confirmed BDC buyer per SEC 13F — already allocates to this asset class";
  if (multiPlat && bigAum)      return "Institutional scale + active in alternative credit — positioned to allocate";
  if (a.platform_count > 0 && bigAum)
                                return "Large AUM + inferred alternative credit presence — capacity and appetite align";
  if (signals.length >= 3)      return "Multiple independent data points align — high confidence on fit";
  return null;
}

// ── Source tag display helpers ────────────────────────────────────────────────

export const SOURCE_TAG_STYLES: Record<Signal["sourceTag"], string> = {
  thirteenf: "bg-blue-50 text-blue-700 border-blue-200",
  formd:     "bg-emerald-50 text-emerald-700 border-emerald-200",
  adv:       "bg-slate-100 text-slate-600 border-slate-200",
  brochure:  "bg-violet-50 text-violet-700 border-violet-200",
  inferred:  "bg-amber-50 text-amber-600 border-amber-200",
};

export const SOURCE_TAG_LABELS: Record<Signal["sourceTag"], string> = {
  thirteenf: "SEC 13F",
  formd:     "Form D",
  adv:       "Form ADV",
  brochure:  "ADV Brochure",
  inferred:  "EDGAR Inferred",
};

// ── AUM bucket ────────────────────────────────────────────────────────────────

/**
 * Returns a precise AUM tier label + Tailwind color string based on raw AUM.
 * Replaces the coarse mega/large/mid/small backend tier for display purposes.
 */
export function getAumBucket(aum: number | null): { label: string; color: string } | null {
  if (!aum || aum <= 0) return null;
  if (aum >= 200e9) return { label: ">$200B", color: "bg-purple-200 text-purple-900 border-purple-300" };
  if (aum >= 100e9) return { label: ">$100B", color: "bg-purple-100 text-purple-700 border-purple-200" };
  if (aum >= 50e9)  return { label: ">$50B",  color: "bg-indigo-100 text-indigo-700 border-indigo-200" };
  if (aum >= 25e9)  return { label: ">$25B",  color: "bg-blue-200 text-blue-800 border-blue-300"     };
  if (aum >= 10e9)  return { label: ">$10B",  color: "bg-blue-100 text-blue-700 border-blue-200"     };
  if (aum >= 5e9)   return { label: ">$5B",   color: "bg-sky-100 text-sky-700 border-sky-200"        };
  if (aum >= 1e9)   return { label: "$1–5B",  color: "bg-cyan-50 text-cyan-700 border-cyan-200"      };
  if (aum >= 5e8)   return { label: "$500M–1B", color: "bg-slate-100 text-slate-600 border-slate-200" };
  return                   { label: "<$500M", color: "bg-slate-50 text-slate-500 border-slate-100"   };
}
