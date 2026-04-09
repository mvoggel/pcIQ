"use client";

import { useEffect, useState } from "react";
import { AdvisorProfile, AdvisorFund } from "@/lib/types";
import { fetchAdvisorFunds } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
import {
  buildSignals,
  getPriority,
  getOutcomeAnchor,
  getAumBucket,
  SOURCE_TAG_STYLES,
  SOURCE_TAG_LABELS,
  Signal,
} from "@/lib/advisorSignals";

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

  const location  = [advisor.city, advisor.state].filter(Boolean).join(", ");
  const aumBucket = getAumBucket(advisor.aum);

  const [activeFunds, setActiveFunds] = useState<AdvisorFund[]>([]);
  useEffect(() => {
    if (advisor.allocation_count_90d > 0 && advisor.crd_number) {
      fetchAdvisorFunds(advisor.crd_number)
        .then((r) => setActiveFunds(r.funds))
        .catch(() => {/* silent */});
    }
  }, [advisor.crd_number, advisor.allocation_count_90d]);

  type SyncState = "idle" | "syncing" | "synced" | "duplicate" | "not_configured" | "error";
  const [syncState, setSyncState] = useState<SyncState>("idle");
  const [syncedAt, setSyncedAt] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleContact() {
    if (syncState === "syncing" || syncState === "synced") return;
    setSyncState("syncing");
    setErrorMsg(null);
    try {
      const payload = {
        firm_name: advisor.firm_name,
        crd_number: advisor.crd_number,
        aum_fmt: advisor.aum_fmt ?? null,
        city: advisor.city ?? null,
        state: advisor.state ?? null,
        priority_label: priority.label,
        anchor_text: anchor ?? null,
        signal_bullets: signals.slice(0, 3).map((s) => s.bullet),
      };
      const res = await fetch(`${API_BASE}/api/salesforce/push-lead`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.status === "created") {
        setSyncState("synced");
        setSyncedAt(new Date().toLocaleTimeString());
      } else if (data.status === "duplicate") {
        setSyncState("duplicate");
      } else if (data.status === "not_configured") {
        setSyncState("not_configured");
        setErrorMsg(data.message ?? "Salesforce not configured.");
      } else {
        throw new Error(data.message || "Unknown response");
      }
    } catch (e: unknown) {
      setSyncState("error");
      setErrorMsg(e instanceof Error ? e.message : "Unknown error");
    }
  }

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
            {advisor.aum_fmt && (
              <span className="text-sm text-slate-500">{advisor.aum_fmt}</span>
            )}
            {aumBucket && (
              <span className={`inline-flex items-center text-xs px-2 py-0.5 rounded border font-medium ${aumBucket.color}`}>
                {aumBucket.label}
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

          {/* Active fund allocations — cross-tab intelligence */}
          {activeFunds.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-flex items-center text-xs px-2 py-0.5 rounded border font-semibold bg-blue-50 text-blue-700 border-blue-200">
                  Form D · 90d
                </span>
                <div className="h-px flex-1 bg-slate-100" />
              </div>
              <p className="text-xs text-slate-500 mb-2">
                Actively deploying into {activeFunds.length} competing fund{activeFunds.length > 1 ? "s" : ""} — same platforms as CION's distribution channels:
              </p>
              <ul className="space-y-1.5 pl-1">
                {activeFunds.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-700 leading-relaxed">
                    <span className="shrink-0 text-slate-300 mt-0.5">•</span>
                    <span>
                      <span className="font-medium">{f.entity_name}</span>
                      {f.investment_fund_type && (
                        <span className="text-slate-400"> · {f.investment_fund_type}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
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
        <div className="px-5 py-4 border-t border-slate-100 space-y-2">
          {/* Error / status toast */}
          {errorMsg && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 leading-relaxed">
              {errorMsg}
            </p>
          )}
          {syncState === "duplicate" && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              Lead already exists in Salesforce.
            </p>
          )}

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-slate-400">
              {[...new Set(signals.map((s) => s.source))].join(" · ") || "Form ADV · EDGAR"}
            </p>

            {syncState === "synced" ? (
              <span className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-50 text-emerald-700 border border-emerald-200 text-sm font-semibold rounded-lg">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
                Synced to Salesforce{syncedAt ? ` · ${syncedAt}` : ""}
              </span>
            ) : (
              <button
                onClick={handleContact}
                disabled={syncState === "syncing"}
                className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-wait text-white text-sm font-semibold rounded-lg transition-colors"
              >
                {syncState === "syncing" ? (
                  <>
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>
                    Syncing…
                  </>
                ) : syncState === "error" ? (
                  <>
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                    </svg>
                    Retry
                  </>
                ) : (
                  <>
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
                    </svg>
                    Contact
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
