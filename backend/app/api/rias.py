"""
/api/rias endpoints — RIA enrichment and brochure platform scanning.

Endpoints:
  POST /api/rias/enrich           — backfill AUM + advisor counts
  POST /api/rias/scan-brochures   — scan Part 2A brochures for platform keywords
  GET  /api/rias/stats            — enrichment coverage stats

All protected by INGEST_SECRET bearer token.

WHY BROCHURE SCANNING RUNS ON RAILWAY
──────────────────────────────────────
IAPD brochure endpoints (api.adviserinfo.sec.gov/firms/brochures/IA/{crd})
return HTTP 403 from local/residential IPs. Railway's IP range passes these
blocks. Local brochure_scanner.py delegates to this endpoint rather than
fetching IAPD directly.

Usage:
    curl -X POST https://pciq-production.up.railway.app/api/rias/enrich \
         -H "Authorization: Bearer <INGEST_SECRET>"

    curl -X POST https://pciq-production.up.railway.app/api/rias/scan-brochures \
         -H "Authorization: Bearer <INGEST_SECRET>"
"""

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.config import settings
from app.db.client import get_db
from app.ingestion.adv_client import fetch_ria_by_crd
from app.ingestion.adv_parser import parse_iapd_firm
from app.ingestion.adv_pdf_parser import fetch_adv_data
from app.ingestion.brochure_client import fetch_part2a_text
from app.ingestion.brochure_scanner import PLATFORM_PHRASES, _scan_text, _is_platform_itself
from app.db.writer import upsert_ria, upsert_ria_platform

router = APIRouter(prefix="/api/rias")

_BATCH        = 10    # RIAs per enrich background run — ~100MB peak on Railway
_BROCHURE_BATCH = 15  # RIAs per brochure-scan run — each PDF can be 5-10MB
_DELAY        = 0.3   # seconds between requests


