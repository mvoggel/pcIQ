"""
Pydantic models for SEC Form D filings.

Form D is filed when a company (including private funds) sells securities
under a Reg D exemption. For private credit funds, key fields are:
  - industryGroupType == "Pooled Investment Fund"
  - investmentFundType (Private Equity Fund, Hedge Fund, etc.)
  - totalOfferingAmount / totalAmountSold
  - dateOfFirstSale (the signal trigger date)
  - relatedPersons (GPs / fund managers)
  - issuerAddress (where the fund is based)
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class InvestmentFundType(StrEnum):
    PRIVATE_EQUITY = "Private Equity Fund"
    HEDGE_FUND = "Hedge Fund"
    VENTURE_CAPITAL = "Venture Capital Fund"
    OTHER = "Other Investment Fund"


class IndustryGroupType(StrEnum):
    POOLED_INVESTMENT_FUND = "Pooled Investment Fund"
    OTHER = "Other"


class IssuerAddress(BaseModel):
    street1: str = ""
    street2: str = ""
    city: str = ""
    state_or_country: str = ""
    zip_code: str = ""

    @property
    def display(self) -> str:
        parts = [p for p in [self.city, self.state_or_country] if p]
        return ", ".join(parts)


class RelatedPerson(BaseModel):
    first_name: str = ""
    last_name: str = ""
    relationship: list[str] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class OfferingAmounts(BaseModel):
    total_offering_amount: float | None = None
    total_amount_sold: float | None = None
    total_remaining: float | None = None

    @field_validator("total_offering_amount", "total_amount_sold", "total_remaining", mode="before")
    @classmethod
    def coerce_numeric(cls, v):
        if v in (None, "", "Indefinite"):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None


class FormDFiling(BaseModel):
    """
    Parsed representation of a single Form D filing.
    This is what gets written to the `form_d_filings` table.
    """

    # EDGAR metadata
    cik: str
    accession_no: str
    entity_name: str
    filed_at: date | None = None

    # Offering classification
    industry_group_type: str = ""
    investment_fund_type: str = ""

    # Key dates
    date_of_first_sale: date | None = None

    # Amounts
    offering: OfferingAmounts = Field(default_factory=OfferingAmounts)

    # Investor count
    total_investors: int | None = None
    has_non_accredited_investors: bool = False

    # Issuer info
    address: IssuerAddress = Field(default_factory=IssuerAddress)
    phone: str = ""

    # Related persons (GPs / fund managers)
    related_persons: list[RelatedPerson] = Field(default_factory=list)

    # Raw fields for debugging / future enrichment
    federal_exemptions: list[str] = Field(default_factory=list)
    is_amendment: bool = False

    @property
    def is_pooled_investment_fund(self) -> bool:
        return "Pooled" in self.industry_group_type

    @property
    def is_private_credit_candidate(self) -> bool:
        """
        True if this filing looks like a private credit / BDC-adjacent fund.

        Form D has no "private credit" category — these funds file as
        "Private Equity Fund" or "Other Investment Fund". We exclude known
        non-private-credit types by fund_type and name keywords.
        """
        if not self.is_pooled_investment_fund:
            return False

        fund_type = self.investment_fund_type.lower()

        # Exclude explicit non-private-credit fund types
        if fund_type == "venture capital fund":
            return False

        # Exclude real estate by name (common false positives)
        name = self.entity_name.lower()
        real_estate_keywords = [
            "real estate", "realty", "reit", "property", "properties",
            "housing", "mortgage", "land", "industrial", "multifamily",
            "residential", "commercial real",
        ]
        if any(kw in name for kw in real_estate_keywords):
            return False

        # Keep: Private Equity Fund, Other Investment Fund, Hedge Fund
        return any(kw in fund_type for kw in ["private equity", "other investment", "hedge"])

    @property
    def offering_size_m(self) -> float | None:
        if self.offering.total_offering_amount is None:
            return None
        return round(self.offering.total_offering_amount / 1_000_000, 2)
