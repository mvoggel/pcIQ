export interface Signal {
  fund_name: string;
  fund_type: string;
  offering_size_m: number | null;
  date_of_first_sale: string | null;
  fund_state: string;
  platforms: string[];
  known_platforms: string[];
  solicitation_states: string[];
  is_in_territory: boolean;
  priority_score: number;
  cik: string;
  accession_no: string;
}

export interface SignalsResponse {
  territory: string;
  states: string[];
  days: number;
  total_filings_scanned: number;
  platform_counts: Record<string, number>;
  signals: Signal[];
}

export interface CionFund {
  ticker: string;
  name: string;
  strategy: string;
  focus: string;
  exchange: string;
  currency: string;
  nav: number | null;
  nav_prev_close: number | null;
  nav_change: number | null;
  nav_change_pct: number | null;
  fifty_two_week_change_pct: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  fifty_day_avg: number | null;
  two_hundred_day_avg: number | null;
  sparkline: number[];
  error?: string;
}

export interface ClientType {
  label: string;
  clients: number | null;
  aum: number | null;
}

export interface ManagerIntelligence {
  crd: string;
  firm_name: string;
  sec_number: string;
  scope: string;           // "ACTIVE" | "INACTIVE"
  city: string;
  state: string;
  phone: string;
  branches: number | null;
  relying_advisers: number;
  iapd_url: string;
  adv_pdf_url: string;
  search_query: string;
  // ADV PDF data (populated when available)
  aum: number | null;
  discretionary_aum: number | null;
  total_clients: number | null;
  total_employees: number | null;
  investment_advisory_employees: number | null;
  client_types: ClientType[];
}

export interface RiaMatch {
  firm_name: string;
  crd_number: string;
  state: string;
  city: string;
  aum: number | null;
  private_fund_aum: number | null;
  website: string | null;
  num_advisors: number | null;
  total_accounts: number | null;
}

export interface ConfirmedRia {
  firm_name: string;
  crd_number: string;
  state: string;
  city: string;
  aum: number | null;
  private_fund_aum: number | null;
  num_advisors: number | null;
  matched_platforms: string[];   // which platform(s) created the match
  source: string;                // "csv" | "scrape" | "edgar_inferred"
}

export interface AdvisorProfile {
  crd_number: string;
  firm_name: string;
  city: string;
  state: string;
  aum: number | null;
  aum_fmt: string | null;
  aum_tier: "mega" | "large" | "mid" | "small" | "unknown";
  private_fund_aum: number | null;
  private_fund_aum_fmt: string | null;
  num_advisors: number | null;
  platforms: string[];
  platform_sources: Record<string, string>;  // {platform: "csv"|"adv_brochure"|"edgar_inferred"}
  platform_count: number;
  allocation_count_90d: number;
  activity_score: number;
  thirteenf_bdc_value_usd: number | null;   // total $ held in BDC positions per latest 13F
  thirteenf_period: string | null;           // e.g. "2024-12-31"
}

export interface AdvisorsResponse {
  territory: string;
  states: string[];
  total: number;
  advisors: AdvisorProfile[];
}

export interface ThirteenFHolder {
  filer_cik: string;
  filer_name: string;
  ria_crd: string | null;
  period_of_report: string | null;
  total_bdc_value_usd: number;
  tickers: string[];
}

export interface ThirteenFHoldersResponse {
  total: number;
  holders: ThirteenFHolder[];
}

export interface FundEnrichment {
  cik: string;
  accession_no: string;
  entity_name: string;
  investment_fund_type: string;
  filed_at: string | null;
  date_of_first_sale: string | null;
  is_amendment: boolean;
  city: string | null;
  state_or_country: string | null;
  total_offering_amount: number | null;
  total_amount_sold: number | null;
  total_investors: number | null;
  has_non_accredited: boolean;
  exemptions: { code: string; label: string }[];
  related_persons: { name: string; relationships: string[] }[];
  website: string;
  phone: string;
  sic_description: string;
  manager_intelligence: ManagerIntelligence | null;
  confirmed_rias: ConfirmedRia[];
  likely_rias: RiaMatch[];
}