def _check_token(authorization: str | None) -> None:
    if not settings.ingest_secret:
        raise HTTPException(status_code=503, detail="Ingest secret not configured")
    if authorization != f"Bearer {settings.ingest_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _enrich_one(crd: str) -> bool:
    """
    Try to enrich a single RIA's AUM.
    Attempt 1: IAPD detail (fast, works from Railway IPs).
    Attempt 2: ADV PDF parse (slower, works from any IP).
    Returns True if AUM was successfully written.
    """
    # Attempt 1: IAPD detail endpoint
    try:
        data = await fetch_ria_by_crd(crd)
        if data:
            ria = parse_iapd_firm(data, crd_number=crd)
            if ria and ria.aum is not None:
                upsert_ria(ria)
                return True
    except Exception:
        pass

    # Attempt 2: ADV PDF (works from any IP — same source as fund modal manager card)
    try:
        adv = await fetch_adv_data(crd, timeout=20.0)
        if adv and adv.total_aum is not None:
            db = get_db()
            db.table("rias").update({
                "aum": adv.total_aum,
                "num_advisors": adv.investment_advisory_employees,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("crd_number", crd).execute()
            return True
    except Exception:
        pass

    return False


async def _enrich_batch() -> None:
    """Background task: enrich one batch of null-AUM RIAs.

    Orders by updated_at ASC so each batch processes different RIAs — failed
    attempts get their updated_at bumped so they rotate to the back of the queue
    instead of being selected again every single batch.
    """
    db = get_db()
    result = (
        db.table("rias")
        .select("crd_number")
        .is_("aum", "null")
        .eq("is_active", True)
        .order("updated_at", desc=False)   # oldest-touched first → cycles through all
        .limit(_BATCH)
        .execute()
    )
    rows = result.data or []

    for row in rows:
        crd = (row.get("crd_number") or "").strip()
        if not crd:
            continue
        success = await _enrich_one(crd)
        if not success:
            # Bump updated_at so this RIA moves to the back of the queue next batch
            try:
                db.table("rias").update({
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("crd_number", crd).execute()
            except Exception:
                pass
        await asyncio.sleep(_DELAY)


@router.post("/enrich")
async def enrich_rias(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Backfill AUM for the next 10 null-AUM RIAs. Runs in background after response.
    Call repeatedly until stats shows unenriched = 0.
    Wait ~45s between calls to let the background task complete.
    """
    _check_token(authorization)
    background_tasks.add_task(_enrich_batch)
    return {
        "status": "started",
        "batch": _BATCH,
        "message": f"Enriching next {_BATCH} RIAs in background. Wait 45s then check /api/rias/stats.",
    }


@router.get("/stats")
async def ria_stats(
    authorization: str | None = Header(default=None),
) -> dict:
    """Count of enriched vs unenriched RIAs."""
    _check_token(authorization)
    db = get_db()

    total_res = db.table("rias").select("*", count="exact").execute()
    unenriched_res = (
        db.table("rias")
        .select("*", count="exact")
        .is_("aum", "null")
        .eq("is_active", True)
        .execute()
    )

    total = total_res.count or 0
    unenriched = unenriched_res.count or 0

    return {
        "total": total,
        "enriched": total - unenriched,
        "unenriched": unenriched,
        "pct_done": round((total - unenriched) / total * 100, 1) if total else 0,
    }


# ── brochure scanning ────────────────────────────────────────────────────────

async def _scan_brochure_batch() -> dict:
    """
    Background task: scan the next _BROCHURE_BATCH RIAs for Part 2A platform mentions.

    Picks RIAs where brochure_scanned_at IS NULL, oldest-enriched first.
    After scan (hit or miss), stamps brochure_scanned_at so they're skipped next run.

    Uses a single shared httpx client for connection reuse.
    """
    db = get_db()

    # Fetch next batch — RIAs never yet brochure-scanned, most recently enriched first
    # (enriched RIAs are more likely to have ADV Part 2A brochures on file)
    rows = (
        db.table("rias")
        .select("crd_number, firm_name")
        .eq("is_active", True)
        .is_("brochure_scanned_at", "null")
        .order("updated_at", desc=True)
        .limit(_BROCHURE_BATCH)
        .execute()
    ).data or []

    hits:     dict[str, list[str]] = {}
    no_pdf:   int = 0
    errors:   int = 0
    scanned:  int = 0

    async with httpx.AsyncClient() as client:
        for row in rows:
            crd  = (row.get("crd_number") or "").strip()
            name = (row.get("firm_name")  or "").strip()
            if not crd:
                continue

            scanned += 1

            if _is_platform_itself(name):
                _stamp_brochure_scan(db, crd)
                continue

            text, status = await fetch_part2a_text(crd, client)

            if status == "ok" and text:
                found = _scan_text(text)
                if found:
                    hits[crd] = found
                    for platform in found:
                        try:
                            upsert_ria_platform(crd, platform, source="adv_brochure")
                        except Exception:
                            pass
            elif status in ("no_brochures", "no_part2a", "404"):
                no_pdf += 1
            else:
                errors += 1

            _stamp_brochure_scan(db, crd)
            await asyncio.sleep(_DELAY)

    return {
        "scanned": scanned,
        "hits": len(hits),
        "no_brochure": no_pdf,
        "errors": errors,
        "matches": hits,
    }


def _stamp_brochure_scan(db, crd: str) -> None:
    """Mark this RIA as brochure-scanned so it's skipped next batch."""
    try:
        db.table("rias").update({
            "brochure_scanned_at": datetime.now(timezone.utc).isoformat(),
        }).eq("crd_number", crd).execute()
    except Exception:
        pass


@router.post("/scan-brochures")
async def scan_brochures(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Scan the next 15 RIAs' ADV Part 2A brochures for platform keywords (iCapital, CAIS, etc.).
    Runs in background after immediate response.

    Call repeatedly (with 60s gaps to let batches complete) until all RIAs are scanned.
    Matches are written to ria_platforms with source='adv_brochure'.

    Requires brochure_scanned_at column on rias table (nullable TIMESTAMPTZ).
    RIAs are stamped after each scan so they're never re-scanned unless you NULL the column.

    Usage:
        curl -X POST https://pciq-production.up.railway.app/api/rias/scan-brochures \\
             -H "Authorization: Bearer <INGEST_SECRET>"
    """
    _check_token(authorization)
    background_tasks.add_task(_scan_brochure_batch)
    return {
        "status": "started",
        "batch": _BROCHURE_BATCH,
        "message": (
            f"Scanning next {_BROCHURE_BATCH} RIA brochures in background. "
            "Wait 60s then call again. Matches written to ria_platforms (source=adv_brochure)."
        ),
    }
