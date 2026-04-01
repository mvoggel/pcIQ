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


# ---------------------------------------------------------------------------
# Known private markets platforms — flags high-value distribution signals.
# Matching is substring: "icapital" matches "iCapital Markets LLC" etc.
#
# Tier 1 — Direct RIA / alt-wealth platforms (strongest signal: fund is
#           actively reaching registered advisors and their HNW clients)
# Tier 2 — Major wirehouses & large independent BD networks (large advisor
#           force, significant retail distribution reach)
# Tier 3 — Boutique placement agents & investment banks (often institutional
#           but still meaningful for deal flow intelligence)
# ---------------------------------------------------------------------------
KNOWN_PLATFORMS: set[str] = {
    # Tier 1 — Alt-wealth / RIA platforms
    "icapital", "cais", "altigo", "artivest", "moonfare",
    "yield street", "yieldstreet", "cadre", "fundrise",
    "forge securities", "equityzen", "hiive",
    # Tier 2 — Wirehouses & major retail BDs
    "morgan stanley", "merrill lynch",
    "ubs",
    "wells fargo",           # broadened — catches Clearing Services, Advisors FN, etc.
    "raymond james",
    "lpl financial",
    "ameriprise",
    "edward jones",
    "stifel",
    "oppenheimer",
    "baird",
    "janney",
    "piper sandler",
    "kestra",
    "cetera",
    "commonwealth financial",
    "cambridge investment",
    "securities america",
    "advisor group", "osaic",
    "rockefeller",
    "national financial services",   # Fidelity clearing arm
    "fidelity",
    "schwab",
    "pershing",
    "foreside",              # fund distributor — frequently signals retail push
    # Tier 3 — Placement agents & banks with meaningful distribution reach
    "goldman sachs",
    "j.p. morgan securities", "jpmorgan securities",
    "jp morgan securities",
    "houlihan lokey",
    "pjt partners",
    "lazard",
    "cantor fitzgerald",
    "b. riley", "b riley",
    "rbc capital",
    "deutsche bank securities",
    "credit suisse securities",
    "jefferies",
    "evercore",
    "hamilton lane",         # alt investment platform / placement agent
}

# ---------------------------------------------------------------------------
# Platform name normalizer — collapses noisy filing variants into a clean
# canonical display name. Applied before writing platform_counts to the API
# response so the UI panel doesn't show 9 rows of "JPMorgan Asset Management
# (Europe/Asia/Canada/…)" from a single fund's global distribution list.
# ---------------------------------------------------------------------------
PLATFORM_CANONICAL: dict[str, str] = {
    "jpmorgan": "JPMorgan Asset Management",
    "j.p. morgan": "JPMorgan Asset Management",
    "jpmam": "JPMorgan Asset Management",
    "morgan stanley": "Morgan Stanley",
    "merrill lynch": "Merrill Lynch",
    "wells fargo": "Wells Fargo",
    "goldman sachs": "Goldman Sachs",
    "ubs financial": "UBS",
    "raymond james": "Raymond James",
    "lpl financial": "LPL Financial",
    "ameriprise": "Ameriprise",
    "icapital": "iCapital",
    "cais": "CAIS",
    "altigo": "Altigo",
    "houlihan lokey": "Houlihan Lokey",
    "foreside": "Foreside Fund Services",
    "kestra": "Kestra",
    "stifel": "Stifel",
    "oppenheimer": "Oppenheimer",
    "cantor fitzgerald": "Cantor Fitzgerald",
    "pjt partners": "PJT Partners",
    "lazard": "Lazard",
    "rbc capital": "RBC Capital Markets",
    "deutsche bank securities": "Deutsche Bank Securities",
    "credit suisse": "Credit Suisse",
    "rockefeller": "Rockefeller Financial",
    "hamilton lane": "Hamilton Lane",
    "macquarie": "Macquarie",
}


def normalize_platform_name(raw_name: str) -> str:
    """Return a clean canonical name, or the original if no match."""
    lower = raw_name.lower()
    for fragment, canonical in PLATFORM_CANONICAL.items():
        if fragment in lower:
            return canonical
    return raw_name


class SalesCompensationRecipient(BaseModel):
    """
    A broker-dealer or platform that received compensation for distributing
    this fund to investors. Extracted from Form D salesCompensationList.

    This is the key distribution signal: if iCapital appears here,
    the fund was distributed through RIAs on iCapital's platform.
    """
    name: str = ""
    crd_number: str = ""
    associated_bd_name: str = ""
    city: str = ""
    state_or_country: str = ""
    states_of_solicitation: list[str] = Field(default_factory=list)  # 2-letter state codes
    all_states: bool = False  # True if solicited in all US jurisdictions

    @property
    def is_known_platform(self) -> bool:
        name_lower = self.name.lower()
        return any(p in name_lower for p in KNOWN_PLATFORMS)

    @property
    def is_valid(self) -> bool:
        return bool(self.name and self.name.lower() not in ("none", ""))


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

    # Distribution platforms (from salesCompensationList) — THE key signal
    sales_recipients: list[SalesCompensationRecipient] = Field(default_factory=list)

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

        name = self.entity_name.lower()

        # Exclude real estate funds by name
        real_estate_keywords = [
            "real estate", "realty", "reit", "property", "properties",
            "housing", "mortgage", "land", "industrial", "multifamily",
            "residential", "commercial real", "greystar", "homebuilder",
            "single family", "single-family",
        ]
        if any(kw in name for kw in real_estate_keywords):
            return False

        # Exclude angel / crowdfunding networks — too small, not institutional
        angel_keywords = [
            "angel", "angelsdeck", "angelnv", "startup", "crowdfund",
            "seed fund", "accelerator",
        ]
        if any(kw in name for kw in angel_keywords):
            return False

        # Exclude crypto / digital asset funds — not private credit
        crypto_keywords = ["crypto", "bitcoin", "blockchain", "digital asset", "defi", "token"]
        if any(kw in name for kw in crypto_keywords):
            return False

        # Keep: Private Equity Fund, Other Investment Fund, Hedge Fund
        return any(kw in fund_type for kw in ["private equity", "other investment", "hedge"])

    @property
    def offering_size_m(self) -> float | None:
        if self.offering.total_offering_amount is None:
            return None
        return round(self.offering.total_offering_amount / 1_000_000, 2)

    @property
    def platform_names(self) -> list[str]:
        """Names of all distribution platforms/BDs in this filing."""
        return [r.name for r in self.sales_recipients if r.is_valid]

    @property
    def known_platform_names(self) -> list[str]:
        """Only the recognized major platforms (iCapital, CAIS, etc.)."""
        return [r.name for r in self.sales_recipients if r.is_valid and r.is_known_platform]

    @property
    def all_solicitation_states(self) -> set[str]:
        """Union of all states across all sales recipients."""
        states: set[str] = set()
        for r in self.sales_recipients:
            if r.all_states:
                return {"ALL"}
            states.update(r.states_of_solicitation)
        return states
