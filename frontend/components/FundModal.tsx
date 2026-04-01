"use client";

import { useEffect, useState } from "react";
import { ClientType, FundEnrichment, ManagerIntelligence, Signal } from "@/lib/types";
import { fetchFundDetail } from "@/lib/api";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(m: number | null | undefined, label = "M"): string {
  if (m == null) return "—";
  const inM = m / 1_000_000;
  if (inM >= 1000) return `$${(inM / 1000).toFixed(1)}B`;
  return `$${inM % 1 === 0 ? inM.toFixed(0) : inM.toFixed(1)}${label}`;
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return "Not disclosed";
  return new Date(d).toLocaleDateString("en-US", {
    month: "long", day: "numeric", year: "numeric",
  });
}

function edgarUrl(cik: string, accessionNo: string): string {
  const clean = accessionNo.replace(/-/g, "");
  return `https://www.sec.gov/Archives/edgar/data/${cik}/${clean}/${accessionNo}.htm`;
}

// ── sub-components ────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 8 ? "bg-emerald-100 text-emerald-800 border-emerald-200"
    : score >= 5 ? "bg-amber-100 text-amber-800 border-amber-200"
    : "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded border text-sm font-bold ${color}`}>
      {score.toFixed(1)} / 10
    </span>
  );
}

function Skeleton() {
  return <span className="inline-block w-24 h-4 bg-slate-100 rounded animate-pulse" />;
}

function RaiseProgress({
  offered, sold, filedAt, firstSale,
}: {
  offered: number | null;
  sold: number | null;
  filedAt: string | null;
  firstSale: string | null;
}) {
  const hasPct = offered != null && offered > 0 && sold != null;
  const pct = hasPct ? Math.min(100, (sold! / offered!) * 100) : null;

  const fmtAmt = (n: number) => {
    const m = n / 1_000_000;
    return m >= 1000 ? `$${(m / 1000).toFixed(1)}B` : `$${m % 1 === 0 ? m.toFixed(0) : m.toFixed(1)}M`;
  };

  const fmtShort = (d: string) =>
    new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });

  return (
    <div className="space-y-3">
      {/* Progress bar */}
      {hasPct && (
        <div>
          <div className="flex justify-between text-xs text-slate-500 mb-1">
            <span className="font-medium text-slate-700">{fmtAmt(sold!)} raised</span>
            <span className="text-slate-400">of {fmtAmt(offered!)} target ({pct!.toFixed(0)}%)</span>
          </div>
          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Date timeline */}
      <div className="flex items-center gap-0 text-xs">
        {filedAt && (
          <>
            <div className="flex flex-col items-center">
              <div className="w-2 h-2 rounded-full bg-slate-400" />
              <span className="text-slate-500 mt-1 whitespace-nowrap">Filed {fmtShort(filedAt)}</span>
            </div>
            <div className="flex-1 h-px bg-slate-200 mx-2 mb-4" />
          </>
        )}
        {firstSale ? (
          <>
            <div className="flex flex-col items-center">
              <div className="w-2.5 h-2.5 rounded-full bg-blue-500" />
              <span className="text-blue-600 font-medium mt-1 whitespace-nowrap">
                First sale {fmtShort(firstSale)}
              </span>
            </div>
            <div className="flex-1 h-px bg-slate-200 mx-2 mb-4" />
          </>
        ) : filedAt ? (
          <>
            <div className="flex flex-col items-center">
              <div className="w-2 h-2 rounded-full bg-slate-300 border border-dashed border-slate-400" />
              <span className="text-slate-400 mt-1 whitespace-nowrap">First sale TBD</span>
            </div>
            <div className="flex-1 h-px bg-slate-200 mx-2 mb-4" />
          </>
        ) : null}
        <div className="flex flex-col items-center">
          <div className="w-2 h-2 rounded-full bg-slate-300" />
          <span className="text-slate-400 mt-1 whitespace-nowrap">Raise ongoing</span>
        </div>
      </div>
    </div>
  );
}

function fmtAum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000_000_000) return `$${(n / 1_000_000_000_000).toFixed(2)}T`;
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

function ClientTypeBar({ ct }: { ct: ClientType }) {
  return (
    <div className="flex items-center justify-between text-xs py-1 border-b border-slate-100 last:border-0">
      <span className="text-slate-600 truncate pr-3 flex-1">{ct.label}</span>
      <span className="text-slate-500 text-right whitespace-nowrap">
        {ct.clients != null && <span className="mr-2">{ct.clients} {ct.clients === 1 ? "client" : "clients"}</span>}
        {ct.aum != null && <span className="font-medium text-slate-800">{fmtAum(ct.aum)}</span>}
      </span>
    </div>
  );
}

