"""
13F ingestion runner.

Fetches 13F-HR filings from EDGAR for a given date range, filters holdings
to BDC issuers, attempts to match filers to RIAs in our database by name or CIK,
and upserts results to the thirteenf_holdings table.

Matching strategy (in order):
  1. CIK match — filer CIK against rias.cik (most reliable)
  2. Normalized name exact match — strips legal suffixes, compares uppercased
  - NULL-crd rows are still stored — they represent the broader institutional
    buyer universe even without a CRD link.

Usage:
    asyncio.run(run(start_date, end_date))
"""

import asyncio
import logging
import re
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

# Throttle concurrent filing fetches to stay under SEC's 10 req/s limit
_CONCURRENCY = 3


def _clean_efts_name(name: str) -> str:
    """
    Strip suffixes that EFTS appends to entity names before matching.
      "Granite FO LLC  (CIK 0002034090)"  →  "Granite FO LLC"
      "MARKEL GROUP INC.  (MKL)"          →  "MARKEL GROUP INC."
    """
    name = re.sub(r"\s*\(CIK\s+\d+\)\s*$", "", name or "").strip()
    name = re.sub(r"\s*\([A-Z]{1,5}\)\s*$", "", name).strip()
    return name


def _normalize(name: str) -> str:
    """Strip common legal suffixes for fuzzy firm-name matching."""
    name = name.upper()
    for suffix in (" LLC", " LP", " LLP", " INC", " CORP", " CORPORATION",
                   " CO.", " CO,", " ADVISORS", " ADVISERS", " MANAGEMENT",
                   " CAPITAL", " PARTNERS", " GROUP", " FUND"):
        name = name.replace(suffix, "")
    return name.strip()


def _build_ria_index(ria_rows: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Return (name_index, cik_index) where each maps to crd_number."""
    name_idx: dict[str, str] = {}
    cik_idx:  dict[str, str] = {}
    for r in ria_rows:
        crd = r.get("crd_number") or ""
        if not crd:
            continue
        key = _normalize(r.get("firm_name") or "")
        if key:
            name_idx[key] = crd
        cik = (r.get("cik") or "").lstrip("0")
        if cik:
            cik_idx[cik] = crd
    return name_idx, cik_idx


def _match_crd(entity_name: str, filer_cik: str,
               name_index: dict[str, str], cik_index: dict[str, str]) -> str | None:
    """
    Best-effort match. Tries CIK first (most reliable), then normalized name.
    Returns CRD or None.
    """
    # CIK match (strip leading zeros for comparison)
    crd = cik_index.get(filer_cik.lstrip("0"))
    if crd:
        return crd
    # Normalized name match
    key = _normalize(_clean_efts_name(entity_name))
    return name_index.get(key) or None


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

    # ── 1. Load RIA name + CIK → CRD index for matching ─────────────────────
    ria_rows = (
        db.table("rias")
        .select("crd_number, firm_name, cik")
        .eq("is_active", True)
        .execute()
        .data or []
    )
    name_index, cik_index = _build_ria_index(ria_rows)
    log.info("Loaded %d RIAs for matching (%d with CIK, %d by name)", len(ria_rows), len(cik_index), len(name_index))

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
        ria_crd = _match_crd(name, cik, name_index, cik_index) or None

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

    # ── 4. Deduplicate within batch (same filer+period+cusip → sum value) ──
    dedup: dict[tuple, dict] = {}
    for r in rows_to_upsert:
        key = (r["filer_cik"], r["period_of_report"], r["cusip"])
        if key in dedup:
            dedup[key]["value_usd"] += r["value_usd"]
            dedup[key]["shares"]    += r["shares"]
        else:
            dedup[key] = dict(r)
    deduped = list(dedup.values())
    log.info("After dedup: %d rows (was %d)", len(deduped), len(rows_to_upsert))

    # ── 5. Upsert in batches ──────────────────────────────────────────
    batch_size = 200
    upserted   = 0
    for i in range(0, len(deduped), batch_size):
        batch = deduped[i : i + batch_size]
        db.table("thirteenf_holdings").upsert(
            batch,
            on_conflict="filer_cik,period_of_report,cusip",
        ).execute()
        upserted += len(batch)

    matched = sum(1 for r in deduped if r["ria_crd"])
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
