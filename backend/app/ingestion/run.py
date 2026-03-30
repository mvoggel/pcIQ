"""
Entry point for manual and scheduled ingestion runs.

Usage:
    python -m app.ingestion.run                          # yesterday → today
    python -m app.ingestion.run --start 2026-03-01       # specific range
    python -m app.ingestion.run --dry-run                # parse only, no DB writes

Pipeline per run:
    1. Search EDGAR for Form D filings in date range
    2. Fetch + parse each filing's XML
    3. Filter to private credit candidates (exclude VC, real estate)
    4. Resolve entities (normalize names, dedup)
    5. Write to Supabase (entities + form_d_filings tables)
"""

import argparse
import asyncio
from datetime import date, timedelta

from app.db.writer import upsert_entity, upsert_filing
from app.ingestion.edgar_client import fetch_form_d_xml, search_form_d_filings
from app.ingestion.entity_resolver import EntityResolver
from app.ingestion.form_d_parser import parse_form_d


async def run(start_date: date, end_date: date, dry_run: bool = False) -> None:
    mode = "DRY RUN — no DB writes" if dry_run else "writing to Supabase"
    print(f"\npcIQ ingestion | {start_date} → {end_date} | {mode}\n")

    filings_meta = await search_form_d_filings(start_date, end_date, max_results=100)
    print(f"Found {len(filings_meta)} Form D filings from EDGAR.\n")

    resolver = EntityResolver()
    private_credit: list = []
    errors = 0

    for meta in filings_meta:
        cik = meta.get("cik", "")
        file_id = meta.get("file_id", "")
        entity = meta.get("entity_name", "unknown")

        # Parse accession number from EFTS _id
        # e.g. "edgar/data/1912207/000191220726000001:primary_doc.xml" → "0001912207-26-000001"
        acc_raw = file_id.split("/")[-1].split(":")[0]
        if len(acc_raw) == 18:
            acc_part = f"{acc_raw[:10]}-{acc_raw[10:12]}-{acc_raw[12:]}"
        else:
            acc_part = acc_raw

        if not cik or not acc_part:
            continue

        try:
            xml = await fetch_form_d_xml(cik, acc_part)
            filing = parse_form_d(xml, cik, acc_part)
            # Attach filed_at from search metadata (not always in XML)
            if not filing.filed_at and meta.get("filed_at"):
                from datetime import date as _date
                try:
                    filing.filed_at = _date.fromisoformat(meta["filed_at"])
                except ValueError:
                    pass
        except Exception as exc:
            print(f"  ✗  {entity}: {exc}")
            errors += 1
            continue

        if not filing.is_private_credit_candidate:
            continue

        private_credit.append(filing)
        entity_record = resolver.resolve(filing.entity_name, cik=filing.cik)

        size = f"${filing.offering_size_m}M" if filing.offering_size_m else "size unknown"
        new_flag = " [new entity]" if entity_record["is_new"] else ""
        print(
            f"  ✓  {filing.entity_name:52s} | {filing.investment_fund_type:22s} | "
            f"{size:14s} | {filing.address.display}{new_flag}"
        )

    print(f"\n{'─'*90}")
    print(f"  Private credit candidates : {len(private_credit)}")
    print(f"  Unique entities resolved  : {len(resolver.all_entities)}")
    print(f"  Parse errors              : {errors}")
    print(f"  Total filings scanned     : {len(filings_meta)}")

    if dry_run or not private_credit:
        if dry_run:
            print("\n  Dry run — skipping DB writes.")
        return

    # --- Write to Supabase ---
    print("\nWriting to Supabase...")
    written = 0
    for filing in private_credit:
        try:
            entity_rec = resolver.resolve(filing.entity_name, cik=filing.cik)
            entity_id = upsert_entity(
                canonical_name=entity_rec["canonical_name"],
                cik=entity_rec["cik"],
                entity_type="fund",
            )
            upsert_filing(filing, entity_id=entity_id)
            written += 1
        except Exception as exc:
            print(f"  ✗  DB write failed for {filing.entity_name}: {exc}")

    print(f"  {written}/{len(private_credit)} filings written to DB.")


def main() -> None:
    parser = argparse.ArgumentParser(description="pcIQ — EDGAR Form D ingestion")
    parser.add_argument(
        "--start", type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", type=date.fromisoformat,
        default=date.today(),
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and filter without writing to DB",
    )
    args = parser.parse_args()
    asyncio.run(run(args.start, args.end, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
