"""
Signal pipeline — fetch, score, and report territory intelligence.

Usage:
    python -m app.signals.run_signals                        # last 7 days, all territories
    python -m app.signals.run_signals --days 14 --state NY   # 14-day window, NY territory
    python -m app.signals.run_signals --days 30              # monthly view

CION territory example (customize to match their actual wholesaler map):
    python -m app.signals.run_signals --territory "Northeast" --states NY,NJ,CT,MA,PA
"""

import argparse
import asyncio
from datetime import date, timedelta

from app.ingestion.edgar_client import fetch_form_d_xml, search_form_d_filings
from app.ingestion.form_d_parser import parse_form_d
from app.signals.scoring import generate_territory_report, print_territory_report

# Default territory definitions — seed for CION demo
# Customize these to match CION's actual wholesaler territory map
DEFAULT_TERRITORIES = {
    "Northeast":  ["NY", "NJ", "CT", "MA", "PA", "RI", "NH", "VT", "ME"],
    "Southeast":  ["FL", "GA", "NC", "SC", "VA", "MD", "DE", "TN", "AL"],
    "Midwest":    ["IL", "OH", "MI", "IN", "WI", "MN", "MO", "IA", "KS"],
    "Southwest":  ["TX", "AZ", "NM", "OK", "CO", "NV", "UT"],
    "West Coast": ["CA", "WA", "OR"],
}


async def run(
    start_date: date,
    end_date: date,
    territory_name: str | None = None,
    territory_states: list[str] | None = None,
) -> None:
    print(f"\npcIQ signal pipeline | {start_date} → {end_date}")
    print("Fetching Form D filings from EDGAR...\n")

    hits = await search_form_d_filings(start_date, end_date, max_results=100)

    filings = []
    errors = 0
    for meta in hits:
        cik = meta.get("cik", "")
        file_id = meta.get("file_id", "")
        acc_raw = file_id.split("/")[-1].split(":")[0]
        acc = f"{acc_raw[:10]}-{acc_raw[10:12]}-{acc_raw[12:]}" if len(acc_raw) == 18 else acc_raw
        if not cik or not acc:
            continue
        try:
            xml = await fetch_form_d_xml(cik, acc)
            filing = parse_form_d(xml, cik, acc)
            if filing.is_private_credit_candidate:
                filings.append(filing)
        except Exception:
            errors += 1

    print(f"Parsed {len(filings)} private credit candidates from {len(hits)} filings. "
          f"({errors} errors)\n")

    # Determine which territories to report
    if territory_name and territory_states:
        territories = {territory_name: territory_states}
    elif territory_name:
        territories = {territory_name: DEFAULT_TERRITORIES.get(territory_name, [])}
    else:
        territories = DEFAULT_TERRITORIES

    for name, states in territories.items():
        if not states:
            print(f"  Skipping '{name}' — no states defined.")
            continue
        report = generate_territory_report(filings, name, states)
        print_territory_report(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="pcIQ — territory signal report")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days")
    parser.add_argument("--territory", help="Territory name (e.g. 'Northeast')")
    parser.add_argument("--states", help="Comma-separated state codes (e.g. NY,NJ,CT)")
    args = parser.parse_args()

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    states = [s.strip().upper() for s in args.states.split(",")] if args.states else None

    asyncio.run(run(start_date, end_date, territory_name=args.territory, territory_states=states))


if __name__ == "__main__":
    main()
