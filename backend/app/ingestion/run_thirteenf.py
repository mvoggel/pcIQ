"""
13F ingestion runner.

Fetches 13F-HR filings from EDGAR for a given date range, filters holdings
to BDC issuers, attempts to match filers to RIAs in our database by name,
and upserts results to the thirteenf_holdings table.

Matching strategy:
  - Filer name (from EDGAR) is fuzzy-matched against rias.firm_name.
  - If a match is found, ria_crd is populated; otherwise it stays NULL.
  - NULL-crd rows are still stored — they can be used for dashboards showing
    the broader institutional buyer universe even without a CRD link.

Usage:
    asyncio.run(run(start_date, end_date))
"""

import asyncio
import logging
from datetime import date, timedelta

from app.db.client import get_db
from app.ingestion.thirteenf_client import (
    BDC_CUSIPS,
    fetch_13f_holdings,
    search_13f_by_cusips,
)


def len_bdc_cusips() -> int:
    return max(1, len(BDC_CUSIPS))

log = logging.getLogger(__name__)

# Throttle concurrent filing fetches to avoid hammering SEC
_CONCURRENCY = 5


def _normalize(name: str) -> str:
    """Lowercase, strip common suffixes for fuzzy matching."""
    name = name.upper()
    for suffix in (" LLC", " LP", " LLP", " INC", " CORP", " CORPORATION",
                   " CO.", " CO,", " ADVISORS", " ADVISERS", " MANAGEMENT",
                   " CAPITAL", " PARTNERS", " GROUP", " FUND"):
        name = name.replace(suffix, "")
    return name.strip()


def _build_ria_index(ria_rows: list[dict]) -> dict[str, str]:
    """Return {normalized_name: crd_number}."""
    idx: dict[str, str] = {}
    for r in ria_rows:
        key = _normalize(r.get("firm_name") or "")
        if key:
            idx[key] = r.get("crd_number") or ""
    return idx


def _match_crd(entity_name: str, ria_index: dict[str, str]) -> str | None:
    """Best-effort name match. Returns CRD string or None."""
    key = _normalize(entity_name)
    return ria_index.get(key) or None


async def run(
    start_date: date,
    end_date: date,
    *,
    max_filers: int = 500,
    dry_run: bool = False,
) -> dict:
    """
    Run 13F ingestion for filings dated between start_date and end_date.

    Returns summary dict: {filers_scanned, bdc_holdings_found, upserted, matched_rias}
    """
    log.info("13F ingestion: %s → %s (max_filers=%d)", start_date, end_date, max_filers)

    db = get_db()

    # ── 1. Load RIA name → CRD index for matching ─────────────────────
    ria_rows = (
        db.table("rias")
        .select("crd_number, firm_name")
        .eq("is_active", True)
        .execute()
        .data or []
    )
    ria_index = _build_ria_index(ria_rows)
    log.info("Loaded %d RIAs for name matching", len(ria_index))

    # ── 2. Search for 13F-HR filings containing our BDC CUSIPs ────────
    # max_filers controls max results per CUSIP (10 CUSIPs × max = total ceiling)
    filings = await search_13f_by_cusips(
        start_date, end_date, max_per_cusip=max(50, max_filers // len_bdc_cusips())
    )
    log.info("Found %d unique 13F filers holding tracked BDCs", len(filings))

    # Debug: capture first 3 raw filings so we can inspect cik/acc_no/raw_id
    debug_sample = [
        {k: v for k, v in f.items()}
        for f in filings[:3]
    ]

    # ── 3. Fetch holdings concurrently (throttled) ────────────────────
    sem     = asyncio.Semaphore(_CONCURRENCY)
    rows_to_upsert: list[dict] = []
    filers_with_bdc = 0

    async def _process(filing: dict) -> None:
        nonlocal filers_with_bdc
        cik      = filing["cik"]
        acc      = filing["accession_no"]
        doc_name = filing.get("doc_name", "")
        name     = filing["entity_name"]
        period   = filing.get("period_of_report") or filing.get("filed_at") or ""
        filed_at = filing.get("filed_at") or ""

        if not cik or not acc:
            return

        async with sem:
            try:
                holdings = await fetch_13f_holdings(cik, acc, doc_name=doc_name)
            except Exception as exc:
                log.warning("Failed to fetch %s / %s: %s", cik, acc, exc)
                return

        if not holdings:
            return

        filers_with_bdc += 1
        ria_crd = _match_crd(name, ria_index) or None

        for h in holdings:
            rows_to_upsert.append({
                "filer_cik":             cik,
                "filer_name":            name,
                "period_of_report":      period[:10] if period else None,
                "filed_at":              filed_at[:10] if filed_at else None,
                "issuer_name":           h["issuer_name"],
                "cusip":                 h["cusip"] or None,
                "ticker":                h["ticker"] or None,
                "value_usd":             h["value_usd"],
                "shares":                h["shares"],
                "investment_discretion": h["investment_discretion"] or None,
                "ria_crd":               ria_crd,
            })

    await asyncio.gather(*[_process(f) for f in filings])

    log.info(
        "Found BDC holdings in %d filers → %d rows to upsert",
        filers_with_bdc, len(rows_to_upsert),
    )

    if dry_run or not rows_to_upsert:
        return {
            "filers_scanned":     len(filings),
            "bdc_holdings_found": len(rows_to_upsert),
            "upserted":           0,
            "matched_rias":       sum(1 for r in rows_to_upsert if r["ria_crd"]),
            "dry_run":            dry_run,
            "debug_sample":       debug_sample,
        }

    # ── 4. Upsert in batches ──────────────────────────────────────────
    batch_size = 200
    upserted   = 0
    for i in range(0, len(rows_to_upsert), batch_size):
        batch = rows_to_upsert[i : i + batch_size]
        db.table("thirteenf_holdings").upsert(
            batch,
            on_conflict="filer_cik,period_of_report,cusip",
        ).execute()
        upserted += len(batch)

    matched = sum(1 for r in rows_to_upsert if r["ria_crd"])
    log.info("Upserted %d rows (%d matched to RIAs)", upserted, matched)

    return {
        "filers_scanned":     len(filings),
        "bdc_holdings_found": len(rows_to_upsert),
        "upserted":           upserted,
        "matched_rias":       matched,
        "dry_run":            False,
        "debug_sample":       debug_sample,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 100  # 13F is quarterly, look back ~90 days
    end   = date.today()
    start = end - timedelta(days=days)
    print(asyncio.run(run(start, end)))
