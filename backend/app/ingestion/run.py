"""
Entry point for manual ingestion runs.

Usage:
    python -m app.ingestion.run
    python -m app.ingestion.run --start 2026-03-01 --end 2026-03-30

Fetches Form D filings from EDGAR for the given date range,
parses each one, and prints a summary. (DB writes come in week 3-4.)
"""

import argparse
import asyncio
from datetime import date, timedelta

from app.ingestion.edgar_client import fetch_form_d_xml, search_form_d_filings
from app.ingestion.form_d_parser import parse_form_d


async def run(start_date: date, end_date: date) -> None:
    print(f"\nFetching Form D filings: {start_date} → {end_date}\n")

    filings_meta = await search_form_d_filings(start_date, end_date, max_results=20)
    print(f"Found {len(filings_meta)} filings.\n")

    pooled_funds = []

    for meta in filings_meta:
        cik = meta.get("cik", "")
        acc = meta.get("file_id", "")  # EDGAR search returns _id as accession path
        entity = meta.get("entity_name", "unknown")

        # _id from EFTS looks like "edgar/data/1234567/0001234567-26-000001.txt"
        # Extract accession number from it
        if "/" in acc:
            acc_part = acc.split("/")[-1].replace(".txt", "")
        else:
            acc_part = acc

        if not cik or not acc_part:
            continue

        try:
            xml = await fetch_form_d_xml(cik, acc_part)
            filing = parse_form_d(xml, cik, acc_part)
        except Exception as exc:
            print(f"  ✗  {entity}: {exc}")
            continue

        if filing.is_pooled_investment_fund:
            pooled_funds.append(filing)
            size = f"${filing.offering_size_m}M" if filing.offering_size_m else "size unknown"
            print(
                f"  ✓  {filing.entity_name:50s} | {filing.investment_fund_type:30s} | "
                f"{size:15s} | {filing.address.display}"
            )

    print(f"\n{len(pooled_funds)} pooled investment funds out of {len(filings_meta)} filings.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Form D filings from EDGAR")
    parser.add_argument("--start", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    asyncio.run(run(args.start, args.end))


if __name__ == "__main__":
    main()
