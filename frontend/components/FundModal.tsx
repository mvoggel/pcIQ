"use client";

import { useEffect, useRef, useState } from "react";
import { ClientType, ConfirmedRia, FundEnrichment, ManagerIntelligence, RiaMatch, Signal } from "@/lib/types";
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

function fmtRiaAum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000_000_000) return `$${(n / 1_000_000_000_000).toFixed(1)}T`;
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}

function RiaRow({ ria }: { ria: RiaMatch }) {
  const iapdUrl = `https://adviserinfo.sec.gov/firm/summary/${ria.crd_number}`;
  const privatePct =
    ria.aum && ria.private_fund_aum
      ? Math.round((ria.private_fund_aum / ria.aum) * 100)
      : null;

  return (
    <div className="flex items-center justify-between py-2.5 border-b border-slate-100 last:border-0 gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-800 truncate">{ria.firm_name}</span>
          {privatePct != null && privatePct > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100 whitespace-nowrap">
              {privatePct}% private funds
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400 mt-0.5">
          {[ria.city, ria.state].filter(Boolean).join(", ")}
          {ria.num_advisors != null && (
            <span className="ml-2">· {ria.num_advisors} advisor{ria.num_advisors !== 1 ? "s" : ""}</span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <div className="text-right">
          <p className="text-xs text-slate-400">AUM</p>
          <p className="text-sm font-semibold text-slate-800">{fmtRiaAum(ria.aum)}</p>
        </div>
        <a
          href={iapdUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:text-blue-800 border border-blue-200 bg-blue-50 rounded px-2 py-1 whitespace-nowrap"
        >
          IAPD →
        </a>
      </div>
    </div>
  );
}

function ConfirmedRiaRow({ ria }: { ria: ConfirmedRia }) {
  const iapdUrl = `https://adviserinfo.sec.gov/firm/summary/${ria.crd_number}`;
  const privatePct =
    ria.aum && ria.private_fund_aum
      ? Math.round((ria.private_fund_aum / ria.aum) * 100)
      : null;

  return (
    <div className="flex items-center justify-between py-2.5 border-b border-emerald-50 last:border-0 gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-800 truncate">{ria.firm_name}</span>
          {ria.matched_platforms.map((p) => (
            <span key={p} className="text-xs px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-100 whitespace-nowrap">
              {p}
            </span>
          ))}
          {ria.source === "csv" && (
            <span title="Confirmed: sourced from platform advisor directory" className="text-xs px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200 whitespace-nowrap font-medium">
              ✓ confirmed
            </span>
          )}
          {ria.source === "edgar_inferred" && (
            <span title="Inferred from EDGAR feeder fund data — not directly confirmed by platform directory" className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200 whitespace-nowrap">
              EDGAR inferred
            </span>
          )}
          {privatePct != null && privatePct > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100 whitespace-nowrap">
              {privatePct}% private funds
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400 mt-0.5">
          {[ria.city, ria.state].filter(Boolean).join(", ")}
          {ria.num_advisors != null && (
            <span className="ml-2">· {ria.num_advisors} advisor{ria.num_advisors !== 1 ? "s" : ""}</span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <div className="text-right">
          <p className="text-xs text-slate-400">AUM</p>
          <p className="text-sm font-semibold text-slate-800">{fmtRiaAum(ria.aum)}</p>
        </div>
        <a
          href={iapdUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:text-blue-800 border border-blue-200 bg-blue-50 rounded px-2 py-1 whitespace-nowrap"
        >
          IAPD →
        </a>
      </div>
    </div>
  );
}

function InfoTooltip({ text, color = "slate" }: { text: string; color?: "slate" | "emerald" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const badge = color === "emerald"
    ? "bg-emerald-200 text-emerald-800"
    : "bg-slate-200 text-slate-600";

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex items-center ml-1">
      <span
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className={`w-3.5 h-3.5 rounded-full ${badge} text-[9px] font-bold inline-flex items-center justify-center leading-none select-none cursor-pointer`}
      >
        i
      </span>
      <span className={`absolute top-full left-1/2 -translate-x-1/2 mt-2 w-64 bg-slate-800 text-white text-xs rounded-lg px-3 py-2 leading-relaxed shadow-lg transition-opacity pointer-events-none z-50 ${open ? "opacity-100" : "opacity-0"}`}>
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 border-4 border-transparent border-b-slate-800" />
        {text}
      </span>
    </span>
  );
}

function ConfirmedAllocators({ rias, loading }: { rias: ConfirmedRia[] | undefined; loading: boolean }) {
  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton /><Skeleton /><Skeleton />
      </div>
    );
  }

  // Don't render the section at all when empty — falls back to Likely Allocators below
  if (!rias || rias.length === 0) return null;

  const uniquePlatforms = [...new Set(rias.flatMap((r) => r.matched_platforms))];
  const csvRows = rias.filter((r) => r.source === "csv" || r.source === "scrape");
  const inferredRows = rias.filter((r) => r.source === "edgar_inferred");
  const hasConfirmed = csvRows.length > 0;

  // Header copy and color depend on whether we have any hard-confirmed rows
  const headerLabel = hasConfirmed
    ? "Platform Allocators"
    : "Platform Inferred Allocators";
  const subLabel = hasConfirmed
    ? `${csvRows.length} confirmed · ${inferredRows.length} inferred · ${uniquePlatforms.join(", ")}`
    : `${rias.length} RIA${rias.length !== 1 ? "s" : ""} · EDGAR inferred · ${uniquePlatforms.join(", ")}`;
  const tooltipText = hasConfirmed
    ? `Three-signal match: (1) this fund distributes via ${uniquePlatforms.join("/")} (Form D salesCompensationList), (2) each RIA is a registered platform partner (platform advisor directory — CSV confirmed), and (3) each RIA is in this fund's solicitation territory.`
    : `EDGAR inference: (1) this fund lists ${uniquePlatforms.join("/")} as a paid distributor in its Form D filing, (2) each RIA has documented private fund exposure in their Form ADV, and (3) each RIA is in this fund's solicitation territory. Platform membership is inferred — not yet confirmed from a platform advisor directory. Import a CSV export from iCapital/CAIS to upgrade rows to confirmed.`;
  const footerText = hasConfirmed
    ? `${csvRows.length} CSV-confirmed platform partner${csvRows.length !== 1 ? "s" : ""} · ${inferredRows.length > 0 ? `${inferredRows.length} EDGAR inferred` : ""} · Source: platform directory + Form ADV`
    : `EDGAR inferred — platform membership derived from Form D filings and ADV private fund data, not a direct platform directory. These are high-probability prospects, not confirmed allocations.`;

  const borderColor = hasConfirmed ? "border-emerald-200" : "border-blue-200";
  const headerBg = hasConfirmed ? "bg-emerald-50 border-emerald-100" : "bg-blue-50 border-blue-100";
  const headerText = hasConfirmed ? "text-emerald-800" : "text-blue-800";
  const subText = hasConfirmed ? "text-emerald-600" : "text-blue-600";
  const footerBg = hasConfirmed ? "bg-emerald-50 border-emerald-100" : "bg-blue-50 border-blue-100";
  const footerText2 = hasConfirmed ? "text-emerald-700" : "text-blue-700";

  return (
    <div className={`border ${borderColor} rounded-lg overflow-hidden`}>
      {/* Header banner */}
      <div className={`px-4 py-2 ${headerBg} border-b flex items-center gap-2`}>
        <div>
          <div className="flex items-center gap-2">
            <span className={`text-xs font-semibold ${headerText} uppercase tracking-wider`}>
              {headerLabel}
            </span>
            <span className={`text-xs ${subText}`}>· {subLabel}</span>
            <InfoTooltip color={hasConfirmed ? "emerald" : "slate"} text={tooltipText} />
          </div>
          <p className={`text-xs ${subText} mt-0.5`}>
            {hasConfirmed ? "Platform partner · In territory · Highest confidence" : "EDGAR inferred · In territory · Import CSV to confirm"}
          </p>
        </div>
      </div>

      <div className="divide-y divide-slate-50 px-4 bg-white">
        {rias.map((ria) => (
          <ConfirmedRiaRow key={ria.crd_number} ria={ria} />
        ))}
      </div>

      <div className={`px-4 py-2 ${footerBg} border-t`}>
        <p className={`text-xs ${footerText2}`}>{footerText}</p>
      </div>
    </div>
  );
}

function LikelyAllocators({ rias, loading }: { rias: RiaMatch[] | undefined; loading: boolean }) {
  const [filterLarge, setFilterLarge] = useState(false);

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton /><Skeleton /><Skeleton />
      </div>
    );
  }

  if (!rias || rias.length === 0) {
    return (
      <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
        <p className="text-xs text-slate-500 leading-relaxed">
          No RIA data available for this territory yet.{" "}
          <span className="font-medium">Run ADV ingestion</span> (
          <code className="text-slate-600 bg-slate-100 rounded px-1">make ingest-adv-state STATE=NY</code>
          ) to populate RIA profiles.
        </p>
      </div>
    );
  }

  const filtered = filterLarge ? rias.filter((r) => r.aum != null && r.aum >= 100_000_000) : rias;
  const largeCount = rias.filter((r) => r.aum != null && r.aum >= 100_000_000).length;
  const totalAum = rias.reduce((sum, r) => sum + (r.aum ?? 0), 0);
  const totalAumStr = totalAum >= 1e12
    ? `$${(totalAum / 1e12).toFixed(1)}T`
    : totalAum >= 1e9
    ? `$${(totalAum / 1e9).toFixed(0)}B`
    : `$${(totalAum / 1e6).toFixed(0)}M`;

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      {/* Stat + filter bar */}
      <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 text-xs text-slate-500 flex-wrap">
          <span className="font-semibold text-slate-800 text-sm">{rias.length} RIAs</span>
          <span className="text-slate-300">·</span>
          <span>{totalAumStr} total AUM in territory</span>
          <span className="text-slate-300">·</span>
          <span>{largeCount} firms over $100M AUM</span>
        </div>
        <button
          onClick={() => setFilterLarge((f) => !f)}
          className={`text-xs px-2.5 py-1 rounded border font-medium transition-colors whitespace-nowrap ${
            filterLarge
              ? "bg-blue-600 text-white border-blue-600"
              : "text-slate-500 border-slate-300 hover:border-blue-400 hover:text-blue-600"
          }`}
        >
          $100M+ AUM
        </button>
      </div>

      <div className="divide-y divide-slate-100 px-4">
        {filtered.length === 0 ? (
          <p className="text-xs text-slate-400 py-4 text-center">No RIAs over $100M AUM in this territory.</p>
        ) : (
          filtered.map((ria) => (
            <RiaRow key={ria.crd_number} ria={ria} />
          ))
        )}
      </div>
      <div className="px-4 py-2 bg-slate-50 border-t border-slate-100">
        <p className="text-xs text-slate-400">
          Profile match only — RIAs in territory{filterLarge ? " · $100M+ AUM filter active" : " · $100M+ AUM"} · Not confirmed allocations · Source: Form ADV
        </p>
      </div>
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

  // Lock body scroll while modal is open.
  // This prevents iOS Safari from drifting the viewport horizontally
  // when the user scrolls inside the modal.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Fetch enriched detail — abort when modal closes or fund switches
  useEffect(() => {
    const controller = new AbortController();
    setLoadingDetail(true);
    setDetailError(false);
    fetchFundDetail(signal.cik, signal.accession_no, controller.signal)
      .then((d) => { if (!controller.signal.aborted) setDetail(d); })
      .catch((e) => { if (e.name !== "AbortError") setDetailError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoadingDetail(false); });
    return () => controller.abort();
  }, [signal.cik, signal.accession_no]);

  const loading = loadingDetail;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-xl max-h-[92vh] overflow-y-auto overscroll-y-contain"
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

          {/* ── Confirmed Advisors Buying This Strategy ── */}
          {(loading || (detail?.confirmed_rias && detail.confirmed_rias.length > 0)) && (
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-400 mb-1">
                Confirmed Advisors Buying This Strategy
              </p>
              <p className="text-xs text-slate-400 mb-2 normal-case">
                Platform partner · In territory · Highest confidence
              </p>
              <ConfirmedAllocators rias={detail?.confirmed_rias} loading={loading} />
            </div>
          )}

          {/* ── Likely Advisors Buying This Strategy ── */}
          <div>
            <div className="flex items-center gap-1 mb-1">
              <p className="text-xs uppercase tracking-wider text-slate-400">
                Likely Advisors Buying This Strategy
              </p>
              <InfoTooltip text="RIAs in this fund's solicitation territory with $100M+ AUM, sourced from Form ADV filings. These firms have the scale and geography to allocate to this strategy — but platform relationship is not yet confirmed. Use as a prospecting list alongside the Confirmed section above." />
            </div>
            <p className="text-xs text-slate-400 mb-2 normal-case">RIAs in territory · $100M+ AUM · Form ADV</p>
            <LikelyAllocators rias={detail?.likely_rias} loading={loading} />
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
