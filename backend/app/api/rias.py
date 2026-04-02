"""
/api/rias/enrich — backfill AUM + advisor counts for RIAs with null AUM.

Data source priority:
  1. IAPD detail endpoint — fast, structured (works from Railway IPs, 403 from local)
  2. ADV PDF fallback — slower but works from any IP (same as ADV cache in fund modal)

Protected by INGEST_SECRET bearer token.

Usage:
    curl -X POST https://pciq-production.up.railway.app/api/rias/enrich \
         -H "Authorization: Bearer <INGEST_SECRET>"
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.config import settings
from app.db.client import get_db
from app.ingestion.adv_client import fetch_ria_by_crd
from app.ingestion.adv_parser import parse_iapd_firm
from app.ingestion.adv_pdf_parser import fetch_adv_data
from app.db.writer import upsert_ria

router = APIRouter(prefix="/api/rias")

_BATCH = 10       # RIAs per background run — keeps peak memory ~100MB on Railway
_DELAY = 0.3      # seconds between requests


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
