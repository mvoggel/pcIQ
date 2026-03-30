"""
Pydantic model for a Registered Investment Advisor (RIA).

Data source: SEC Form ADV via EDGAR / IAPD API.

Form ADV is filed annually by every RIA registered with the SEC.
Key fields for pcIQ:
  - aum:            assets under management — proxy for how much capital they allocate
  - num_accounts:   number of client accounts — proxy for distribution reach
  - private_fund_aum: portion of AUM in private funds — direct relevance signal
  - state:          for territory mapping
  - crd_number:     FINRA CRD# — the stable cross-system identifier for an RIA firm
"""

from datetime import date

from pydantic import BaseModel, Field, field_validator


class RIA(BaseModel):
    crd_number: str                          # FINRA CRD# — primary key
    cik: str = ""                            # SEC CIK (if filed with SEC)
    firm_name: str
    aum: float | None = None                 # total AUM ($)
    private_fund_aum: float | None = None    # AUM in private funds ($)
    num_accounts: int | None = None          # number of client accounts
    num_employees: int | None = None         # total employees
    num_investment_advisors: int | None = None
    city: str = ""
    state: str = ""                          # 2-letter state code
    zip_code: str = ""
    website: str = ""
    is_sec_registered: bool = True
    adv_filed_at: date | None = None         # date of most recent ADV filing
    related_persons: list[str] = Field(default_factory=list)  # key principals

    @field_validator("aum", "private_fund_aum", mode="before")
    @classmethod
    def coerce_numeric(cls, v):
        if v in (None, "", "N/A"):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @property
    def aum_m(self) -> float | None:
        return round(self.aum / 1_000_000, 1) if self.aum else None

    @property
    def private_fund_pct(self) -> float | None:
        if self.aum and self.private_fund_aum:
            return round(self.private_fund_aum / self.aum * 100, 1)
        return None