function ManagerCard({ mgr }: { mgr: ManagerIntelligence }) {
  const isActive = mgr.scope?.toUpperCase() === "ACTIVE";
  const hasAdv = mgr.aum != null || (mgr.client_types && mgr.client_types.length > 0);

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-3 pb-2 bg-slate-50 border-b border-slate-100">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm font-semibold text-slate-800">{mgr.firm_name}</p>
              {mgr.scope && (
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                  isActive ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
                }`}>
                  {mgr.scope}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              CRD #{mgr.crd}
              {mgr.sec_number && <span className="ml-2">· SEC {mgr.sec_number}</span>}
              {mgr.city && mgr.state && <span className="ml-2">· {mgr.city}, {mgr.state}</span>}
            </p>
          </div>
          <div className="flex gap-1.5 shrink-0">
            <a href={mgr.iapd_url} target="_blank" rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:text-blue-800 border border-blue-200 bg-blue-50 rounded px-2 py-1 whitespace-nowrap">
              IAPD →
            </a>
            <a href={mgr.adv_pdf_url} target="_blank" rel="noopener noreferrer"
              className="text-xs text-slate-500 hover:text-slate-700 border border-slate-200 bg-white rounded px-2 py-1 whitespace-nowrap">
              ADV PDF →
            </a>
          </div>
        </div>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-4 divide-x divide-slate-100 bg-white text-center">
        <div className="px-2 py-2.5">
          <p className="text-xs text-slate-400 mb-0.5">AUM</p>
          <p className="text-sm font-bold text-slate-900">{fmtAum(mgr.aum)}</p>
        </div>
        <div className="px-2 py-2.5">
          <p className="text-xs text-slate-400 mb-0.5">Clients</p>
          <p className="text-sm font-bold text-slate-900">
            {mgr.total_clients != null ? mgr.total_clients.toLocaleString() : "—"}
          </p>
        </div>
        <div className="px-2 py-2.5">
          <p className="text-xs text-slate-400 mb-0.5">Employees</p>
          <p className="text-sm font-bold text-slate-900">
            {mgr.total_employees != null ? mgr.total_employees : "—"}
          </p>
        </div>
        <div className="px-2 py-2.5">
          <p className="text-xs text-slate-400 mb-0.5">Advisors</p>
          <p className="text-sm font-bold text-slate-900">
            {mgr.investment_advisory_employees != null ? mgr.investment_advisory_employees : "—"}
          </p>
        </div>
      </div>

      {/* Client type breakdown */}
      {mgr.client_types && mgr.client_types.length > 0 && (
        <div className="px-4 py-3 border-t border-slate-100 bg-white">
          <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">AUM by Client Type</p>
          {mgr.client_types.map((ct) => (
            <ClientTypeBar key={ct.label} ct={ct} />
          ))}
        </div>
      )}

      {/* Footer note */}
      <div className="px-4 py-2 bg-slate-50 border-t border-slate-100">
        <p className="text-xs text-slate-400">
          {hasAdv
            ? "Source: Form ADV Part 1A · SEC IAPD"
            : `Matched via IAPD search for "${mgr.search_query}" — click IAPD for full detail`
          }
          {!hasAdv && " · Verify this is the correct adviser"}
        </p>
      </div>
    </div>
  );
}

function StatBox({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">{label}</p>
      <div className="text-sm font-medium text-slate-800">{children}</div>
    </div>
  );
}

// ── main modal ────────────────────────────────────────────────────────────────

interface Props {
  signal: Signal;
  onClose: () => void;
}

export default function FundModal({ signal, onClose }: Props) {
  const [detail, setDetail] = useState<FundEnrichment | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [detailError, setDetailError] = useState(false);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Fetch enriched detail — abort on modal close or fund change
  useEffect(() => {
    const controller = new AbortController();
    setLoadingDetail(true);
    setDetailError(false);
    setDetail(null);
    fetchFundDetail(signal.cik, signal.accession_no, controller.signal)
      .then(setDetail)
      .catch((e) => { if (e.name !== "AbortError") setDetailError(true); })
      .finally(() => setLoadingDetail(false));
    return () => controller.abort();
  }, [signal.cik, signal.accession_no]);

  const loading = loadingDetail;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-xl max-h-[92vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="px-6 pt-6 pb-4 border-b border-slate-100">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-semibold text-slate-900 leading-tight">
                {signal.fund_name}
              </h2>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded">
                  {signal.fund_type}
                </span>
                {detail?.is_amendment && (
                  <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded">
                    Amended filing
                  </span>
                )}
                {detail?.sic_description && (
                  <span className="px-2 py-0.5 bg-slate-50 text-slate-500 text-xs rounded border border-slate-200">
                    {detail.sic_description}
                  </span>
                )}
              </div>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors mt-0.5 shrink-0">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="px-6 py-5 space-y-6">

          {/* ── Key stats ── */}
          <div className="grid grid-cols-3 gap-4">
            <StatBox label="Priority Score">
              <ScoreBadge score={signal.priority_score} />
            </StatBox>
            <StatBox label="Offering Size">
              {loading ? <Skeleton /> : fmt(detail?.total_offering_amount)}
            </StatBox>
            <StatBox label="Amount Sold">
              {loading ? <Skeleton /> : fmt(detail?.total_amount_sold)}
            </StatBox>
            <StatBox label="First Sale Date">
              {loading ? <Skeleton /> : fmtDate(detail?.date_of_first_sale)}
            </StatBox>
            <StatBox label="Investors">
              {loading ? <Skeleton /> : (detail?.total_investors ?? "—")}
            </StatBox>
            <StatBox label="Location">
              {loading ? <Skeleton /> : [detail?.city, detail?.state_or_country].filter(Boolean).join(", ") || "—"}
            </StatBox>
          </div>

          {/* ── Raise timeline + progress ── */}
          {(detail?.total_offering_amount || detail?.filed_at) && (
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 mb-3">Raise Progress</p>
              <RaiseProgress
                offered={detail.total_offering_amount ?? null}
                sold={detail.total_amount_sold ?? null}
                filedAt={detail.filed_at ?? null}
                firstSale={detail.date_of_first_sale ?? null}
              />
            </div>
          )}

          {/* ── Contact (website / phone) ── */}
          {(detail?.website || detail?.phone) && (
            <div className="flex gap-6 text-sm">
              {detail.website && (
                <div>
                  <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">Website</p>
                  <a
                    href={detail.website.startsWith("http") ? detail.website : `https://${detail.website}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline truncate"
                  >
                    {detail.website}
                  </a>
                </div>
              )}
              {detail.phone && (
                <div>
                  <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">Phone</p>
                  <span className="text-slate-700">{detail.phone}</span>
                </div>
              )}
            </div>
          )}

          {/* ── Fund managers / GPs ── */}
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">Fund Managers / GPs</p>
            {loading ? (
              <div className="space-y-1.5">
                <Skeleton /><Skeleton />
              </div>
            ) : detail?.related_persons && detail.related_persons.length > 0 ? (
              <ul className="space-y-1.5">
                {detail.related_persons.map((p, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0 mt-1.5" />
                    <span>
                      <span className="font-medium text-slate-800">{p.name}</span>
                      {p.relationships.length > 0 && (
                        <span className="text-slate-400 text-xs ml-2">
                          {p.relationships.join(", ")}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-400 italic">Not disclosed in filing</p>
            )}
          </div>

          {/* ── Manager Intelligence (IAPD) ── */}
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">
              Manager Intelligence
              <span className="ml-1 normal-case text-slate-300">SEC IAPD</span>
            </p>
            {loading ? (
              <div className="space-y-2">
                <Skeleton /><Skeleton /><Skeleton />
              </div>
            ) : detail?.manager_intelligence ? (
              <ManagerCard mgr={detail.manager_intelligence} />
            ) : (
              <p className="text-sm text-slate-400 italic">
                No matching SEC-registered adviser found — may be state-registered or exempt.
              </p>
            )}
          </div>

          {/* ── Exemption type ── */}
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">Regulatory Exemption</p>
            {loading ? (
              <Skeleton />
            ) : detail?.exemptions && detail.exemptions.length > 0 ? (
              <div className="space-y-1">
                {detail.exemptions.map((ex) => (
                  <div key={ex.code} className="flex items-center gap-2">
                    <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 text-xs rounded font-mono">
                      {ex.code}
                    </span>
                    <span className="text-sm text-slate-700">{ex.label}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">—</p>
            )}
          </div>

          {/* ── Distribution platforms ── */}
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">
              Distribution Platforms
              <span className="ml-1 normal-case text-slate-300">({signal.platforms.length})</span>
            </p>
            {signal.platforms.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {signal.platforms.map((p) => {
                  const known = signal.known_platforms.map(x => x.toLowerCase()).includes(p.toLowerCase());
                  return (
                    <span
                      key={p}
                      className={`px-2 py-1 rounded text-xs font-medium border ${
                        known ? "bg-blue-100 text-blue-700 border-blue-200" : "bg-slate-100 text-slate-600 border-slate-200"
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

          {/* ── Solicitation states ── */}
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-400 mb-2">States Being Solicited</p>
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

          {/* ── Roadmap callout ── */}
          <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3">
            <p className="text-xs font-semibold text-blue-700 mb-1">Coming in a later release</p>
            <p className="text-xs text-blue-600 leading-relaxed">
              RIA intelligence: which advisors on iCapital or CAIS have allocated to this fund,
              their AUM, and contact territory — sourced from Form ADV.
            </p>
          </div>

        </div>

        {/* ── Footer ── */}
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
