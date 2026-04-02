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


def fetch_confirmed_allocators(
    filing_id: int,
    solicitation_states: list[str],
    fund_state: str = "",
    limit: int = 20,
) -> list[dict]:
    """
    Return RIAs that are BOTH registered on a platform distributing this fund
    AND in the fund's territory. These are HIGH-CONFIDENCE probable buyers.

    Inference chain (all three must hold):
      1. Fund Y is on iCapital/CAIS  →  fund_platforms.is_known_platform = True
      2. RIA X is an iCapital/CAIS partner  →  ria_platforms table
      3. RIA X is in Fund Y's territory  →  state match

    Returns [] if the fund has no known platforms or ria_platforms table is empty.
    Each result row includes `matched_platforms` — which platform(s) created the match.
    """
    db = get_db()

    # Step 1: which known platforms distribute this fund?
    plat_result = (
        db.table("fund_platforms")
        .select("platform_name")
        .eq("filing_id", filing_id)
        .eq("is_known_platform", True)
        .execute()
    )
    fund_platform_names = [p["platform_name"] for p in (plat_result.data or [])]
    if not fund_platform_names:
        return []

    # Step 2: RIA CRDs registered on tracked platforms.
    # fund_platforms stores full legal names ("iCapital Markets LLC") while
    # ria_platforms stores brand names ("iCapital") — do a substring match.
    rp_all = db.table("ria_platforms").select("crd_number, platform_name").execute()
    if not rp_all.data:
        return []

    # Match: ria platform brand is a substring of the fund platform name (case-insensitive)
    # e.g. "iCapital" in "iCapital Markets LLC" → match
    def _platform_matches(fund_name: str, ria_brand: str) -> bool:
        return ria_brand.lower() in fund_name.lower()

    rp_result_data = [
        r for r in rp_all.data
        if any(_platform_matches(fp, r["platform_name"]) for fp in fund_platform_names)
    ]

    if not rp_result_data:
        return []

    # Index: crd → [platform1, platform2, ...]
    crd_to_platforms: dict[str, list[str]] = {}
    for r in rp_result_data:
        crd_to_platforms.setdefault(r["crd_number"], []).append(r["platform_name"])

    platform_crds = list(crd_to_platforms.keys())

    # Step 3: filter to territory
    states = [s.upper() for s in solicitation_states if s and s.upper() != "ALL"]
    if not states and fund_state:
        states = [fund_state.upper()]
    if not states:
        # No territory info — return all platform members (still valuable intel)
        ria_result = (
            db.table("rias")
            .select("firm_name, crd_number, state, city, aum, private_fund_aum, num_advisors")
            .in_("crd_number", platform_crds)
            .eq("is_active", True)
            .order("aum", desc=True, nullsfirst=False)
            .limit(limit)
            .execute()
        )
    else:
        ria_result = (
            db.table("rias")
            .select("firm_name, crd_number, state, city, aum, private_fund_aum, num_advisors")
            .in_("crd_number", platform_crds)
            .in_("state", states)
            .eq("is_active", True)
            .order("aum", desc=True, nullsfirst=False)
            .limit(limit)
            .execute()
        )

    results = []
    for row in (ria_result.data or []):
        row["matched_platforms"] = crd_to_platforms.get(row["crd_number"], [])
        results.append(row)

    return results


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
