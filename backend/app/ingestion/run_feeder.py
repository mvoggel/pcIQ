"""
Feeder fund / access vehicle ingestion.

Searches EDGAR for Form D filers whose entity name contains a known platform
keyword — "iCapital", "CAIS", "Benefit Street", "Apollo Access", "Blackstone Access", etc.
These are the access vehicles / feeder funds that package underlying strategies
for distribution through wirehouse and RIA platforms.

What this gives us:
  - Which underlying funds each platform is actively packaging right now
  - Capital flow data (how much has been raised through each access vehicle)
  - States where each platform is targeting distribution

Usage:
    python -m app.ingestion.run_feeder                       # last 180 days
    python -m app.ingestion.run_feeder --days 365            # last year
    python -m app.ingestion.run_feeder --dry-run             # no DB writes
"""

import argparse
import asyncio
import re
from datetime import date, timedelta

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.db.writer import upsert_feeder_fund
from app.ingestion.edgar_client import fetch_form_d_xml
from app.ingestion.form_d_parser import parse_form_d

# Platforms to track — each keyword is searched as a quoted phrase in EDGAR EFTS.
# The entity_name of the filing must contain the keyword for it to count as a feeder.
PLATFORM_KEYWORDS = [
    "iCapital",
    "CAIS",
    "Benefit Street",
    "Apollo Access",
    "Blackstone Access",
    "Partners Capital",
    "Artivest",
    "Altigo",
    "Halo",
    "InvestX",
]

# Map keyword → canonical platform name stored in feeder_funds.platform_name
_KEYWORD_TO_PLATFORM: dict[str, str] = {
    "iCapital": "iCapital",
    "CAIS": "CAIS",
    "Benefit Street": "Benefit Street Partners",
    "Apollo Access": "Apollo",
    "Blackstone Access": "Blackstone",
    "Partners Capital": "Partners Capital",
    "Artivest": "Artivest",
    "Altigo": "Altigo",
    "Halo": "Halo",
    "InvestX": "InvestX",
}

EFTS_BASE = "https://efts.sec.gov"
_REQUEST_DELAY = 0.2


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.edgar_user_agent,
        "Accept": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    resp = await client.get(url, params=params, headers=_headers(), timeout=30)
    resp.raise_for_status()
    await asyncio.sleep(_REQUEST_DELAY)
    return resp.json()


def _strip_platform_prefix(entity_name: str, keyword: str) -> str:
    """
    Strip the platform brand from an access vehicle name to reveal the underlying.

    Examples:
      "iCapital Blue Owl Senior Loan Fund II"    → "Blue Owl Senior Loan Fund II"
      "CAIS KKR Real Estate Finance Trust"       → "KKR Real Estate Finance Trust"
      "iCapital - Blue Owl SLF II, LLC"          → "Blue Owl SLF II, LLC"
    """
    # Remove the platform keyword (case-insensitive) and common separators
    pattern = re.compile(
        r"(?i)^" + re.escape(keyword) + r"[\s\-–—:,]+"
    )
    stripped = pattern.sub("", entity_name).strip()
    # Remove leading legal / structural prefixes that aren't fund names
    stripped = re.sub(r"^(?:Fund|Access|Series|Class)\s+", "", stripped, flags=re.IGNORECASE)
    return stripped.strip() if stripped else entity_name


def _detect_platform(entity_name: str) -> tuple[str, str] | None:
    """
    Return (keyword, canonical_platform_name) if entity_name contains a known
    platform keyword; None otherwise.
    Checks longer keywords first to avoid "iCapital" matching before "iCapital Access".
    """
    for kw in sorted(PLATFORM_KEYWORDS, key=len, reverse=True):
        if kw.lower() in entity_name.lower():
            return kw, _KEYWORD_TO_PLATFORM[kw]
    return None


