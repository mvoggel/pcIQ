import { SignalsResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchSignals(
  territory: string,
  days: number = 7
): Promise<SignalsResponse> {
  const url = `${API_BASE}/api/signals?territory=${encodeURIComponent(territory)}&days=${days}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}
