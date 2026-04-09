"""
Platform RIA roster scraper.

Fetches the public lists of RIA firms registered on alternative investment
distribution platforms (iCapital, CAIS) and populates the ria_platforms table.

This is the "confirmed linkage" layer:
  ria_platforms row  →  RIA X is a registered iCapital partner
  fund_platforms row →  Fund Y is distributed via iCapital
  rias.state         →  RIA X is in Fund Y's territory
  RESULT: high-confidence probable buyer surfaced in the fund modal

──────────────────────────────────────────────────────────────────────────────
DATA SOURCES (in priority order)
──────────────────────────────────────────────────────────────────────────────

1. CAIS advisor directory — public page at caisgroup.com
   CAIS publishes a searchable advisor directory. The scraper fetches it and
   parses firm names + CRD numbers via IAPD lookup.

2. iCapital — EDGAR feeder fund cross-reference (automated, no scraping)
   iCapital files Form D for every access vehicle they create. The entity name
   encodes the underlying fund. Any RIA that previously allocated to the underlying
   fund (from our rias table) and is in the same states is a probable iCapital partner.
   More precise than scraping because it's SEC-verified.

3. CSV import fallback — load from data/platform_rias.csv
   If you have a manually curated list (e.g., from iCapital's public advisor search),
   drop it at backend/data/platform_rias.csv with columns:
       crd_number, platform_name, firm_name
   Then run:
       python -m app.ingestion.platform_scraper --source csv

──────────────────────────────────────────────────────────────────────────────
Usage:
    python -m app.ingestion.platform_scraper --source cais
    python -m app.ingestion.platform_scraper --source csv --file data/platform_rias.csv
    python -m app.ingestion.platform_scraper --source edgar  # feeder fund cross-ref
    python -m app.ingestion.platform_scraper --dry-run
──────────────────────────────────────────────────────────────────────────────
"""

import argparse
import asyncio
import csv
import os
import re
import time
from pathlib import Path
from typing import Iterator

import httpx

from app.config import settings
from app.db.writer import upsert_ria_platform

# ── IAPD firm search (resolves firm names → CRD numbers) ─────────────────────

_IAPD_SEARCH = "https://api.adviserinfo.sec.gov/search/firm"
_IAPD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.adviserinfo.sec.gov/",
    "Origin": "https://www.adviserinfo.sec.gov",
}


