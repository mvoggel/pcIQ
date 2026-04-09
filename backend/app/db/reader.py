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
    rp_all = db.table("ria_platforms").select("crd_number, platform_name, source").execute()
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

    # Index: crd → platforms list + highest-confidence source
    # Priority: csv (confirmed directory) > scrape > edgar_inferred (broad inference)
    _SOURCE_RANK = {"csv": 3, "scrape": 2, "edgar_inferred": 1}
    crd_to_platforms: dict[str, list[str]] = {}
    crd_to_source: dict[str, str] = {}
    for r in rp_result_data:
        crd = r["crd_number"]
        crd_to_platforms.setdefault(crd, []).append(r["platform_name"])
        new_src = r.get("source") or "edgar_inferred"
        cur_src = crd_to_source.get(crd, "edgar_inferred")
        if _SOURCE_RANK.get(new_src, 0) > _SOURCE_RANK.get(cur_src, 0):
            crd_to_source[crd] = new_src

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

    confirmed_crds = [r["crd_number"] for r in (ria_result.data or []) if r.get("crd_number")]

    # Enrich with 13F BDC holdings
    thirteenf_by_crd: dict[str, float] = {}
    if confirmed_crds:
        try:
            tf_rows = (
                db.table("thirteenf_holdings")
                .select("ria_crd, value_usd")
                .in_("ria_crd", confirmed_crds)
                .execute()
            ).data or []
            for tf in tf_rows:
                crd2 = tf.get("ria_crd") or ""
                thirteenf_by_crd[crd2] = thirteenf_by_crd.get(crd2, 0) + (tf.get("value_usd") or 0)
        except Exception:
            pass

    # Enrich with recent allocation counts
    alloc_by_crd: dict[str, int] = {}
    if confirmed_crds:
        try:
            cutoff = (date.today() - timedelta(days=90)).isoformat()
            ria_id_rows = (
                db.table("rias")
                .select("id, crd_number")
                .in_("crd_number", confirmed_crds)
                .execute()
            ).data or []
            crd_to_id = {r["crd_number"]: r["id"] for r in ria_id_rows}
            ria_ids = list(crd_to_id.values())
            if ria_ids:
                alloc_rows = (
                    db.table("ria_fund_allocations")
                    .select("ria_id")
                    .gte("signal_date", cutoff)
                    .in_("ria_id", ria_ids[:500])
                    .execute()
                ).data or []
                id_to_crd = {v: k for k, v in crd_to_id.items()}
                for a in alloc_rows:
                    crd2 = id_to_crd.get(a["ria_id"], "")
                    if crd2:
                        alloc_by_crd[crd2] = alloc_by_crd.get(crd2, 0) + 1
        except Exception:
            pass

    def _priority_score(aum, private_fund_aum, tf_val, alloc_count) -> int:
        has_deals = alloc_count > 0
        has_thirteenf = tf_val is not None and tf_val > 0
        high_aum = aum is not None and aum >= 1e9
        if (has_deals or has_thirteenf) and high_aum:
            return 3
        if has_deals or has_thirteenf or high_aum:
            return 2
        return 1

    results = []
    for row in (ria_result.data or []):
        crd2 = row["crd_number"]
        tf_val = thirteenf_by_crd.get(crd2)
        alloc_count = alloc_by_crd.get(crd2, 0)
        row["matched_platforms"] = crd_to_platforms.get(crd2, [])
        row["source"] = crd_to_source.get(crd2, "edgar_inferred")
        row["thirteenf_bdc_value_usd"] = tf_val
        row["allocation_count_90d"] = alloc_count
        row["priority_score"] = _priority_score(row.get("aum"), row.get("private_fund_aum"), tf_val, alloc_count)
        results.append(row)

    results.sort(key=lambda r: r["priority_score"], reverse=True)
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
