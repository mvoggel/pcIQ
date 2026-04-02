"""
/api/platforms — platform RIA roster management endpoints.

POST /api/platforms/ingest/feeder  — run feeder fund ingestion from EDGAR
POST /api/platforms/ingest/rias    — populate ria_platforms from a data source
GET  /api/platforms/stats          — counts per platform in ria_platforms + feeder_funds

All write endpoints are protected by INGEST_SECRET bearer token.
"""

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.config import settings
from app.db.client import get_db

router = APIRouter(prefix="/api/platforms")


def _check_token(authorization: str | None) -> None:
    if not settings.ingest_secret:
        raise HTTPException(status_code=503, detail="Ingest secret not configured")
    if authorization != f"Bearer {settings.ingest_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _run_feeder_ingest(days: int) -> None:
    """Background task: run feeder fund ingestion for the past `days` days."""
    from app.ingestion.run_feeder import run as feeder_run
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    await feeder_run(start_date, end_date, dry_run=False)


async def _run_platform_ria_ingest(source: str) -> None:
    """Background task: populate ria_platforms from the given source."""
    from app.ingestion.platform_scraper import run as scraper_run
    await scraper_run(source, dry_run=False)


@router.post("/ingest/feeder")
async def ingest_feeder_funds(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    days: int = 180,
) -> dict:
    """
    Trigger feeder fund ingestion from EDGAR.
    Searches for Form D filers with iCapital, CAIS, etc. in entity name.
    Runs in background — check /api/platforms/stats after ~60s.
    """
    _check_token(authorization)
    background_tasks.add_task(_run_feeder_ingest, days)
    return {
        "status": "started",
        "message": f"Scanning EDGAR for feeder funds over the last {days} days. Check /api/platforms/stats after ~60s.",
        "days": days,
    }


@router.post("/ingest/rias")
async def ingest_platform_rias(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
    source: str = "edgar",
) -> dict:
    """
    Populate ria_platforms table from a data source.

    source options:
      edgar  — infer from feeder_funds + rias tables (run /ingest/feeder first)
      cais   — scrape CAIS advisor directory
      csv    — load from backend/data/platform_rias.csv
    """
    _check_token(authorization)
    if source not in ("edgar", "cais", "csv"):
        raise HTTPException(status_code=400, detail="source must be: edgar | cais | csv")
    background_tasks.add_task(_run_platform_ria_ingest, source)
    return {
        "status": "started",
        "source": source,
        "message": f"Populating ria_platforms from source='{source}'. Check /api/platforms/stats after ~30s.",
    }


@router.get("/stats")
async def platform_stats(
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Return counts of feeder funds and confirmed platform RIAs per platform.
    """
    _check_token(authorization)
    db = get_db()

    # Feeder funds per platform
    feeder_result = db.table("feeder_funds").select("platform_name").execute()
    feeder_by_platform: dict[str, int] = {}
    for row in (feeder_result.data or []):
        p = row["platform_name"]
        feeder_by_platform[p] = feeder_by_platform.get(p, 0) + 1

    # Platform RIAs per platform
    ria_result = db.table("ria_platforms").select("platform_name, source").execute()
    rias_by_platform: dict[str, int] = {}
    rias_by_source: dict[str, int] = {}
    for row in (ria_result.data or []):
        p = row["platform_name"]
        s = row["source"]
        rias_by_platform[p] = rias_by_platform.get(p, 0) + 1
        rias_by_source[s] = rias_by_source.get(s, 0) + 1

    platforms = sorted(set(list(feeder_by_platform.keys()) + list(rias_by_platform.keys())))

    return {
        "platforms": [
            {
                "name": p,
                "feeder_funds": feeder_by_platform.get(p, 0),
                "registered_rias": rias_by_platform.get(p, 0),
            }
            for p in platforms
        ],
        "totals": {
            "feeder_funds": sum(feeder_by_platform.values()),
            "registered_rias": sum(rias_by_platform.values()),
        },
        "ria_sources": rias_by_source,
    }
