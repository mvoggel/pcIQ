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
