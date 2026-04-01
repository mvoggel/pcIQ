import { CionFund, FundEnrichment, SignalsResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

export async function fetchSignals(
  territory: string,
  days: number = 7
): Promise<SignalsResponse> {
  const url = `${API_BASE}/api/signals?territory=${encodeURIComponent(territory)}&days=${days}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}
