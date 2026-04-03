"""
Local bulk RIA enrichment — runs via ADV PDF from any IP (no Railway needed).

The IAPD detail endpoint (/firms/registration/summary/{crd}) blocks local IPs with 403.
The ADV PDF URL (reports.adviserinfo.sec.gov/reports/ADV/{crd}/PDF/{crd}.pdf) is fully
public with no IP restriction — same data source the Railway enrichment falls back to.

This script bypasses Railway entirely: fetches null-AUM RIAs from Supabase, enriches
them concurrently via ADV PDF, writes results back. Run it once to build coverage fast,
then let the weekly GitHub Action handle new RIAs going forward.

Expect ~60–90 min for 2,000 RIAs (some fail fast if no SEC ADV on file — state-registered
or exempt firms return 404 immediately and don't block the queue).

Usage:
    make enrich-bulk              # all null-AUM RIAs
    make enrich-bulk MAX=50       # small test run
    make enrich-bulk MAX=500      # partial run, safe to re-run (skips already-enriched)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone

from app.db.client import get_db
from app.ingestion.adv_pdf_parser import fetch_adv_data

# ── config ────────────────────────────────────────────────────────────────────

_CONCURRENCY = 6    # parallel PDF fetches — respectful to SEC servers
_TIMEOUT     = 25   # seconds per PDF (large ADVs can be slow)
_DELAY       = 0.3  # seconds between task starts to stagger requests


# ── core ──────────────────────────────────────────────────────────────────────

async def _enrich_one(crd: str, sem: asyncio.Semaphore) -> tuple[str, bool, str]:
    """
    Fetch ADV PDF for a single CRD and update rias table.
    Returns (crd, success, reason).
    """
    db = get_db()
    async with sem:
        try:
            adv = await fetch_adv_data(crd, timeout=float(_TIMEOUT))
        except Exception as exc:
            _bump_updated_at(db, crd)
            return crd, False, f"fetch error: {type(exc).__name__}"

    if adv is None:
        _bump_updated_at(db, crd)
        return crd, False, "no ADV found (state-registered or exempt)"

    if adv.total_aum is None:
        _bump_updated_at(db, crd)
        return crd, False, "ADV parsed but no AUM in Item 5.F"

    try:
        db.table("rias").update({
            "aum":          adv.total_aum,
            "num_advisors": adv.investment_advisory_employees,
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        }).eq("crd_number", crd).execute()
    except Exception as exc:
        return crd, False, f"db write error: {exc}"

    return crd, True, f"${adv.total_aum / 1e9:.2f}B" if adv.total_aum >= 1e9 else f"${adv.total_aum / 1e6:.0f}M"


def _bump_updated_at(db, crd: str) -> None:
    """Move this RIA to the back of the enrichment queue."""
    try:
        db.table("rias").update({
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("crd_number", crd).execute()
    except Exception:
        pass


# ── main ─────────────────────────────────────────────────────────────────────

async def run(max_rias: int = 0, verbose: bool = False) -> None:
    db = get_db()

    # Pull all null-AUM active RIAs, oldest-touched first so re-runs don't
    # duplicate work done in a previous session.
    query = (
        db.table("rias")
        .select("crd_number, firm_name")
        .is_("aum", "null")
        .eq("is_active", True)
        .order("updated_at", desc=False)
    )
    if max_rias:
        query = query.limit(max_rias)

    rows = query.execute().data or []
    if not rows:
        print("✓ No null-AUM RIAs found — already fully enriched!")
        return

    total = len(rows)
    est_min_lo = total * 3 // (_CONCURRENCY * 60)
    est_min_hi = total * 8 // (_CONCURRENCY * 60)
    print(f"\npcIQ bulk RIA enrichment")
    print(f"  {total:,} RIAs to enrich  |  concurrency={_CONCURRENCY}  |  source=ADV PDF")
    print(f"  Estimated time: {est_min_lo}–{est_min_hi} minutes")
    print(f"  Safe to interrupt (Ctrl-C) and re-run — already-enriched RIAs are skipped\n")

    sem = asyncio.Semaphore(_CONCURRENCY)
    crds = [(r["crd_number"], r.get("firm_name", "")) for r in rows]

    enriched = 0
    failed   = 0
    start    = time.monotonic()

    async def _staggered(crd: str, firm: str, i: int):
        await asyncio.sleep(i * _DELAY)
        return await _enrich_one(crd, sem)

    tasks = [
        asyncio.create_task(_staggered(crd, firm, i))
        for i, (crd, firm) in enumerate(crds)
    ]

    for fut in asyncio.as_completed(tasks):
        crd, ok, reason = await fut
        if ok:
            enriched += 1
        else:
            failed += 1
            if verbose:
                print(f"\n  ✗  {crd}: {reason}")

        done    = enriched + failed
        elapsed = time.monotonic() - start
        rate    = done / elapsed if elapsed > 0 else 0
        eta_s   = (total - done) / rate if rate > 0 else 0

        bar_filled = int(30 * done / total)
        bar = "█" * bar_filled + "░" * (30 - bar_filled)
        pct = done / total * 100
        print(
            f"  [{bar}] {pct:4.0f}%  "
            f"{enriched:,} enriched  {failed:,} skipped  "
            f"eta {eta_s/60:.0f}m",
            end="\r", flush=True
        )

    elapsed = time.monotonic() - start
    skip_pct = failed / total * 100 if total else 0
    print(f"\n\n{'─'*60}")
    print(f"  Done in {elapsed/60:.1f} min")
    print(f"  Enriched:  {enriched:,} of {total:,} RIAs ({enriched/total*100:.0f}%)")
    print(f"  Skipped:   {failed:,} ({skip_pct:.0f}%) — state-registered, exempt, or no ADV on file")
    print(f"  Rate:      {enriched / (elapsed/60):.0f} RIAs/min average")
    print()

    # Print current overall enrichment stats
    try:
        total_res = db.table("rias").select("*", count="exact").execute()
        unen_res  = (
            db.table("rias")
            .select("*", count="exact")
            .is_("aum", "null")
            .eq("is_active", True)
            .execute()
        )
        n_total   = total_res.count  or 0
        n_unen    = unen_res.count   or 0
        n_enriched = n_total - n_unen
        print(f"  Database totals: {n_enriched:,} / {n_total:,} enriched ({n_enriched/n_total*100:.0f}%)")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pcIQ — bulk local RIA enrichment via ADV PDF (no Railway required)"
    )
    parser.add_argument(
        "--max", type=int, default=0,
        help="Limit to first N RIAs (0 = all). Safe to re-run — enriched RIAs are skipped."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print each failure reason inline"
    )
    args = parser.parse_args()
    asyncio.run(run(max_rias=args.max, verbose=args.verbose))


if __name__ == "__main__":
    main()
