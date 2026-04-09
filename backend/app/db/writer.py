"""
DB write layer — persists parsed filings and resolved entities to Supabase.

All writes use upsert so the ingestion job is safe to re-run (idempotent).
  - entities:        upsert on canonical_name
  - form_d_filings:  upsert on accession_no (unique per filing)
  - rias:            upsert on crd_number (stable FINRA identifier)
"""

from datetime import date, datetime, timezone

from app.db.client import get_db
from app.models.form_d import FormDFiling
from app.models.ria import RIA


def upsert_entity(canonical_name: str, cik: str = "", entity_type: str = "fund") -> int:
    """
    Upsert an entity record. Returns the entity's DB id.
    """
    db = get_db()
    result = (
        db.table("entities")
        .upsert(
            {
                "canonical_name": canonical_name,
                "cik": cik or None,
                "entity_type": entity_type,
            },
            on_conflict="canonical_name",
        )
        .execute()
    )
    return result.data[0]["id"]


def upsert_filing(filing: FormDFiling, entity_id: int | None = None, raw_xml: str = "") -> int:
    """
    Upsert a Form D filing. Returns the filing's DB id.
    Idempotent — safe to call again if the same accession_no is re-processed.
    raw_xml: the source XML string — stored so the modal can parse GPs without a live EDGAR fetch.
    """
    db = get_db()

    row = {
        "cik": filing.cik,
        "accession_no": filing.accession_no,
        "entity_name": filing.entity_name,
        "entity_id": entity_id,
        "filed_at": filing.filed_at.isoformat() if filing.filed_at else None,
        "date_of_first_sale": (
            filing.date_of_first_sale.isoformat() if filing.date_of_first_sale else None
        ),
        "industry_group_type": filing.industry_group_type or None,
        "investment_fund_type": filing.investment_fund_type or None,
        "total_offering_amount": filing.offering.total_offering_amount,
        "total_amount_sold": filing.offering.total_amount_sold,
        "total_investors": filing.total_investors,
        "has_non_accredited": filing.has_non_accredited_investors,
        "is_amendment": filing.is_amendment,
        "city": filing.address.city or None,
        "state_or_country": filing.address.state_or_country or None,
        "federal_exemptions": filing.federal_exemptions or [],
        "raw_xml": raw_xml or None,
    }

    result = (
        db.table("form_d_filings")
        .upsert(row, on_conflict="accession_no")
        .execute()
    )
    filing_id = result.data[0]["id"]

    # Write sales compensation recipients (platform signals)
    if filing.sales_recipients:
        upsert_fund_platforms(filing_id, filing.sales_recipients)

    return filing_id


def upsert_fund_platforms(filing_id: int, recipients) -> None:
    """
    Upsert all sales compensation recipients for a filing.
    Idempotent on (filing_id, platform_name).
    """
    db = get_db()
    rows = [
        {
            "filing_id": filing_id,
            "platform_name": r.name,
            "crd_number": r.crd_number or None,
            "is_known_platform": r.is_known_platform,
            "states": r.states_of_solicitation or [],
            "all_states": r.all_states,
        }
        for r in recipients
        if r.is_valid
    ]
    if rows:
        db.table("fund_platforms").upsert(rows, on_conflict="filing_id,platform_name").execute()


def upsert_ria_platform(crd_number: str, platform_name: str, source: str = "scrape") -> None:
    """
    Upsert a single (crd_number, platform_name) record into ria_platforms.
    Idempotent — safe to call repeatedly as we rescrape directories.
    """
    db = get_db()
    db.table("ria_platforms").upsert(
        {"crd_number": crd_number, "platform_name": platform_name, "source": source},
        on_conflict="crd_number,platform_name",
    ).execute()


