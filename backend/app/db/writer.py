"""
DB write layer — persists parsed filings and resolved entities to Supabase.

All writes use upsert so the ingestion job is safe to re-run (idempotent).
  - entities:        upsert on canonical_name
  - form_d_filings:  upsert on accession_no (unique per filing)
"""

from app.db.client import get_db
from app.models.form_d import FormDFiling


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


def upsert_filing(filing: FormDFiling, entity_id: int | None = None) -> int:
    """
    Upsert a Form D filing. Returns the filing's DB id.
    Idempotent — safe to call again if the same accession_no is re-processed.
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
    }

    result = (
        db.table("form_d_filings")
        .upsert(row, on_conflict="accession_no")
        .execute()
    )
    return result.data[0]["id"]
