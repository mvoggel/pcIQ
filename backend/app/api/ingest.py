"""
/api/ingest/trigger — kick off a background EDGAR ingestion run.

Protected by a bearer token (INGEST_SECRET env var).
Called by the GitHub Actions daily workflow.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Header, HTTPException, BackgroundTasks

from app.config import settings
from app.db.client import get_db
from app.db.writer import upsert_allocation_events
from app.ingestion.run import run as run_ingestion
from app.models.form_d import FormDFiling, IssuerAddress, OfferingAmounts, SalesCompensationRecipient

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

    background_tasks.add_task(_run)

    return {"status": "started", "start": str(start), "end": str(end), "days": days}


@router.post("/backfill-allocations")
async def backfill_allocations(
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    One-time backfill: write ria_fund_allocations for all existing form_d_filings.

    Iterates every filing in the DB, finds its known platforms (from fund_platforms),
    then matches against ria_platforms to write allocation events. Safe to re-run —
    upserts on (ria_id, filing_id).

    Runs in background. Check /api/rias/stats after ~2 min for progress signal.
    """
    _check_token(authorization)

    async def _backfill() -> None:
        db = get_db()

        # Fetch all filings with their platforms in one go
        filings = (
            db.table("form_d_filings")
            .select("id, cik, accession_no, entity_name, investment_fund_type, "
                    "date_of_first_sale, filed_at, state_or_country, city")
            .execute()
        ).data or []

        if not filings:
            return

        filing_ids = [f["id"] for f in filings]

        # Batch-fetch all fund_platforms
        all_platforms = []
        for i in range(0, len(filing_ids), 500):
            batch = (
                db.table("fund_platforms")
                .select("filing_id, platform_name, is_known_platform, states, all_states")
                .in_("filing_id", filing_ids[i : i + 500])
                .execute()
            ).data or []
            all_platforms.extend(batch)

        platforms_by_filing: dict[int, list[dict]] = {}
        for p in all_platforms:
            platforms_by_filing.setdefault(p["filing_id"], []).append(p)

        total_written = 0
        for row in filings:
            fid = row["id"]
            platforms = platforms_by_filing.get(fid, [])
            if not platforms:
                continue

            recipients = [
                SalesCompensationRecipient(
                    name=p["platform_name"],
                    states_of_solicitation=p.get("states") or [],
                    all_states=p.get("all_states") or False,
                )
                for p in platforms
            ]

            filing = FormDFiling(
                cik=row["cik"],
                accession_no=row["accession_no"],
                entity_name=row["entity_name"] or "",
                investment_fund_type=row.get("investment_fund_type") or "",
                industry_group_type="Pooled Investment Fund",
                date_of_first_sale=row.get("date_of_first_sale"),
                filed_at=row.get("filed_at"),
                offering=OfferingAmounts(),
                address=IssuerAddress(
                    city=row.get("city") or "",
                    state_or_country=row.get("state_or_country") or "",
                ),
                sales_recipients=recipients,
            )

            try:
                written = upsert_allocation_events(fid, filing)
                total_written += written
            except Exception:
                pass

        print(f"Backfill complete: {total_written} allocation events written across {len(filings)} filings.")

    background_tasks.add_task(_backfill)
    return {
        "status": "started",
        "message": "Backfilling ria_fund_allocations from all existing form_d_filings. Runs in background (~1–2 min).",
    }
