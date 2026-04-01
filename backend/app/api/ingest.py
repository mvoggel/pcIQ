"""
/api/ingest/trigger — kick off a background EDGAR ingestion run.

Protected by a bearer token (INGEST_SECRET env var).
Called by the GitHub Actions daily workflow.
"""

import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Header, HTTPException, BackgroundTasks

from app.config import settings
from app.ingestion.run import run as run_ingestion

router = APIRouter(prefix="/api/ingest")


def _check_token(authorization: str | None) -> None:
    if not settings.ingest_secret:
        raise HTTPException(status_code=503, detail="Ingest secret not configured")
    expected = f"Bearer {settings.ingest_secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/trigger")
async def trigger_ingest(
    background_tasks: BackgroundTasks,
    days: int = 2,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Trigger an ingestion run for the last `days` days (default 2).
    Runs in the background so the HTTP response returns immediately.
    """
    _check_token(authorization)

    end = date.today()
    start = end - timedelta(days=days)

    async def _run() -> None:
        await run_ingestion(start, end, dry_run=False)

    background_tasks.add_task(asyncio.ensure_future, _run())

    return {"status": "started", "start": str(start), "end": str(end), "days": days}
