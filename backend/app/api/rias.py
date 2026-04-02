"""
/api/rias/enrich — backfill AUM + advisor counts for RIAs with null AUM.

Calls the IAPD detail endpoint (works from Railway datacenter IPs, 403 from residential).
Protected by the same INGEST_SECRET bearer token as /api/ingest/trigger.

Usage:
    curl -X POST https://pciq-production.up.railway.app/api/rias/enrich \
         -H "Authorization: Bearer <INGEST_SECRET>" \
         -d "batch=50"
"""

import asyncio

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.config import settings
from app.db.client import get_db
from app.db.writer import upsert_ria
from app.ingestion.adv_client import fetch_ria_by_crd
from app.ingestion.adv_parser import parse_iapd_firm
from app.models.ria import RIA

router = APIRouter(prefix="/api/rias")

_REQUEST_DELAY = 0.2  # seconds between IAPD calls — well under 10 req/s SEC limit


def _check_token(authorization: str | None) -> None:
    if not settings.ingest_secret:
        raise HTTPException(status_code=503, detail="Ingest secret not configured")
    if authorization != f"Bearer {settings.ingest_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _enrich_rias(batch: int) -> dict:
    """
    Fetch RIAs with null AUM, call IAPD detail endpoint, update DB.
    Returns a summary dict with counts.
    """
    db = get_db()

    # Fetch RIAs that still have null AUM (need enrichment)
    result = (
        db.table("rias")
        .select("crd_number, firm_name, state")
        .is_("aum", "null")
        .eq("is_active", True)
        .limit(batch)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {"status": "done", "enriched": 0, "failed": 0, "remaining": 0}

    enriched = 0
    failed = 0

    for row in rows:
        crd = row.get("crd_number", "")
        if not crd:
            failed += 1
            continue

        try:
            data = await fetch_ria_by_crd(crd)
            if not data:
                failed += 1
                await asyncio.sleep(_REQUEST_DELAY)
                continue

            ria = parse_iapd_firm(data, crd_number=crd)
            if ria and (ria.aum is not None or ria.num_investment_advisors is not None):
                upsert_ria(ria)
                enriched += 1
            else:
                failed += 1
        except Exception:
            failed += 1

        await asyncio.sleep(_REQUEST_DELAY)

    # Count remaining unenriched
    remaining_result = (
        db.table("rias")
        .select("crd_number", count="exact")
        .is_("aum", "null")
        .eq("is_active", True)
        .execute()
    )
    remaining = remaining_result.count or 0

    return {
        "status": "done",
        "enriched": enriched,
        "failed": failed,
        "remaining": remaining,
    }


@router.post("/enrich")
async def enrich_rias(
    background_tasks: BackgroundTasks,
    batch: int = 50,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Backfill AUM + advisor data for RIAs with null AUM.
    Calls IAPD detail endpoint — must run from Railway (403 from local IPs).
    batch: number of RIAs to enrich per call (default 50, max 200).
    """
    _check_token(authorization)
    batch = min(batch, 200)

    background_tasks.add_task(asyncio.ensure_future, _enrich_rias(batch))

    return {
        "status": "started",
        "batch": batch,
        "message": f"Enriching up to {batch} RIAs with null AUM in background.",
    }


@router.get("/stats")
async def ria_stats(
    authorization: str | None = Header(default=None),
) -> dict:
    """Quick count of enriched vs unenriched RIAs."""
    _check_token(authorization)
    db = get_db()

    total = db.table("rias").select("crd_number", count="exact").execute()
    unenriched = (
        db.table("rias")
        .select("crd_number", count="exact")
        .is_("aum", "null")
        .execute()
    )

    total_count = total.count or 0
    unenriched_count = unenriched.count or 0

    return {
        "total": total_count,
        "enriched": total_count - unenriched_count,
        "unenriched": unenriched_count,
    }
