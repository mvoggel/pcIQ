"""
Supabase reader — fetch Form D filings + associated platforms for signal scoring,
plus RIA profile matching for the fund detail modal.

Reads from already-ingested data rather than re-fetching from EDGAR.
"""

from datetime import date, timedelta

from app.db.client import get_db
from app.models.form_d import (
    FormDFiling,
    IssuerAddress,
    OfferingAmounts,
    SalesCompensationRecipient,
)


def fetch_filings_for_signals(days: int = 7) -> list[FormDFiling]:
    """
    Return private-credit-candidate FormDFiling objects from the last `days` days.

    Joins form_d_filings with fund_platforms so scoring logic can run
    against the same data structure as the live EDGAR pipeline.
    """
    db = get_db()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    result = (
        db.table("form_d_filings")
        .select(
            "id, cik, accession_no, entity_name, investment_fund_type, "
            "industry_group_type, total_offering_amount, total_amount_sold, "
            "date_of_first_sale, filed_at, state_or_country, city, is_amendment"
        )
        .gte("filed_at", cutoff)
        .execute()
    )

    rows = result.data
    if not rows:
        return []

    # Fetch platforms for all returned filings in one query
    filing_ids = [r["id"] for r in rows]
    plat_result = (
        db.table("fund_platforms")
        .select("filing_id, platform_name, is_known_platform, states, all_states")
        .in_("filing_id", filing_ids)
        .execute()
    )

    # Index platforms by filing_id
    platforms_by_id: dict[int, list[dict]] = {}
    for p in plat_result.data:
        platforms_by_id.setdefault(p["filing_id"], []).append(p)

    filings: list[FormDFiling] = []
    for row in rows:
        platforms = platforms_by_id.get(row["id"], [])
        recipients = [
            SalesCompensationRecipient(
                name=p["platform_name"],
                states_of_solicitation=p["states"] or [],
                all_states=p["all_states"] or False,
            )
            for p in platforms
        ]
        filing = FormDFiling(
            cik=row["cik"],
            accession_no=row["accession_no"],
            entity_name=row["entity_name"],
            filed_at=row["filed_at"],
            # Only private-credit candidates are written to DB, but preserve what's stored
            industry_group_type=row.get("industry_group_type") or "Pooled Investment Fund",
            investment_fund_type=row.get("investment_fund_type") or "",
            date_of_first_sale=row["date_of_first_sale"],
            offering=OfferingAmounts(
                total_offering_amount=row["total_offering_amount"],
                total_amount_sold=row["total_amount_sold"],
            ),
            address=IssuerAddress(
                city=row.get("city") or "",
                state_or_country=row.get("state_or_country") or "",
            ),
            sales_recipients=recipients,
            is_amendment=row.get("is_amendment") or False,
        )
        if filing.is_private_credit_candidate:
            filings.append(filing)

    return filings


def fetch_likely_rias(
    solicitation_states: list[str],
    fund_state: str = "",
    min_aum: float = 100_000_000,
    limit: int = 20,
) -> list[dict]:
    """
    Return RIAs in the fund's territory that meet the AUM threshold.

    These are 'likely allocator' profile matches — NOT confirmed allocations.
    Logic: right geography + significant AUM + private fund history = relevant prospect.

    Args:
        solicitation_states: 2-letter state codes from the fund's Form D.
                             Empty list means fall back to fund_state.
        fund_state:          Issuer state — fallback when no solicitation states disclosed.
        min_aum:             Minimum AUM to be considered a meaningful allocator ($).
        limit:               Max number of RIA profiles to return.
    """
    db = get_db()

    states = [s.upper() for s in solicitation_states if s and s.upper() != "ALL"]
    if not states and fund_state:
        states = [fund_state.upper()]
    if not states:
        return []

    result = (
        db.table("rias")
        .select(
            "firm_name, crd_number, state, city, aum, private_fund_aum, "
            "website, num_advisors, total_accounts"
        )
        .in_("state", states)
        .or_(f"aum.gte.{min_aum},aum.is.null")
        .eq("is_active", True)
        .order("aum", desc=True, nullsfirst=False)
        .limit(limit)
        .execute()
    )

    return result.data or []
