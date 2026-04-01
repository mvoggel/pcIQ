"""
/api/signals — territory intelligence endpoint.

Returns scored territory signal reports from already-ingested Supabase data.
~200ms response vs. 30–60s for live EDGAR fetch.
"""

from fastapi import APIRouter, Query

from app.db.reader import fetch_filings_for_signals
from app.signals.scoring import generate_territory_report
from app.signals.run_signals import DEFAULT_TERRITORIES

router = APIRouter(prefix="/api")

TERRITORY_NAMES = list(DEFAULT_TERRITORIES.keys())


@router.get("/territories")
def get_territories() -> list[dict]:
    return [{"name": name, "states": states} for name, states in DEFAULT_TERRITORIES.items()]


@router.get("/signals")
def get_signals(
    territory: str = Query(default="Northeast"),
    days: int = Query(default=7, ge=1, le=180),
) -> dict:
    if territory not in DEFAULT_TERRITORIES:
        territory = "Northeast"

    filings = fetch_filings_for_signals(days=days)
    states = DEFAULT_TERRITORIES[territory]
    report = generate_territory_report(filings, territory, states)

    in_territory = [s for s in report.top_signals if s.is_in_territory]

    return {
        "territory": report.territory_name,
        "states": report.states,
        "days": days,
        "total_filings_scanned": report.total_filings_scanned,
        "platform_counts": report.platform_counts,
        "signals": [
            {
                "fund_name": s.fund_name,
                "fund_type": s.fund_type,
                "offering_size_m": s.offering_size_m,
                "date_of_first_sale": s.date_of_first_sale.isoformat() if s.date_of_first_sale else None,
                "fund_state": s.fund_state,
                "platforms": s.platforms,
                "known_platforms": s.known_platforms,
                "solicitation_states": s.solicitation_states,
                "is_in_territory": s.is_in_territory,
                "priority_score": s.priority_score,
                "cik": s.cik,
                "accession_no": s.accession_no,
            }
            for s in in_territory
        ],
    }
