"use client";

import { AdvisorProfile } from "@/lib/types";

// ── Priority tier ────────────────────────────────────────────────────────────

interface PriorityTier {
  label: string;
  emoji: string;
  badgeClass: string;
  borderClass: string;
  rankClass: string;
}

function getPriority(a: AdvisorProfile): PriorityTier {
  const hasRecentDeals = a.allocation_count_90d > 0;
  const multiPlatform = a.platform_count >= 2;
  const onePlatform = a.platform_count === 1;
  const bigAum = a.aum_tier === "mega" || a.aum_tier === "large";

  if (hasRecentDeals && (multiPlatform || bigAum)) {
    return {
      label: "High Priority",
      emoji: "🔥",
      badgeClass: "bg-red-50 text-red-700 border-red-200",
      borderClass: "border-red-200",
      rankClass: "bg-red-600 text-white",
    };
  }
  if (hasRecentDeals || multiPlatform || (onePlatform && bigAum)) {
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

// ── Confidence label ─────────────────────────────────────────────────────────

function getConfidence(a: AdvisorProfile): { label: string; color: string } {
  const signals =
    (a.platform_count > 0 ? 1 : 0) +
    (a.allocation_count_90d > 0 ? 1 : 0) +
    (a.aum != null ? 1 : 0) +
    (a.private_fund_aum != null ? 1 : 0);

  if (signals >= 3)
    return { label: "Strong signal", color: "text-emerald-600" };
  if (signals >= 2)
    return { label: "Emerging signal", color: "text-amber-600" };
  return { label: "Limited data", color: "text-slate-400" };
}

// ── Reasoning bullets ────────────────────────────────────────────────────────

function buildReasons(a: AdvisorProfile): string[] {
  const r: string[] = [];

  // Recent deal activity — highest signal
  if (a.allocation_count_90d >= 3) {
    r.push(`Allocated to ${a.allocation_count_90d} similar funds in the last 90 days — actively deploying`);
  } else if (a.allocation_count_90d === 2) {
    r.push(`Allocated to 2 similar funds in the last 90 days`);
  } else if (a.allocation_count_90d === 1) {
    r.push(`Made 1 allocation to a similar fund in the last 90 days`);
  }

  // Platform access — confirms distribution channel overlap
  if (a.platforms.length >= 3) {
    r.push(
      `Active on ${a.platforms.slice(0, 2).join(", ")} and ${a.platforms.length - 2} other platforms CION distributes through`
    );
  } else if (a.platforms.length === 2) {
    r.push(`Active on both ${a.platforms[0]} and ${a.platforms[1]} — overlaps CION's distribution channels`);
  } else if (a.platforms.length === 1) {
    r.push(`Confirmed ${a.platforms[0]} partner — accesses deals through CION's channel`);
  }

  // Private fund AUM — shows appetite
  if (a.private_fund_aum && a.private_fund_aum >= 5e8) {
    r.push(`${a.private_fund_aum_fmt} already allocated to private funds — high conviction buyer`);
  } else if (a.private_fund_aum && a.private_fund_aum >= 1e8) {
    r.push(`${a.private_fund_aum_fmt} in private fund allocations — established appetite`);
  }

  // AUM tier — capacity signal
  if (a.aum_tier === "mega") {
    r.push(`${a.aum_fmt} AUM — institutional scale, meaningful ticket size expected`);
  } else if (a.aum_tier === "large") {
    r.push(`${a.aum_fmt} AUM — significant allocation capacity`);
  } else if (a.aum_tier === "mid" && a.aum_fmt) {
    r.push(`${a.aum_fmt} AUM`);
  }

  // Advisor count — reach within firm
  if (a.num_advisors && a.num_advisors >= 200) {
    r.push(`${a.num_advisors.toLocaleString()} advisors — broad reach across the firm`);
  } else if (a.num_advisors && a.num_advisors >= 50) {
    r.push(`${a.num_advisors} advisors on staff`);
  }

  return r.slice(0, 4); // cap at 4 bullets
}

// ── Outcome anchor ───────────────────────────────────────────────────────────

function getOutcomeAnchor(a: AdvisorProfile): string | null {
  if (a.allocation_count_90d > 0 && a.platform_count > 0) {
    return "Active buying behavior + confirmed platform access → strong fit for current raise";
  }
  if (a.platform_count >= 2) {
    return "Multi-platform presence → positioned to access CION across channels";
  }
  if (a.aum_tier === "mega" && a.platform_count > 0) {
    return "Institutional buyer with confirmed platform access → worth a direct call";
  }
  if (a.allocation_count_90d > 0) {
    return "Recent allocation activity signals active deployment cycle";
  }
  return null;
}

// ── Single card ──────────────────────────────────────────────────────────────

function TopAdvisorCard({ advisor, rank }: { advisor: AdvisorProfile; rank: number }) {
  const priority = getPriority(advisor);
  const confidence = getConfidence(advisor);
  const reasons = buildReasons(advisor);
  const anchor = getOutcomeAnchor(advisor);

  return (
    <div className={`bg-white rounded-xl border ${priority.borderClass} p-5 flex gap-4`}>
      {/* Rank pill */}
      <div className="shrink-0 flex flex-col items-center gap-2 pt-0.5">
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${priority.rankClass}`}
        >
          {rank}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header row */}
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
          <span
            className={`shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full border ${priority.badgeClass}`}
          >
            {priority.emoji} {priority.label}
          </span>
        </div>

        {/* Reasoning bullets */}
        {reasons.length > 0 && (
          <ul className="space-y-1 mb-3">
            {reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-600">
                <span className="text-slate-300 mt-0.5 shrink-0">•</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Footer: anchor + confidence */}
        <div className="flex items-center justify-between gap-3 pt-2 border-t border-slate-100">
          {anchor ? (
            <p className="text-xs text-slate-500 italic leading-tight">
              → {anchor}
            </p>
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

// ── Panel ────────────────────────────────────────────────────────────────────

interface Props {
  advisors: AdvisorProfile[];
  territory: string;
}

export default function TopAdvisorsPanel({ advisors, territory }: Props) {
  const top10 = advisors.slice(0, 10);

  if (top10.length === 0) return null;

  const highCount = top10.filter(
    (a) => getPriority(a).label === "High Priority"
  ).length;

  return (
    <section className="mb-8">
      {/* Section header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            Top 10 to Call This Week
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {highCount > 0
              ? `${highCount} high-priority firm${highCount > 1 ? "s" : ""} showing active buying signals`
              : "Ranked by platform presence, AUM, and recent allocation activity"}
            {territory ? ` · ${territory}` : ""}
          </p>
        </div>
        <span className="text-xs text-slate-400 hidden sm:inline">
          Based on public SEC + EDGAR data
        </span>
      </div>

      {/* Cards */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {top10.map((a, i) => (
          <TopAdvisorCard key={a.crd_number || i} advisor={a} rank={i + 1} />
        ))}
      </div>
    </section>
  );
}
