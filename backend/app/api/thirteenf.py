"""
/api/thirteenf — 13F holdings ingestion trigger and query endpoints.

Endpoints:
  POST /api/thirteenf/trigger   — run ingestion synchronously (protected)
  GET  /api/thirteenf/holders   — top firms holding BDC positions
"""

from datetime import date, timedelta

from fastapi import APIRouter, Header, HTTPException, Query

from app.config import settings
from app.db.client import get_db
from app.ingestion.run_thirteenf import run as run_thirteenf

router = APIRouter(prefix="/api/thirteenf")


def _check_token(authorization: str | None) -> None:
    if not settings.ingest_secret:
        raise HTTPException(status_code=503, detail="Ingest secret not configured")
    if authorization != f"Bearer {settings.ingest_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/trigger")
async def trigger_thirteenf(
    days: int = Query(default=100, ge=1, le=365),
    max_filers: int = Query(default=500, ge=1, le=2000),
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Run 13F ingestion synchronously — waits for completion and returns results.
    Runs in-process so Railway doesn't scale down mid-run.
    Protected by the same INGEST_SECRET as Form D ingestion.
    """
    _check_token(authorization)

    end   = date.today()
    start = end - timedelta(days=days)

    result = await run_thirteenf(start, end, max_filers=max_filers)
    return {"status": "completed", "start": str(start), "end": str(end), **result}


@router.get("/holders")
def get_thirteenf_holders(
    limit: int = Query(default=50, ge=1, le=200),
    min_value_usd: int = Query(default=10_000_000, description="Minimum BDC position value"),
) -> dict:
    """
    Return the largest institutional BDC holders from 13F data,
    aggregated by filer, sorted by total BDC position value descending.
    """
    db = get_db()
    rows = (
        db.table("thirteenf_holdings")
        .select("filer_cik, filer_name, ria_crd, period_of_report, value_usd, ticker")
        .gte("value_usd", min_value_usd)
        .execute()
        .data or []
    )

    # Aggregate by filer_cik
    by_filer: dict[str, dict] = {}
    for r in rows:
        cik = r["filer_cik"]
        if cik not in by_filer:
            by_filer[cik] = {
                "filer_cik":       cik,
                "filer_name":      r.get("filer_name") or "",
                "ria_crd":         r.get("ria_crd"),
                "period_of_report": r.get("period_of_report"),
                "total_bdc_value_usd": 0,
                "tickers":         [],
            }
        by_filer[cik]["total_bdc_value_usd"] += r.get("value_usd") or 0
        ticker = r.get("ticker")
        if ticker and ticker not in by_filer[cik]["tickers"]:
            by_filer[cik]["tickers"].append(ticker)

    holders = sorted(
        by_filer.values(),
        key=lambda x: x["total_bdc_value_usd"],
        reverse=True,
    )[:limit]

    return {
        "total":   len(holders),
        "holders": holders,
    }