async def _search_feeder_filings(
    keyword: str,
    start_date: date,
    end_date: date,
    max_results: int = 200,
    debug: bool = False,
) -> list[dict]:
    """Search EDGAR EFTS for Form D filings mentioning `keyword`."""
    url = f"{EFTS_BASE}/LATEST/search-index"
    results = []
    from_offset = 0
    page_size = min(max_results, 100)

    async with httpx.AsyncClient() as client:
        while len(results) < max_results:
            params = {
                "q": f'"{keyword}"',
                "forms": "D",
                "dateRange": "custom",
                "startdt": start_date.isoformat(),
                "enddt": end_date.isoformat(),
                "from": from_offset,
                "hits.hits.total.value": "true",
            }
            data = await _get(client, url, params)
            hits = data.get("hits", {}).get("hits", [])
            total = data.get("hits", {}).get("total", {}).get("value", 0)

            if debug and from_offset == 0:
                print(f"    [debug] '{keyword}': {total} total hits from EDGAR full-text search")

            if not hits:
                break

            for hit in hits:
                src = hit.get("_source", {})

                # Entity name lives in display_names (list), not entity_name.
                # Format: "iCapital-Blue Owl SLF II, L.P.  (CIK 0002124526)"
                display_names = src.get("display_names") or []
                raw_name = display_names[0] if display_names else ""
                entity_name = re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", raw_name).strip()

                if debug:
                    print(f"    [debug]   {entity_name!r}")

                # Only keep filings where entity_name contains the keyword
                # (vs. filings where the platform merely appears as a broker-dealer)
                if keyword.lower() not in entity_name.lower():
                    continue

                ciks = src.get("ciks", [])
                cik = ciks[0] if ciks else ""
                # adsh is already formatted with dashes: "0002124526-26-000001"
                accession_no = src.get("adsh", "")
                if not cik or not accession_no:
                    continue

                results.append({
                    "entity_name": entity_name,
                    "cik": cik,
                    "accession_no": accession_no,
                    "filed_at": src.get("file_date", ""),
                })

            from_offset += page_size
            if from_offset >= total or from_offset >= max_results:
                break

    return results[:max_results]


async def run(
    start_date: date,
    end_date: date,
    dry_run: bool = False,
    debug: bool = False,
) -> None:
    mode = "DRY RUN" if dry_run else "writing to Supabase"
    print(f"\npcIQ feeder fund ingestion | {start_date} → {end_date} | {mode}\n")

    all_feeders: list[dict] = []     # rows ready to write
    seen_accessions: set[str] = set()  # dedup across keyword searches

    for keyword in PLATFORM_KEYWORDS:
        hits = await _search_feeder_filings(keyword, start_date, end_date, debug=debug)
        if not hits:
            continue

        print(f"  {keyword}: {len(hits)} filings with entity-name match")

        for meta in hits:
            entity_name = meta.get("entity_name", "")
            cik = meta.get("cik", "")
            acc = meta.get("accession_no", "")

            if not cik or not acc or acc in seen_accessions:
                continue
            seen_accessions.add(acc)

            # Identify platform
            match = _detect_platform(entity_name)
            if not match:
                continue
            detected_kw, platform_name = match

            # Fetch and parse Form D XML for raise details
            total_raised = None
            target_raise = None
            states: list[str] = []
            try:
                xml = await fetch_form_d_xml(cik, acc, timeout=5.0)
                filing = parse_form_d(xml, cik, acc)
                total_raised = filing.offering.total_amount_sold
                target_raise = filing.offering.total_offering_amount
                sol = filing.all_solicitation_states
                if sol != {"ALL"}:
                    states = sorted(sol)
            except Exception:
                pass  # proceed without raise data

            underlying = _strip_platform_prefix(entity_name, detected_kw)

            filed_str = meta.get("filed_at") or ""
            try:
                from datetime import date as _date
                filed_at = _date.fromisoformat(filed_str) if filed_str else None
            except ValueError:
                filed_at = None

            row = {
                "cik": cik,
                "accession_no": acc,
                "entity_name": entity_name,
                "platform_name": platform_name,
                "underlying_fund": underlying,
                "total_raised": total_raised,
                "target_raise": target_raise,
                "states": states,
                "filed_at": filed_at,
            }
            all_feeders.append(row)

            size_str = (
                f"${total_raised / 1_000_000:.0f}M raised"
                if total_raised else "raise unknown"
            )
            print(f"    ✓  [{platform_name}] {underlying[:55]:55s} | {size_str}")

    print(f"\n{'─'*80}")
    print(f"  Total feeder funds found : {len(all_feeders)}")

    if dry_run or not all_feeders:
        if dry_run:
            print("  Dry run — skipping DB writes.")
        return

    print("\nWriting to Supabase...")
    written = 0
    for row in all_feeders:
        try:
            upsert_feeder_fund(row)
            written += 1
        except Exception as exc:
            print(f"  ✗  DB write failed for {row['entity_name']}: {exc}")

    print(f"  {written}/{len(all_feeders)} feeder funds written to DB.")


def main() -> None:
    parser = argparse.ArgumentParser(description="pcIQ — feeder fund ingestion")
    parser.add_argument(
        "--days", type=int, default=180,
        help="Number of days to look back (default: 180)",
    )
    parser.add_argument(
        "--start", type=date.fromisoformat, default=None,
        help="Start date override (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", type=date.fromisoformat, default=None,
        help="End date override (YYYY-MM-DD)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw EDGAR hit entity names before filtering")
    args = parser.parse_args()

    end_date = args.end or date.today()
    start_date = args.start or (end_date - timedelta(days=args.days))

    asyncio.run(run(start_date, end_date, dry_run=args.dry_run, debug=args.debug))


if __name__ == "__main__":
    main()
