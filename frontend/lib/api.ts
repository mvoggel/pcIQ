import { AdvisorsResponse, CionFund, FundEnrichment, NPortMetrics, SignalsResponse, ThirteenFHoldersResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchAdvisors(
  territory: string = "",
  limit: number = 50
): Promise<AdvisorsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (territory) params.set("territory", territory);
  const res = await fetch(`${API_BASE}/api/advisors?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchCompetitorFunds(): Promise<CionFund[]> {
  const res = await fetch(`${API_BASE}/api/cion/competitors`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchCionFunds(): Promise<CionFund[]> {
  const res = await fetch(`${API_BASE}/api/cion/funds`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchFundDetail(
  cik: string,
  accessionNo: string,
  signal?: AbortSignal
): Promise<FundEnrichment> {
  const url = `${API_BASE}/api/fund/${cik}/${encodeURIComponent(accessionNo)}`;
  const res = await fetch(url, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchThirteenFHolders(
  limit: number = 50,
  minValueUsd: number = 1_000_000
): Promise<ThirteenFHoldersResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    min_value_usd: String(minValueUsd),
  });
  const res = await fetch(`${API_BASE}/api/thirteenf/holders?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchFundMovements(cik: string, accessionNo: string): Promise<{
  movements: { firm_name: string; crd_number: string; city: string | null; state: string | null; aum_fmt: string | null; signal_date: string }[];
  total: number;
}> {
  const res = await fetch(`${API_BASE}/api/fund/${cik}/${encodeURIComponent(accessionNo)}/movements`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchAdvisorFunds(crd: string): Promise<import("./types").AdvisorFundsResponse> {
  const res = await fetch(`${API_BASE}/api/advisors/${encodeURIComponent(crd)}/funds`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchNPortMetrics(): Promise<Record<string, NPortMetrics>> {
  const res = await fetch(`${API_BASE}/api/cion/nport-metrics`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchPlatformStats(): Promise<{
  rias_tracked: number;
  aum_represented: string;
  states_covered: number;
  feeder_funds: number;
}> {
  const res = await fetch(`${API_BASE}/api/cion/platform-stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchSignals(
  territory: string,
  days: number = 7
): Promise<SignalsResponse> {
  const url = `${API_BASE}/api/signals?territory=${encodeURIComponent(territory)}&days=${days}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}