def upsert_feeder_fund(row: dict) -> None:
    """
    Upsert a feeder fund / access vehicle record.
    row keys: cik, accession_no, entity_name, platform_name, underlying_fund,
              total_raised, target_raise, states, filed_at
    Idempotent on accession_no.
    """
    db = get_db()
    db.table("feeder_funds").upsert(
        {
            "cik": row["cik"],
            "accession_no": row["accession_no"],
            "entity_name": row["entity_name"],
            "platform_name": row["platform_name"],
            "underlying_fund": row.get("underlying_fund"),
            "total_raised": row.get("total_raised"),
            "target_raise": row.get("target_raise"),
            "states": row.get("states") or [],
            "filed_at": row["filed_at"].isoformat() if row.get("filed_at") else None,
        },
        on_conflict="accession_no",
    ).execute()


def upsert_allocation_events(filing_id: int, filing: FormDFiling) -> int:
    """
    For a newly ingested Form D filing, find RIAs that use the same distribution
    platforms and write allocation event rows to ria_fund_allocations.

    Logic:
      filing → known platform names (iCapital, CAIS, etc.)
      platform names → ria_platforms → crd_numbers
      crd_numbers → rias → ria ids
      ria ids + filing_id → ria_fund_allocations (upsert on ria_id, filing_id)

    Returns count of rows written.
    """
    db = get_db()

    platform_names = filing.known_platform_names  # full legal names, e.g. "iCapital Markets LLC"
    if not platform_names:
        return 0

    signal_date = (filing.date_of_first_sale or filing.filed_at or date.today()).isoformat()

    # ria_platforms stores brand names ("iCapital", "CAIS") while fund_platforms stores
    # full legal names ("iCapital Markets LLC", "CAIS Capital LLC"). Use substring match:
    # ria brand is contained in the fund platform legal name (case-insensitive).
    all_ria_platforms = (
        db.table("ria_platforms")
        .select("crd_number, platform_name")
        .execute()
        .data or []
    )

    fund_names_lower = [n.lower() for n in platform_names]
    crd_numbers = list({
        r["crd_number"]
        for r in all_ria_platforms
        if r.get("crd_number") and r.get("platform_name")
        and any(r["platform_name"].lower() in fn for fn in fund_names_lower)
    })
    if not crd_numbers:
        return 0

    # Get ria ids
    ria_rows = (
        db.table("rias")
        .select("id")
        .in_("crd_number", crd_numbers[:500])
        .execute()
        .data or []
    )
    ria_ids = [r["id"] for r in ria_rows if r.get("id")]
    if not ria_ids:
        return 0

    rows = [
        {
            "ria_id": ria_id,
            "filing_id": filing_id,
            "signal_date": signal_date,
            "source": "form_d",
            "confidence": 1.0,
        }
        for ria_id in ria_ids
    ]

    # Upsert in batches of 500 (Supabase PostgREST limit)
    written = 0
    for i in range(0, len(rows), 500):
        db.table("ria_fund_allocations").upsert(
            rows[i : i + 500],
            on_conflict="ria_id,filing_id",
        ).execute()
        written += len(rows[i : i + 500])

    return written


def upsert_ria(ria: RIA, entity_id: int | None = None) -> int:
    """
    Upsert an RIA record. Idempotent on crd_number.
    Returns the RIA's DB id.
    """
    db = get_db()
    row = {
        "crd_number": ria.crd_number,
        "cik": ria.cik or None,
        "firm_name": ria.firm_name,
        "entity_id": entity_id,
        "aum": ria.aum,
        "private_fund_aum": ria.private_fund_aum,
        "total_accounts": ria.num_accounts,
        "num_advisors": ria.num_investment_advisors,
        "city": ria.city or None,
        "state": ria.state or None,
        "zip_code": ria.zip_code or None,
        "website": ria.website or None,
        "is_active": True,
        "adv_filed_at": ria.adv_filed_at.isoformat() if ria.adv_filed_at else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = (
        db.table("rias")
        .upsert(row, on_conflict="crd_number")
        .execute()
    )
    return result.data[0]["id"]
