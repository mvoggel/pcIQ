"""
ADV ingestion — fetch RIA firm data from IAPD and write to Supabase.

Usage:
    python -m app.ingestion.run_adv --state NY          # all SEC RIAs in NY
    python -m app.ingestion.run_adv --crd 109018        # single firm by CRD
    python -m app.ingestion.run_adv --state NY --dry-run

CRD numbers for key firms relevant to private credit distribution:
  CION Investments:   check IAPD manually (they're a BDC, not an RIA)
  iCapital:           173333
  CAIS:               check IAPD
  Fidelity:           7784
  Schwab:             5765
  Merrill Lynch:      7691
"""

import argparse
import asyncio

from app.db.writer import upsert_entity, upsert_ria
from app.ingestion.adv_client import (
    fetch_edgar_submissions,
    search_adv_filers,
)
from app.ingestion.entity_resolver import EntityResolver
from app.models.ria import RIA


async def _fetch_ria(crd: str, cik: str = "") -> "RIA | None":
    """Try IAPD first, fall back to EDGAR submissions."""
    from app.models.ria import RIA

    # Attempt 1: IAPD (rich data — AUM, accounts, state)
    data = await fetch_ria_by_crd(crd)
    if data:
        ria = parse_iapd_firm(data, crd_number=crd)
        if ria:
            return ria

    # Attempt 2: EDGAR submissions (name, CIK, state, filing dates)
    if cik:
        submissions = await fetch_edgar_submissions(cik)
        if submissions:
            return parse_edgar_submissions(submissions, crd_number=crd)

    return None


async def run_by_crd(crd: str, dry_run: bool = False) -> None:
    """Fetch and upsert a single RIA by CRD number."""
    print(f"\nFetching RIA CRD {crd}...")
    ria = await _fetch_ria(crd)
    if not ria:
        print(f"  ✗  CRD {crd} not found via IAPD or EDGAR.")
        return

    aum_str = f"${ria.aum_m}M AUM" if ria.aum_m else "AUM unknown"
    print(f"  ✓  {ria.firm_name} | {ria.city}, {ria.state} | {aum_str}")

    if dry_run:
        print("  Dry run — skipping DB write.")
        return

    resolver = EntityResolver()
    entity_rec = resolver.resolve(ria.firm_name, cik=ria.cik)
    entity_id = upsert_entity(entity_rec["canonical_name"], cik=entity_rec["cik"], entity_type="ria")
    ria_id = upsert_ria(ria, entity_id=entity_id)
    print(f"  Written to DB: ria.id={ria_id}")


async def run_by_state(state: str, max_results: int, dry_run: bool = False) -> None:
    """
    Fetch active RIAs from IAPD for a given state and write to Supabase.

    IAPD search returns CRDs directly — no secondary name→CRD lookup needed.
    For each hit we call fetch_ria_by_crd to get full data including AUM.
    """
    print(f"\npcIQ ADV ingestion | state={state} | max={max_results}\n")

    hits = await search_adv_filers(state=state, max_results=max_results)
    print(f"Found {len(hits)} active IA registrants in {state}.\n")

    if not hits:
        print("  No results — check that IAPD is reachable and the state code is valid.")
        return

    resolver = EntityResolver()
    written = 0
    errors = 0
    skipped = 0

    for hit in hits:
        crd = hit.get("crd", "")
        name = hit.get("entity_name", "").strip()
        if not crd or not name:
            skipped += 1
            continue

        # Build RIA from IAPD search data — CRD, name, state, city come from search.
        # AUM is not available in search results (detail endpoint requires data-center IP);
        # it will be backfilled when the fund modal fetches the ADV PDF from Railway.
        ria = RIA(
            crd_number=crd,
            firm_name=name,
            state=hit.get("state", "").upper(),
            city=hit.get("city", ""),
            aum=None,
            private_fund_aum=None,
        )

        print(f"  ✓  {ria.firm_name:50s} | {ria.state:2s} | AUM pending")

        if not dry_run:
            try:
                entity_rec = resolver.resolve(ria.firm_name, cik=ria.cik)
                entity_id = upsert_entity(
                    entity_rec["canonical_name"], cik=entity_rec["cik"], entity_type="ria"
                )
                upsert_ria(ria, entity_id=entity_id)
                written += 1
            except Exception as exc:
                print(f"    ✗  DB write failed: {exc}")
                errors += 1

    print(f"\n{'─'*70}")
    print(f"  Found           : {len(hits)}")
    print(f"  Skipped (no data): {skipped}")
    if not dry_run:
        print(f"  Written to DB  : {written}")
        print(f"  Errors         : {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="pcIQ — Form ADV / RIA ingestion")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--crd", help="Fetch single RIA by CRD number")
    group.add_argument("--state", help="Fetch all SEC RIAs in a state (2-letter code)")
    parser.add_argument("--max", type=int, default=50, help="Max results for --state mode")
    parser.add_argument("--dry-run", action="store_true", help="Parse without writing to DB")
    args = parser.parse_args()

    if args.crd:
        asyncio.run(run_by_crd(args.crd, dry_run=args.dry_run))
    else:
        asyncio.run(run_by_state(args.state, max_results=args.max, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