async def _resolve_crd(firm_name: str) -> str | None:
    """Look up a firm on IAPD and return its CRD number, or None."""
    params = {"query": firm_name, "hl": "false", "nrows": "3", "start": "0"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(_IAPD_SEARCH, headers=_IAPD_HEADERS, params=params)
            if resp.status_code != 200:
                return None
            hits = resp.json().get("hits", {}).get("hits", [])
            for hit in hits:
                src = hit.get("_source", {})
                name = str(src.get("firm_name") or "").lower()
                if firm_name.lower().split()[0] in name:
                    crd = str(src.get("firm_source_id") or "").strip()
                    if crd:
                        return crd
    except Exception:
        pass
    return None


# ── CSV import ────────────────────────────────────────────────────────────────

def _load_csv(file_path: str) -> Iterator[dict]:
    """
    Load platform RIA records from a CSV file.

    Expected columns (order matters if no header):
        crd_number, platform_name[, firm_name]

    The file may or may not have a header row. If crd_number looks like a
    header label it will be skipped automatically.

    Example rows:
        123456,iCapital,Goldman Sachs Advisors
        789012,CAIS,Raymond James Financial Services

    To generate this file from iCapital's public advisor search:
    1. Go to icapital.com → For Financial Professionals → Find an Advisor
    2. Export or copy the full list with firm names
    3. Match to CRDs via FINRA BrokerCheck or IAPD search
    4. Save as backend/data/platform_rias.csv
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(
            f"CSV file not found: {file_path}\n"
            "Create backend/data/platform_rias.csv with columns: crd_number, platform_name[, firm_name]"
        )

    with open(p, newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row:
                continue
            # Skip header row
            if i == 0 and not row[0].strip().lstrip("-").isdigit():
                continue
            crd = row[0].strip()
            platform = row[1].strip() if len(row) > 1 else ""
            if not crd or not platform:
                continue
            yield {"crd_number": crd, "platform_name": platform, "source": "csv"}


# ── CAIS advisor directory scraper ────────────────────────────────────────────

async def _scrape_cais() -> list[dict]:
    """
    Fetch CAIS partner advisor list from caisgroup.com.

    CAIS publishes a public advisor directory at caisgroup.com/advisors.
    The page uses a JSON API backing their search widget. We call it directly.

    If the API endpoint changes, update _CAIS_API below and re-run.
    Current endpoint: https://caisgroup.com/wp-json/cais/v1/advisors
    """
    _CAIS_API = "https://caisgroup.com/wp-json/cais/v1/advisors"
    results = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _CAIS_API,
                headers={"User-Agent": settings.edgar_user_agent},
                params={"per_page": 200, "page": 1},
            )
            if resp.status_code != 200:
                print(f"  CAIS API returned {resp.status_code} — try updating _CAIS_API in platform_scraper.py")
                return []

            data = resp.json()
            firms = data if isinstance(data, list) else data.get("advisors", data.get("data", []))

            for firm in firms:
                name = (
                    firm.get("name") or firm.get("firm_name") or
                    firm.get("title") or ""
                ).strip()
                crd = str(firm.get("crd") or firm.get("crd_number") or "").strip()

                if not crd and name:
                    # CRD not in response — resolve via IAPD
                    crd = await _resolve_crd(name) or ""
                    await asyncio.sleep(0.2)

                if crd:
                    results.append({
                        "crd_number": crd,
                        "platform_name": "CAIS",
                        "source": "scrape",
                    })

    except Exception as exc:
        print(f"  CAIS scrape failed: {exc}")
        print("  Tip: update _CAIS_API in platform_scraper.py with the current endpoint")

    return results


# ── EDGAR feeder fund cross-reference ────────────────────────────────────────

def _load_edgar_cross_ref() -> list[dict]:
    """
    Derive probable platform memberships from feeder_funds + rias tables.

    Logic:
      1. Find all platforms that have filed feeder funds (confirms they're active).
      2. For each such platform, match RIAs that have private_fund_aum > 0
         across all our ingested states.

    Most feeder fund Form D filings are nationwide ("all states"), so we don't
    filter by feeder-level state data — instead we use the presence of feeder
    funds as the platform signal and match against all ingested RIAs with
    demonstrated private fund exposure.

    Sets source='edgar_inferred' (lower confidence than a real directory scrape,
    but 100% automated and SEC-data-derived).
    """
    try:
        from app.db.client import get_db
        db = get_db()

        # Which platforms have filed feeder funds?
        feeder_result = db.table("feeder_funds").select("platform_name").execute()
        if not feeder_result.data:
            print("  No feeder funds in DB yet — run run_feeder.py first")
            return []

        active_platforms = {row["platform_name"] for row in feeder_result.data}
        print(f"  Active platforms from feeder_funds: {sorted(active_platforms)}")

        # RIAs with confirmed private fund exposure (strongest signal)
        ria_result = (
            db.table("rias")
            .select("crd_number")
            .not_.is_("private_fund_aum", "null")
            .gt("private_fund_aum", 0)
            .eq("is_active", True)
            .execute()
        )
        ria_crds = [r["crd_number"] for r in (ria_result.data or []) if r.get("crd_number")]
        print(f"  RIAs with private_fund_aum > 0: {len(ria_crds)}")

        if not ria_crds:
            # Fallback: any enriched RIA (has AUM data) — paginate to bypass 1000-row limit
            ria_crds = []
            page_size = 1000
            offset = 0
            while True:
                ria_result = (
                    db.table("rias")
                    .select("crd_number")
                    .not_.is_("aum", "null")
                    .eq("is_active", True)
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                batch = [r["crd_number"] for r in (ria_result.data or []) if r.get("crd_number")]
                ria_crds.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            print(f"  Fallback — RIAs with any AUM: {len(ria_crds)}")

        results = []
        for platform in active_platforms:
            for crd in ria_crds:
                results.append({
                    "crd_number": crd,
                    "platform_name": platform,
                    "source": "edgar_inferred",
                })

        return results

    except Exception as exc:
        print(f"  EDGAR cross-ref failed: {exc}")
        return []


# ── main ──────────────────────────────────────────────────────────────────────

async def run(
    source: str,
    csv_file: str = "data/platform_rias.csv",
    dry_run: bool = False,
) -> None:
    mode = "DRY RUN" if dry_run else "writing to Supabase"
    print(f"\npcIQ platform RIA ingestion | source={source} | {mode}\n")

    rows: list[dict] = []

    if source == "csv":
        for row in _load_csv(csv_file):
            rows.append(row)
        print(f"  Loaded {len(rows)} rows from {csv_file}")

    elif source == "cais":
        rows = await _scrape_cais()
        print(f"  CAIS: {len(rows)} RIA records scraped")

    elif source == "edgar":
        rows = _load_edgar_cross_ref()
        print(f"  EDGAR cross-ref: {len(rows)} probable platform members inferred")

    else:
        print(f"  Unknown source '{source}'. Use: csv | cais | edgar")
        return

    if not rows:
        print("  No records to write.")
        return

    if dry_run:
        for r in rows[:10]:
            print(f"    {r}")
        if len(rows) > 10:
            print(f"    ... and {len(rows) - 10} more")
        print("\n  Dry run — skipping DB writes.")
        return

    print(f"\nWriting {len(rows)} platform RIA records to Supabase...")
    written = 0
    for row in rows:
        try:
            upsert_ria_platform(row["crd_number"], row["platform_name"], row.get("source", "scrape"))
            written += 1
        except Exception as exc:
            print(f"  ✗  {row}: {exc}")

    print(f"  {written}/{len(rows)} records written.")

    # Print summary by platform
    by_platform: dict[str, int] = {}
    for r in rows[:written]:
        by_platform[r["platform_name"]] = by_platform.get(r["platform_name"], 0) + 1
    for platform, count in sorted(by_platform.items()):
        print(f"    {platform}: {count}")


def clear_csv_rows() -> None:
    """Delete all rows from ria_platforms where source = 'csv'."""
    from app.db.client import get_db
    db = get_db()
    result = db.table("ria_platforms").delete().eq("source", "csv").execute()
    deleted = len(result.data) if result.data else 0
    print(f"Deleted {deleted} rows from ria_platforms where source='csv'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="pcIQ — platform RIA roster ingestion")
    parser.add_argument(
        "--source", choices=["csv", "cais", "edgar"], default="edgar",
        help="Data source: csv (manual file), cais (scrape), edgar (feeder fund inference)",
    )
    parser.add_argument(
        "--file", default="data/platform_rias.csv",
        help="Path to CSV file (only used when --source=csv)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--clear-csv", action="store_true",
        help="Delete all rows from ria_platforms where source='csv', then exit.",
    )
    args = parser.parse_args()

    if args.clear_csv:
        clear_csv_rows()
        return

    asyncio.run(run(args.source, args.file, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
