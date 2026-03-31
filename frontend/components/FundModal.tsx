"use client";

import { useEffect } from "react";
import { Signal } from "@/lib/types";

function formatSize(m: number | null): string {
  if (m === null) return "Not disclosed";
  if (m >= 1000) return `$${(m / 1000).toFixed(1)}B`;
  return `$${m}M`;
}

function formatDate(d: string | null): string {
  if (!d) return "Not disclosed";
  return new Date(d).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 8
      ? "bg-emerald-100 text-emerald-800 border-emerald-200"
      : score >= 5
      ? "bg-amber-100 text-amber-800 border-amber-200"
      : "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded border text-sm font-bold ${color}`}>
      {score.toFixed(1)} / 10
    </span>
  );
}

function edgarUrl(cik: string, accessionNo: string): string {
  const clean = accessionNo.replace(/-/g, "");
  return `https://www.sec.gov/Archives/edgar/data/${cik}/${clean}/${accessionNo}.htm`;
}

interface Props {
  signal: Signal;
  onClose: () => void;
}

export default function FundModal({ signal, onClose }: Props) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const knownSet = new Set(signal.known_platforms.map((p) => p.toLowerCase()));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" />

      {/* Panel */}
      <div
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-slate-100">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-semibold text-slate-900 leading-tight">
                {signal.fund_name}
              </h2>
              <span className="inline-block mt-1 px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded">
                {signal.fund_type}
              </span>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 transition-colors shrink-0 mt-0.5"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5">

          {/* Key stats grid */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">Priority Score</p>
              <ScoreBadge score={signal.priority_score} />
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">Offering Size</p>
              <p className="text-sm font-medium text-slate-800">{formatSize(signal.offering_size_m)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">First Sale Date</p>
              <p className="text-sm text-slate-700">{formatDate(signal.date_of_first_sale)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">Fund Location</p>
              <p className="text-sm text-slate-700">{signal.fund_state || "—"}</p>
            </div>
          </div>

          {/* Distribution platforms */}
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">
              Distribution Platforms
              <span className="ml-1 normal-case text-slate-300">({signal.platforms.length})</span>
            </p>
            {signal.platforms.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {signal.platforms.map((p) => {
                  const known = knownSet.has(p.toLowerCase());
                  return (
                    <span
                      key={p}
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        known
                          ? "bg-blue-100 text-blue-700 border border-blue-200"
                          : "bg-slate-100 text-slate-600 border border-slate-200"
                      }`}
                    >
                      {known && <span className="mr-1">★</span>}
                      {p}
                    </span>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-400 italic">
                No broker-dealer compensation disclosed — likely a direct institutional placement.
              </p>
            )}
          </div>

          {/* Solicitation states */}
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">
              States Being Solicited
            </p>
            {signal.solicitation_states.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {signal.solicitation_states.map((s) => (
                  <span key={s} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded font-mono">
                    {s}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">All states / not specified</p>
            )}
          </div>

          {/* Future enrichment callout */}
          <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3">
            <p className="text-xs font-semibold text-blue-700 mb-1">Coming in a later release</p>
            <p className="text-xs text-blue-600 leading-relaxed">
              RIA intelligence: which advisors on iCapital or CAIS have allocated to this fund, their AUM,
              and contact territory — sourced from Form ADV.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-100 flex items-center justify-between">
          <a
            href={edgarUrl(signal.cik, signal.accession_no)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:text-blue-800 underline underline-offset-2"
          >
            View Form D on SEC EDGAR →
          </a>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-sm text-slate-500 hover:text-slate-700 border border-slate-200 rounded hover:bg-slate-50 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
