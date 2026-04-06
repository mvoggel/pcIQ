"""
ADV Part 2A brochure platform scanner.

Scans Part 2A narrative brochures for mentions of iCapital, CAIS, Altigo, etc.
A sentence like "We use iCapital Network to facilitate client subscriptions..."
is a self-reported SEC-filed statement — higher confidence than EDGAR inference.

Source tag written: 'adv_brochure'
Confidence ranking: csv > adv_brochure > scrape > edgar_inferred

WHY BROCHURE FETCHING ROUTES THROUGH RAILWAY
──────────────────────────────────────────────
ADV Part 2A brochures are a separate document from Part 1A, filed via IARD and
published exclusively on IAPD (adviserinfo.sec.gov). The IAPD API endpoints
return HTTP 403 from local/residential IPs:

  403  https://api.adviserinfo.sec.gov/firms/brochures/IA/{crd}     (brochure list)
  403  https://api.adviserinfo.sec.gov/firms/registration/summary/{crd}  (version IDs)

Railway's shared IP range passes these blocks. This script triggers Railway's
/api/rias/scan-brochures endpoint in a loop — Railway fetches IAPD, scans
brochures, and writes matches to ria_platforms. This local script just drives
the loop and reports progress.

Platform keywords scanned for:
  iCapital Network, CAIS, Altigo/SEI Access, Halo Investing, InvestX, Artivest

Usage:
    make scan-brochures          # full scan (calls Railway repeatedly)
    make scan-brochures DRY=1    # dry run — calls Railway but matches not committed
    make scan-brochures V=1      # verbose — show each match as Railway reports it

    python -m app.ingestion.brochure_scanner --dry-run
    python -m app.ingestion.brochure_scanner --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time

import httpx

# ── platforms to scan for ─────────────────────────────────────────────────────
# Used by Railway endpoint (rias.py imports _scan_text and PLATFORM_PHRASES from here).
# dict preserves insertion order — longer/more-specific phrases checked first.

PLATFORM_PHRASES: dict[str, str] = {
    "iCapital Network":  "iCapital",
    "icapitalnetwork":   "iCapital",
    "iCapital":          "iCapital",
    "CAIS Group":        "CAIS",
    "caisgroup.com":     "CAIS",
    "CAIS platform":     "CAIS",
    "CAIS":              "CAIS",
    "SEI Access":        "Altigo",   # Altigo rebranded → SEI Access in late 2023
    "Altigo":            "Altigo",
    "Halo Investing":    "Halo",
    "Halo platform":     "Halo",
    "InvestX":           "InvestX",
    "Artivest":          "Artivest",
}

_PLATFORM_OWN_NAMES = {
    "icapital", "cais", "altigo", "sei access", "halo investing",
    "investx", "artivest",
}


def _scan_text(text: str) -> list[str]:
    """Return deduped list of canonical platform names found in text."""
    found: list[str] = []
    lower = text.lower()
    for phrase, canonical in PLATFORM_PHRASES.items():
        if phrase.lower() in lower and canonical not in found:
            found.append(canonical)
    return found


def _is_platform_itself(firm_name: str) -> bool:
    lower = firm_name.lower()
    return any(own in lower for own in _PLATFORM_OWN_NAMES)


# ── Railway endpoint driver ───────────────────────────────────────────────────

_RAILWAY_URL     = os.getenv("RAILWAY_URL", "https://pciq-production.up.railway.app")
_ENDPOINT        = "/api/rias/scan-brochures"
_BATCH_WAIT_S    = 65   # seconds to wait after each batch (Railway background task)


async def _trigger_batch(client: httpx.AsyncClient, token: str) -> dict | None:
    """POST one scan-brochures batch to Railway. Returns the response dict or None."""
    url = f"{_RAILWAY_URL}{_ENDPOINT}"
    try:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 401:
            raise ValueError("Railway returned 401 — check INGEST_SECRET env var")
        return None
    except httpx.TimeoutException:
        return None
    except ValueError:
        raise
    except Exception:
        return None


async def _count_unscanned() -> int:
    """
    How many RIAs still have brochure_scanned_at IS NULL?
    Queries Supabase directly (no Railway needed for reads).
    """
    from app.db.client import get_db
    db = get_db()
    try:
        res = (
            db.table("rias")
            .select("*", count="exact")
            .eq("is_active", True)
            .is_("brochure_scanned_at", "null")
            .execute()
        )
        return res.count or 0
    except Exception:
        return -1


async def run(dry_run: bool = False, verbose: bool = False) -> None:
    token = os.getenv("INGEST_SECRET", "").strip()
    if not token:
        # Try reading from .env file in backend directory
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if os.path.exists(env_file):
            for line in open(env_file):
                if line.startswith("INGEST_SECRET="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not token:
        print(
            "\n  ✗  INGEST_SECRET not set.\n"
            "     Run:  export INGEST_SECRET=<your-secret>\n"
            "     Then: make scan-brochures\n"
        )
        return

    unscanned = await _count_unscanned()
    print(f"\npcIQ brochure scanner  |  dry_run={dry_run}")
    print(f"  Route: local → Railway → IAPD Part 2A → ria_platforms")
    print(f"  Unscanned RIAs: {unscanned if unscanned >= 0 else 'unknown'}")

    if dry_run:
        print(
            "\n  Dry-run mode not yet supported for Railway-routed scanning.\n"
            "  (Railway writes directly to DB — no local dry-run intercept.)\n"
            "  Re-run without DRY=1 to run the actual scan.\n"
        )
        return

    if unscanned == 0:
        print("  ✓ All RIAs already brochure-scanned — nothing to do!\n")
        return

    print(f"  Batch size: 15 RIAs/call | wait: {_BATCH_WAIT_S}s between calls")
    print(f"  Estimated calls: {max(1, unscanned // 15):,}")
    print(f"  Estimated time:  {max(1, unscanned // 15) * _BATCH_WAIT_S // 60:.0f}–{max(1, unscanned // 15) * _BATCH_WAIT_S * 2 // 60:.0f} min")
    print(f"  Safe to interrupt (Ctrl-C) — Railway stamps each scanned RIA\n")

    start     = time.monotonic()
    total_hits  = 0
    total_scans = 0
    call_num    = 0

    async with httpx.AsyncClient() as client:
        while True:
            remaining = await _count_unscanned()
            if remaining == 0:
                break

            call_num += 1
            result = await _trigger_batch(client, token)

            if result is None:
                print(f"  ✗  Call {call_num}: Railway unreachable — retrying in 30s")
                await asyncio.sleep(30)
                continue

            batch_hits  = result.get("hits", 0)
            batch_scans = result.get("scanned", 0)
            total_hits  += batch_hits
            total_scans += batch_scans
            matches      = result.get("matches", {})

            elapsed = time.monotonic() - start
            print(
                f"  Call {call_num:3d} | scanned {batch_scans:2d} | "
                f"hits {batch_hits} | total hits {total_hits} | "
                f"{remaining:,} remaining | {elapsed/60:.1f}m elapsed"
            )

            if verbose and matches:
                for crd, platforms in matches.items():
                    print(f"    ✓  CRD {crd} → {', '.join(platforms)}")

            if remaining <= 0:
                break

            # Wait for Railway background task to complete before next trigger
            await asyncio.sleep(_BATCH_WAIT_S)

    elapsed = time.monotonic() - start
    final_remaining = await _count_unscanned()
    print(f"\n{'─'*60}")
    print(f"  Completed in {elapsed/60:.1f} min")
    print(f"  Total scanned: {total_scans:,}")
    print(f"  Total matches: {total_hits:,}  (written to ria_platforms, source='adv_brochure')")
    if final_remaining > 0:
        print(f"  Still unscanned: {final_remaining:,}  (re-run to continue)")
    else:
        print(f"  ✓ All RIAs brochure-scanned!")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pcIQ — ADV Part 2A brochure scanner (routes through Railway)"
    )
    parser.add_argument("--dry-run",  action="store_true", help="No DB writes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each match")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
